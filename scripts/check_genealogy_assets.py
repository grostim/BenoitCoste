"""Public-artifact checks for the genealogy chapter.

The checker is intentionally dependency-free so it can run in GitHub Actions
without Gramps, a database export, or credentials.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET


class AssetValidationError(ValueError):
    """Raised when a public genealogy asset violates a safety contract."""


SVG_NS = "http://www.w3.org/2000/svg"
_REMOTE_RE = re.compile(r"(?i)(?:https?|file):|//[A-Za-z0-9.-]+")
_EMBEDDED_IMAGE_RE = re.compile(
    r"(?is)data:image/(?:png|jpe?g|gif|webp);base64,[A-Za-z0-9+/=\s]+"
)
_HANDLE_RE = re.compile(r"(?<![A-Za-z0-9])(?:I|F|S|C|E|O|N|M|P)\d{3,}(?![A-Za-z0-9])")
_FONT_RE = re.compile(r"(?i)(?:font-size\s*[=:]\s*['\"]?)([0-9]+(?:\.[0-9]+)?)\s*(pt|px)?")
_LENGTH_RE = re.compile(r"^\s*([0-9]+(?:\.[0-9]+)?)\s*(mm|cm|in|pt|px)?\s*$", re.I)


@dataclass(frozen=True)
class SvgMetrics:
    width: str
    height: str
    text_elements: int
    path_elements: int
    image_elements: int
    marker_elements: int
    minimum_font_pt: float | None


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _length_to_mm(value: str | None) -> float | None:
    if not value:
        return None
    match = _LENGTH_RE.match(value)
    if not match:
        return None
    number = float(match.group(1))
    unit = (match.group(2) or "px").lower()
    return number * {
        "mm": 1.0,
        "cm": 10.0,
        "in": 25.4,
        "pt": 25.4 / 72.0,
        "px": 25.4 / 96.0,
    }[unit]


def _font_pt(value: float, unit: str | None, *, user_unit_mm: float = 25.4 / 96.0) -> float:
    if unit is None:
        return value * user_unit_mm * 72.0 / 25.4
    unit = unit.lower()
    if unit == "pt":
        return value
    if unit == "mm":
        return value * 72.0 / 25.4
    if unit == "cm":
        return value * 72.0 / 2.54
    return value * 72.0 / 96.0


def _user_unit_mm(root: ET.Element) -> float:
    """Return the physical size of one user unit in the root viewBox."""
    width_mm = _length_to_mm(root.get("width"))
    height_mm = _length_to_mm(root.get("height"))
    parts = (root.get("viewBox") or "").replace(",", " ").split()
    if width_mm is None or height_mm is None or len(parts) != 4:
        return 25.4 / 96.0
    try:
        view_width = float(parts[2])
        view_height = float(parts[3])
    except ValueError:
        return 25.4 / 96.0
    if view_width <= 0 or view_height <= 0:
        return 25.4 / 96.0
    return min(width_mm / view_width, height_mm / view_height)


def _contains_external_resource(value: str) -> bool:
    """Reject network/file references while allowing embedded raster images.

    Base64 payloads regularly contain ``//``.  Searching the complete data URI
    with ``_REMOTE_RE`` therefore produces false positives, while allowing all
    ``data:`` URIs would permit embedded SVG/HTML content.  Replace only the
    raster image form emitted by the report before checking the remaining
    value, and reject any other data URI as well.
    """
    scrubbed = _EMBEDDED_IMAGE_RE.sub("embedded-image", value.strip())
    if re.search(r"(?i)\bdata:", scrubbed):
        return True
    return _REMOTE_RE.search(scrubbed) is not None


def _without_embedded_images(value: str) -> str:
    """Remove trusted image payloads before scanning text-like metadata."""
    return _EMBEDDED_IMAGE_RE.sub("embedded-image", value)


def inspect_svg(data: bytes, *, expected_labels: tuple[str, ...] = ()) -> SvgMetrics:
    """Parse and validate one SVG without trusting its producer."""
    try:
        root = ET.fromstring(data)
    except ET.ParseError as error:
        raise AssetValidationError("SVG is not well-formed XML") from error
    if _local(root.tag) != "svg":
        raise AssetValidationError("root element is not svg")
    serialized = data.decode("utf-8", errors="replace")
    user_unit_mm = _user_unit_mm(root)
    # The SVG namespace is conventionally an http URI and is not an external
    # asset. Inspect resource-bearing attributes and CSS text instead.
    for node in root.iter():
        for attribute, value in node.attrib.items():
            local_attribute = _local(attribute).lower()
            if local_attribute in {"href", "src", "style"} and _contains_external_resource(value):
                raise AssetValidationError("SVG contains an external or file resource")
    for style_node in root.iter():
        if _local(style_node.tag) == "style" and _contains_external_resource("".join(style_node.itertext())):
            raise AssetValidationError("SVG contains an external or file resource")
    if "<script" in serialized.lower() or "javascript:" in serialized.lower():
        raise AssetValidationError("SVG contains executable content")
    semantic_fragments: list[str] = []
    for node in root.iter():
        if _local(node.tag) not in {"path", "polygon", "polyline", "circle", "rect", "line", "ellipse"}:
            semantic_fragments.append(" ".join(node.itertext()))
        for attribute, value in node.attrib.items():
            local_attribute = _local(attribute).lower()
            if local_attribute in {"id", "href", "src", "class", "aria-label", "title"} or local_attribute.startswith("data-"):
                semantic_fragments.append(_without_embedded_images(value))
    if _HANDLE_RE.search("\n".join(semantic_fragments)):
        raise AssetValidationError("SVG contains a Gramps technical identifier")
    width = root.get("width", "")
    height = root.get("height", "")
    if _length_to_mm(width) is None or _length_to_mm(height) is None:
        view_box = root.get("viewBox", "").split()
        if len(view_box) != 4:
            raise AssetValidationError("SVG has no usable physical dimensions")
        try:
            if float(view_box[2]) <= 0 or float(view_box[3]) <= 0:
                raise ValueError
        except ValueError as error:
            raise AssetValidationError("SVG viewBox is invalid") from error
    text_nodes = [node for node in root.iter() if _local(node.tag) == "text"]
    path_nodes = [node for node in root.iter() if _local(node.tag) == "path"]
    image_nodes = [node for node in root.iter() if _local(node.tag) == "image"]
    marker_nodes = []
    for node in root.iter():
        local = _local(node.tag)
        stroke = node.get("stroke", "").lower()
        if local in {"polygon", "polyline"} and stroke == "#7c2f3a":
            marker_nodes.append(node)
        elif (
            local == "path"
            and stroke == "#7c2f3a"
            and node.get("d", "").rstrip().endswith("Z")
            and node.get("d", "").count("L") >= 3
        ):
            marker_nodes.append(node)
    text = " ".join("".join(node.itertext()) for node in text_nodes) + " " + serialized
    for label in expected_labels:
        if label and label not in text:
            raise AssetValidationError(f"expected label is absent: {label}")
    font_values: list[float] = []
    for match in _FONT_RE.finditer(serialized):
        font_values.append(
            _font_pt(
                float(match.group(1)),
                match.group(2),
                user_unit_mm=user_unit_mm,
            )
        )
    return SvgMetrics(
        width=width,
        height=height,
        text_elements=len(text_nodes),
        path_elements=len(path_nodes),
        image_elements=len(image_nodes),
        marker_elements=len(marker_nodes),
        minimum_font_pt=min(font_values) if font_values else None,
    )


def validate_svg_file(
    path: Path,
    *,
    expected_labels: tuple[str, ...] = (),
    minimum_text_elements: int = 1,
    minimum_path_elements: int = 1,
    minimum_image_elements: int = 0,
    minimum_font_pt: float | None = None,
) -> SvgMetrics:
    data = path.read_bytes()
    metrics = inspect_svg(data, expected_labels=expected_labels)
    if metrics.text_elements < minimum_text_elements:
        raise AssetValidationError(f"SVG contains too few text elements: {metrics.text_elements}")
    if metrics.path_elements < minimum_path_elements:
        raise AssetValidationError(f"SVG contains too few path elements: {metrics.path_elements}")
    if metrics.image_elements < minimum_image_elements:
        raise AssetValidationError(f"SVG contains too few image elements: {metrics.image_elements}")
    if minimum_font_pt is not None and metrics.minimum_font_pt is not None and metrics.minimum_font_pt < minimum_font_pt:
        raise AssetValidationError("SVG contains text below the configured print-size threshold")
    return metrics


def validate_asset_directory(directory: Path, *, expected_labels: tuple[str, ...] = ()) -> dict[str, object]:
    if not directory.is_dir():
        raise AssetValidationError(f"asset directory does not exist: {directory}")
    report: dict[str, object] = {"directory": directory.name, "svg": {}, "binary": {}}
    for path in sorted(directory.glob("*.svg")):
        metrics = validate_svg_file(path, expected_labels=expected_labels)
        report["svg"][path.name] = asdict(metrics)  # type: ignore[index]
    for suffix in ("*.pdf", "*.png"):
        for path in sorted(directory.glob(suffix)):
            if path.stat().st_size == 0:
                raise AssetValidationError(f"empty binary asset: {path.name}")
            report["binary"][path.name] = path.stat().st_size  # type: ignore[index]
    if not report["svg"]:  # type: ignore[truthy-bool]
        raise AssetValidationError("no SVG assets found")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args(argv)
    try:
        import json
        print(json.dumps(validate_asset_directory(args.directory), ensure_ascii=False, indent=2))
    except (OSError, AssetValidationError) as error:
        print(f"asset validation failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
