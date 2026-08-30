"""Offline contract tests for the genealogy chapter pipeline."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

from scripts.build_portrait_gallery import build_portrait_gallery, fixture_records
from scripts.check_genealogy_assets import AssetValidationError, inspect_svg, validate_svg_file
from scripts.relations_gramps import RelationshipResolver
from scripts.update_genealogy import (
    AddonCapabilityError,
    build_assets,
    ensure_addon_capability,
    load_config,
    make_detail_svg,
    make_overview_svg,
    report_options,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "genealogy_fixture.json"


class GenealogyPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = load_config(ROOT / "genealogie" / "report.toml")
        self.fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    def test_public_configuration_is_explicit_and_secret_free(self) -> None:
        options = report_options(self.config)
        self.assertTrue(all(isinstance(value, str) for value in options.values()))
        self.assertEqual(options["ancestor_generations"], "2")
        self.assertEqual(options["descendant_generations"], "1")
        self.assertEqual(options["privacy_mode"], "publication_safe")
        self.assertEqual(options["show_portraits"], "True")
        self.assertEqual(options["incl_private"], "False")
        self.assertEqual(options["living_people"], "0")
        self.assertEqual(options["respect_media_crop"], "True")
        self.assertEqual(options["off"], "svg")
        self.assertEqual(options["highlight_tag"], "Cité dans les Mémoires de Benoît Coste")
        self.assertEqual(options["show_highlight_markers"], "False")
        config_text = (ROOT / "genealogie" / "report.toml").read_text(encoding="utf-8")
        self.assertNotIn("GRAMPSWEB_API_PASS", config_text)
        self.assertNotIn("Bearer ", config_text)

    def test_chapter_keeps_only_the_full_page_fan_figure(self) -> None:
        chapter = (ROOT / "genealogie" / "chapitre.tex").read_text(encoding="utf-8")
        self.assertIn("arbre-benoit-coste-a4-overview.pdf", chapter)
        self.assertIn(r"\includepdf[fitpaper]", chapter)
        self.assertNotIn("parente-citee", chapter)
        for index in range(1, 5):
            self.assertNotIn(f"arbre-benoit-coste-a4-{index}.pdf", chapter)

    def test_chapter_introduction_is_reader_facing(self) -> None:
        chapter = (ROOT / "genealogie" / "chapitre.tex").read_text(encoding="utf-8")
        self.assertIn("ajout du transcripteur", chapter.lower())
        self.assertIn("ascendants et les descendants directs du couple Coste/Colomb", chapter)
        self.assertNotIn("Gramps", chapter)
        self.assertNotIn("publication_safe", chapter)
        self.assertNotIn("pipeline", chapter)
        self.assertNotIn("Limites éditoriales", chapter)

    def test_relationship_resolver_handles_blood_and_in_law_paths(self) -> None:
        def person(handle: str, gid: str, gender: int) -> dict[str, object]:
            return {
                "handle": handle,
                "gramps_id": gid,
                "gender": gender,
                "primary_name": {"first_name": gid, "surname_list": [{"surname": "Test"}]},
            }

        people = [
            person("center", "I0095", 1),
            person("spouse", "I0096", 0),
            person("father", "I0001", 1),
            person("mother", "I0002", 0),
            person("sibling", "I0003", 0),
            person("sibling-spouse", "I0004", 1),
            person("grandchild", "I0006", 0),
            person("child", "I0007", 1),
            person("child-spouse", "I0008", 0),
            person("spouse-parent-1", "I0009", 1),
            person("spouse-parent-2", "I0010", 0),
            person("spouse-sibling", "I0011", 0),
            person("spouse-sibling-spouse", "I0012", 1),
            person("unknown", "I0005", 0),
        ]
        families = [
            {"father_handle": "father", "mother_handle": "mother", "child_ref_list": [{"ref": "center"}, {"ref": "sibling"}]},
            {"father_handle": "center", "mother_handle": "spouse", "child_ref_list": [{"ref": "child"}]},
            {"father_handle": "child", "mother_handle": "child-spouse", "child_ref_list": [{"ref": "grandchild"}]},
            {"father_handle": "spouse-parent-1", "mother_handle": "spouse-parent-2", "child_ref_list": [{"ref": "spouse"}, {"ref": "spouse-sibling"}]},
            {"father_handle": "spouse-sibling", "mother_handle": "spouse-sibling-spouse", "child_ref_list": []},
            {"father_handle": "sibling", "mother_handle": "sibling-spouse", "child_ref_list": []},
        ]
        resolver = RelationshipResolver(people, families, "center")
        self.assertEqual(resolver.resolve("father").label, "le père")
        self.assertEqual(resolver.resolve("sibling").label, "la sœur")
        self.assertEqual(resolver.resolve("sibling-spouse").label, "conjoint(e) de la sœur")
        self.assertEqual(resolver.resolve("grandchild").label, "la petite-fille")
        self.assertEqual(
            resolver.resolve("spouse-sibling-spouse").label,
            "conjoint(e) de la sœur de I0096 Test (par alliance)",
        )
        self.assertEqual(resolver.resolve("unknown").label, "relation non résolue dans la structure Gramps")

    def test_gallery_formats_usage_name_and_one_page_per_person(self) -> None:
        with tempfile.TemporaryDirectory(prefix="gallery-test-") as tmp:
            result = build_portrait_gallery(fixture_records(self.fixture), Path(tmp) / "assets")
            tex = result.tex_path.read_text(encoding="utf-8")
            self.assertEqual(result.people, 3)
            self.assertEqual(result.pages, 3)
            self.assertEqual(result.people_with_portraits, 2)
            self.assertEqual(result.portrait_count, 4)
            self.assertEqual(tex.count(r"\clearpage"), 3)
            self.assertIn(r"\underline{Joséphine}", tex)
            self.assertIn("Benoît COSTE", tex)
            self.assertIn("COLOMB DE GAST", tex)
            self.assertIn("\u00e9pouse", tex)
            self.assertNotIn("I0095", tex)
            self.assertNotIn("/tmp/", tex)
            self.assertNotIn(r"%\linewidth", tex)
            self.assertIn("genealogie/assets/galerie/portraits/", tex)
            self.assertEqual(len(list((Path(tmp) / "assets" / "galerie" / "portraits").glob("*.jpg"))), 3)

    def test_old_addon_is_rejected_without_override(self) -> None:
        with self.assertRaises(AddonCapabilityError):
            ensure_addon_capability({"version": "1.2.4", "options_help": {"ancestor_generations": []}})
        self.assertEqual(
            {
                "highlight_tag",
                "show_highlight_markers",
            },
            ensure_addon_capability(
                {
                    "options_help": {
                        "highlight_tag": [],
                        "show_highlight_markers": [],
                    }
                }
            ),
        )

    def test_detail_views_are_vector_crops(self) -> None:
        svg = Path(ROOT / "tests" / "fixtures" / "fan.svg").read_bytes()
        detail = make_detail_svg(svg, crop=(1, 1))
        metrics = inspect_svg(detail, expected_labels=("Coste",))
        self.assertEqual(metrics.width, "297mm")
        self.assertEqual(metrics.height, "210mm")
        self.assertGreater(metrics.path_elements, 0)
        view_box = [
            float(part) for part in (ET.fromstring(detail).get("viewBox") or "").split()
        ]
        self.assertLess(view_box[0], 500.0)
        self.assertLess(view_box[1], 350.0)
        self.assertGreater(view_box[2], 500.0)
        self.assertGreater(view_box[3], 350.0)
        self.assertEqual(
            ET.fromstring(detail).get("style"),
            "background: #FAF9F5",
        )

    def test_detail_views_keep_the_focal_labels_inside_a_safe_viewport(self) -> None:
        svg = Path(ROOT / "tests" / "fixtures" / "fan.svg").read_bytes()
        for crop in ((0, 0), (1, 0), (0, 1), (1, 1)):
            detail = make_detail_svg(svg, crop=crop)
            root = ET.fromstring(detail)
            x, y, width, height = (
                float(part) for part in (root.get("viewBox") or "").split()
            )
            # The focal couple is centred at (500, 350). Each logical detail
            # must retain it with room for the long combined label; a quadrant
            # that ends exactly at the focal point is an empty/clipped panel.
            self.assertLessEqual(x, 300.0)
            self.assertGreaterEqual(x + width, 700.0)
            self.assertLessEqual(y, 300.0)
            self.assertGreaterEqual(y + height, 420.0)
            self.assertIn(b"Beno\xc3\xaet Coste", detail)
            self.assertIn(b"Antoinette Jos\xc3\xa9phine Colomb", detail)

    def test_detail_views_filter_labels_outside_the_logical_tile(self) -> None:
        svg = Path(ROOT / "tests" / "fixtures" / "fan.svg").read_bytes()
        svg = svg.replace(
            b"</svg>",
            b'<text x="700" y="100" font-size="8">OutOfTile</text></svg>',
        )
        detail = make_detail_svg(svg, crop=(0, 0))
        self.assertNotIn(b"OutOfTile", detail)
        self.assertIn(b"Beno\xc3\xaet Coste", detail)
        self.assertIn(b"Antoinette Jos\xc3\xa9phine Colomb", detail)

    def test_overview_keeps_the_complete_canonical_viewbox(self) -> None:
        svg = Path(ROOT / "tests" / "fixtures" / "fan.svg").read_bytes()
        overview = make_overview_svg(svg)
        metrics = inspect_svg(overview, expected_labels=("Coste", "Colomb"))
        self.assertEqual(metrics.width, "297mm")
        self.assertEqual(metrics.height, "210mm")
        overview_root = ET.fromstring(overview)
        overview_view_box = [
            float(part) for part in (overview_root.get("viewBox") or "").split()
        ]
        self.assertLessEqual(overview_view_box[0], 0.0)
        self.assertLessEqual(overview_view_box[1], 0.0)
        self.assertGreaterEqual(overview_view_box[0] + overview_view_box[2], 1000.0)
        self.assertGreaterEqual(overview_view_box[1] + overview_view_box[3], 700.0)
        self.assertAlmostEqual(
            overview_view_box[2] / overview_view_box[3],
            297.0 / 210.0,
            delta=1e-5,
        )
        self.assertIn(b"style=\"background: #FAF9F5\"", overview)

    def test_asset_checker_rejects_remote_resources_and_gramps_ids(self) -> None:
        base = Path(ROOT / "tests" / "fixtures" / "fan.svg").read_bytes()
        with self.assertRaises(AssetValidationError):
            inspect_svg(base.replace(b"</svg>", b'<text href="https://example.invalid">leak</text></svg>'))
        with self.assertRaises(AssetValidationError):
            inspect_svg(base.replace(b"</svg>", b"<text>I0123</text></svg>"))

    def test_asset_checker_allows_embedded_image_data_uri(self) -> None:
        base = Path(ROOT / "tests" / "fixtures" / "fan.svg").read_bytes()
        embedded = base.replace(
            b"</svg>",
            b'<image href="data:image/png;base64,I0123////" x="0" y="0" width="1" height="1" /></svg>',
        )
        metrics = inspect_svg(embedded, expected_labels=("Coste",))
        self.assertEqual(metrics.image_elements, 2)

        path_marker = base.replace(
            b"</svg>",
            b'<path d="M10 10 L12 12 L10 14 L8 12 Z" fill="#B55A52" stroke="#7C2F3A" stroke-width="1" /></svg>',
        )
        self.assertEqual(inspect_svg(path_marker).marker_elements, 2)

    def test_asset_checker_converts_unitless_font_size_to_physical_points(self) -> None:
        svg = b'''<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="100mm" viewBox="0 0 100 100">
          <path d="M0 0 L1 1" />
          <text x="1" y="10" font-size="10">Coste</text>
        </svg>'''
        metrics = inspect_svg(svg, expected_labels=("Coste",))
        self.assertAlmostEqual(metrics.minimum_font_pt or 0.0, 10.0 * 72.0 / 25.4, places=5)

    def test_fixture_build_exercises_conversion_and_public_manifest(self) -> None:
        with tempfile.TemporaryDirectory(prefix="genealogy-test-") as tmp:
            output = Path(tmp) / "assets"
            stale = output / "galerie" / "portraits" / "stale.jpg"
            stale.parent.mkdir(parents=True)
            stale.write_bytes(b"stale")
            result = build_assets(self.config, output_dir=output, fixture=self.fixture)
            self.assertEqual(result["manifest"]["ancestor_generations"], 2)
            self.assertEqual(result["manifest"]["descendant_generations"], 1)
            self.assertFalse(result["manifest"]["show_highlight_markers"])
            self.assertNotIn("collateral_graph", result["manifest"])
            self.assertEqual(result["manifest"]["gallery"]["people"], 3)
            self.assertEqual(result["manifest"]["gallery"]["pages"], 3)
            self.assertEqual(result["manifest"]["gallery"]["people_with_portraits"], 2)
            self.assertEqual(result["manifest"]["gallery"]["portraits"], 4)
            self.assertFalse(stale.exists())
            expected = {
                "arbre-benoit-coste.svg",
                "arbre-benoit-coste.pdf",
                "arbre-benoit-coste.png",
                "arbre-benoit-coste-a4-overview.svg",
                "arbre-benoit-coste-a4-overview.pdf",
                "arbre-benoit-coste-a4-overview.png",
                "arbre-benoit-coste-a4-1.svg",
                "arbre-benoit-coste-a4-1.pdf",
                "arbre-benoit-coste-a4-1.png",
                "galerie/galerie.tex",
                "manifest.json",
            }
            files = {str(path.relative_to(output)) for path in output.rglob("*") if path.is_file()}
            self.assertTrue(expected.issubset(files))
            self.assertEqual(
                {path for path in files if path.startswith("galerie/portraits/") and path.endswith(".jpg")},
                {
                    "galerie/portraits/portrait-6d91715dce195b78f347.jpg",
                    "galerie/portraits/portrait-98957cda47c33436d148.jpg",
                    "galerie/portraits/portrait-cae0c1932888b318fc42.jpg",
                },
            )
            self.assertFalse(any(path.startswith("parente-citee") for path in files))
            manifest = (output / "manifest.json").read_text(encoding="utf-8")
            self.assertNotIn("person-center", manifest)
            self.assertNotIn("person-private", manifest)
            validate_svg_file(output / "arbre-benoit-coste.svg", expected_labels=("Coste", "Colomb"))


if __name__ == "__main__":
    unittest.main()