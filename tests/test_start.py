import os
import sys
import textwrap
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


RESEARCH_CODE_DIR = Path(__file__).resolve().parents[1] / "research_code"
if str(RESEARCH_CODE_DIR) not in sys.path:
    sys.path.insert(0, str(RESEARCH_CODE_DIR))

import config_utils

from start import (
    ConfigResolutionError,
    load_config,
    load_statistics_aggregation_runtime_config,
    resolve_config,
)


class LoadConfigTests(unittest.TestCase):
    def test_start_reexports_public_config_helpers(self):
        import start

        self.assertIs(start.require_path, config_utils.require_path)
        self.assertIs(start.require_section, config_utils.require_section)
        self.assertIs(start.parse_int, config_utils.parse_int)
        self.assertIs(start.parse_bool, config_utils.parse_bool)
        self.assertIs(start.parse_bool_with_default, config_utils.parse_bool_with_default)
        self.assertIs(start.parse_positive_int, config_utils.parse_positive_int)
        self.assertIs(start.parse_float, config_utils.parse_float)
        self.assertIs(start.parse_iso_datetime, config_utils.parse_iso_datetime)

    def test_load_config_resolves_null_imports_and_formats_paths(self):
        config_text = textwrap.dedent(
            """
            create_tiles:
              paths:
                data_dir: /tmp/mapillary-data
                processed_dir: "{data_dir}/processed"
                starter_dir: "{data_dir}/starter"
                tiles_save_dir: "{processed_dir}/tiles"
                final_unfiltered_dir: "{processed_dir}/unfiltered"
              filenames:
                report_file: "{starter_dir}/report.parquet"
                absolute_file: "{processed_dir}/report.csv"
            get_metadata:
              paths:
                data_dir: null
                processed_dir: null
                starter_dir: null
                tiles_save_dir: null
                final_unfiltered_dir: null
              filenames:
                report_file: null
                absolute_file: null
            """
        )

        with TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.yaml"
            config_path.write_text(config_text, encoding="utf-8")

            cfg = load_config(str(config_path), script_name="get_metadata")

        self.assertEqual(cfg["paths"]["processed_dir"], "/tmp/mapillary-data/processed")
        self.assertEqual(cfg["paths"]["starter_dir"], "/tmp/mapillary-data/starter")
        self.assertEqual(cfg["paths"]["tiles_save_dir"], "/tmp/mapillary-data/processed/tiles")
        self.assertEqual(cfg["paths"]["final_unfiltered_dir"], "/tmp/mapillary-data/processed/unfiltered")
        self.assertEqual(cfg["filenames"]["report_file"], "/tmp/mapillary-data/starter/report.parquet")
        self.assertEqual(cfg["filenames"]["absolute_file"], "/tmp/mapillary-data/processed/report.csv")

    def test_load_config_uses_yaml_section_order_as_canonical_run_order(self):
        config_text = textwrap.dedent(
            """
            metadata_download:
              paths:
                raw_metadata_dir: null
            get_metadata:
              paths:
                raw_metadata_dir: /tmp/raw-metadata
            """
        )

        with TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.yaml"
            config_path.write_text(config_text, encoding="utf-8")

            with self.assertRaises(ConfigResolutionError):
                load_config(str(config_path), script_name="metadata_download")

    def test_resolve_config_prefers_canonical_owner_over_later_override(self):
        raw_config = {
            "create_tiles": {"params": {"zoom_level": 8}},
            "get_linestrings_from_tiles": {"params": {"zoom_level": 99}},
            "statistics_aggregation": {"params": {"zoom_level": None}},
        }

        cfg = resolve_config("statistics_aggregation", raw_config)

        self.assertEqual(cfg["params"]["zoom_level"], 8)

    def test_resolve_config_does_not_import_from_later_script(self):
        raw_config = {
            "get_metadata": {"params": {"mly_key": None}},
            "metadata_download": {"params": {"mly_key": "later-owner"}},
        }

        with self.assertRaises(ConfigResolutionError):
            resolve_config("get_metadata", raw_config)

    def test_load_config_prefers_local_non_null_override(self):
        config_text = textwrap.dedent(
            """
            create_tiles:
              params:
                zoom_level: 8
            statistics_aggregation:
              params:
                zoom_level: 11
            """
        )

        with TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.yaml"
            config_path.write_text(config_text, encoding="utf-8")

            cfg = load_config(str(config_path), script_name="statistics_aggregation")

        self.assertEqual(cfg["params"]["zoom_level"], 11)

    def test_load_config_prefers_cli_override_over_local_and_imported_values(self):
        config_text = textwrap.dedent(
            """
            create_tiles:
              params:
                zoom_level: 8
            statistics_aggregation:
              params:
                zoom_level: 11
            """
        )

        with TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.yaml"
            config_path.write_text(config_text, encoding="utf-8")

            cfg = load_config(
                str(config_path),
                script_name="statistics_aggregation",
                cli_overrides={"params": {"zoom_level": 13}},
            )

        self.assertEqual(cfg["params"]["zoom_level"], 13)

    def test_load_config_raises_when_null_import_cannot_be_resolved(self):
        config_text = textwrap.dedent(
            """
            create_tiles:
              paths:
                data_dir: null
                processed_dir: null
                starter_dir: null
            """
        )

        with TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.yaml"
            config_path.write_text(config_text, encoding="utf-8")

            with self.assertRaises(ConfigResolutionError):
                load_config(str(config_path), script_name="create_tiles")

    def test_load_config_raises_when_script_section_missing(self):
        config_text = textwrap.dedent(
            """
            create_tiles:
              paths:
                data_dir: /tmp/mapillary-data
                processed_dir: "{data_dir}/processed"
            """
        )

        with TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.yaml"
            config_path.write_text(config_text, encoding="utf-8")

            with self.assertRaises(ConfigResolutionError):
                load_config(str(config_path), script_name="missing_script")

    def test_load_statistics_aggregation_runtime_config_builds_expected_paths(self):
        cfg = {
            "params": {"zoom_level": 8},
            "paths": {
                "stats_dir": "/tmp/processed/stats",
                "processed_dir": "/tmp/processed",
                "osm_saving_dir": "/tmp/osm",
            },
            "filenames": {
                "country_filename": "countries.parquet",
                "continents_filename": "/tmp/processed/continents.parquet",
                "ghsl_filename": "GHS_UCDB_GLOBE_R2024A.gpkg",
                "africapolis_filename": "AFRICAPOLIS2020.shp",
            },
            "statistics": {
                "geographic_layers": {
                    "urban_area_layers": ["ghsl", "africapolis"],
                },
                "aggregation": {
                    "urban_layer_cols": ["ID_HDC_G0", "agglosID"],
                    "memory_limit_gb": 32,
                    "number_of_cpus": 64,
                    "max_workers": 8,
                    "process_non_temporal_osm": False,
                },
            },
        }

        runtime_cfg = load_statistics_aggregation_runtime_config(cfg)

        self.assertEqual(runtime_cfg["results_dir"], os.path.abspath("/tmp/processed/stats/geographic_layers"))
        self.assertEqual(runtime_cfg["results_dir_compiled"], os.path.abspath("/tmp/processed/stats/summary"))
        self.assertEqual(runtime_cfg["country_layer"], os.path.abspath("/tmp/processed/intersected_countries.parquet"))
        self.assertEqual(runtime_cfg["continent_layer"], os.path.abspath("/tmp/processed/continents.parquet"))
        self.assertEqual(
            runtime_cfg["urban_layers"],
            [
                "country_intersected_intersected_GHS_UCDB_GLOBE_R2024A.parquet",
                "country_intersected_intersected_AFRICAPOLIS2020.parquet",
            ],
        )
        self.assertEqual(runtime_cfg["sub_threads"], 8)
        self.assertFalse(runtime_cfg["process_non_temporal_osm"])
