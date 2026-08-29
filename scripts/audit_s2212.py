"""Read-only audit of people cited by source S2212.

The complete API responses stay in memory only. The optional JSON report is
written outside the repository and contains handles solely for a private
follow-up operation; it is never a publication input.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
from gramps_api import GrampsApiError, GrampsApiClient, client_from_external_env  # noqa: E402

REPO_ROOT = SCRIPT_DIR.parent


def _handle(value: Any) -> str | None:
    if isinstance(value, dict):
        value = value.get("ref") or value.get("handle")
    return str(value) if value else None


def _refs(values: Any) -> set[str]:
    if not isinstance(values, list):
        return set()
    result: set[str] = set()
    for value in values:
        found = _handle(value)
        if found:
            result.add(found)
    return result


def _nested_citation_refs(row: dict[str, Any]) -> set[str]:
    result = _refs(row.get("citation_list"))
    for event_ref in row.get("event_ref_list") or []:
        if isinstance(event_ref, dict):
            result.update(_refs(event_ref.get("citation_list")))
    return result


def _person_name(person: dict[str, Any]) -> str:
    primary = person.get("primary_name") or {}
    first = str(primary.get("call") or primary.get("first_name") or "").strip()
    surname_list = primary.get("surname_list") or []
    surname = ""
    if surname_list and isinstance(surname_list[0], dict):
        surname = str(surname_list[0].get("surname") or "").strip()
    return " ".join(part for part in (first, surname) if part) or "Personne sans nom"


def _family_members(family: dict[str, Any]) -> set[str]:
    result: set[str] = set()
    for key in ("father_handle", "mother_handle", "father", "mother"):
        found = _handle(family.get(key))
        if found:
            result.add(found)
    for child in family.get("child_ref_list") or family.get("children") or []:
        found = _handle(child)
        if found:
            result.add(found)
    return result


def _family_partners(family: dict[str, Any]) -> set[str]:
    """Return the two partners identified by a family-level citation."""
    result: set[str] = set()
    for key in ("father_handle", "mother_handle", "father", "mother"):
        found = _handle(family.get(key))
        if found:
            result.add(found)
    return result


def _resolve_people_by_citation(
    owners: dict[str, list[dict[str, str]]],
    people_by_handle: dict[str, dict[str, Any]],
    families_by_handle: dict[str, dict[str, Any]],
    events_by_handle: dict[str, dict[str, Any]],
) -> dict[str, set[str]]:
    """Resolve citation owners through people, events, and families."""
    families_by_event: dict[str, set[str]] = defaultdict(set)
    for family_handle, family in families_by_handle.items():
        for event_ref in family.get("event_ref_list") or []:
            event_handle = _handle(event_ref)
            if event_handle:
                families_by_event[event_handle].add(family_handle)

    people_by_citation: dict[str, set[str]] = defaultdict(set)
    for citation_handle, owner_rows in owners.items():
        for owner in owner_rows:
            owner_type = owner["type"]
            owner_handle = owner["handle"]
            if owner_type == "person" and owner_handle in people_by_handle:
                people_by_citation[citation_handle].add(owner_handle)
            elif owner_type == "family" and owner_handle in families_by_handle:
                people_by_citation[citation_handle].update(
                    _family_partners(families_by_handle[owner_handle])
                )
            elif owner_type == "event" and owner_handle in events_by_handle:
                event = events_by_handle[owner_handle]
                resolved = _refs(event.get("person_ref_list"))
                for family_handle in families_by_event.get(owner_handle, set()):
                    resolved.update(_family_partners(families_by_handle[family_handle]))
                # Some API projections omit person_ref_list. The person event
                # refs above are a safe fallback and do not guess identities.
                if not resolved:
                    for person_handle, person in people_by_handle.items():
                        if any(
                            _handle(ref) == owner_handle
                            for ref in person.get("event_ref_list") or []
                        ):
                            resolved.add(person_handle)
                people_by_citation[citation_handle].update(resolved)
    return people_by_citation


def _list_all(client: GrampsApiClient, collection: str, *, extend: str | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for page in range(1, 201):
        query: dict[str, str | int] = {"page": page, "pagesize": 500}
        if extend:
            query["extend"] = extend
        data = client.get_json(f"/{collection}/", query=query)
        if isinstance(data, list):
            page_rows = data
        elif isinstance(data, dict):
            page_rows = next((data[key] for key in (collection, "items", "results") if isinstance(data.get(key), list)), [])
        else:
            raise GrampsApiError(f"unexpected {collection} collection response")
        rows.extend(row for row in page_rows if isinstance(row, dict))
        if len(page_rows) < 500:
            return rows
    raise GrampsApiError(f"{collection} pagination safety bound reached")


def audit(client: GrampsApiClient, *, source_gramps_id: str = "S2212") -> dict[str, Any]:
    sources = _list_all(client, "sources")
    source_matches = [row for row in sources if str(row.get("gramps_id")) == source_gramps_id]
    if len(source_matches) != 1:
        raise GrampsApiError(f"expected one source {source_gramps_id}, found {len(source_matches)}")
    source = source_matches[0]
    source_handle = str(source.get("handle") or "")
    if not source_handle:
        raise GrampsApiError("source has no handle")
    citations = _list_all(client, "citations")
    source_citations = [row for row in citations if str(row.get("source_handle") or row.get("source") or "") == source_handle]
    citation_handles = {str(row.get("handle")) for row in source_citations if row.get("handle")}
    people = _list_all(client, "people", extend="citation_list,event_ref_list")
    families = _list_all(
        client,
        "families",
        extend="citation_list,child_ref_list,event_ref_list,father_handle,mother_handle",
    )
    events = _list_all(client, "events", extend="citation_list,person_ref_list")
    owners: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in people:
        row_handle = str(row.get("handle") or "")
        for citation_handle in _nested_citation_refs(row) & citation_handles:
            owners[citation_handle].append({"type": "person", "handle": row_handle})
    for row in families:
        row_handle = str(row.get("handle") or "")
        for citation_handle in _nested_citation_refs(row) & citation_handles:
            owners[citation_handle].append({"type": "family", "handle": row_handle})
    for row in events:
        row_handle = str(row.get("handle") or "")
        for citation_handle in _nested_citation_refs(row) & citation_handles:
            owners[citation_handle].append({"type": "event", "handle": row_handle})
    people_by_handle = {str(row.get("handle")): row for row in people if row.get("handle")}
    families_by_handle = {str(row.get("handle")): row for row in families if row.get("handle")}
    events_by_handle = {str(row.get("handle")): row for row in events if row.get("handle")}
    people_by_citation = _resolve_people_by_citation(
        owners, people_by_handle, families_by_handle, events_by_handle
    )
    all_candidates = set().union(*people_by_citation.values()) if people_by_citation else set()
    candidate_rows = []
    for person_handle in sorted(all_candidates):
        person = people_by_handle.get(person_handle, {})
        cited_ids = sorted(citation_handle for citation_handle, handles in people_by_citation.items() if person_handle in handles)
        candidate_rows.append(
            {
                "handle": person_handle,
                "gramps_id": person.get("gramps_id"),
                "name": _person_name(person),
                "citation_handles": cited_ids,
            }
        )
    unresolved = sorted(citation_handles - set(owners))
    report = {
        "schema": 2,
        "source": {"gramps_id": source_gramps_id, "handle": source_handle, "title": source.get("title")},
        "citations_total": len(source_citations),
        "citations_with_owner": sum(bool(owners.get(handle)) for handle in citation_handles),
        "people_resolved": len(all_candidates),
        "people_candidates": candidate_rows,
        "unresolved_citation_handles": unresolved,
        "unresolved_citations": [
            {
                "gramps_id": row.get("gramps_id"),
                "handle": row.get("handle"),
                "page": row.get("page"),
                "confidence": row.get("confidence"),
            }
            for row in sorted(
                (row for row in source_citations if row.get("handle") in set(unresolved)),
                key=lambda row: (str(row.get("gramps_id") or ""), str(row.get("handle"))),
            )
        ],
        "owner_type_counts": {
            kind: sum(1 for values in owners.values() for owner in values if owner["type"] == kind)
            for kind in ("person", "family", "event")
        },
        "write_operations": 0,
        "note": "Read-only audit. Candidate people require chronological/homonym review before tagging.",
    }
    return report


def _private_output(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    try:
        resolved.relative_to(REPO_ROOT.resolve())
    except ValueError:
        return resolved
    raise ValueError("audit output must be outside the repository")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default="S2212")
    parser.add_argument("--output", type=Path, default=Path("/tmp/benoit-coste-s2212-audit.json"))
    parser.add_argument("--env-file", type=Path)
    args = parser.parse_args(argv)
    try:
        report = audit(client_from_external_env(args.env_file), source_gramps_id=args.source)
        output = _private_output(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({
            "output": str(output),
            "source": report["source"]["gramps_id"],
            "citations_total": report["citations_total"],
            "citations_with_owner": report["citations_with_owner"],
            "people_resolved": report["people_resolved"],
            "unresolved_count": len(report["unresolved_citation_handles"]),
            "write_operations": report["write_operations"],
        }, ensure_ascii=False))
        return 0
    except (OSError, ValueError, GrampsApiError) as error:
        print(f"S2212 audit failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
