"""Render one SVG with the system librsvg/Cairo bindings.

This helper is optional: the main pipeline selects it only when a Python
interpreter can import both ``gi.repository.Rsvg`` and ``cairo``. It keeps
SVG -> PDF/PNG conversion vector-faithful without requiring a CLI converter.
"""

from __future__ import annotations

import math
import re
import sys
from pathlib import Path

import cairo
import gi

gi.require_version("Rsvg", "2.0")
from gi.repository import Rsvg  # noqa: E402


_LENGTH_RE = re.compile(r"^\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*(mm|cm|in|pt|pc|px)?\s*$")


def _length_to_points(value: str | None, fallback_px: float) -> float:
    if not value:
        return fallback_px * 72.0 / 90.0
    match = _LENGTH_RE.match(value)
    if not match:
        return fallback_px * 72.0 / 90.0
    number = float(match.group(1))
    unit = match.group(2) or "px"
    factors = {
        "mm": 72.0 / 25.4,
        "cm": 72.0 / 2.54,
        "in": 72.0,
        "pt": 1.0,
        "pc": 12.0,
        "px": 72.0 / 90.0,
    }
    return number * factors[unit]


def _render(source: Path, target: Path, format_name: str) -> None:
    handle = Rsvg.Handle.new_from_file(str(source))
    dimensions = handle.get_dimensions()
    width_px = float(dimensions.width)
    height_px = float(dimensions.height)
    if not math.isfinite(width_px) or not math.isfinite(height_px) or width_px <= 0 or height_px <= 0:
        raise RuntimeError("SVG has no positive finite dimensions")

    root_width = None
    root_height = None
    try:
        import xml.etree.ElementTree as ET

        root = ET.parse(source).getroot()
        root_width = root.get("width")
        root_height = root.get("height")
    except (OSError, ET.ParseError):
        pass

    if format_name == "pdf":
        width_pt = _length_to_points(root_width, width_px)
        height_pt = _length_to_points(root_height, height_px)
        surface = cairo.PDFSurface(str(target), width_pt, height_pt)
        context = cairo.Context(surface)
        context.scale(width_pt / width_px, height_pt / height_px)
        handle.render_cairo(context)
        surface.finish()
        return

    if format_name == "png":
        width = max(1, int(math.ceil(width_px)))
        height = max(1, int(math.ceil(height_px)))
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
        context = cairo.Context(surface)
        context.scale(width / width_px, height / height_px)
        handle.render_cairo(context)
        surface.write_to_png(str(target))
        surface.finish()
        return

    raise RuntimeError(f"unsupported format: {format_name}")


def main(argv: list[str]) -> int:
    if len(argv) != 4:
        print("usage: render_svg_librsvg.py SOURCE TARGET FORMAT", file=sys.stderr)
        return 2
    source, target, format_name = Path(argv[1]), Path(argv[2]), argv[3]
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        _render(source, target, format_name)
    except Exception as error:  # pragma: no cover - exercised by subprocess gate
        print(f"librsvg conversion failed: {type(error).__name__}: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
