"""Offline rollback regression tests for the citation-tag writer."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from scripts.apply_cited_tag import GrampsApiError, apply


class FakeClient:
    def __init__(self) -> None:
        self.person = {
            "handle": "person-h",
            "gramps_id": "I0001",
            "gender": 0,
            "tag_list": [],
            "primary_name": {"first_name": "Madeleine", "surname_list": [{"surname": "Coste"}]},
        }
        self.put_payloads: list[dict[str, object]] = []

    def list_collection(self, collection: str) -> list[dict[str, str]]:
        self.assert_collection(collection, "tags")
        return [{"handle": "tag-h", "name": "Cité dans les Mémoires de Benoît Coste"}]

    def get_json(self, path: str, **_kwargs: object) -> object:
        if path.startswith("/people/?gql="):
            return [{"handle": "person-h", "gramps_id": "I0001"}]
        if path.startswith("/people/person-h"):
            return deepcopy(self.person)
        raise AssertionError(f"unexpected GET path: {path}")

    def put_json(self, path: str, payload: dict[str, object], **_kwargs: object) -> None:
        if path != "/people/person-h":
            raise AssertionError(f"unexpected PUT path: {path}")
        self.put_payloads.append(deepcopy(payload))
        self.person = deepcopy(payload)
        if len(self.put_payloads) == 1:
            # Reproduce the observed server-side mutation of an untouched field.
            self.person["gender"] = 99

    @staticmethod
    def assert_collection(actual: str, expected: str) -> None:
        if actual != expected:
            raise AssertionError(f"unexpected collection: {actual}")


class CitedTagRollbackTests(unittest.TestCase):
    def test_unexpected_field_change_rolls_back_the_current_person(self) -> None:
        client = FakeClient()
        original = deepcopy(client.person)
        with tempfile.TemporaryDirectory(prefix="cited-tag-test-") as tmp:
            root = Path(tmp)
            approval = root / "approval.json"
            approval.write_text(
                json.dumps({
                    "approval": {"status": "approved"},
                    "approved_people": [{"gramps_id": "I0001"}],
                }),
                encoding="utf-8",
            )
            with self.assertRaises(GrampsApiError):
                apply(
                    client,
                    approval,
                    backup_path=root / "backup.json",
                    result_path=root / "result.json",
                    dry_run=False,
                )

        self.assertEqual(len(client.put_payloads), 2)
        self.assertEqual(client.person, original)


if __name__ == "__main__":
    unittest.main()
