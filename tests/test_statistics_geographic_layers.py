import importlib
import sys
import types
import unittest
from pathlib import Path
from unittest import mock


RESEARCH_CODE_DIR = Path(__file__).resolve().parents[1] / "research_code"
if str(RESEARCH_CODE_DIR) not in sys.path:
    sys.path.insert(0, str(RESEARCH_CODE_DIR))


def import_statistics_module():
    sys.modules.pop("statistics_geographic_layers", None)

    fake_numpy = types.ModuleType("numpy")
    fake_pandas = types.ModuleType("pandas")
    fake_duckdb = types.ModuleType("duckdb")
    fake_mercantile = types.ModuleType("mercantile")
    fake_shapely = types.ModuleType("shapely")
    fake_shapely.to_wkb = lambda geometry: geometry
    fake_shapely.box = lambda *args: args

    with mock.patch.dict(
        sys.modules,
        {
            "numpy": fake_numpy,
            "pandas": fake_pandas,
            "duckdb": fake_duckdb,
            "mercantile": fake_mercantile,
            "shapely": fake_shapely,
        },
    ):
        return importlib.import_module("statistics_geographic_layers")


class StatisticsGeographicLayersTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_statistics_module()

    def test_load_statistics_runtime_config_uses_defaults_and_overrides(self):
        cfg = {
            "paths": {"stats_dir": "/tmp/stats"},
            "params": {"zoom_level": "9"},
            "statistics": {
                "geographic_layers": {
                    "osm_distance": "20",
                    "score": "0.95",
                    "urban_area_layers": ["CUSTOM_LAYER"],
                    "urban_area_cols": ["urban_id"],
                }
            },
        }

        runtime = self.module.load_statistics_runtime_config(cfg)

        self.assertEqual(runtime["osm_distance"], 20)
        self.assertEqual(runtime["pred_distance"], 10)
        self.assertEqual(runtime["score"], 0.95)
        self.assertEqual(runtime["threshold"], 0.3)
        self.assertEqual(runtime["zoom_level"], 9)
        self.assertEqual(runtime["urban_area_layers"], ["CUSTOM_LAYER"])
        self.assertEqual(runtime["urban_area_cols"], ["urban_id"])
        self.assertEqual(runtime["results_dir"], "/tmp/stats/geographic_layers")

    def test_sql_in_list_escapes_quotes_and_rejects_empty_input(self):
        self.assertEqual(
            self.module._sql_in_list(["primary", "trunk's"]),
            "('primary', 'trunk''s')",
        )

        with self.assertRaises(ValueError):
            self.module._sql_in_list([])

    def test_create_osm_general_strings_builds_expected_aliases(self):
        result = self.module.create_osm_general_strings(
            {"primary": ["primary", "primary_link"]},
            suffix="_summary",
            alias_prefix="pred_",
        )

        self.assertIn("COUNT(DISTINCT CASE WHEN osm_tags_highway IN ('primary', 'primary_link')", result)
        self.assertIn("as pred_primary_id_summary", result)
        self.assertIn("as pred_primary_length_summary", result)

    def test_create_surface_urban_rural_strings_covers_all_metric_variants(self):
        result = self.module.create_surface_urban_rural_strings(
            {"residential": ["residential"]},
            pred_col="predicted_surface",
            suffix="_tile",
            alias_prefix="agg_",
        )

        self.assertIn("agg_residential_urban_unpaved_tile", result)
        self.assertIn("agg_residential_rural_unpaved_tile", result)
        self.assertIn("agg_residential_urban_paved_tile", result)
        self.assertIn("agg_residential_rural_paved_tile", result)
        self.assertIn("THEN predicted_surface ELSE 0 END", result)

    def test_build_metric_catalog_respects_custom_shared_configuration(self):
        metrics = self.module.build_metric_catalog(
            {
                "shared": {
                    "highways": ["primary"],
                    "areas": ["urban", "rural"],
                    "road_types": ["paved"],
                    "road_classes": {"primary": ["primary"]},
                }
            }
        )

        self.assertEqual(metrics["highways"], ["primary"])
        self.assertEqual(metrics["length_tags"], ["primary_length", "primary_length_urban", "primary_length_rural"])
        self.assertEqual(metrics["pred_id_tags"], ["pred_primary_id", "pred_primary_id_urban", "pred_primary_id_rural"])
        self.assertEqual(metrics["paved_tags"], ["primary_urban_paved", "primary_rural_paved", "primary_paved"])
        self.assertEqual(metrics["osm_total_cols"], ["b.osm_primary_length", "a.osm_primary_length_urban", "a.osm_primary_length_rural", "b.osm_primary_id", "a.osm_primary_id_urban", "a.osm_primary_id_rural", "b.number_of_osm_ids", "a.number_of_osm_ids_urban", "a.number_of_osm_ids_rural"])

    def test_correct_z14_tiles_osm_parses_triplets(self):
        parsed = self.module.correct_z14_tiles_osm([["1 2 14"], ["30 40 14"]])

        self.assertEqual(parsed, [[1, 2, 14], [30, 40, 14]])

