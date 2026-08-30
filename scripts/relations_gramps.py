"""Resolve family relationships for the portrait gallery.

The public gallery uses the live Gramps family structure exposed by the API.
This module deliberately keeps handles internal: callers receive only a
French label and a sorting rank.  The optional CLI at the bottom runs the
native Gramps relationship calculator in a real Gramps runtime as an oracle
for live smoke tests; it never writes the database.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import argparse
import glob
import json
import os
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class Relationship:
    label: str
    rank: int


def _ref(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("ref") or value.get("handle") or "")
    return str(value or "")


def _gender(value: Any) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number in {0, 1} else None


def _display_name(person: dict[str, Any]) -> str:
    name = person.get("primary_name") or {}
    first = str(name.get("call") or name.get("first_name") or "").strip()
    surnames = name.get("surname_list") or []
    surname = ""
    if surnames and isinstance(surnames[0], dict):
        surname = str(surnames[0].get("surname") or "").strip()
    return " ".join(part for part in (first, surname) if part) or "Personne sans nom"


def _family_children(family: dict[str, Any]) -> list[str]:
    values = family.get("child_ref_list") or family.get("children") or family.get("child_handles") or []
    if isinstance(values, dict):
        values = values.values()
    return [child for child in (_ref(value) for value in values) if child]


class RelationshipResolver:
    """Resolve blood and in-law relations from Gramps family rows."""

    def __init__(self, people: Iterable[dict[str, Any]], families: Iterable[dict[str, Any]], focal_handle: str):
        self.people = {str(row.get("handle")): row for row in people if row.get("handle")}
        self.focal_handle = focal_handle
        self.parents: dict[str, list[str]] = {}
        self.children: dict[str, list[str]] = {}
        self.spouses: dict[str, set[str]] = {}
        for family in families:
            father = _ref(family.get("father_handle") or family.get("father"))
            mother = _ref(family.get("mother_handle") or family.get("mother"))
            parents = [parent for parent in (father, mother) if parent]
            children = _family_children(family)
            for child in children:
                self.parents.setdefault(child, []).extend(parent for parent in parents if parent not in self.parents.get(child, []))
            for parent in parents:
                self.children.setdefault(parent, []).extend(child for child in children if child not in self.children.get(parent, []))
            if father and mother:
                self.spouses.setdefault(father, set()).add(mother)
                self.spouses.setdefault(mother, set()).add(father)

    def _ancestor_distances(self, start: str) -> dict[str, int]:
        distances = {start: 0}
        queue: deque[str] = deque([start])
        while queue:
            current = queue.popleft()
            for parent in self.parents.get(current, []):
                if parent not in distances:
                    distances[parent] = distances[current] + 1
                    queue.append(parent)
        return distances

    def _descendant_distances(self, start: str) -> dict[str, int]:
        distances = {start: 0}
        queue: deque[str] = deque([start])
        while queue:
            current = queue.popleft()
            for child in self.children.get(current, []):
                if child not in distances:
                    distances[child] = distances[current] + 1
                    queue.append(child)
        return distances

    def _person_gender(self, handle: str) -> int | None:
        return _gender(self.people.get(handle, {}).get("gender"))

    def _gendered(self, masculine: str, feminine: str, handle: str) -> str:
        return feminine if self._person_gender(handle) == 0 else masculine

    @staticmethod
    def _generation_word(distance: int, masculine: str, feminine: str, gender: int | None) -> str:
        base = feminine if gender == 0 else masculine
        if distance == 1:
            relation = base
        elif distance == 2:
            prefix = "grand-" if base.startswith(("père", "mère")) else ("petite-" if gender == 0 else "petit-")
            relation = prefix + base
        else:
            prefix = "arrière-" * (distance - 2)
            generation_prefix = "grand-" if base.startswith(("père", "mère")) else ("petite-" if gender == 0 else "petit-")
            relation = prefix + generation_prefix + base
        article = "la" if gender == 0 else "le"
        return f"{article} {relation}"

    def _blood_relation(self, origin: str, target: str) -> Relationship | None:
        if origin == target:
            return Relationship("lui-même", 0)
        ancestors = self._ancestor_distances(origin)
        if target in ancestors and ancestors[target] > 0:
            distance = ancestors[target]
            label = self._generation_word(distance, "père", "mère", self._person_gender(target))
            return Relationship(label, distance)
        descendants = self._descendant_distances(origin)
        if target in descendants and descendants[target] > 0:
            distance = descendants[target]
            label = self._generation_word(distance, "fils", "fille", self._person_gender(target))
            return Relationship(label, distance)

        target_ancestors = self._ancestor_distances(target)
        common = set(ancestors) & set(target_ancestors)
        common.discard(origin)
        common.discard(target)
        if not common:
            return None
        common_handle = min(common, key=lambda handle: ancestors[handle] + target_ancestors[handle])
        up = ancestors[common_handle]
        down = target_ancestors[common_handle]
        if up == 1 and down == 1:
            label = self._gendered("le frère", "la sœur", target)
            return Relationship(label, 2)
        if up == 2 and down == 1:
            label = self._gendered("l'oncle", "la tante", target)
            return Relationship(label, 3)
        if up == 1 and down == 2:
            label = self._gendered("le neveu", "la nièce", target)
            return Relationship(label, 3)
        if up >= 2 and down >= 2:
            degree = min(up, down) - 1
            if degree == 1:
                cousin = "cousin germain"
            elif degree == 2:
                cousin = "cousin issu de germain"
            else:
                cousin = f"cousin au {degree}e degré"
            if self._person_gender(target) == 0:
                cousin = cousin.replace("cousin", "cousine", 1)
            return Relationship("le " + cousin if self._person_gender(target) != 0 else "la " + cousin, up + down)
        return None

    def _in_law_relation(self, target: str) -> Relationship | None:
        for spouse in sorted(self.spouses.get(target, set())):
            blood = self._blood_relation(self.focal_handle, spouse)
            if blood and blood.label != "lui-même":
                return Relationship(f"conjoint(e) de {blood.label}", blood.rank + 1)
        for focal_spouse in sorted(self.spouses.get(self.focal_handle, set())):
            blood = self._blood_relation(focal_spouse, target)
            if blood and blood.label != "lui-même":
                return Relationship(f"{blood.label} de {_display_name(self.people.get(focal_spouse, {}))} (par alliance)", blood.rank + 1)
            for target_spouse in sorted(self.spouses.get(target, set())):
                spouse_blood = self._blood_relation(focal_spouse, target_spouse)
                if spouse_blood and spouse_blood.label != "lui-même":
                    return Relationship(
                        f"conjoint(e) de {spouse_blood.label} de {_display_name(self.people.get(focal_spouse, {}))} (par alliance)",
                        spouse_blood.rank + 2,
                    )
        return None

    def resolve(self, target_handle: str) -> Relationship:
        if target_handle == self.focal_handle:
            return Relationship("lui-même", 0)
        target_gender = self._person_gender(target_handle)
        if target_handle in self.spouses.get(self.focal_handle, set()):
            return Relationship("l'épouse" if target_gender == 0 else "l'époux", 1)
        blood = self._blood_relation(self.focal_handle, target_handle)
        if blood:
            return blood
        in_law = self._in_law_relation(target_handle)
        if in_law:
            return in_law
        return Relationship("relation non résolue dans la structure Gramps", 99)


def resolve_relationships(people: Iterable[dict[str, Any]], families: Iterable[dict[str, Any]], focal_handle: str) -> dict[str, Relationship]:
    resolver = RelationshipResolver(people, families, focal_handle)
    return {handle: resolver.resolve(handle) for handle in resolver.people}


def native_relationships_from_gramps(tree_dir: str, focal_gramps_id: str, target_ids: list[str]) -> dict[str, str]:
    """Run Gramps' own French relationship calculator, read-only.

    This function is intentionally lazy-imported so the publication pipeline
    remains standard-library/API based and CI does not need Gramps.
    """
    from gramps.gen.db.utils import make_database
    from gramps.gen.relationship import get_relationship_calculator
    from gramps.gen.utils.grampslocale import GrampsLocale

    db = make_database("sqlite")
    db.load(tree_dir, None, mode="r")
    by_id = {
        db.get_person_from_handle(handle).get_gramps_id(): db.get_person_from_handle(handle)
        for handle in db.get_person_handles()
    }
    locale = GrampsLocale(lang="fr")
    calculator = get_relationship_calculator(reinit=True, clocale=locale)
    focal = by_id[focal_gramps_id]
    return {
        target_id: calculator.get_one_relationship(db, focal, by_id[target_id], extra_info=False, olocale=locale)
        for target_id in target_ids
        if target_id in by_id
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tree-dir", default=None)
    parser.add_argument("--focal", default="I0095")
    parser.add_argument("--target", action="append", dest="targets", required=True)
    args = parser.parse_args(argv)
    tree_dir = args.tree_dir or next(iter(glob.glob("/root/gramps/grampsdb/*")), None)
    if not tree_dir:
        parser.error("no Gramps tree directory found")
    print(json.dumps(native_relationships_from_gramps(tree_dir, args.focal, args.targets), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
