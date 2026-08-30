"""Build a public-safe, one-page-per-person portrait gallery.

The live collector reads GrampsWeb and downloads only portrait-like image
media.  The renderer writes sanitized JPEGs and a generated LaTeX fragment;
there is no hand-maintained person list.  Fixture mode keeps CI network-free.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import io
import json
from pathlib import Path
import re
from typing import Any, Callable, Iterable

from PIL import Image, ImageOps

from gramps_api import GrampsApiClient, GrampsApiError
from relations_gramps import RelationshipResolver


MONTHS = {
    1: "janvier", 2: "février", 3: "mars", 4: "avril", 5: "mai", 6: "juin",
    7: "juillet", 8: "août", 9: "septembre", 10: "octobre", 11: "novembre", 12: "décembre",
}
MONTH_NAMES = {
    "JAN": "janvier", "FEB": "février", "MAR": "mars", "APR": "avril",
    "MAY": "mai", "JUN": "juin", "JUL": "juillet", "AUG": "août",
    "SEP": "septembre", "OCT": "octobre", "NOV": "novembre", "DEC": "décembre",
}


@dataclass(frozen=True)
class Portrait:
    data: bytes
    rect: tuple[float, float, float, float] | None
    description: str


@dataclass(frozen=True)
class GalleryRecord:
    gramps_id: str
    handle: str
    first_name: str
    call_name: str
    surname: str
    gender: int | None
    private: bool
    relation: str
    relation_rank: int
    birth: tuple[str, str] | None
    death: tuple[str, str] | None
    occupations: tuple[str, ...]
    portraits: tuple[Portrait, ...]


@dataclass(frozen=True)
class GalleryBuild:
    tex_path: Path
    portrait_paths: tuple[Path, ...]
    people: int
    pages: int
    people_with_portraits: int
    portrait_count: int
    private_people: int
    portrait_errors: tuple[str, ...]


def _ref(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("ref") or value.get("handle") or "")
    return str(value or "")


def _rows(payload: Any, collection: str) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in (collection.strip("/"), "items", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
    raise GrampsApiError(f"unexpected {collection} collection shape")


def _list_all(client: GrampsApiClient, collection: str, *, extend: str | None = None) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for page in range(1, 201):
        query: dict[str, str | int] = {"page": page, "pagesize": 500}
        if extend:
            query["extend"] = extend
        page_rows = _rows(client.get_json(f"/{collection.strip('/')}/", query=query), collection)
        result.extend(page_rows)
        if len(page_rows) < 500:
            return result
    raise GrampsApiError(f"{collection} collection exceeded the pagination safety bound")


def _person_name_parts(person: dict[str, Any]) -> tuple[str, str, str]:
    name = person.get("primary_name") or {}
    first = str(name.get("first_name") or "").strip()
    call = str(name.get("call") or "").strip()
    surnames = name.get("surname_list") or []
    surname = ""
    if surnames and isinstance(surnames[0], dict):
        surname = str(surnames[0].get("surname") or "").strip()
    return first, call, surname


def _place_name(place: dict[str, Any] | None) -> str:
    if not place:
        return ""
    name = place.get("name")
    if isinstance(name, dict):
        return str(name.get("value") or name.get("string") or name.get("name") or "").strip()
    return str(name or place.get("title") or "").strip()


def _date_label(date: Any) -> str:
    if not isinstance(date, dict):
        return ""
    dateval = date.get("dateval") or []
    if isinstance(dateval, list) and len(dateval) >= 3:
        try:
            day, month, year = int(dateval[0] or 0), int(dateval[1] or 0), int(dateval[2] or 0)
        except (TypeError, ValueError):
            day = month = year = 0
        if year:
            if day and month:
                label = f"{day} {MONTHS.get(month, str(month))} {year}"
            elif month:
                label = f"{MONTHS.get(month, str(month))} {year}"
            else:
                label = str(year)
            if int(date.get("quality") or 0) == 1:
                label = "vers " + label
            return label
    text = str(date.get("text") or "").strip()
    if not text:
        return ""
    tokens = text.split()
    if len(tokens) >= 3 and tokens[-1].isdigit() and tokens[-2].upper() in MONTH_NAMES:
        return " ".join(tokens[:-2] + [MONTH_NAMES[tokens[-2].upper()], tokens[-1]])
    if len(tokens) == 2 and tokens[0].upper() in MONTH_NAMES and tokens[1].isdigit():
        return f"{MONTH_NAMES[tokens[0].upper()]} {tokens[1]}"
    return text


def _event_fact(event: dict[str, Any] | None, places: dict[str, dict[str, Any]]) -> tuple[str, str] | None:
    if not event:
        return None
    date = _date_label(event.get("date"))
    place = _place_name(places.get(_ref(event.get("place"))))
    if not date and not place:
        return None
    return date or "date non renseignée", place or "lieu non renseigné"


def _event_ref_handle(ref: Any) -> str:
    return _ref(ref)


def _primary_events(person: dict[str, Any], events: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for ref in person.get("event_ref_list") or []:
        role = ref.get("role") if isinstance(ref, dict) else ""
        # A person's own fact must be Primary.  Participant references are not
        # silently promoted to births/deaths/professions.
        if role not in ("Primary", ""):
            continue
        event = events.get(_event_ref_handle(ref))
        if event:
            result.append(event)
    return result


def _best_event(person: dict[str, Any], event_type: str, events: dict[str, dict[str, Any]], places: dict[str, dict[str, Any]]) -> tuple[str, str] | None:
    candidates = [event for event in _primary_events(person, events) if event.get("type") == event_type]
    if not candidates:
        return None
    # Prefer a precise date and a named place; retain the first source order as
    # a deterministic tie-breaker for duplicate Gramps events.
    candidates.sort(key=lambda event: (
        0 if _date_label(event.get("date")) else 1,
        0 if _place_name(places.get(_ref(event.get("place")))) else 1,
    ))
    return _event_fact(candidates[0], places)


def _occupations(person: dict[str, Any], events: dict[str, dict[str, Any]]) -> tuple[str, ...]:
    values: list[str] = []
    for event in _primary_events(person, events):
        if event.get("type") != "Occupation":
            continue
        description = str(event.get("description") or "").strip()
        if not description:
            continue
        if description not in values:
            values.append(description)
    return tuple(values)


def _portrait_candidate(media: dict[str, Any]) -> bool:
    mime = str(media.get("mime") or "").lower()
    path = str(media.get("path") or "").lower()
    if not (mime.startswith("image/") or path.endswith((".jpg", ".jpeg", ".png", ".gif", ".tif", ".tiff"))):
        return False
    text = " ".join(str(media.get(key) or "") for key in ("desc", "title")).lower()
    excluded = ("médaille", "medaille", "armoir", "revers", "cartouche", "annotation", "acte", "registre", "capture d'écran", "capture d’", "fiche")
    if any(word in text for word in excluded):
        return False
    return any(word in text for word in ("portrait", "photo", "photographie", "peint", "double portrait"))


def _rect(value: Any) -> tuple[float, float, float, float] | None:
    if not isinstance(value, (list, tuple)) or len(value) < 4:
        return None
    try:
        values = tuple(float(x) for x in value[:4])
    except (TypeError, ValueError):
        return None
    if values[2] <= values[0] or values[3] <= values[1]:
        return None
    return values  # type: ignore[return-value]


def _person_portraits(person: dict[str, Any], media_by_handle: dict[str, dict[str, Any]], media_loader: Callable[[str], bytes]) -> tuple[tuple[Portrait, ...], list[str]]:
    portraits: list[Portrait] = []
    errors: list[str] = []
    seen: set[tuple[str, tuple[float, float, float, float] | None]] = set()
    for media_ref in person.get("media_list") or []:
        handle = _ref(media_ref)
        media = media_by_handle.get(handle)
        if not handle or not media or not _portrait_candidate(media):
            continue
        crop = _rect(media_ref.get("rect") if isinstance(media_ref, dict) else None)
        key = (handle, crop)
        if key in seen:
            continue
        seen.add(key)
        try:
            portraits.append(Portrait(media_loader(handle), crop, str(media.get("desc") or media.get("title") or "Portrait")))
        except (GrampsApiError, OSError) as error:
            errors.append(f"{person.get('gramps_id', 'person')}: media indisponible ({type(error).__name__})")
    return tuple(portraits), errors


def collect_live_records(client: GrampsApiClient, config: dict[str, Any]) -> tuple[list[dict[str, Any]], tuple[str, ...]]:
    """Collect tagged people and public-safe fields from GrampsWeb."""
    tag_name = str(config["gramps"]["highlight_tag"])
    tags = _list_all(client, "tags")
    matching_tags = [tag for tag in tags if tag.get("name") == tag_name and tag.get("handle")]
    if len(matching_tags) != 1:
        raise GrampsApiError(f"expected exactly one gallery tag, found {len(matching_tags)}")
    tag_handle = str(matching_tags[0]["handle"])
    people_rows = _list_all(client, "people", extend="tag_list,media_list,family_list,parent_family_list")
    tagged_rows = [person for person in people_rows if tag_handle in (person.get("tag_list") or [])]
    if not tagged_rows:
        raise GrampsApiError("gallery tag contains no people")
    full_people = [client.get_json(f"/people/{person['handle']}", query={"extend": "all"}) for person in tagged_rows]
    all_families = _list_all(client, "families")
    event_rows = _list_all(client, "events")
    place_rows = _list_all(client, "places")
    events = {str(row.get("handle")): row for row in event_rows if row.get("handle")}
    places = {str(row.get("handle")): row for row in place_rows if row.get("handle")}
    media_by_handle: dict[str, dict[str, Any]] = {}
    for person in full_people:
        for media_ref in person.get("media_list") or []:
            handle = _ref(media_ref)
            if handle and handle not in media_by_handle:
                media_by_handle[handle] = client.get_json(f"/media/{handle}")
    media_cache: dict[str, bytes] = {}

    def load_media(handle: str) -> bytes:
        if handle not in media_cache:
            media_cache[handle] = client.download(f"/media/{handle}/file")
        return media_cache[handle]

    focal_gid = str(config["gramps"].get("center_person") or "I0095")
    focal = next((person for person in full_people if person.get("gramps_id") == focal_gid), None)
    if focal is None:
        focal = next((person for person in people_rows if person.get("gramps_id") == focal_gid), None)
    if focal is None:
        raise GrampsApiError(f"gallery focal person {focal_gid} was not found")
    resolver = RelationshipResolver(people_rows, all_families, str(focal.get("handle")))
    records: list[dict[str, Any]] = []
    errors: list[str] = []
    for person in full_people:
        first, call, surname = _person_name_parts(person)
        relation = resolver.resolve(str(person.get("handle")))
        portraits, portrait_errors = _person_portraits(person, media_by_handle, load_media)
        errors.extend(portrait_errors)
        private = bool(person.get("private"))
        records.append({
            "gramps_id": str(person.get("gramps_id") or ""),
            "handle": str(person.get("handle") or ""),
            "first_name": first,
            "call_name": call,
            "surname": surname,
            "gender": person.get("gender"),
            "private": private,
            "relation": relation.label,
            "relation_rank": relation.rank,
            "birth": _best_event(person, "Birth", events, places),
            "death": _best_event(person, "Death", events, places),
            "occupations": list(_occupations(person, events)),
            "portraits": [{"data": portrait.data, "rect": portrait.rect, "description": portrait.description} for portrait in portraits],
        })
    return records, tuple(errors)


def _latex_escape(value: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$",
        "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}",
        "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(char, char) for char in value)


def _given_name_markup(first_name: str, call_name: str) -> str:
    if not call_name:
        return _latex_escape(first_name)
    parts = re.split(r"([\s-]+)", first_name)
    result: list[str] = []
    for part in parts:
        if part == call_name:
            result.append(r"\underline{" + _latex_escape(part) + "}")
        else:
            result.append(_latex_escape(part))
    return "".join(result)


def _name_markup(record: GalleryRecord) -> str:
    given = _given_name_markup(record.first_name, record.call_name)
    surname = _latex_escape(record.surname.upper())
    return " ".join(part for part in (given, surname) if part) or "Personne sans nom"


def _fact_markup(label: str, fact: tuple[str, str] | None) -> str:
    if not fact:
        return rf"\textbf{{{label}}} : non renseignée"
    date, place = fact
    return rf"\textbf{{{label}}} : {_latex_escape(date)} — {_latex_escape(place)}"


def _portrait_bytes(raw: bytes, rect: tuple[float, float, float, float] | None) -> bytes:
    with Image.open(io.BytesIO(raw)) as opened:
        image = ImageOps.exif_transpose(opened)
        if image.mode in ("RGBA", "LA") or "transparency" in image.info:
            background = Image.new("RGB", image.size, "white")
            alpha = image.convert("RGBA")
            background.paste(alpha, mask=alpha.getchannel("A"))
            image = background
        else:
            image = image.convert("RGB")
        if rect:
            width, height = image.size
            x1, y1, x2, y2 = rect
            pad_x = max(2.0, (x2 - x1) * 0.10)
            pad_y = max(2.0, (y2 - y1) * 0.10)
            left = max(0, int(width * (x1 - pad_x) / 100.0))
            top = max(0, int(height * (y1 - pad_y) / 100.0))
            right = min(width, int(width * (x2 + pad_x) / 100.0))
            bottom = min(height, int(height * (y2 + pad_y) / 100.0))
            if right > left and bottom > top:
                image = image.crop((left, top, right, bottom))
        image.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
        output = io.BytesIO()
        image.save(output, format="JPEG", quality=92, optimize=True, progressive=True)
        return output.getvalue()


def _as_portrait(value: Any) -> Portrait:
    if not isinstance(value, dict):
        raise ValueError("portrait must be an object")
    raw = value.get("data") or value.get("data_base64")
    if isinstance(raw, str):
        if raw.startswith("data:"):
            raw = raw.split(",", 1)[1]
        raw = base64.b64decode(raw)
    if not isinstance(raw, (bytes, bytearray)):
        raise ValueError("portrait has no binary data")
    return Portrait(bytes(raw), _rect(value.get("rect")), str(value.get("description") or "Portrait"))


def _record(value: dict[str, Any]) -> GalleryRecord:
    birth = value.get("birth")
    death = value.get("death")
    return GalleryRecord(
        gramps_id=str(value.get("gramps_id") or ""),
        handle=str(value.get("handle") or ""),
        first_name=str(value.get("first_name") or ""),
        call_name=str(value.get("call_name") or value.get("call") or ""),
        surname=str(value.get("surname") or ""),
        gender=int(value["gender"]) if value.get("gender") in (0, 1, "0", "1") else None,
        private=bool(value.get("private", False)),
        relation=str(value.get("relation") or "relation non résolue dans la structure Gramps"),
        relation_rank=int(value.get("relation_rank", 99)),
        birth=tuple(birth) if isinstance(birth, (list, tuple)) and len(birth) == 2 else birth if isinstance(birth, tuple) else None,
        death=tuple(death) if isinstance(death, (list, tuple)) and len(death) == 2 else death if isinstance(death, tuple) else None,
        occupations=tuple(str(item) for item in (value.get("occupations") or []) if str(item).strip()),
        portraits=tuple(_as_portrait(item) for item in (value.get("portraits") or [])),
    )


def _write_portrait(portrait: Portrait, directory: Path) -> Path:
    normalized = _portrait_bytes(portrait.data, portrait.rect)
    digest = hashlib.sha256(normalized).hexdigest()[:20]
    path = directory / f"portrait-{digest}.jpg"
    if not path.exists():
        path.write_bytes(normalized)
    return path


def _image_block(paths: list[str], *, columns: int, height: str) -> str:
    cells: list[str] = []
    for path in paths:
        cells.append(
            "\\begin{minipage}[t]{%.3f\\linewidth}\\centering\\includegraphics[width=\\linewidth,height=%s,keepaspectratio]{%s}\\end{minipage}"
            % (0.95 / columns, height, _latex_escape(path)))
    rows: list[str] = []
    for index in range(0, len(cells), columns):
        rows.append("\\hfill".join(cells[index:index + columns]))
    return "\\par\\medskip\n".join(rows)


def _info_block(record: GalleryRecord) -> str:
    lines = [
        _fact_markup("Naissance", record.birth),
        _fact_markup("Décès", record.death),
    ]
    if record.occupations:
        lines.append(r"\textbf{Profession} :\begin{itemize}\setlength{\itemsep}{0pt}\setlength{\parskip}{0pt}")
        lines.extend(r"\item " + _latex_escape(item) for item in record.occupations)
        lines.append(r"\end{itemize}")
    else:
        lines.append(r"\textbf{Profession} : non renseignée")
    return "\\par\n".join(lines)


def _person_page(record: GalleryRecord, paths: list[str], *, first_page: bool) -> str:
    if record.private:
        title = r"\textit{Personne privée}"
        relation = r"\textbf{Relation avec Benoît Coste} : non publiée"
        content = r"\textit{Les informations de cette personne ne sont pas publiées.}"
    else:
        title = _name_markup(record)
        relation = r"\textbf{Relation avec Benoît Coste} : " + _latex_escape(record.relation)
        content = _info_block(record)
    heading = r"{\Large\bfseries Galerie de portraits}\par\medskip" if first_page else ""
    body: list[str] = [
        r"\clearpage",
        r"\thispagestyle{plain}",
        r"\begingroup",
        r"\newgeometry{top=1.25cm,bottom=1.25cm,left=1.35cm,right=1.35cm}",
        r"\raggedbottom",
        heading,
        r"{\LARGE\bfseries " + title + r"}\par",
        r"\medskip",
        relation + r"\par",
        r"\medskip",
    ]
    if paths and len(paths) == 1 and not record.private:
        body.extend([
            r"\noindent\begin{minipage}[t]{0.52\textwidth}",
            content,
            r"\end{minipage}\hfill",
            r"\begin{minipage}[t]{0.43\textwidth}\centering",
            r"\includegraphics[width=\linewidth,height=0.62\textheight,keepaspectratio]{" + _latex_escape(paths[0]) + r"}",
            r"\end{minipage}",
        ])
    elif paths and not record.private:
        body.extend([
            content,
            r"\par\medskip",
            _image_block(paths, columns=2 if len(paths) <= 4 else 3, height="0.29\\textheight" if len(paths) <= 4 else "0.19\\textheight"),
        ])
    else:
        body.append(content)
    body.extend([r"\restoregeometry", r"\endgroup", ""])
    return "\n".join(body)


def build_portrait_gallery(records: Iterable[dict[str, Any]], output_dir: Path, *, portrait_errors: Iterable[str] = ()) -> GalleryBuild:
    """Write the gallery TeX and cleaned portrait files into ``output_dir``."""
    gallery_dir = output_dir / "galerie"
    portrait_dir = gallery_dir / "portraits"
    portrait_dir.mkdir(parents=True, exist_ok=True)
    typed = [_record(record) for record in records]
    typed.sort(key=lambda record: (record.relation_rank, record.surname.casefold(), record.first_name.casefold(), record.gramps_id))
    paths_by_person: list[list[Path]] = []
    all_paths: dict[str, Path] = {}
    for record in typed:
        person_paths: list[Path] = []
        if not record.private:
            for portrait in record.portraits:
                path = _write_portrait(portrait, portrait_dir)
                all_paths[str(path)] = path
                if path not in person_paths:
                    person_paths.append(path)
        paths_by_person.append(person_paths)
    tex_path = gallery_dir / "galerie.tex"
    fragments = [
        "% Generated by scripts/build_portrait_gallery.py; do not edit by hand.",
        "% One page is emitted for each tagged person.",
    ]
    for index, (record, paths) in enumerate(zip(typed, paths_by_person)):
        display_paths = [
            "genealogie/assets/" + path.relative_to(output_dir).as_posix()
            for path in paths
        ]
        fragments.append(_person_page(record, display_paths, first_page=index == 0))
    tex_path.write_text("\n".join(fragments), encoding="utf-8")
    return GalleryBuild(
        tex_path=tex_path,
        portrait_paths=tuple(sorted(all_paths.values())),
        people=len(typed),
        pages=len(typed),
        people_with_portraits=sum(bool(paths) for paths in paths_by_person),
        portrait_count=sum(len(paths) for paths in paths_by_person),
        private_people=sum(record.private for record in typed),
        portrait_errors=tuple(portrait_errors),
    )


def fixture_records(fixture: dict[str, Any]) -> list[dict[str, Any]]:
    gallery = fixture.get("gallery")
    if not isinstance(gallery, list) or not gallery:
        raise ValueError("fixture has no gallery records")
    return [row for row in gallery if isinstance(row, dict)]


__all__ = [
    "GalleryBuild",
    "GalleryRecord",
    "Portrait",
    "build_portrait_gallery",
    "collect_live_records",
    "fixture_records",
]
