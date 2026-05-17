import importlib
import random
import sys
import types
import unittest
from pathlib import Path
from unittest import mock


RESEARCH_CODE_DIR = Path(__file__).resolve().parents[1] / "research_code"
if str(RESEARCH_CODE_DIR) not in sys.path:
    sys.path.insert(0, str(RESEARCH_CODE_DIR))


def import_csv_to_parquet_module():
    sys.modules.pop("csv_to_parquet", None)

    fake_duckdb = types.ModuleType("duckdb")
    fake_start = types.ModuleType("start")
    fake_start.load_config = lambda path=None: {}

    with mock.patch.dict(
        sys.modules,
        {
            "duckdb": fake_duckdb,
            "start": fake_start,
        },
    ):
        return importlib.import_module("csv_to_parquet")


class ConvertCsvToParquetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_csv_to_parquet_module()

    def test_convert_csv_to_parquet_connects_installs_spatial_and_executes_query(self):
        generator = random.Random(801)

        class RecordingConnection:
            def __init__(self):
                self.execute_calls = []
                self.closed = False

            def execute(self, query):
                self.execute_calls.append(query)

            def close(self):
                self.closed = True

        connection = RecordingConnection()
        temp_suffix = generator.randint(0, int(1e12))
        input_path = f"/tmp/data_{generator.randint(100, 999)}.csv"
        output_path = f"/tmp/output_{generator.randint(100, 999)}.parquet"

        with (
            mock.patch.object(self.module.duckdb, "connect", return_value=connection, create=True) as connect_mock,
            mock.patch.object(self.module.random, "randint", return_value=temp_suffix),
            mock.patch.object(self.module.os.path, "exists", side_effect=lambda p: p == f"csv_to_parquet_temp_{temp_suffix}.db"),
            mock.patch.object(self.module.os, "remove") as remove_mock,
        ):
            self.module.convert_csv_to_parquet(input_path, output_path)

        connect_mock.assert_called_once_with(f"csv_to_parquet_temp_{temp_suffix}.db")
        self.assertEqual(connection.execute_calls[0], "INSTALL SPATIAL;")
        self.assertEqual(connection.execute_calls[1], "LOAD SPATIAL;")
        self.assertIn(input_path, connection.execute_calls[2])
        self.assertIn(output_path, connection.execute_calls[2])
        self.assertIn("ST_AsWKB(ST_GeomFromText(geometry))", connection.execute_calls[2])
        self.assertTrue(connection.closed)
        remove_mock.assert_called_once_with(f"csv_to_parquet_temp_{temp_suffix}.db")

    def test_convert_csv_to_parquet_closes_and_cleans_up_when_query_fails(self):
        generator = random.Random(802)

        class FailingConnection:
            def __init__(self):
                self.execute_calls = []
                self.closed = False

            def execute(self, query):
                self.execute_calls.append(query)
                if len(self.execute_calls) >= 3:
                    raise RuntimeError("boom")

            def close(self):
                self.closed = True

        connection = FailingConnection()
        temp_suffix = generator.randint(0, int(1e12))

        with (
            mock.patch.object(self.module.duckdb, "connect", return_value=connection, create=True),
            mock.patch.object(self.module.random, "randint", return_value=temp_suffix),
            mock.patch.object(self.module.os.path, "exists", side_effect=lambda p: p == f"csv_to_parquet_temp_{temp_suffix}.db"),
            mock.patch.object(self.module.os, "remove") as remove_mock,
        ):
            self.module.convert_csv_to_parquet(
                f"/tmp/in_{generator.randint(100, 999)}.csv",
                f"/tmp/out_{generator.randint(100, 999)}.parquet",
            )

        self.assertTrue(connection.closed)
        remove_mock.assert_called_once_with(f"csv_to_parquet_temp_{temp_suffix}.db")

    def test_convert_csv_to_parquet_does_not_remove_temp_db_if_it_does_not_exist(self):
        generator = random.Random(803)

        class RecordingConnection:
            def __init__(self):
                self.closed = False

            def execute(self, query):
                pass

            def close(self):
                self.closed = True

        connection = RecordingConnection()
        temp_suffix = generator.randint(0, int(1e12))

        with (
            mock.patch.object(self.module.duckdb, "connect", return_value=connection, create=True),
            mock.patch.object(self.module.random, "randint", return_value=temp_suffix),
            mock.patch.object(self.module.os.path, "exists", return_value=False),
            mock.patch.object(self.module.os, "remove") as remove_mock,
        ):
            self.module.convert_csv_to_parquet(
                f"/tmp/in_{generator.randint(100, 999)}.csv",
                f"/tmp/out_{generator.randint(100, 999)}.parquet",
            )

        remove_mock.assert_not_called()
        self.assertTrue(connection.closed)

    def test_convert_csv_to_parquet_query_includes_all_expected_columns(self):
        generator = random.Random(804)
        queries_seen = []

        class CapturingConnection:
            def __init__(self):
                self.closed = False

            def execute(self, query):
                queries_seen.append(query)

            def close(self):
                self.closed = True

        connection = CapturingConnection()
        temp_suffix = generator.randint(0, int(1e12))
        input_path = f"/tmp/seeded_{generator.randint(1000, 9999)}.csv"
        output_path = f"/tmp/seeded_out_{generator.randint(1000, 9999)}.parquet"

        with (
            mock.patch.object(self.module.duckdb, "connect", return_value=connection, create=True),
            mock.patch.object(self.module.random, "randint", return_value=temp_suffix),
            mock.patch.object(self.module.os.path, "exists", return_value=False),
            mock.patch.object(self.module.os, "remove"),
        ):
            self.module.convert_csv_to_parquet(input_path, output_path)

        conversion_query = queries_seen[2]
        for col in ["sequence", "id", "url", "long", "lat", "geometry", "height",
                    "width", "altitude", "make", "model", "creator", "is_pano", "timestamp"]:
            self.assertIn(col, conversion_query)
        self.assertIn("FORMAT PARQUET", conversion_query)
        self.assertIn("zstd", conversion_query)


class CsvToParquetMainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_csv_to_parquet_module()

    def test_main_exits_with_usage_when_tile_argument_missing(self):
        cfg = {
            "paths": {
                "splitted_raw_metadata_dir": "/tmp/splitted",
                "tile_partitioned_parquet_raw_metadata_dir": "/tmp/parquet",
                "raw_metadata_dir": "/tmp/raw",
            },
            "csv_split_params": {"updated_after": "2000-01-01T00:00:00"},
        }

        with (
            mock.patch.object(self.module, "load_config", return_value=cfg),
            mock.patch.object(self.module.sys, "argv", ["csv_to_parquet.py"]),
            mock.patch.object(self.module.os, "chdir"),
        ):
            with self.assertRaises(SystemExit):
                self.module.main()

    def test_main_uses_splitted_files_when_available(self):
        cfg = {
            "paths": {
                "splitted_raw_metadata_dir": "/tmp/splitted",
                "tile_partitioned_parquet_raw_metadata_dir": "/tmp/parquet",
                "raw_metadata_dir": "/tmp/raw",
            },
            "csv_split_params": {"updated_after": "2000-01-01T00:00:00"},
        }
        tile = "159-145-8"

        converted = []

        def fake_exists(path):
            norm = path.replace("\\", "/")
            if norm.endswith("/tmp/splitted"):
                return True
            if norm.endswith(f"/tmp/parquet/tile={tile}"):
                return False
            return False

        with (
            mock.patch.object(self.module, "load_config", return_value=cfg),
            mock.patch.object(self.module.sys, "argv", ["csv_to_parquet.py", tile]),
            mock.patch.object(self.module.os, "chdir"),
            mock.patch.object(self.module.os.path, "exists", side_effect=fake_exists),
            mock.patch.object(self.module.os, "listdir", return_value=[f"metadata_unfiltered_{tile}_part_1.csv", "missing_sequences_x.csv"]),
            mock.patch.object(self.module.os.path, "getmtime", return_value=32503680000),
            mock.patch.object(self.module.os, "makedirs"),
            mock.patch.object(self.module, "convert_csv_to_parquet", side_effect=lambda i, o: converted.append((i, o))),
        ):
            self.module.main()

        self.assertEqual(len(converted), 1)
        self.assertIn("/tmp/splitted", converted[0][0].replace("\\", "/"))
        self.assertIn(f"/tmp/parquet/tile={tile}", converted[0][1].replace("\\", "/"))

    def test_main_falls_back_to_raw_metadata_when_no_recent_split(self):
        cfg = {
            "paths": {
                "splitted_raw_metadata_dir": "/tmp/splitted",
                "tile_partitioned_parquet_raw_metadata_dir": "/tmp/parquet",
                "raw_metadata_dir": "/tmp/raw",
            },
            "csv_split_params": {"updated_after": "2100-01-01T00:00:00"},
        }
        tile = "160-141-8"
        raw_file = f"metadata_unfiltered_{tile}.csv"

        converted = []

        def fake_exists(path):
            norm = path.replace("\\", "/")
            if norm.endswith("/tmp/splitted"):
                return True
            if norm.endswith(f"/tmp/raw/{raw_file}"):
                return True
            if norm.endswith(f"/tmp/parquet/tile={tile}"):
                return False
            return False

        with (
            mock.patch.object(self.module, "load_config", return_value=cfg),
            mock.patch.object(self.module.sys, "argv", ["csv_to_parquet.py", tile]),
            mock.patch.object(self.module.os, "chdir"),
            mock.patch.object(self.module.os.path, "exists", side_effect=fake_exists),
            mock.patch.object(self.module.os, "listdir", return_value=[f"metadata_unfiltered_{tile}_old.csv"]),
            mock.patch.object(self.module.os.path, "getmtime", return_value=946684800),
            mock.patch.object(self.module.os, "makedirs"),
            mock.patch.object(self.module, "convert_csv_to_parquet", side_effect=lambda i, o: converted.append((i, o))),
        ):
            self.module.main()

        self.assertEqual(len(converted), 1)
        self.assertIn(f"/tmp/raw/{raw_file}", converted[0][0].replace("\\", "/"))

    def test_main_accepts_tile_prefixed_argument_format(self):
        cfg = {
            "paths": {
                "splitted_raw_metadata_dir": "/tmp/splitted",
                "tile_partitioned_parquet_raw_metadata_dir": "/tmp/parquet",
                "raw_metadata_dir": "/tmp/raw",
            },
            "csv_split_params": {"updated_after": "2100-01-01T00:00:00"},
        }
        tile = "160-141-8"
        tile_arg = f"tile={tile}"
        raw_file = f"metadata_unfiltered_{tile}.csv"

        converted = []

        def fake_exists(path):
            norm = path.replace("\\", "/")
            if norm.endswith("/tmp/splitted"):
                return True
            if norm.endswith(f"/tmp/raw/{raw_file}"):
                return True
            if norm.endswith(f"/tmp/parquet/tile={tile}"):
                return False
            return False

        with (
            mock.patch.object(self.module, "load_config", return_value=cfg),
            mock.patch.object(self.module.sys, "argv", ["csv_to_parquet.py", tile_arg]),
            mock.patch.object(self.module.os, "chdir"),
            mock.patch.object(self.module.os.path, "exists", side_effect=fake_exists),
            mock.patch.object(self.module.os, "listdir", return_value=[f"metadata_unfiltered_{tile}_old.csv"]),
            mock.patch.object(self.module.os.path, "getmtime", return_value=946684800),
            mock.patch.object(self.module.os, "makedirs"),
            mock.patch.object(self.module, "convert_csv_to_parquet", side_effect=lambda i, o: converted.append((i, o))),
        ):
            self.module.main()

        self.assertEqual(len(converted), 1)
        self.assertIn(f"/tmp/raw/{raw_file}", converted[0][0].replace("\\", "/"))
        self.assertIn(f"/tmp/parquet/tile={tile}", converted[0][1].replace("\\", "/"))
