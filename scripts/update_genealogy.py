"""Reproducible local build for the genealogy chapter.

Normal mode reads GrampsWeb through credentials supplied outside this
repository, launches the configured report, validates its SVG, derives A4
vector detail views from that SVG, and renders PDF/PNG companions. Fixture
mode exercises the same local gates without network access.

No command in this file prints a token, password, response body, or raw
Gramps handle. Public output is accepted only after the SVG safety gate passes.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import errno
import pty
import re
import select
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
from typing import Any
from urllib.parse import urlencode
import xml.etree.ElementTree as ET

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from check_genealogy_assets import AssetValidationError, inspect_svg, validate_svg_file  # noqa: E402
from gramps_api import GrampsApiClient, GrampsApiError, client_from_external_env  # noqa: E402


class PipelineError(RuntimeError):
    """The local build cannot safely produce a public chapter."""


class AddonCapabilityError(PipelineError):
    """The installed report addon does not expose the required option."""


def load_config(path: Path) -> dict[str, Any]:
    with path.open("rb") as stream:
        return tomllib.load(stream)


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _option_names(report: Any) -> set[str]:
    """Extract option keys from all known GrampsWeb report-info shapes."""
    names: set[str] = set()
    if not isinstance(report, dict):
        return names
    for key in ("options_help", "options_dict", "options", "available_options", "option_list"):
        value = report.get(key)
        if isinstance(value, dict):
            names.update(str(item) for item in value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, str):
                    names.add(item)
                elif isinstance(item, dict):
                    for candidate in ("key", "name", "id", "option"):
                        if isinstance(item.get(candidate), str):
                            names.add(item[candidate])
    return names


def ensure_addon_capability(report: dict[str, Any], *, allow_missing: bool = False) -> set[str]:
    names = _option_names(report)
    required = {"highlight_tag", "show_highlight_markers"}
    missing = sorted(required - names)
    if missing and not allow_missing:
        version = report.get("version", "unknown")
        raise AddonCapabilityError(
            "installed Two-Way Fan Chart addon does not expose required options "
            f"{', '.join(missing)} (report version {version}); install the "
            "publication-safe addon branch "
            "before generating public assets"
        )
    return names


def report_options(config: dict[str, Any]) -> dict[str, Any]:
    gramps = config["gramps"]
    report = config["fan_chart"]
    return {
        "ancestor_generations": str(int(report["ancestor_generations"])),
        "descendant_generations": str(int(report["descendant_generations"])),
        "center_family": str(gramps["center_family"]),
        "show_portraits": "True" if _as_bool(report["show_portraits"]) else "False",
        "portrait_source": str(report["portrait_source"]),
        "privacy_mode": str(report["privacy_mode"]),
        "incl_private": "False",
        "living_people": "0",
        "orientation": str(report["orientation"]),
        "paper_size": str(report["paper_size"]),
        "output_format": "svg",
        "off": "svg",
        "preset": "custom",
        "highlight_tag": str(gramps["highlight_tag"]),
        "show_highlight_markers": (
            "True" if _as_bool(report.get("show_highlight_markers", False)) else "False"
        ),
        "respect_media_crop": "True",
    }


def _find_value(value: Any, keys: tuple[str, ...]) -> Any:
    if isinstance(value, dict):
        for key in keys:
            if key in value and value[key] not in (None, ""):
                return value[key]
        for child in value.values():
            found = _find_value(child, keys)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_value(child, keys)
            if found is not None:
                return found
    return None


def _report_task_id(value: Any) -> str | None:
    found = _find_value(value, ("task_id", "id", "task"))
    if isinstance(found, dict):
        found = _find_value(found, ("task_id", "id"))
    return str(found) if found else None


def _report_download_href(value: Any) -> str | None:
    found = _find_value(value, ("download_url", "file_url", "url", "href", "filename"))
    return str(found) if found else None


def run_remote_report(client: GrampsApiClient, config: dict[str, Any], report_info: dict[str, Any]) -> bytes:
    options = report_options(config)
    ensure_addon_capability(report_info)
    encoded = urlencode({"options": json.dumps(options, ensure_ascii=False, separators=(",", ":")), "locale": "fr"})
    launch = client.post_json(f"/reports/{config['gramps']['report_id']}/file?{encoded}", {})
    task_id = _report_task_id(launch)
    if not task_id:
        href = _report_download_href(launch)
        if not href:
            raise PipelineError("report endpoint returned neither a task nor a download reference")
        return client.download(href)
    deadline = time.monotonic() + 900
    last_status = "unknown"
    task: Any = None
    while time.monotonic() < deadline:
        task = client.get_json(f"/tasks/{task_id}")
        last_status = str((task or {}).get("status") or (task or {}).get("state") or "unknown")
        if last_status.upper() in {"SUCCESS", "FINISHED", "COMPLETED"} or _report_download_href(task):
            break
        if last_status.upper() in {"FAILURE", "FAILED", "REVOKED"}:
            raise PipelineError(f"report task ended with status {last_status}")
        time.sleep(5)
    else:
        raise PipelineError(f"report task did not finish before timeout (status {last_status})")
    href = _report_download_href(task)
    if href and not href.lower().endswith(".svg"):
        filename = Path(href).name
        href = f"/reports/{config['gramps']['report_id']}/file/processed/{filename}"
    if not href:
        href = f"/reports/{config['gramps']['report_id']}/file/processed/{task_id}.svg"
    return client.download(href)


def _svg_root(data: bytes) -> ET.Element:
    try:
        root = ET.fromstring(data)
    except ET.ParseError as error:
        raise PipelineError("report output is not valid SVG") from error
    if root.tag.rsplit("}", 1)[-1] != "svg":
        raise PipelineError("report output root is not SVG")
    return root


def _viewbox(root: ET.Element) -> tuple[float, float, float, float]:
    parts = (root.get("viewBox") or "").replace(",", " ").split()
    if len(parts) != 4:
        raise PipelineError("canonical SVG has no four-component viewBox")
    try:
        values = tuple(float(part) for part in parts)
    except ValueError as error:
        raise PipelineError("canonical SVG viewBox is not numeric") from error
    if values[2] <= 0 or values[3] <= 0:
        raise PipelineError("canonical SVG viewBox has no positive area")
    return values  # type: ignore[return-value]


_A4_LANDSCAPE_ASPECT = 297.0 / 210.0


def _panel_background_fill(source: ET.Element) -> str:
    """Return a safe solid fill for presentation-only panel margins."""
    for node in source:
        if node.tag.rsplit("}", 1)[-1] != "rect":
            continue
        fill = (node.get("fill") or "").strip()
        if fill and fill.lower() not in {"none", "transparent"}:
            if re.fullmatch(r"#[0-9A-Fa-f]{3,8}|[A-Za-z]+", fill):
                return fill
    return "#FFFFFF"


def _panel_background_style(source: ET.Element) -> str:
    """Paint aspect-ratio letterbox areas with the chart background.

    A canonical SVG and an A4 wrapper can have slightly different aspect
    ratios.  ``preserveAspectRatio=meet`` then leaves transparent bands outside
    the canonical viewBox; some rasterizers display those bands as black.  A
    The wrapper gets an explicit presentation background (and a CSS fallback)
    so the vector geometry stays undistorted while the output remains
    deterministic across rasterizers.
    """
    return f"background: {_panel_background_fill(source)}"


def _fit_viewbox_to_aspect(
    view_box: tuple[float, float, float, float],
    *,
    aspect: float = _A4_LANDSCAPE_ASPECT,
) -> tuple[float, float, float, float]:
    """Expand a viewBox to an output aspect without clipping its contents."""
    x, y, width, height = view_box
    current = width / height
    if math.isclose(current, aspect, rel_tol=1e-12, abs_tol=1e-12):
        return view_box
    if current > aspect:
        fitted_height = width / aspect
        delta = (fitted_height - height) / 2.0
        return x, y - delta, width, fitted_height
    fitted_width = height * aspect
    delta = (fitted_width - width) / 2.0
    return x - delta, y, fitted_width, height


def _append_panel_background(
    panel: ET.Element,
    *,
    view_box: tuple[float, float, float, float],
    fill: str,
) -> None:
    """Fill the complete presentation viewport before copying source nodes."""
    x, y, width, height = view_box
    panel.append(ET.Element("{http://www.w3.org/2000/svg}rect", {
        "x": f"{x:g}",
        "y": f"{y:g}",
        "width": f"{width:g}",
        "height": f"{height:g}",
        "fill": fill,
    }))


_SVG_NUMBER_RE = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?")


def _svg_number(value: str | None) -> float | None:
    """Read the first numeric component of an SVG attribute."""
    if not value:
        return None
    match = _SVG_NUMBER_RE.search(value)
    return float(match.group(0)) if match else None


def _text_bbox(node: ET.Element) -> tuple[float, float, float, float] | None:
    """Estimate a text element's bounds for safe vector-panel cropping."""
    x = _svg_number(node.get("x"))
    y = _svg_number(node.get("y"))
    content = "".join(node.itertext()).strip()
    if x is None or y is None or not content:
        return None
    font_size = _svg_number(node.get("font-size")) or 12.0
    # This conservative estimate is used only to keep identity labels away
    # from panel edges; the original SVG remains the rendering authority.
    width = max(font_size, len(content) * font_size * 0.60)
    anchor = (node.get("text-anchor") or "start").lower()
    if anchor == "middle":
        left, right = x - width / 2.0, x + width / 2.0
    elif anchor == "end":
        left, right = x - width, x
    else:
        left, right = x, x + width
    return left, y - font_size * 1.15, right, y + font_size * 0.30


def _element_bbox(
    node: ET.Element,
    *,
    source_bounds: tuple[float, float, float, float],
) -> tuple[float, float, float, float] | None:
    """Return a conservative bbox for simple visible SVG primitives."""
    local = node.tag.rsplit("}", 1)[-1]
    if local == "text":
        return _text_bbox(node)
    if local in {"circle", "ellipse"}:
        cx = _svg_number(node.get("cx"))
        cy = _svg_number(node.get("cy"))
        rx = _svg_number(node.get("rx")) if local == "ellipse" else _svg_number(node.get("r"))
        ry = _svg_number(node.get("ry")) if local == "ellipse" else rx
        if None not in (cx, cy, rx, ry):
            return cx - rx, cy - ry, cx + rx, cy + ry  # type: ignore[operator]
        return None
    if local in {"image", "rect"}:
        x = _svg_number(node.get("x")) or 0.0
        y = _svg_number(node.get("y")) or 0.0
        width = _svg_number(node.get("width"))
        height = _svg_number(node.get("height"))
        if width is None or height is None:
            return None
        source_x, source_y, source_width, source_height = source_bounds
        if (
            local == "rect"
            and x <= source_x
            and y <= source_y
            and width >= source_width
            and height >= source_height
        ):
            # Omit the full-page background from content-driven expansion.
            return None
        return x, y, x + width, y + height
    if local == "line":
        values = [_svg_number(node.get(key)) for key in ("x1", "y1", "x2", "y2")]
        if all(value is not None for value in values):
            x1, y1, x2, y2 = values  # type: ignore[misc]
            return min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)
    if local in {"polygon", "polyline"}:
        values = [float(match.group(0)) for match in _SVG_NUMBER_RE.finditer(node.get("points", ""))]
        if len(values) >= 4:
            points = list(zip(values[::2], values[1::2]))
            xs, ys = zip(*points)
            return min(xs), min(ys), max(xs), max(ys)
    return None


def _detail_viewbox(
    source: ET.Element,
    *,
    crop: tuple[int, int],
    columns: int,
    rows: int,
) -> tuple[float, float, float, float]:
    """Return an overlapping logical tile with a safe label margin."""
    source_x, source_y, source_width, source_height = _viewbox(source)
    tile_width, tile_height = source_width / columns, source_height / rows
    tile_x = source_x + crop[0] * tile_width
    tile_y = source_y + crop[1] * tile_height

    # A detail page must retain enough of the focal area to be useful on its
    # own. The overlap also prevents labels at the centre seam from becoming
    # empty or half-visible panels. Content bounds below can expand it further.
    overlap_x = tile_width * 0.42
    overlap_y = tile_height * 0.42
    left = max(source_x, tile_x - overlap_x)
    top = max(source_y, tile_y - overlap_y)
    right = min(source_x + source_width, tile_x + tile_width + overlap_x)
    bottom = min(source_y + source_height, tile_y + tile_height + overlap_y)
    selection = (left, top, right, bottom)
    source_bounds = (source_x, source_y, source_width, source_height)
    padding_x = max(4.0, tile_width * 0.02)
    padding_y = max(4.0, tile_height * 0.02)
    for node in source.iter():
        bbox = _element_bbox(node, source_bounds=source_bounds)
        if bbox is None:
            continue
        bx0, by0, bx1, by1 = bbox
        if bx1 < selection[0] or bx0 > selection[2] or by1 < selection[1] or by0 > selection[3]:
            continue
        left = max(source_x, min(left, bx0 - padding_x))
        top = max(source_y, min(top, by0 - padding_y))
        right = min(source_x + source_width, max(right, bx1 + padding_x))
        bottom = min(source_y + source_height, max(bottom, by1 + padding_y))
    return left, top, max(1.0, right - left), max(1.0, bottom - top)


def _detail_selection(
    source: ET.Element,
    *,
    crop: tuple[int, int],
    columns: int,
    rows: int,
    overlap: float = 0.15,
) -> tuple[float, float, float, float]:
    """Return the logical detail tile, with a small seam overlap."""
    source_x, source_y, source_width, source_height = _viewbox(source)
    tile_width, tile_height = source_width / columns, source_height / rows
    tile_x = source_x + crop[0] * tile_width
    tile_y = source_y + crop[1] * tile_height
    return (
        max(source_x, tile_x - tile_width * overlap),
        max(source_y, tile_y - tile_height * overlap),
        min(source_x + source_width, tile_x + tile_width * (1.0 + overlap)),
        min(source_y + source_height, tile_y + tile_height * (1.0 + overlap)),
    )


def _bbox_center_in(
    bbox: tuple[float, float, float, float],
    selection: tuple[float, float, float, float],
) -> bool:
    """Return whether a label-bearing primitive belongs to a tile."""
    bx0, by0, bx1, by1 = bbox
    sx0, sy0, sx1, sy1 = selection
    return sx0 <= (bx0 + bx1) / 2.0 <= sx1 and sy0 <= (by0 + by1) / 2.0 <= sy1


def _text_path_endpoint_bbox(
    node: ET.Element,
    *,
    source: ET.Element,
) -> tuple[float, float, float, float] | None:
    """Estimate a curved label's bounds from its referenced arc endpoints."""
    text_path = next(
        (child for child in node if child.tag.rsplit("}", 1)[-1] == "textPath"),
        None,
    )
    if text_path is None:
        return None
    href = text_path.get("href") or text_path.get("{http://www.w3.org/1999/xlink}href")
    if not href or not href.startswith("#"):
        return None
    target = next(
        (candidate for candidate in source.iter() if candidate.get("id") == href[1:]),
        None,
    )
    if target is None:
        return None
    values = [
        float(value)
        for value in re.findall(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)", target.get("d", ""))
    ]
    if len(values) < 4:
        return None
    x_values = (values[0], values[-2])
    y_values = (values[1], values[-1])
    return min(x_values), min(y_values), max(x_values), max(y_values)


def _detail_label_centers(
    source: ET.Element,
    *,
    selection: tuple[float, float, float, float],
) -> set[int]:
    """Identify top-level label/image nodes belonging to a logical tile.

    The SVG is deliberately kept as the canonical source. This helper only
    decides which presentation labels and portraits are visible in a detail;
    it never changes their text, dates, privacy state, or marker geometry.
    """
    source_bounds = _viewbox(source)
    selected: set[int] = set()
    for index, node in enumerate(list(source)):
        local = node.tag.rsplit("}", 1)[-1]
        if local not in {"text", "image", "circle", "ellipse", "polygon"}:
            continue
        bbox = _element_bbox(node, source_bounds=source_bounds)
        if bbox is not None and _bbox_center_in(bbox, selection):
            selected.add(index)
            continue
        if local != "text":
            continue
        # Curved ancestor/descendant labels use a path in <defs> and have no
        # direct x/y bbox. The path's endpoint midpoint is a conservative
        # sector anchor, sufficient to keep a whole logical branch together.
        text_path = next(
            (child for child in node if child.tag.rsplit("}", 1)[-1] == "textPath"),
            None,
        )
        if text_path is None:
            continue
        href = text_path.get("href") or text_path.get("{http://www.w3.org/1999/xlink}href")
        if not href or not href.startswith("#"):
            continue
        target = next(
            (candidate for candidate in source.iter() if candidate.get("id") == href[1:]),
            None,
        )
        if target is None:
            continue
        path_bbox = _text_path_endpoint_bbox(node, source=source)
        if path_bbox is None:
            continue
        center = ((path_bbox[0] + path_bbox[2]) / 2.0, (path_bbox[1] + path_bbox[3]) / 2.0)
        sx0, sy0, sx1, sy1 = selection
        if sx0 <= center[0] <= sx1 and sy0 <= center[1] <= sy1:
            selected.add(index)
    return selected


def _content_detail_viewbox(
    source: ET.Element,
    *,
    crop: tuple[int, int],
    columns: int,
    rows: int,
) -> tuple[float, float, float, float]:
    """Derive a detail viewport from selected content, not tile whitespace."""
    source_x, source_y, source_width, source_height = _viewbox(source)
    tile_width, tile_height = source_width / columns, source_height / rows
    selection = _detail_selection(
        source,
        crop=crop,
        columns=columns,
        rows=rows,
    )
    selected_indices = _detail_label_centers(source, selection=selection)
    boxes: list[tuple[float, float, float, float]] = []
    source_bounds = (source_x, source_y, source_width, source_height)
    for index, node in enumerate(list(source)):
        if index not in selected_indices:
            continue
        bbox = _element_bbox(node, source_bounds=source_bounds)
        if bbox is None and node.tag.rsplit("}", 1)[-1] == "text":
            bbox = _text_path_endpoint_bbox(node, source=source)
        if bbox is not None:
            boxes.append(bbox)

    # Every panel retains the focal medallion and the long central labels.
    center_x = source_x + source_width / 2.0
    center_y = source_y + source_height / 2.0
    anchor_width = tile_width * 0.24
    anchor_height = tile_height * 0.24
    boxes.append(
        (
            center_x - anchor_width,
            center_y - anchor_height,
            center_x + anchor_width,
            center_y + anchor_height,
        )
    )
    if not boxes:
        return _detail_viewbox(source, crop=crop, columns=columns, rows=rows)

    left = min(box[0] for box in boxes)
    top = min(box[1] for box in boxes)
    right = max(box[2] for box in boxes)
    bottom = max(box[3] for box in boxes)
    padding_x = max(8.0, tile_width * 0.04)
    padding_y = max(8.0, tile_height * 0.04)
    left = max(source_x, left - padding_x)
    top = max(source_y, top - padding_y)
    right = min(source_x + source_width, right + padding_x)
    bottom = min(source_y + source_height, bottom + padding_y)
    return left, top, max(1.0, right - left), max(1.0, bottom - top)


def make_detail_svg(data: bytes, *, crop: tuple[int, int], columns: int = 2, rows: int = 2) -> bytes:
    """Create a vector crop; no raster intermediate is introduced."""
    source = _svg_root(data)
    raw_view_box = _content_detail_viewbox(
        source,
        crop=crop,
        columns=columns,
        rows=rows,
    )
    crop_x, crop_y, crop_width, crop_height = _fit_viewbox_to_aspect(raw_view_box)
    panel_view_box = (crop_x, crop_y, crop_width, crop_height)
    panel = ET.Element("{http://www.w3.org/2000/svg}svg", {
        "xmlns": "http://www.w3.org/2000/svg",
        "width": "297mm",
        "height": "210mm",
        "viewBox": f"{crop_x:g} {crop_y:g} {crop_width:g} {crop_height:g}",
        "preserveAspectRatio": "xMidYMid meet",
        "style": _panel_background_style(source),
    })
    _append_panel_background(
        panel,
        view_box=panel_view_box,
        fill=_panel_background_fill(source),
    )
    selection = _detail_selection(
        source,
        crop=crop,
        columns=columns,
        rows=rows,
    )
    selected_indices = _detail_label_centers(source, selection=selection)
    for index, child in enumerate(list(source)):
        if child.tag.rsplit("}", 1)[-1] in {"text", "image", "circle", "ellipse", "polygon"}:
            if index not in selected_indices:
                continue
        panel.append(copy.deepcopy(child))
    return ET.tostring(panel, encoding="utf-8", xml_declaration=True)


def make_overview_svg(data: bytes) -> bytes:
    """Create a dedicated A4 overview without replacing the poster asset."""
    source = _svg_root(data)
    view_box = _fit_viewbox_to_aspect(_viewbox(source))
    x, y, width, height = view_box
    panel = ET.Element("{http://www.w3.org/2000/svg}svg", {
        "xmlns": "http://www.w3.org/2000/svg",
        "width": "297mm",
        "height": "210mm",
        "viewBox": f"{x:g} {y:g} {width:g} {height:g}",
        "preserveAspectRatio": "xMidYMid meet",
        "style": _panel_background_style(source),
    })
    _append_panel_background(
        panel,
        view_box=view_box,
        fill=_panel_background_fill(source),
    )
    for child in list(source):
        panel.append(copy.deepcopy(child))
    return ET.tostring(panel, encoding="utf-8", xml_declaration=True)


def _run_converter(command: list[str]) -> None:
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise PipelineError(f"conversion failed for {Path(command[-1]).suffix or 'asset'}")


def _run_converter_in_pty(command: list[str], *, timeout: int = 180) -> None:
    """Run the confined Chromium Snap with a terminal, not a pipe.

    The installed Snap exits successfully but discards its output file when
    stdout/stderr are pipes. A PTY reproduces the interactive invocation and
    keeps the output deterministic; captured diagnostic text is discarded.
    """
    master, slave = pty.openpty()
    process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=slave, stderr=slave, close_fds=True)
    os.close(slave)
    deadline = time.monotonic() + timeout
    try:
        while process.poll() is None:
            if time.monotonic() >= deadline:
                process.kill()
                process.wait()
                raise PipelineError("Chromium conversion timed out")
            readable, _writable, _exceptional = select.select([master], [], [], 0.2)
            if readable:
                try:
                    os.read(master, 8192)
                except OSError as error:
                    if error.errno != errno.EIO:
                        raise
        # Drain the PTY after process exit so the child is fully reaped.
        while True:
            readable, _writable, _exceptional = select.select([master], [], [], 0)
            if not readable:
                break
            try:
                os.read(master, 8192)
            except OSError as error:
                if error.errno == errno.EIO:
                    break
                raise
    finally:
        os.close(master)
    if process.returncode != 0:
        raise PipelineError(f"conversion failed for {Path(command[-1]).suffix or 'asset'}")


def _librsvg_python() -> str | None:
    """Return a Python interpreter with the optional native bindings."""
    candidates: list[str] = []
    configured = os.environ.get("GENEALOGIE_RENDER_PYTHON")
    if configured:
        candidates.append(configured)
    candidates.append(sys.executable)
    candidates.extend(["/usr/bin/python3", "/usr/local/bin/python3"])
    seen: set[str] = set()
    probe = "import cairo, gi; gi.require_version('Rsvg', '2.0'); from gi.repository import Rsvg"
    for candidate in candidates:
        if candidate in seen or not shutil.which(candidate) and not Path(candidate).exists():
            continue
        seen.add(candidate)
        checked = subprocess.run(
            [candidate, "-c", probe],
            capture_output=True,
            text=True,
            check=False,
        )
        if checked.returncode == 0:
            return candidate
    return None


def _run_librsvg(source: Path, target: Path, format_name: str) -> bool:
    renderer = _librsvg_python()
    if renderer is None:
        return False
    completed = subprocess.run(
        [renderer, str(SCRIPT_DIR / "render_svg_librsvg.py"), str(source), str(target), format_name],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise PipelineError(f"librsvg conversion failed for {format_name}")
    return True


def convert_svg(source: Path, target: Path, format_name: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    rsvg = shutil.which("rsvg-convert")
    inkscape = shutil.which("inkscape")
    imagemagick = shutil.which("convert")
    if rsvg:
        command = [rsvg, "-f", format_name, "-o", str(target), str(source)]
    elif inkscape:
        command = [inkscape, str(source), f"--export-type={format_name}", f"--export-filename={target}"]
    elif imagemagick:
        command = [imagemagick, "-background", "none", str(source), str(target)]
    else:
        if _run_librsvg(source, target, format_name):
            if not target.exists() or target.stat().st_size == 0:
                raise PipelineError(f"librsvg produced no {format_name} asset")
            return
        browser = shutil.which("chromium") or shutil.which("chromium-browser")
        if browser:
            profile = Path(tempfile.mkdtemp(prefix="genealogie-chromium-"))
            try:
                if format_name == "pdf":
                    command = [
                        browser,
                        "--headless",
                        "--no-sandbox",
                        "--disable-gpu",
                        "--allow-file-access-from-files",
                        f"--user-data-dir={profile}",
                        "--no-pdf-header-footer",
                        f"--print-to-pdf={target}",
                        source.resolve().as_uri(),
                    ]
                elif format_name == "png":
                    command = [
                        browser,
                        "--headless",
                        "--no-sandbox",
                        "--disable-gpu",
                        "--allow-file-access-from-files",
                        f"--user-data-dir={profile}",
                        "--hide-scrollbars",
                        "--window-size=2400,1600",
                        f"--screenshot={target}",
                        source.resolve().as_uri(),
                    ]
                else:
                    raise PipelineError(f"unsupported SVG conversion format: {format_name}")
                _run_converter_in_pty(command)
            finally:
                shutil.rmtree(profile, ignore_errors=True)
            if not target.exists() or target.stat().st_size == 0:
                raise PipelineError(f"Chromium produced no {format_name} asset")
            return
        raise PipelineError("no SVG converter found (rsvg-convert, inkscape, ImageMagick, or Chromium)")
    _run_converter(command)
    if not target.exists() or target.stat().st_size == 0:
        raise PipelineError(f"converter produced no {format_name} asset")


def _atomic_copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".tmp")
    shutil.copyfile(source, temporary)
    os.replace(temporary, target)


def _atomic_write(target: Path, data: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".tmp")
    temporary.write_bytes(data)
    os.replace(temporary, target)


def _safe_manifest(
    output_dir: Path,
    config: dict[str, Any],
    files: list[Path],
    report_version: str,
    *,
    canonical_name: str,
) -> dict[str, Any]:
    checksums = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(files)
        if path.exists() and path.suffix.lower() in {".svg", ".pdf", ".png"}
    }
    return {
        "schema": 1,
        "report": config["gramps"]["report_id"],
        "report_version": report_version,
        "center_family": config["gramps"]["center_family"],
        "tag_name": config["gramps"]["highlight_tag"],
        "source_reference": config["gramps"]["source_gramps_id"],
        "ancestor_generations": int(config["fan_chart"]["ancestor_generations"]),
        "descendant_generations": int(config["fan_chart"]["descendant_generations"]),
        "privacy_mode": config["fan_chart"]["privacy_mode"],
        "show_portraits": _as_bool(config["fan_chart"]["show_portraits"]),
        "show_highlight_markers": _as_bool(
            config["fan_chart"].get("show_highlight_markers", False)
        ),
        "canonical": canonical_name,
        "files": checksums,
        "notes": [
            "SVG canonique; PDF et PNG dérivent de la même source SVG.",
            "Les handles Gramps, jetons et données brutes ne sont pas publiés.",
        ],
    }


def _fixture_report_info(fixture: dict[str, Any]) -> dict[str, Any]:
    return fixture.get("report") or {
        "version": "fixture",
        "options_help": {
            "highlight_tag": [],
            "show_highlight_markers": [],
        },
    }


def build_assets(
    config: dict[str, Any],
    *,
    output_dir: Path,
    fixture: dict[str, Any] | None = None,
    client: GrampsApiClient | None = None,
    allow_missing_highlight: bool = False,
) -> dict[str, Any]:
    report_info = _fixture_report_info(fixture or {}) if fixture is not None else client.get_json(
        f"/reports/{config['gramps']['report_id']}?include_help=true"
    )
    ensure_addon_capability(report_info, allow_missing=allow_missing_highlight)
    if fixture is not None:
        options = report_options(config)
        if "fan_svg" in fixture:
            fan_svg = Path(fixture["fan_svg"]).read_bytes() if not str(fixture["fan_svg"]).lstrip().startswith("<") else str(fixture["fan_svg"]).encode()
        elif "fan_svg_path" in fixture:
            fan_svg = (Path(fixture["fan_svg_path"]).parent / Path(fixture["fan_svg_path"]).name).read_bytes()
        else:
            raise PipelineError("fixture has no fan_svg or fan_svg_path")
        report_version = str(report_info.get("version", "fixture"))
    else:
        if client is None:
            raise PipelineError("a live client is required outside fixture mode")
        ensure_addon_capability(report_info)
        fan_svg = run_remote_report(client, config, report_info)
        options = report_options(config)
        report_version = str(report_info.get("version", "unknown"))
    try:
        canonical_metrics = inspect_svg(fan_svg, expected_labels=("Coste", "Colomb"))
    except AssetValidationError as error:
        raise PipelineError(f"canonical report SVG rejected: {error}") from error
    if canonical_metrics.image_elements == 0 and options["show_portraits"]:
        # A report may legitimately use external image references only if they
        # are embedded before publication; external references are rejected by
        # inspect_svg, so this is an honest integration failure, not a fallback.
        raise PipelineError("portrait mode was requested but canonical SVG contains no embedded images")
    stage = Path(tempfile.mkdtemp(prefix="genealogie-build-"))
    try:
        stage.mkdir(parents=True, exist_ok=True)
        outputs_config = config.get("outputs") or {}
        fan_stem = str(outputs_config.get("canonical_fan_stem") or "arbre-benoit-coste")
        validation_config = config.get("validation") or {}
        expected_labels = tuple(str(label) for label in validation_config.get("expected_labels", ("Coste", "Colomb")))
        minimum_text_elements = int(validation_config.get("minimum_text_elements", 1))
        minimum_path_elements = int(validation_config.get("minimum_path_elements", 1))
        minimum_image_elements = int(validation_config.get("minimum_image_elements", 0))
        minimum_a4_font_pt = float(validation_config.get("minimum_a4_font_pt", 0.0))
        fan_path = stage / f"{fan_stem}.svg"
        fan_path.write_bytes(fan_svg)
        validate_svg_file(
            fan_path,
            expected_labels=expected_labels,
            minimum_text_elements=minimum_text_elements,
            minimum_path_elements=minimum_path_elements,
            minimum_image_elements=minimum_image_elements,
        )
        overview = stage / f"{fan_stem}-a4-overview.svg"
        overview.write_bytes(make_overview_svg(fan_svg))
        detail_paths: list[Path] = []
        for index, crop in enumerate(((0, 0), (1, 0), (0, 1), (1, 1)), start=1):
            detail = stage / f"{fan_stem}-a4-{index}.svg"
            detail.write_bytes(make_detail_svg(fan_svg, crop=crop))
            detail_paths.append(detail)
        for panel in [overview, *detail_paths]:
            validate_svg_file(
                panel,
                expected_labels=expected_labels,
                minimum_text_elements=minimum_text_elements,
                minimum_path_elements=minimum_path_elements,
                minimum_image_elements=minimum_image_elements,
                minimum_font_pt=None if panel == overview else minimum_a4_font_pt,
            )
        for svg in sorted(stage.glob("*.svg")):
            stem = svg.with_suffix("")
            convert_svg(svg, stem.with_suffix(".pdf"), "pdf")
            convert_svg(svg, stem.with_suffix(".png"), "png")
        # DOT is a source artifact, but the versioned public package only
        # retains a handle-free DOT if the configuration explicitly asks for it.
        manifest_files = [path for path in stage.iterdir() if path.suffix.lower() in {".svg", ".pdf", ".png"}]
        manifest = _safe_manifest(
            output_dir,
            config,
            manifest_files,
            report_version,
            canonical_name=fan_path.name,
        )
        _atomic_write(stage / "manifest.json", (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
        output_dir.mkdir(parents=True, exist_ok=True)
        for path in manifest_files:
            _atomic_copy(path, output_dir / path.name)
        _atomic_copy(stage / "manifest.json", output_dir / "manifest.json")
        return {"output_dir": str(output_dir), "files": sorted(path.name for path in manifest_files), "manifest": manifest}
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def load_fixture(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise PipelineError("fixture root must be a JSON object")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=REPO_ROOT / "genealogie" / "report.toml")
    parser.add_argument("--fixture", type=Path, help="offline fixture JSON")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--dry-run", action="store_true", help="validate fixture/config without writing assets")
    parser.add_argument("--allow-missing-highlight", action="store_true", help="diagnose an old addon; never use for publication")
    parser.add_argument("--env-file", type=Path, help="external credential file, outside this repository")
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
        fixture = load_fixture(args.fixture) if args.fixture else None
        if args.dry_run:
            if fixture is None:
                raise PipelineError("--dry-run requires --fixture so no live report is launched")
            with tempfile.TemporaryDirectory(prefix="genealogie-dry-run-") as tmp:
                result = build_assets(
                    config,
                    output_dir=Path(tmp),
                    fixture=fixture,
                    allow_missing_highlight=args.allow_missing_highlight,
                )
                print(json.dumps({"mode": "fixture-dry-run", "files": result["files"]}, ensure_ascii=False))
            return 0
        output_dir = args.output_dir or REPO_ROOT / "genealogie" / "assets"
        if fixture is not None:
            result = build_assets(config, output_dir=output_dir, fixture=fixture, allow_missing_highlight=args.allow_missing_highlight)
        else:
            client = client_from_external_env(args.env_file)
            result = build_assets(config, output_dir=output_dir, client=client)
        print(json.dumps({"output_dir": result["output_dir"], "files": result["files"]}, ensure_ascii=False))
        return 0
    except (OSError, KeyError, ValueError, json.JSONDecodeError, GrampsApiError, PipelineError) as error:
        print(f"genealogy build failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
