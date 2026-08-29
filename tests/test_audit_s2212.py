"""Offline regression tests for citation-to-person resolution."""

from __future__ import annotations

import unittest

from scripts.audit_s2212 import _resolve_people_by_citation


class CitationResolutionTests(unittest.TestCase):
    def test_event_citation_resolves_family_members_when_event_has_no_person_refs(self) -> None:
        owners = {"citation": [{"type": "event", "handle": "event-h"}]}
        people = {
            "father-h": {"gramps_id": "I0001"},
            "mother-h": {"gramps_id": "I0002"},
            "child-h": {"gramps_id": "I0003"},
        }
        families = {
            "family-h": {
                "event_ref_list": [{"ref": "event-h"}],
                "father_handle": "father-h",
                "mother_handle": "mother-h",
                "child_ref_list": [{"ref": "child-h"}],
            }
        }
        events = {"event-h": {"person_ref_list": []}}

        resolved = _resolve_people_by_citation(owners, people, families, events)

        self.assertEqual(
            resolved,
            {"citation": {"father-h", "mother-h"}},
        )


if __name__ == "__main__":
    unittest.main()
