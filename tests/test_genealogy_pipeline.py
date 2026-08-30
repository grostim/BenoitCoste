"""Offline contract tests for the genealogy chapter pipeline."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

from scripts.check_genealogy_assets import AssetValidationError, inspect_svg, validate_svg_file
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
        self.assertIn("ascendants et descendants directs du\ncouple Coste/Colomb", chapter.replace("\r\n", "\n"))
        self.assertNotIn("Gramps", chapter)
        self.assertNotIn("publication_safe", chapter)
        self.assertNotIn("pipeline", chapter)
        self.assertNotIn("Limites éditoriales", chapter)

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
            result = build_assets(self.config, output_dir=output, fixture=self.fixture)
            self.assertEqual(result["manifest"]["ancestor_generations"], 2)
            self.assertEqual(result["manifest"]["descendant_generations"], 1)
            self.assertFalse(result["manifest"]["show_highlight_markers"])
            self.assertNotIn("collateral_graph", result["manifest"])
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
                "manifest.json",
            }
            self.assertTrue(expected.issubset({path.name for path in output.iterdir()}))
            self.assertFalse(
                {path.name for path in output.iterdir()} & {
                    "parente-citee.svg",
                    "parente-citee.pdf",
                    "parente-citee.png",
                }
            )
            manifest = (output / "manifest.json").read_text(encoding="utf-8")
            self.assertNotIn("person-center", manifest)
            self.assertNotIn("person-private", manifest)
            validate_svg_file(output / "arbre-benoit-coste.svg", expected_labels=("Coste", "Colomb"))


if __name__ == "__main__":
    unittest.main()