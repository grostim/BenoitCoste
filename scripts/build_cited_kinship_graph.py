"""Deterministic Graphviz graph for cited collateral relatives.

Input is a private, temporary JSON projection produced by the local update
runner. Output labels contain only privacy-safe names; technical Gramps
handles are used for computation and never become DOT node IDs or SVG text.
"""

from __future__ import annotations

import argparse
from collections import deque
import html
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any, Iterable


class KinshipGraphError(ValueError):
    """Input or Graphviz output cannot satisfy the graph contract."""


def _name(person: dict[str, Any]) -> str:
    if person.get("visible", True) is False or person.get("masked", False):
        return "Personne privée"
    if person.get("name"):
        return str(person["name"])
    primary = person.get("primary_name") or {}
    first = str(primary.get("call") or primary.get("first_name") or "").strip()
    surnames = primary.get("surname_list") or []
    surname = ""
    if surnames and isinstance(surnames[0], dict):
        surname = str(surnames[0].get("surname") or "").strip()
    if not surname:
        surname = str(primary.get("surname") or "").strip()
    return " ".join(part for part in (first, surname) if part) or "Personne sans nom"


def _dates(person: dict[str, Any]) -> str:
    if person.get("visible", True) is False or person.get("masked", False):
        return ""
    birth = str(person.get("birth") or "").strip()
    death = str(person.get("death") or "").strip()
    if birth or death:
        return f" ({birth}–{death})".strip(" ()")
    return ""


def _children(family: dict[str, Any]) -> tuple[str, ...]:
    values = family.get("children") or family.get("child_handles") or []
    if isinstance(values, dict):
        values = values.values()
    result: list[str] = []
    for value in values:
        if isinstance(value, dict):
            value = value.get("ref") or value.get("handle")
        if value:
            result.append(str(value))
    for value in family.get("child_ref_list") or []:
        if isinstance(value, dict):
            value = value.get("ref")
        if value and str(value) not in result:
            result.append(str(value))
    return tuple(result)


def _family_people(family: dict[str, Any]) -> tuple[str, ...]:
    values: list[str] = []
    for key in ("father", "father_handle", "mother", "mother_handle"):
        value = family.get(key)
        if isinstance(value, dict):
            value = value.get("ref") or value.get("handle")
        if value:
            values.append(str(value))
    return tuple(values) + _children(family)


def _tagged(person: dict[str, Any], tag_handle: str | None) -> bool:
    if isinstance(person.get("tagged"), bool):
        return bool(person["tagged"])
    return bool(tag_handle and tag_handle in (person.get("tag_list") or []))


def _visible(person: dict[str, Any]) -> bool:
    return person.get("visible", True) is not False and not person.get("excluded", False)


def _escape_dot(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def normalise_data(data: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    people_rows = data.get("people") or []
    family_rows = data.get("families") or []
    people: dict[str, dict[str, Any]] = {}
    for row in people_rows:
        if not isinstance(row, dict):
            continue
        handle = row.get("handle") or row.get("id") or row.get("gramps_id")
        if handle:
            people[str(handle)] = row
    families: dict[str, dict[str, Any]] = {}
    for row in family_rows:
        if not isinstance(row, dict):
            continue
        handle = row.get("handle") or row.get("id") or row.get("gramps_id")
        if handle:
            families[str(handle)] = row
    return people, families


def _adjacency(
    people: dict[str, dict[str, Any]], families: dict[str, dict[str, Any]]
) -> dict[tuple[str, str], tuple[tuple[str, str], ...]]:
    adjacency: dict[tuple[str, str], list[tuple[str, str]]] = {}
    for family_handle, family in families.items():
        family_node = ("family", family_handle)
        members = [handle for handle in _family_people(family) if handle in people]
        adjacency.setdefault(family_node, [])
        for person_handle in members:
            person_node = ("person", person_handle)
            adjacency.setdefault(person_node, []).append(family_node)
            adjacency[family_node].append(person_node)
    return {node: tuple(neighbours) for node, neighbours in adjacency.items()}


def _shortest_path(
    adjacency: dict[tuple[str, str], tuple[tuple[str, str], ...]],
    start: tuple[str, str],
    target: tuple[str, str],
) -> tuple[tuple[str, str], ...] | None:
    queue: deque[tuple[str, str]] = deque([start])
    previous: dict[tuple[str, str], tuple[str, str] | None] = {start: None}
    while queue:
        node = queue.popleft()
        if node == target:
            path: list[tuple[str, str]] = []
            while node is not None:
                path.append(node)
                node = previous[node]  # type: ignore[assignment]
            return tuple(reversed(path))
        for neighbour in adjacency.get(node, ()):
            if neighbour not in previous:
                previous[neighbour] = node
                queue.append(neighbour)
    return None


def select_cited_subgraph(
    data: dict[str, Any],
    *,
    center_handle: str,
    tag_handle: str | None = None,
) -> dict[str, Any]:
    """Return tagged people plus the minimal bipartite family paths to center."""
    people, families = normalise_data(data)
    if center_handle not in people:
        raise KinshipGraphError("center person is absent from the private projection")
    adjacency = _adjacency(people, families)
    start = ("person", center_handle)
    selected_people: set[str] = {center_handle}
    selected_families: set[str] = set()
    tagged_handles = sorted(
        handle for handle, person in people.items()
        if _tagged(person, tag_handle) and _visible(person)
    )
    connected_tagged: list[str] = []
    unconnected_tagged: list[str] = []
    for handle in tagged_handles:
        path = _shortest_path(adjacency, start, ("person", handle))
        if path is None:
            unconnected_tagged.append(handle)
            continue
        connected_tagged.append(handle)
        for kind, node_handle in path:
            if kind == "person":
                selected_people.add(node_handle)
            else:
                selected_families.add(node_handle)
    # Never expose a private person as a tagged node. A private connector stays
    # in the path so the relationship remains understandable, but its rendered
    # label is the neutral privacy label.
    selected_families = {
        handle for handle in selected_families
        if handle in families and any(member in selected_people for member in _family_people(families[handle]))
    }
    return {
        "people": [people[handle] for handle in sorted(selected_people)],
        "families": [families[handle] for handle in sorted(selected_families)],
        "tagged_handles": connected_tagged,
        "unconnected_tagged_handles": unconnected_tagged,
        "center_handle": center_handle,
    }


def build_dot(subgraph: dict[str, Any], *, tag_handle: str | None = None) -> str:
    """Build handle-free DOT with shape and colour citation semantics."""
    people, families = normalise_data(subgraph)
    center_handle = str(subgraph.get("center_handle") or "")
    tagged_handles = {
        handle for handle, person in people.items()
        if _tagged(person, tag_handle) or handle in set(subgraph.get("tagged_handles") or [])
    }
    person_ids = {
        handle: f"p{index}"
        for index, handle in enumerate(sorted(people, key=lambda h: (_name(people[h]), h)))
    }
    family_ids = {
        handle: f"f{index}"
        for index, handle in enumerate(sorted(families))
    }
    lines = [
        "graph cited_kinship {",
        '  graph [rankdir=LR, bgcolor="transparent", pad="0.2", nodesep="0.35", ranksep="0.55", splines=polyline];',
        '  node [fontname="DejaVu Sans", fontsize=10, style="filled", fillcolor="#FAF9F5", color="#8B8982", fontcolor="#242321"];',
        '  edge [color="#9B9992", penwidth=1.0];',
    ]
    for handle, node_id in person_ids.items():
        person = people[handle]
        label = _name(person) + _dates(person)
        if handle == center_handle:
            label = "Benoît Coste" if not label else label
        if handle in tagged_handles:
            lines.append(
                f'  {node_id} [label="{_escape_dot(label)}", shape=doublecircle, color="#7C2F3A", '
                'penwidth=2.2, fillcolor="#F4E7E5"];'
            )
        else:
            lines.append(f'  {node_id} [label="{_escape_dot(label)}", shape=ellipse];')
    for handle, node_id in family_ids.items():
        lines.append(f'  {node_id} [label="", shape=point, width=0.08, height=0.08, color="#8B8982", fillcolor="#8B8982"];')
        for member in _family_people(families[handle]):
            if member in person_ids:
                lines.append(f"  {person_ids[member]} -- {node_id};")
    lines.append("}")
    return "\n".join(lines) + "\n"


def _dot_attributes(value: str) -> dict[str, str]:
    attributes: dict[str, str] = {}
    for key, raw_value in re.findall(r'(\w+)="((?:\\.|[^"\\])*)"', value):
        attributes[key] = raw_value.replace(r'\"', '"').replace(r"\\", "\\")
    return attributes


def _fallback_graph_svg(dot_text: str) -> bytes:
    """Render the generated, restricted DOT subset without Graphviz.

    This is deliberately not a general DOT parser. It only accepts the node
    and edge grammar emitted by :func:`build_dot`, keeping the fallback small,
    deterministic, and unable to expose source handles as labels.
    """
    nodes: dict[str, dict[str, str]] = {}
    edges: list[tuple[str, str]] = []
    node_pattern = re.compile(r"^\s+(p\d+|f\d+)\s+\[(.*)\];\s*$")
    edge_pattern = re.compile(r"^\s+(p\d+|f\d+)\s+--\s+(p\d+|f\d+)\s*;\s*$")
    for line in dot_text.splitlines():
        node_match = node_pattern.match(line)
        if node_match:
            nodes[node_match.group(1)] = _dot_attributes(node_match.group(2))
            continue
        edge_match = edge_pattern.match(line)
        if edge_match:
            edges.append((edge_match.group(1), edge_match.group(2)))
    if not nodes:
        raise KinshipGraphError("generated DOT contains no renderable nodes")

    people = sorted(node_id for node_id in nodes if node_id.startswith("p"))
    families = sorted(node_id for node_id in nodes if node_id.startswith("f"))

    # The fallback must remain useful when Graphviz is absent.  A single
    # vertical rank makes a 30-person graph several metres tall in the PDF and
    # forces the chapter to shrink its labels to illegibility.  Keep people in
    # a deterministic three-column grid and put family junctions between the
    # person columns.  The layout is intentionally simple; edges are still
    # drawn behind every node so the complete bipartite path remains visible.
    person_columns = min(3, max(1, (len(people) + 9) // 10))
    family_columns = max(1, person_columns - 1)
    row_step = 116
    origin_x = 260
    origin_y = 90
    person_radius_x = 210
    person_radius_y = 38
    person_positions = {
        node_id: (
            origin_x + (index % person_columns) * 700,
            origin_y + (index // person_columns) * row_step,
        )
        for index, node_id in enumerate(people)
    }
    family_positions = {
        node_id: (
            origin_x + (index % family_columns + 0.5) * 700,
            origin_y + (index // family_columns) * row_step,
        )
        for index, node_id in enumerate(families)
    }
    max_x = max(
        [x + person_radius_x for x, _y in person_positions.values()]
        + [x + 16 for x, _y in family_positions.values()]
        + [origin_x + person_radius_x],
    )
    max_y = max(
        [y + person_radius_y for _x, y in person_positions.values()]
        + [y + 16 for _x, y in family_positions.values()]
        + [origin_y + person_radius_y],
    )
    width = int(max_x + 80)
    height = int(max(220, max_y + 80))
    positions = {**person_positions, **family_positions}
    elements = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}px" height="{height}px" viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" fill="#FAF9F5"/>',
    ]
    for left, right in edges:
        if left not in positions or right not in positions:
            continue
        x1, y1 = positions[left]
        x2, y2 = positions[right]
        elements.append(f'<path d="M{x1} {y1} L{x2} {y2}" fill="none" stroke="#9B9992" stroke-width="2"/>')
    for node_id in families:
        x, y = family_positions[node_id]
        attributes = nodes[node_id]
        color = attributes.get("color", "#8B8982")
        fill = attributes.get("fillcolor", color)
        elements.append(f'<circle cx="{x}" cy="{y}" r="7" fill="{html.escape(fill)}" stroke="{html.escape(color)}" stroke-width="1.5"/>')
    for node_id in people:
        x, y = person_positions[node_id]
        attributes = nodes[node_id]
        label = html.escape(attributes.get("label", ""))
        color = html.escape(attributes.get("color", "#8B8982"))
        fill = html.escape(attributes.get("fillcolor", "#FAF9F5"))
        penwidth = html.escape(attributes.get("penwidth", "1.4"))
        elements.append(f'<ellipse cx="{x}" cy="{y}" rx="{person_radius_x}" ry="{person_radius_y}" fill="{fill}" stroke="{color}" stroke-width="{penwidth}"/>')
        if attributes.get("shape") == "doublecircle":
            elements.append(f'<ellipse cx="{x}" cy="{y}" rx="{person_radius_x - 8}" ry="{person_radius_y - 8}" fill="none" stroke="{color}" stroke-width="1.4"/>')
        # Split long labels into two lines without changing their wording.
        # The DOT renderer also receives the same single label; this is only a
        # presentation improvement for the dependency-free fallback.
        plain_label = html.unescape(label)
        words = plain_label.split()
        lines: list[str] = []
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if current and len(candidate) > 30 and len(lines) == 0:
                lines.append(current)
                current = word
            else:
                current = candidate
        if current:
            lines.append(current)
        lines = lines[:2] or [""]
        if len(lines) == 1:
            elements.append(f'<text x="{x}" y="{y + 5}" text-anchor="middle" font-family="DejaVu Sans, sans-serif" font-size="16" fill="#242321">{html.escape(lines[0])}</text>')
        else:
            elements.append(
                f'<text x="{x}" text-anchor="middle" font-family="DejaVu Sans, sans-serif" font-size="16" fill="#242321">'
                f'<tspan x="{x}" y="{y - 5}">{html.escape(lines[0])}</tspan>'
                f'<tspan x="{x}" y="{y + 14}">{html.escape(lines[1])}</tspan>'
                "</text>"
            )
    elements.append("</svg>")
    return "\n".join(elements).encode("utf-8")


def _render_with_librsvg(source: Path, target: Path, format_name: str) -> None:
    helper = Path(__file__).resolve().parent / "render_svg_librsvg.py"
    candidates = []
    configured = os.environ.get("GENEALOGIE_RENDER_PYTHON")
    if configured:
        candidates.append(configured)
    candidates.extend(["/usr/bin/python3", "/usr/local/bin/python3"])
    probe = "import cairo, gi; gi.require_version('Rsvg', '2.0'); from gi.repository import Rsvg"
    renderer = next(
        (
            candidate
            for candidate in candidates
            if (Path(candidate).exists() or shutil.which(candidate))
            and subprocess.run([candidate, "-c", probe], capture_output=True, check=False).returncode == 0
        ),
        None,
    )
    if renderer is None:
        raise KinshipGraphError(f"no renderer available for fallback {format_name}")
    completed = subprocess.run(
        [renderer, str(helper), str(source), str(target), format_name],
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0 or not target.exists() or target.stat().st_size == 0:
        raise KinshipGraphError(f"fallback renderer produced no {format_name} asset")


def render_graph(dot_text: str, output_dir: Path, stem: str, *, dot_command: str = "dot") -> dict[str, Path]:
    """Render DOT once per requested public format.

    Graphviz is preferred. When it is unavailable, the restricted fallback
    keeps the DOT source and produces the same public formats from a
    handle-free SVG.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    dot_path = output_dir / f"{stem}.dot"
    dot_path.write_text(dot_text, encoding="utf-8")
    outputs: dict[str, Path] = {"dot": dot_path}
    dot_binary = shutil.which(dot_command)
    if dot_binary is None:
        svg_path = output_dir / f"{stem}.svg"
        svg_path.write_bytes(_fallback_graph_svg(dot_text))
        outputs["svg"] = svg_path
        for suffix in ("pdf", "png"):
            target = output_dir / f"{stem}.{suffix}"
            _render_with_librsvg(svg_path, target, suffix)
            outputs[suffix] = target
        return outputs
    for suffix in ("svg", "pdf", "png"):
        target = output_dir / f"{stem}.{suffix}"
        command = [dot_binary, f"-T{suffix}", str(dot_path), "-o", str(target)]
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            raise KinshipGraphError(f"Graphviz failed while producing {suffix}")
        if not target.exists() or target.stat().st_size == 0:
            raise KinshipGraphError(f"Graphviz produced no {suffix} asset")
        outputs[suffix] = target
    return outputs


def build_from_data(
    data: dict[str, Any],
    *,
    center_handle: str,
    tag_handle: str | None,
    output_dir: Path | None = None,
    stem: str = "parente-citee",
    render: bool = False,
) -> tuple[dict[str, Any], str, dict[str, Path]]:
    subgraph = select_cited_subgraph(data, center_handle=center_handle, tag_handle=tag_handle)
    dot = build_dot(subgraph, tag_handle=tag_handle)
    outputs: dict[str, Path] = {}
    if render:
        if output_dir is None:
            raise KinshipGraphError("output_dir is required when render=True")
        outputs = render_graph(dot, output_dir, stem)
    return subgraph, dot, outputs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data", type=Path, help="private temporary JSON projection")
    parser.add_argument("--center-handle", required=True)
    parser.add_argument("--tag-handle")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--stem", default="parente-citee")
    args = parser.parse_args(argv)
    try:
        data = json.loads(args.data.read_text(encoding="utf-8"))
        _subgraph, dot, outputs = build_from_data(
            data,
            center_handle=args.center_handle,
            tag_handle=args.tag_handle,
            output_dir=args.output_dir,
            stem=args.stem,
            render=True,
        )
        print(json.dumps({"outputs": sorted(path.name for path in outputs.values())}, ensure_ascii=False))
    except (OSError, json.JSONDecodeError, KinshipGraphError) as error:
        print(f"kinship graph failed: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
