import sys
import textwrap
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


RESEARCH_CODE_DIR = Path(__file__).resolve().parents[1] / "research_code"
if str(RESEARCH_CODE_DIR) not in sys.path:
    sys.path.insert(0, str(RESEARCH_CODE_DIR))

from start import load_config


class LoadConfigTests(unittest.TestCase):
    def test_load_config_formats_paths_and_filenames(self):
        config_text = textwrap.dedent(
            """
            paths:
              data_dir: /tmp/mapillary-data
              processed_dir: "{data_dir}/processed"
              starter_dir: "{data_dir}/starter"
              tiles_save_dir: "{processed_dir}/tiles"
              final_unfiltered_dir: "{processed_dir}/unfiltered"
              keep_number: 42
            filenames:
              report_file: "{starter_dir}/report.parquet"
              absolute_file: "{processed_dir}/report.csv"
              keep_boolean: false
            """
        )

        with TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.yaml"
            config_path.write_text(config_text, encoding="utf-8")

            cfg = load_config(str(config_path))

        self.assertEqual(cfg["paths"]["processed_dir"], "/tmp/mapillary-data/processed")
        self.assertEqual(cfg["paths"]["starter_dir"], "/tmp/mapillary-data/starter")
        self.assertEqual(cfg["paths"]["tiles_save_dir"], "/tmp/mapillary-data/processed/tiles")
        self.assertEqual(cfg["paths"]["final_unfiltered_dir"], "/tmp/mapillary-data/processed/unfiltered")
        self.assertEqual(cfg["filenames"]["report_file"], "/tmp/mapillary-data/starter/report.parquet")
        self.assertEqual(cfg["filenames"]["absolute_file"], "/tmp/mapillary-data/processed/report.csv")

    def test_load_config_keeps_non_string_values_unchanged(self):
        config_text = textwrap.dedent(
            """
            paths:
              data_dir: /tmp/mapillary-data
              processed_dir: "{data_dir}/processed"
              starter_dir: "{data_dir}/starter"
              retries: 3
              enabled: true
            filenames:
              empty_name: ""
              expected_null: null
            """
        )

        with TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.yaml"
            config_path.write_text(config_text, encoding="utf-8")

            cfg = load_config(str(config_path))

        self.assertEqual(cfg["paths"]["retries"], 3)
        self.assertTrue(cfg["paths"]["enabled"])
        self.assertEqual(cfg["filenames"]["empty_name"], "")
        self.assertIsNone(cfg["filenames"]["expected_null"])

    def test_load_config_uses_data_dir_fallback_when_starter_dir_missing(self):
        config_text = textwrap.dedent(
            """
            paths:
              data_dir: /tmp/mapillary-data
              processed_dir: "{data_dir}/processed"
            filenames:
              report_file: "{starter_dir}/report.parquet"
              processed_file: "{processed_dir}/summary.csv"
            """
        )

        with TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.yaml"
            config_path.write_text(config_text, encoding="utf-8")

            cfg = load_config(str(config_path))

        self.assertEqual(cfg["filenames"]["report_file"], "/tmp/mapillary-data/report.parquet")
        self.assertEqual(cfg["filenames"]["processed_file"], "/tmp/mapillary-data/processed/summary.csv")

