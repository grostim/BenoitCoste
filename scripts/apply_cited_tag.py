"""Safely apply the S2212 citation tag after an explicit review manifest.

This command is intentionally fail-closed. The read-only S2212 audit produces
``people_candidates``; it does not produce ``approved_people``. A human must
create a separate manifest with ``approval.status = "approved"`` and an exact
list of approved Gramps IDs before ``--apply`` can write anything.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import time
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
from gramps_api import GrampsApiClient, GrampsApiError, client_from_external_env  # noqa: E402

REPO_ROOT = SCRIPT_DIR.parent
TAG_NAME = "Cité dans les Mémoires de Benoît Coste"


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _strip_readonly(obj: dict[str, Any]) -> dict[str, Any]:
    cleaned = deepcopy(obj)
    for key in ("profile", "extended", "change", "backlinks", "formatted"):
        cleaned.pop(key, None)
    return cleaned


def _handle(row: dict[str, Any]) -> str:
    return str(row.get("handle") or "")


def _load_approval(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    resolved = path.expanduser().resolve()
    try:
        resolved.relative_to(REPO_ROOT.resolve())
    except ValueError:
        pass
    else:
        raise ValueError("approval manifest must stay outside the repository")
    document = json.loads(resolved.read_text(encoding="utf-8"))
    if document.get("approval", {}).get("status") != "approved":
        raise ValueError('approval manifest must contain approval.status = "approved"')
    approved = document.get("approved_people")
    if not isinstance(approved, list) or not approved:
        raise ValueError("approval manifest must contain a non-empty approved_people list")
    rows = []
    for item in approved:
        if isinstance(item, str):
            rows.append({"gramps_id": item})
        elif isinstance(item, dict) and item.get("gramps_id"):
            rows.append(item)
        else:
            raise ValueError("approved_people entries need an exact gramps_id")
    return document, rows


def _get_person_by_gid(client: GrampsApiClient, gid: str, candidate_handle: str | None = None) -> dict[str, Any]:
    if candidate_handle:
        person = client.get_json(f"/people/{candidate_handle}?extend=all&profile=self,families,events")
        if str(person.get("gramps_id")) != gid:
            raise GrampsApiError(f"approval handle does not resolve to approved person {gid}")
        return person
    matches = client.get_json(f'/people/?gql=gramps_id%20%3D%20%22{gid}%22&pagesize=2')
    if not isinstance(matches, list) or len(matches) != 1:
        raise GrampsApiError(f"expected one live person for approved ID {gid}")
    return client.get_json(f"/people/{matches[0]['handle']}?extend=all&profile=self,families,events")


def _tag_handle(client: GrampsApiClient, *, create: bool = False) -> str:
    tags = client.list_collection("tags")
    matches = [tag for tag in tags if tag.get("name") == TAG_NAME]
    if len(matches) == 1:
        return str(matches[0]["handle"])
    if len(matches) > 1:
        raise GrampsApiError("duplicate citation tags exist; refusing to choose one")
    if not create:
        raise GrampsApiError(f"required tag is absent: {TAG_NAME}")
    created = client.post_json("/tags/", {"name": TAG_NAME, "color": "#7C2F3A", "priority": 0})
    if isinstance(created, dict) and created.get("handle"):
        created_handle = str(created["handle"])
    else:
        created_handle = ""
    # Read back by exact name; the POST envelope is not authoritative.
    tags = client.list_collection("tags")
    matches = [tag for tag in tags if tag.get("name") == TAG_NAME]
    if len(matches) != 1:
        raise GrampsApiError("tag creation did not leave exactly one exact-name tag")
    if created_handle and str(matches[0].get("handle")) != created_handle:
        raise GrampsApiError("tag creation response and read-back disagree")
    return str(matches[0]["handle"])


def apply(
    client: GrampsApiClient,
    approval_path: Path,
    *,
    backup_path: Path,
    result_path: Path,
    dry_run: bool = True,
    create_tag: bool = False,
) -> dict[str, Any]:
    approval, approved_rows = _load_approval(approval_path)
    tag_handle = _tag_handle(client, create=create_tag if not dry_run else False)
    snapshots: list[dict[str, Any]] = []
    plan: list[dict[str, Any]] = []
    for row in approved_rows:
        gid = str(row["gramps_id"])
        person = _get_person_by_gid(client, gid, str(row.get("handle")) if row.get("handle") else None)
        snapshot = {"gramps_id": gid, "handle": _handle(person), "object": person}
        snapshots.append(snapshot)
        current_tags = list(person.get("tag_list") or [])
        plan.append({"gramps_id": gid, "handle": _handle(person), "already_tagged": bool(tag_handle and tag_handle in current_tags)})
    backup_path = backup_path.expanduser().resolve()
    result_path = result_path.expanduser().resolve()
    for path in (backup_path, result_path):
        try:
            path.relative_to(REPO_ROOT.resolve())
        except ValueError:
            pass
        else:
            raise ValueError("backup/result files must stay outside the repository")
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    backup_payload = {
        "schema": 1,
        "tag_name": TAG_NAME,
        "approval_manifest_sha256": hashlib.sha256(approval_path.read_bytes()).hexdigest(),
        "people": snapshots,
        "write_operations": 0 if dry_run else len([item for item in plan if not item["already_tagged"]]),
    }
    backup_path.write_text(json.dumps(backup_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if dry_run:
        result = {"mode": "dry-run", "tag_name": TAG_NAME, "approved_count": len(plan), "plan": plan, "write_operations": 0, "backup": str(backup_path)}
        result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return result
    if not tag_handle:
        raise GrampsApiError("internal error: no tag handle after live resolution")
    writes: list[dict[str, Any]] = []
    try:
        for snapshot in snapshots:
            person = snapshot["object"]
            gid = snapshot["gramps_id"]
            tags = list(person.get("tag_list") or [])
            if tag_handle in tags:
                writes.append({"gramps_id": gid, "action": "unchanged"})
                continue
            cleaned = _strip_readonly(person)
            cleaned["tag_list"] = tags + [tag_handle]
            cleaned["change"] = int(time.time())
            # Register the object before the request: the server may accept a
            # PUT and then mutate an unrelated field, or the client may lose
            # the response after the write. Both cases must trigger rollback.
            writes.append({"gramps_id": gid, "action": "tagged"})
            client.put_json(f"/people/{snapshot['handle']}", cleaned)
            after = client.get_json(f"/people/{snapshot['handle']}?extend=all&profile=self,families,events")
            if tag_handle not in (after.get("tag_list") or []):
                raise GrampsApiError(f"tag missing after write for {gid}")
            before_compare = deepcopy(person)
            after_compare = deepcopy(after)
            before_compare.pop("tag_list", None)
            after_compare.pop("tag_list", None)
            before_compare.pop("change", None)
            after_compare.pop("change", None)
            for key in ("profile", "extended", "backlinks", "formatted"):
                before_compare.pop(key, None)
                after_compare.pop(key, None)
            if _canonical(before_compare) != _canonical(after_compare):
                raise GrampsApiError(f"untouched field changed for {gid}; restoring from backup")
    except Exception:
        # Restore every object touched in this run, then stop. Restoration is
        # verified by a fresh GET; errors are surfaced without raw payloads.
        for item in writes:
            if item["action"] != "tagged":
                continue
            snap = next(row for row in snapshots if row["gramps_id"] == item["gramps_id"])
            restored = _strip_readonly(snap["object"])
            try:
                client.put_json(f"/people/{snap['handle']}", restored)
                check = client.get_json(f"/people/{snap['handle']}?extend=all&profile=self,families,events")
                if _canonical(_strip_readonly(check)) != _canonical(_strip_readonly(snap["object"])):
                    raise GrampsApiError(f"rollback verification failed for {item['gramps_id']}")
            except Exception as rollback_error:
                raise GrampsApiError(f"write failed and rollback failed for {item['gramps_id']}") from rollback_error
        raise
    result = {
        "mode": "apply",
        "tag_name": TAG_NAME,
        "tag_verified_by_name": True,
        "approved_count": len(plan),
        "write_operations": sum(item["action"] == "tagged" for item in writes),
        "writes": writes,
        "backup": str(backup_path),
    }
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("approval_manifest", type=Path)
    parser.add_argument("--backup", type=Path, default=Path("/tmp/benoit-coste-cited-tag-backup.json"))
    parser.add_argument("--result", type=Path, default=Path("/tmp/benoit-coste-cited-tag-apply.json"))
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--apply", action="store_true", help="perform full-object PUTs; omitted means read-only plan")
    parser.add_argument("--create-tag", action="store_true", help="create the exact tag if absent; only with --apply")
    args = parser.parse_args(argv)
    if args.create_tag and not args.apply:
        parser.error("--create-tag requires --apply")
    try:
        result = apply(
            client_from_external_env(args.env_file),
            args.approval_manifest,
            backup_path=args.backup,
            result_path=args.result,
            dry_run=not args.apply,
            create_tag=args.create_tag,
        )
        print(json.dumps({key: result[key] for key in ("mode", "tag_name", "approved_count", "write_operations", "backup") if key in result}, ensure_ascii=False))
        return 0
    except (OSError, ValueError, json.JSONDecodeError, GrampsApiError) as error:
        print(f"cited-tag operation failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
