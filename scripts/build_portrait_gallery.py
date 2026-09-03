"""Build a public-safe, one-page-per-person portrait gallery.

The live collector reads GrampsWeb and downloads only portrait-like image
media.  The renderer writes sanitized JPEGs and a generated LaTeX fragment;
there is no hand-maintained person list.  Fixture mode keeps CI network-free.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass, replace
import hashlib
import io
import json
from pathlib import Path
import re
from typing import Any, Callable, Iterable
import unicodedata

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
UNKNOWN_RELATION = "relation non résolue dans la structure Gramps"


@dataclass(frozen=True)
class Portrait:
    data: bytes
    rect: tuple[float, float, float, float] | None
    description: str
    media_key: str = ""
    artwork_name: str = ""
    artwork_date: str = ""
    artist: str = ""
    source: str = ""
    source_url: str = ""


@dataclass(frozen=True)
class GalleryCitation:
    source_title: str
    locator: str
    text: str = ""
    page_number: int | None = None


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
    citations: tuple[GalleryCitation, ...] = ()


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
    return date or "date non renseignée", place


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


def _attribute_key(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", text.casefold().replace("’", "'")).strip()


def _media_attributes(media: dict[str, Any]) -> dict[str, list[str]]:
    values: dict[str, list[str]] = {}
    for item in media.get("attribute_list") or []:
        if not isinstance(item, dict):
            continue
        key = _attribute_key(item.get("type"))
        value = str(item.get("value") or "").strip()
        if key and value:
            values.setdefault(key, []).append(value)
    return values


def _first_attribute(attributes: dict[str, list[str]], *keys: str) -> str:
    for key in keys:
        values = attributes.get(_attribute_key(key)) or []
        if values:
            return values[0]
    return ""


def _media_metadata(media: dict[str, Any]) -> tuple[str, str, str, str, str]:
    """Project media metadata into artwork name/date/artist/source fields."""
    description = str(media.get("desc") or media.get("title") or "").strip()
    quoted = re.search(r"[\"“]([^\"”]+)[\"”]", description)
    artwork_name = (quoted.group(1).strip() if quoted else description) or "Portrait"
    attributes = _media_attributes(media)
    artwork_date = _first_attribute(
        attributes,
        "Date",
        "Date de l'œuvre",
        "Date de création",
        "Année",
        "Year",
    )
    if not artwork_date and isinstance(media.get("date"), dict):
        artwork_date = _date_label(media.get("date"))
    artist = _first_attribute(attributes, "Artiste", "Artist", "Auteur", "Peintre")
    source_reference = _first_attribute(attributes, "Référence ouvrage", "Référence", "Reference")
    source_value = _first_attribute(attributes, "Source")
    source_url = source_value if source_value.lower().startswith(("http://", "https://")) else ""
    if not source_url:
        source_url = _first_attribute(attributes, "URL")
    source = source_reference or source_value or source_url
    return artwork_name, artwork_date, artist, source, source_url


def _rect(value: Any) -> tuple[float, float, float, float] | None:
    if not isinstance(value, (list, tuple)) or len(value) < 4:
        return None
    try:
        values = tuple(float(x) for x in value[:4])
    except (TypeError, ValueError):
        return None
    if values[2] <= values[0] or values[3] <= values[1]:
        return None
    if values[0] <= 0 and values[1] <= 0 and values[2] >= 100 and values[3] >= 100:
        return None
    return values  # type: ignore[return-value]


def _media_identity(media: dict[str, Any], handle: str) -> str:
    for field in ("checksum", "path"):
        value = str(media.get(field) or "").strip()
        if value:
            return f"{field}:{value}"
    return f"handle:{handle}"


def _person_portraits(person: dict[str, Any], media_by_handle: dict[str, dict[str, Any]], media_loader: Callable[[str], bytes]) -> tuple[tuple[Portrait, ...], list[str]]:
    candidates: list[tuple[str, dict[str, Any], tuple[float, float, float, float] | None, str]] = []
    seen: set[tuple[str, tuple[float, float, float, float] | None]] = set()
    for media_ref in person.get("media_list") or []:
        handle = _ref(media_ref)
        media = media_by_handle.get(handle)
        if not handle or not media or not _portrait_candidate(media):
            continue
        crop = _rect(media_ref.get("rect") if isinstance(media_ref, dict) else None)
        identity = _media_identity(media, handle)
        key = (identity, crop)
        if key in seen:
            continue
        seen.add(key)
        candidates.append((handle, media, crop, identity))

    # If Gramps exposes the same image once in full and once with a face rect,
    # the complete reference wins for this person.  This also handles duplicate
    # media objects carrying the same checksum/path.
    complete_identities = {identity for _handle_value, _media, crop, identity in candidates if crop is None}
    portraits: list[Portrait] = []
    errors: list[str] = []
    for handle, media, crop, identity in candidates:
        if crop is not None and identity in complete_identities:
            continue
        try:
            artwork_name, artwork_date, artist, source, source_url = _media_metadata(media)
            portraits.append(
                Portrait(
                    media_loader(handle),
                    crop,
                    str(media.get("desc") or media.get("title") or "Portrait"),
                    identity,
                    artwork_name,
                    artwork_date,
                    artist,
                    source,
                    source_url,
                )
            )
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
    source_rows = _list_all(client, "sources")
    citation_rows = _list_all(client, "citations")
    events = {str(row.get("handle")): row for row in event_rows if row.get("handle")}
    places = {str(row.get("handle")): row for row in place_rows if row.get("handle")}
    families = {str(row.get("handle")): row for row in all_families if row.get("handle")}
    citations = {str(row.get("handle")): row for row in citation_rows if row.get("handle")}
    source_gid = str(config["gramps"].get("source_gramps_id") or "")
    source_matches = [row for row in source_rows if str(row.get("gramps_id") or "") == source_gid]
    if source_gid and len(source_matches) != 1:
        raise GrampsApiError(f"expected exactly one gallery source {source_gid}, found {len(source_matches)}")
    source_handle = str(source_matches[0].get("handle") or "") if source_matches else ""
    source_title = str(source_matches[0].get("title") or "") if source_matches else ""
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
            "portraits": [
                {
                    "data": portrait.data,
                    "rect": portrait.rect,
                    "description": portrait.description,
                    "media_key": portrait.media_key,
                    "artwork_name": portrait.artwork_name,
                    "artwork_date": portrait.artwork_date,
                    "artist": portrait.artist,
                    "source": portrait.source,
                    "source_url": portrait.source_url,
                }
                for portrait in portraits
            ],
            "citations": [
                {
                    "source_title": citation.source_title,
                    "locator": citation.locator,
                    "text": citation.text,
                    "page_number": citation.page_number,
                }
                for citation in _person_citations(person, events, families, citations, source_handle, source_title)
            ],
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
        value = "Non renseignée"
    else:
        date, place = fact
        value = f"{date} — {place}" if place else date
    return rf"\galleryfact{{{_latex_escape(label)}}}{{{_latex_escape(value)}}}"


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
    description = str(value.get("description") or "Portrait")
    return Portrait(
        bytes(raw),
        _rect(value.get("rect")),
        description,
        str(value.get("media_key") or ""),
        str(value.get("artwork_name") or value.get("name") or description),
        str(value.get("artwork_date") or value.get("date") or ""),
        str(value.get("artist") or ""),
        str(value.get("source") or ""),
        str(value.get("source_url") or ""),
    )


def _citation_details(value: Any) -> tuple[str, str, int | None]:
    """Extract a normalized locator, page number, and quoted citation text."""
    raw = " ".join(str(value or "").split())
    if not raw:
        return "Localisation non renseignée", "", None
    page = re.search(r"\b[Pp]age\s+(\d+)", raw)
    if not page:
        page = re.search(r"\bp\.?\s*(\d+)", raw)
    if not page:
        return (raw if len(raw) <= 140 else raw[:137].rstrip() + "…"), "", None
    page_number = int(page.group(1))
    prefix = raw[:page.start()].strip(" —–-")
    citation_text = raw[page.end():].lstrip(" —–-").strip()
    chapter = re.search(r"\bChapitre\s+(?:Chapitre\s+)?(\d+)", prefix, re.IGNORECASE)
    if chapter:
        locator = f"Chapitre {chapter.group(1)} — p. {page_number}"
    else:
        locator = f"p. {page_number}"
    return locator, citation_text, page_number


def _citation_locator(value: Any) -> str:
    return _citation_details(value)[0]


def _as_citation(value: Any) -> GalleryCitation:
    if isinstance(value, dict):
        source_title = str(value.get("source_title") or value.get("source") or "").strip()
        raw_value = value.get("page") or value.get("locator")
        parsed_locator, parsed_text, page_number = _citation_details(raw_value)
        locator = str(value.get("locator") or "").strip() or parsed_locator
        citation_text = str(value.get("text") or value.get("citation_text") or "").strip() or parsed_text
        supplied_page_number = value.get("page_number")
        if isinstance(supplied_page_number, int) and supplied_page_number >= 0:
            page_number = supplied_page_number
    else:
        source_title = ""
        locator, citation_text, page_number = _citation_details(value)
    return GalleryCitation(source_title, locator, citation_text, page_number)


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
        citations=tuple(_as_citation(item) for item in (value.get("citations") or [])),
    )


def _citation_handles_for_person(
    person: dict[str, Any],
    events: dict[str, dict[str, Any]],
    families: dict[str, dict[str, Any]],
) -> list[str]:
    handles: list[str] = []
    seen: set[str] = set()

    def add(values: Any) -> None:
        for value in values or []:
            handle = _ref(value)
            if handle and handle not in seen:
                seen.add(handle)
                handles.append(handle)

    add(person.get("citation_list"))
    for event_ref in person.get("event_ref_list") or []:
        event = events.get(_ref(event_ref))
        if event:
            add(event.get("citation_list"))
    for family_ref in (person.get("family_list") or []) + (person.get("parent_family_list") or []):
        family = families.get(_ref(family_ref))
        if family:
            add(family.get("citation_list"))
    return handles


def _person_citations(
    person: dict[str, Any],
    events: dict[str, dict[str, Any]],
    families: dict[str, dict[str, Any]],
    citations: dict[str, dict[str, Any]],
    source_handle: str,
    source_title: str,
) -> tuple[GalleryCitation, ...]:
    result: list[GalleryCitation] = []
    seen: set[tuple[str, str, str]] = set()
    for handle in _citation_handles_for_person(person, events, families):
        citation = citations.get(handle)
        if not citation or _ref(citation.get("source_handle")) != source_handle:
            continue
        item = _as_citation({"source_title": source_title, "page": citation.get("page")})
        key = (item.source_title, item.locator, item.text)
        if key not in seen:
            seen.add(key)
            result.append(item)
    result.sort(key=lambda item: (item.page_number is None, item.page_number if item.page_number is not None else 0))
    return tuple(result)


def _write_portrait(portrait: Portrait, directory: Path) -> Path:
    normalized = _portrait_bytes(portrait.data, portrait.rect)
    digest = hashlib.sha256(normalized).hexdigest()[:20]
    path = directory / f"portrait-{digest}.jpg"
    if not path.exists():
        path.write_bytes(normalized)
    return path


def _portrait_identity(portrait: Portrait) -> str:
    return portrait.media_key or hashlib.sha256(portrait.data).hexdigest()


def _deduplicate_portraits(portraits: Iterable[Portrait]) -> tuple[Portrait, ...]:
    values = list(portraits)
    complete = {_portrait_identity(portrait) for portrait in values if portrait.rect is None}
    result: list[Portrait] = []
    seen: set[tuple[str, tuple[float, float, float, float] | None]] = set()
    for portrait in values:
        identity = _portrait_identity(portrait)
        if portrait.rect is not None and identity in complete:
            continue
        key = (identity, portrait.rect)
        if key in seen:
            continue
        seen.add(key)
        result.append(portrait)
    return tuple(result)


def _portrait_initials(record: GalleryRecord) -> str:
    given = record.call_name or record.first_name
    given_letter = next((char for char in given if char.isalpha()), "")
    surname_letter = next((char for char in record.surname if char.isalpha()), "")
    return (given_letter + surname_letter).upper() or "?"


def _display_relation(record: GalleryRecord) -> str:
    """Capitalize the relation and omit the current person's repeated name."""
    relation = record.relation.strip()
    if not relation:
        return relation
    given = record.call_name.strip()
    if not given and record.first_name:
        given = record.first_name.split()[0]
    suffixes: list[str] = []
    if given and record.surname.strip():
        suffixes.append(f"{given} {record.surname.strip()}")
    if given:
        suffixes.append(given)
    for suffix in sorted(set(suffixes), key=len, reverse=True):
        relation = re.sub(r"\s+" + re.escape(suffix) + r"$", "", relation, flags=re.IGNORECASE).rstrip()
        if relation != record.relation.strip():
            break
    return relation[:1].upper() + relation[1:]


def _framed_image(path: str, height: str, *, width: str = r"0.88\linewidth") -> str:
    return (
        r"\setlength{\fboxsep}{4pt}\setlength{\fboxrule}{0.8pt}"
        r"\fcolorbox{GalleryTerracotta}{white}{"
        r"\includegraphics[width=" + width + r",height=" + height
        + r",keepaspectratio]{" + _latex_escape(path) + r"}}"
    )


def _portrait_caption(portrait: Portrait) -> str:
    name = portrait.artwork_name or portrait.description or "Portrait"
    date = (portrait.artwork_date or "").strip()
    artist = (portrait.artist or "").strip()
    unknown_values = {"non renseigné", "non renseignée"}
    if date.casefold() in unknown_values:
        date = ""
    if artist.casefold() in unknown_values:
        artist = ""
    source = portrait.source or "Non renseignée"
    if portrait.source_url and source != portrait.source_url:
        source_markup = r"\href{" + _latex_escape(portrait.source_url) + r"}{" + _latex_escape(source) + r"}"
    elif source.lower().startswith(("http://", "https://")):
        source_markup = r"\href{" + _latex_escape(source) + r"}{Source en ligne}"
    else:
        source_markup = _latex_escape(source)
    lines = [
        r"\par\vspace{0.10cm}",
        r"\galleryworktitle{" + _latex_escape(name) + r"}",
    ]
    if date:
        lines.append(r"\galleryworkline{Date}{" + _latex_escape(date) + r"}")
    if artist:
        lines.append(r"\galleryworkline{Artiste}{" + _latex_escape(artist) + r"}")
    lines.append(r"\galleryworkline{Source}{" + source_markup + r"}")
    return "\n".join(lines)


def _info_card(content: str) -> str:
    return (
        r"\noindent\setlength{\fboxsep}{8pt}"
        r"\colorbox{GalleryCream}{"
        r"\parbox[t]{\dimexpr\linewidth-2\fboxsep\relax}{" + content + r"}}"
    )


def _portrait_placeholder(record: GalleryRecord) -> str:
    initials = "—" if record.private else _latex_escape(_portrait_initials(record))
    label = "Portrait non publié" if record.private else "Portrait non disponible"
    return "\n".join([
        r"\begin{minipage}[t]{0.43\textwidth}\centering",
        r"\setlength{\fboxsep}{0pt}\setlength{\fboxrule}{0.8pt}",
        r"\fcolorbox{GallerySand}{GalleryCream}{",
        r"\parbox[c][0.50\textheight][c]{0.90\linewidth}{\centering",
        r"{\fontsize{48}{54}\selectfont\bfseries\color{GalleryBordeaux} " + initials + r"}\par\medskip",
        r"{\small\color{GalleryMuted}" + _latex_escape(label) + r"}\par}}",
        r"\end{minipage}",
    ])


def _image_block(items: list[tuple[str, Portrait]], *, columns: int, height: str) -> str:
    cells: list[str] = []
    for path, portrait in items:
        cells.append(
            "\\begin{minipage}[t]{%.3f\\linewidth}\\centering\n%s\n%s\n\\end{minipage}"
            % (0.95 / columns, _framed_image(path, height), _portrait_caption(portrait))
        )
    rows: list[str] = []
    for index in range(0, len(cells), columns):
        rows.append("\\hfill".join(cells[index:index + columns]))
    return "\\par\\medskip\n".join(rows)


def _info_block(record: GalleryRecord, *, include_occupation: bool = True) -> str:
    lines = [
        _fact_markup("Naissance", record.birth),
        _fact_markup("Décès", record.death),
    ]
    if include_occupation and record.occupations:
        size = r"\footnotesize" if len(record.occupations) > 4 else r"\small"
        lines.extend([
            r"\gallerysection{Profession}",
            size + r"\begin{itemize}\setlength{\itemsep}{0pt}\setlength{\topsep}{2pt}\setlength{\parsep}{0pt}\setlength{\parskip}{0pt}",
        ])
        lines.extend(r"\item " + _latex_escape(item) for item in record.occupations)
        lines.append(r"\end{itemize}")
    elif include_occupation:
        lines.append(r"\galleryfact{Profession}{Non renseignée}")
    return "\n".join(lines)


def _citation_markup(citation: GalleryCitation) -> str:
    value = _latex_escape(citation.locator)
    if citation.text:
        value += r" — \textit{« " + _latex_escape(citation.text) + r" »}"
    return value


def _citation_block(record: GalleryRecord, *, compact: bool = False) -> str:
    lines = [
        r"\noindent\setlength{\fboxsep}{6pt}\colorbox{GalleryCream}{",
        r"\parbox[t]{\dimexpr\linewidth-2\fboxsep-0.4cm\relax}{",
        r"\gallerysection{Citations dans l'ouvrage}",
    ]
    source_titles = tuple(dict.fromkeys(citation.source_title for citation in record.citations if citation.source_title))
    if source_titles and not compact:
        lines.append(r"{\scriptsize\itshape\color{GalleryMuted} " + _latex_escape(" ; ".join(source_titles)) + r"}\par\vspace{0.10cm}")
    if record.citations:
        if len(record.citations) <= 12:
            lines.extend([
                r"{\footnotesize\begin{itemize}\setlength{\itemsep}{0pt}\setlength{\topsep}{1pt}\setlength{\parsep}{0pt}\setlength{\parskip}{0pt}",
            ])
            lines.extend(r"\item " + _citation_markup(citation) for citation in record.citations)
            lines.append(r"\end{itemize}}")
        else:
            column_count = 3 if compact and len(record.citations) > 20 else 2
            midpoint = (len(record.citations) + column_count - 1) // column_count
            columns = tuple(
                record.citations[index:index + midpoint]
                for index in range(0, len(record.citations), midpoint)
            )
            width = 0.97 / len(columns)
            for index, column in enumerate(columns):
                if index:
                    lines.append(r"\hfill")
                lines.append(r"\begin{minipage}[t]{%.3f\linewidth}" % width)
                lines.append(r"\scriptsize\begin{itemize}\setlength{\itemsep}{0pt}\setlength{\topsep}{0pt}\setlength{\parsep}{0pt}\setlength{\parskip}{0pt}")
                lines.extend(r"\item " + _citation_markup(citation) for citation in column)
                lines.append(r"\end{itemize}\end{minipage}")
    else:
        lines.append(r"{\footnotesize\itshape\color{GalleryMuted} Aucune citation directement rattachée dans l'ouvrage.}")
    lines.extend([r"}", r"}"])
    return "\n".join(lines)


def _person_page(
    record: GalleryRecord,
    items: list[tuple[str, Portrait]],
    *,
    first_page: bool,
    hide_profession: bool = False,
    hide_citations: bool = False,
) -> str:
    if record.private:
        title = r"\textit{Personne privée}"
        relation = "Non publiée"
        content = r"\textit{Les informations de cette personne ne sont pas publiées.}"
    else:
        title = _name_markup(record)
        relation = _latex_escape(_display_relation(record))
        content = _info_block(record, include_occupation=not hide_profession)
    toc_marker = r"\phantomsection\addcontentsline{toc}{section}{Galerie de portraits}" if first_page else ""
    body: list[str] = [
        r"\clearpage",
        r"\thispagestyle{plain}",
        r"\begingroup",
        r"\newgeometry{top=1.15cm,bottom=1.25cm,left=1.30cm,right=1.30cm}",
        r"\raggedbottom",
        toc_marker,
        r"\gallerypageheader",
        r"{\LARGE\bfseries\color{GalleryInk} " + title + r"}\par",
        r"\vspace{0.12cm}",
        r"\noindent\textcolor{GallerySand}{\rule{\textwidth}{1.1pt}}\par",
        r"\vspace{0.15cm}",
        r"{\footnotesize\bfseries\color{GalleryMuted}\MakeUppercase{Relation avec Benoît Coste}}\par",
        r"{\large\color{GalleryBordeaux} " + relation + r"}\par",
        r"\vspace{0.45cm}",
    ]
    citations_in_portrait_column = bool(
        items
        and len(items) == 1
        and len(record.citations) > 12
        and not record.private
        and not hide_citations
    )
    if items and len(items) == 1 and not record.private:
        portrait_column = [
            _framed_image(items[0][0], r"0.40\textheight", width=r"0.72\linewidth" if citations_in_portrait_column else r"0.88\linewidth"),
            _portrait_caption(items[0][1]),
        ]
        if citations_in_portrait_column:
            portrait_column.extend([r"\par\vspace{0.15cm}", _citation_block(record, compact=True)])
        body.extend([
            r"\noindent\begin{minipage}[t]{0.52\textwidth}",
            _info_card(content),
            r"\end{minipage}\hfill",
            r"\begin{minipage}[t]{0.43\textwidth}\centering",
            *portrait_column,
            r"\end{minipage}",
        ])
    elif items and not record.private:
        body.extend([
            _info_card(content),
            r"\par\vspace{0.40cm}",
            _image_block(items, columns=2 if len(items) <= 4 else 3, height="0.19\\textheight" if len(items) <= 4 else "0.13\\textheight"),
        ])
    else:
        body.extend([
            r"\noindent\begin{minipage}[t]{0.52\textwidth}",
            _info_card(content),
            r"\end{minipage}\hfill",
            _portrait_placeholder(record),
        ])
    if not hide_citations and not citations_in_portrait_column:
        body.extend([
            r"\par\vspace{0.30cm}",
            _citation_block(record),
        ])
    body.extend([
        r"\vfill",
        r"\noindent\textcolor{GallerySand}{\rule{\textwidth}{0.6pt}}\par",
        r"{\scriptsize\color{GalleryMuted}Personnage cité dans les Mémoires de Benoît Coste}\par",
        r"\restoregeometry",
        r"\endgroup",
        "",
    ])
    return "\n".join(body)


def build_portrait_gallery(
    records: Iterable[dict[str, Any]],
    output_dir: Path,
    *,
    portrait_errors: Iterable[str] = (),
    central_person_id: str | None = None,
) -> GalleryBuild:
    """Write the gallery TeX and cleaned portrait files into ``output_dir``.

    ``central_person_id`` identifies the publication's focal person.  The
    central record keeps its identity, life dates, relation, and portraits,
    while its profession and in-book citation sections remain hidden in the
    reader-facing gallery.
    """
    gallery_dir = output_dir / "galerie"
    portrait_dir = gallery_dir / "portraits"
    portrait_dir.mkdir(parents=True, exist_ok=True)
    typed = [
        replace(record, portraits=_deduplicate_portraits(record.portraits))
        for record in (_record(value) for value in records)
        if record.relation != UNKNOWN_RELATION or record.portraits
    ]
    typed.sort(key=lambda record: (record.relation_rank, record.surname.casefold(), record.first_name.casefold(), record.gramps_id))
    portrait_items_by_person: list[list[tuple[Path, Portrait]]] = []
    all_paths: dict[str, Path] = {}
    for record in typed:
        person_items: list[tuple[Path, Portrait]] = []
        if not record.private:
            for portrait in record.portraits:
                path = _write_portrait(portrait, portrait_dir)
                all_paths[str(path)] = path
                if not any(existing_path == path for existing_path, _existing_portrait in person_items):
                    person_items.append((path, portrait))
        portrait_items_by_person.append(person_items)
    tex_path = gallery_dir / "galerie.tex"
    fragments = [
        "% Generated by scripts/build_portrait_gallery.py; do not edit by hand.",
        "% One page is emitted for each tagged person.",
        r"\begingroup",
        r"\definecolor{GalleryBordeaux}{HTML}{7C2F3A}",
        r"\definecolor{GalleryTerracotta}{HTML}{B55A52}",
        r"\definecolor{GalleryCream}{HTML}{F7F1ED}",
        r"\definecolor{GallerySand}{HTML}{DEC9C3}",
        r"\definecolor{GalleryInk}{HTML}{242321}",
        r"\definecolor{GalleryMuted}{HTML}{68655F}",
        r"\newcommand{\gallerypageheader}{%",
        r"  \begingroup\setlength{\fboxsep}{6pt}%",
        r"  \noindent\colorbox{GalleryBordeaux}{\parbox{\dimexpr\textwidth-2\fboxsep\relax}{%",
        r"    {\small\bfseries\color{white}\MakeUppercase{Galerie de portraits}}%",
        r"    \hfill{\footnotesize\color{white}Mémoires de Benoît Coste}}}\par%",
        r"  \endgroup\vspace{0.42cm}%",
        r"}",
        r"\newcommand{\galleryfact}[2]{%",
        r"  {\footnotesize\bfseries\color{GalleryBordeaux}\MakeUppercase{#1}}\par%",
        r"  {\small\color{GalleryInk}#2}\par\vspace{0.45em}%",
        r"}",
        r"\newcommand{\gallerysection}[1]{%",
        r"  {\footnotesize\bfseries\color{GalleryBordeaux}\MakeUppercase{#1}}\par%",
        r"}",
        r"\newcommand{\galleryworkline}[2]{%",
        r"  {\scriptsize\bfseries\color{GalleryBordeaux}#1 : }%",
        r"  {\scriptsize\color{GalleryInk}#2}\par%",
        r"}",
        r"\newcommand{\galleryworktitle}[1]{%",
        r"  {\scriptsize\bfseries\color{GalleryInk}#1}\par%",
        r"}",
    ]
    for index, (record, portrait_items) in enumerate(zip(typed, portrait_items_by_person)):
        display_items = [
            ("genealogie/assets/" + path.relative_to(output_dir).as_posix(), portrait)
            for path, portrait in portrait_items
        ]
        hide_central_details = bool(central_person_id and record.gramps_id == central_person_id)
        fragments.append(
            _person_page(
                record,
                display_items,
                first_page=index == 0,
                hide_profession=hide_central_details,
                hide_citations=hide_central_details,
            )
        )
    fragments.append(r"\endgroup")
    tex_path.write_text("\n".join(fragments), encoding="utf-8")
    return GalleryBuild(
        tex_path=tex_path,
        portrait_paths=tuple(sorted(all_paths.values())),
        people=len(typed),
        pages=len(typed),
        people_with_portraits=sum(bool(items) for items in portrait_items_by_person),
        portrait_count=sum(len(items) for items in portrait_items_by_person),
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
