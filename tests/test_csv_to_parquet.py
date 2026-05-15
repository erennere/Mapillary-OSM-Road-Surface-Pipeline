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
