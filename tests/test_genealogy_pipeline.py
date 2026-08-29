"""Offline contract tests for the genealogy chapter pipeline."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

from scripts.build_cited_kinship_graph import build_from_data, _fallback_graph_svg
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
        config_text = (ROOT / "genealogie" / "report.toml").read_text(encoding="utf-8")
        self.assertNotIn("GRAMPSWEB_API_PASS", config_text)
        self.assertNotIn("Bearer ", config_text)

    def test_old_addon_is_rejected_without_override(self) -> None:
        with self.assertRaises(AddonCapabilityError):
            ensure_addon_capability({"version": "1.2.4", "options_help": {"ancestor_generations": []}})
        self.assertIn("highlight_tag", ensure_addon_capability({"options_help": {"highlight_tag": []}}))

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

    def test_graph_uses_minimal_paths_and_masks_private_connectors(self) -> None:
        subgraph, dot, _outputs = build_from_data(
            self.fixture["graph"],
            center_handle="person-center",
            tag_handle="tag-cited",
        )
        self.assertEqual(subgraph["tagged_handles"], ["person-cited"])
        self.assertEqual(subgraph["unconnected_tagged_handles"], ["person-unrelated"])
        labels = " ".join(row.get("name", "") for row in subgraph["people"])
        self.assertNotIn("Should never be shown", dot)
        self.assertIn("Personne privée", dot)
        self.assertIn("Josephine Colomb", dot)
        self.assertNotIn("person-center", dot)
        self.assertNotIn("person-unrelated", dot)
        self.assertNotIn("Should never be shown", dot)
        self.assertIn("doublecircle", dot)
        self.assertIn("#7C2F3A", dot)

    def test_fallback_graph_is_compact_and_keeps_all_labels(self) -> None:
        people = [
            {"handle": f"person-{index}", "name": f"Personne {index}", "tagged": True}
            for index in range(30)
        ]
        families = [
            {"handle": f"family-{index}", "children": [f"person-{index}", f"person-{(index + 1) % 30}"]}
            for index in range(29)
        ]
        subgraph, dot, _outputs = build_from_data(
            {"people": people, "families": families},
            center_handle="person-0",
            tag_handle="unused-tag",
        )
        svg = _fallback_graph_svg(dot)
        root = ET.fromstring(svg)
        width = float(root.get("width", "0").removesuffix("px"))
        height = float(root.get("height", "0").removesuffix("px"))
        self.assertLess(height / width, 1.0)
        self.assertEqual(len([node for node in root.iter() if node.tag.rsplit("}", 1)[-1] == "text"]), len(subgraph["people"]))
        self.assertEqual(len([node for node in root.iter() if node.tag.rsplit("}", 1)[-1] == "path"]), 58)
        self.assertEqual(len(subgraph["people"]), 30)

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
            self.assertGreater(result["manifest"]["collateral_graph"]["connected_cited_people"], 0)
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
                "parente-citee.svg",
                "parente-citee.pdf",
                "parente-citee.png",
                "manifest.json",
            }
            self.assertTrue(expected.issubset({path.name for path in output.iterdir()}))
            manifest = (output / "manifest.json").read_text(encoding="utf-8")
            self.assertNotIn("person-center", manifest)
            self.assertNotIn("person-private", manifest)
            validate_svg_file(output / "arbre-benoit-coste.svg", expected_labels=("Coste", "Colomb"))
            validate_svg_file(output / "parente-citee.svg", expected_labels=("Coste",))


if __name__ == "__main__":
    unittest.main()
