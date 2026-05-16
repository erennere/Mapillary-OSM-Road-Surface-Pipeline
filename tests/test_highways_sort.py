"""Tests for highways_sort.py – filter_and_copy_file, process_single_tile, process_file."""
import importlib
import os
import random
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

RESEARCH_CODE_DIR = Path(__file__).resolve().parents[1] / "research_code"
if str(RESEARCH_CODE_DIR) not in sys.path:
    sys.path.insert(0, str(RESEARCH_CODE_DIR))


def import_highways_sort():
    for mod in list(sys.modules.keys()):
        if mod.startswith("highways_sort") or mod == "highways_sort":
            del sys.modules[mod]

    fake_duckdb = types.ModuleType("duckdb")
    fake_duckdb.connect = None   # placeholder so patch.object can replace it
    fake_duckdb.sql = lambda q: type("R", (), {"df": lambda self: type("DF", (), {"tolist": lambda self: []})()})()

    fake_pd = types.ModuleType("pandas")
    fake_start = types.ModuleType("start")
    fake_start.load_config = lambda path=None: {}

    fake_mif = types.ModuleType("metadata_intersections_and_filtering")
    fake_mif.finding_tiles_list_for_urban_areas = lambda geom, zoom: []
    fake_mif.layer_intersections = lambda *a, **k: []

    with mock.patch.dict(
        sys.modules,
        {
            "duckdb": fake_duckdb,
            "pandas": fake_pd,
            "start": fake_start,
            "metadata_intersections_and_filtering": fake_mif,
        },
    ):
        return importlib.import_module("highways_sort")


class FilterAndCopyFileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_highways_sort()

    def _make_conn(self, fail_at=None):
        """Build a recording connection that optionally raises at a query index."""
        calls = []
        obj = self

        class Conn:
            def __init__(self):
                self._n = 0
                self.closed = False

            def execute(self, query):
                calls.append(query)
                self._n += 1
                if fail_at is not None and self._n >= fail_at:
                    raise RuntimeError("simulated failure")

            def create_function(self, *args, **kwargs):
                pass

            def close(self):
                self.closed = True

        return Conn(), calls

    def test_success_installs_spatial_and_executes_query(self):
        gen = random.Random(3001)
        osm_filepath = f"/data/osm_{gen.randint(100, 999)}.parquet"
        saving_dir = f"/tmp/out_{gen.randint(100, 999)}"
        cont_file = f"/data/conts_{gen.randint(100, 999)}.parquet"
        cntry_file = f"/data/countries_{gen.randint(100, 999)}.parquet"
        temp_suffix = gen.randint(0, int(1e12))
        conn, calls = self._make_conn()

        with (
            mock.patch.object(self.module.duckdb, "connect", return_value=conn),
            mock.patch.object(self.module.random, "randint", return_value=temp_suffix),
            mock.patch.object(self.module.os, "makedirs"),
            mock.patch.object(self.module.os.path, "exists", side_effect=lambda p: p == f"temp_{temp_suffix}.db"),
            mock.patch.object(self.module.os, "remove"),
        ):
            result = self.module.filter_and_copy_file(
                osm_filepath, saving_dir, 8, cont_file, cntry_file, retries=1
            )

        self.assertTrue(result)
        self.assertTrue(any("SPATIAL" in c.upper() for c in calls))
        self.assertTrue(conn.closed)

    def test_cleans_up_temp_db_on_exception(self):
        gen = random.Random(3002)
        temp_suffix = gen.randint(0, int(1e12))
        conn, _ = self._make_conn(fail_at=1)

        removed = []

        with (
            mock.patch.object(self.module.duckdb, "connect", return_value=conn),
            mock.patch.object(self.module.random, "randint", return_value=temp_suffix),
            mock.patch.object(self.module.os, "makedirs"),
            mock.patch.object(self.module.os.path, "exists",
                              side_effect=lambda p: p == f"temp_{temp_suffix}.db"),
            mock.patch.object(self.module.os, "remove", side_effect=removed.append),
        ):
            self.module.filter_and_copy_file(
                "/data/osm.parquet", "/tmp/out", 8, "/c.parquet", "/cntry.parquet", retries=1
            )

        self.assertIn(f"temp_{temp_suffix}.db", removed)
        self.assertTrue(conn.closed)

    def test_returns_false_on_unrecoverable_error(self):
        gen = random.Random(3003)
        temp_suffix = gen.randint(0, int(1e12))

        with (
            mock.patch.object(self.module.duckdb, "connect", side_effect=RuntimeError("no db")),
            mock.patch.object(self.module.random, "randint", return_value=temp_suffix),
            mock.patch.object(self.module.os, "makedirs"),
            mock.patch.object(self.module.os.path, "exists", return_value=False),
            mock.patch.object(self.module.os, "remove"),
        ):
            result = self.module.filter_and_copy_file(
                "/data/osm.parquet", "/tmp/out", 8, "/c.parquet", "/cntry.parquet", retries=2
            )

        self.assertFalse(result)

    def test_query_contains_osm_filepath_and_zoom_level(self):
        gen = random.Random(3004)
        osm_filepath = f"/data/osm_{gen.randint(100, 999)}.parquet"
        zoom_level = gen.randint(5, 14)
        temp_suffix = gen.randint(0, int(1e12))
        conn, calls = self._make_conn()

        with (
            mock.patch.object(self.module.duckdb, "connect", return_value=conn),
            mock.patch.object(self.module.random, "randint", return_value=temp_suffix),
            mock.patch.object(self.module.os, "makedirs"),
            mock.patch.object(self.module.os.path, "exists",
                              side_effect=lambda p: p == f"temp_{temp_suffix}.db"),
            mock.patch.object(self.module.os, "remove"),
        ):
            self.module.filter_and_copy_file(
                osm_filepath, "/tmp/out", zoom_level, "/c.parquet", "/cntry.parquet", retries=1
            )

        exec_queries = [c for c in calls if osm_filepath in c or str(zoom_level) in c]
        self.assertTrue(len(exec_queries) > 0)


class ProcessSingleTileHighwaysTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_highways_sort()

    def _make_counting_conn(self, total_rows, fail_count=False):
        calls = []

        class FetchResult:
            def fetchone(self):
                return (total_rows,)

        class Conn:
            def __init__(self):
                self.closed = False
                self._n = 0

            def execute(self, query):
                calls.append(query)
                self._n += 1
                if fail_count and self._n == 1:
                    raise RuntimeError("count fail")
                return FetchResult()

            def close(self):
                self.closed = True

        return Conn(), calls

    def test_zero_rows_returns_true_without_writing_chunks(self):
        gen = random.Random(3010)
        tile = f"{gen.randint(0, 100)}-{gen.randint(0, 100)}-8"
        temp_suffix = gen.randint(0, int(1e12))
        conn, _ = self._make_counting_conn(total_rows=0)

        with (
            mock.patch.object(self.module.duckdb, "connect", return_value=conn),
            mock.patch.object(self.module.random, "randint", return_value=temp_suffix),
            mock.patch.object(self.module.os, "makedirs"),
            mock.patch.object(self.module.os.path, "exists",
                              side_effect=lambda p: p == f"temp_{temp_suffix}.db"),
            mock.patch.object(self.module.os, "remove"),
            mock.patch.object(self.module.time, "sleep"),
        ):
            result = self.module.process_single_tile(tile, "/tmp/saving", "/tmp/osm", 8)

        self.assertTrue(result)

    def test_nonzero_rows_writes_correct_number_of_chunks(self):
        gen = random.Random(3011)
        tile = f"{gen.randint(0, 100)}-{gen.randint(0, 100)}-8"
        chunk_size = gen.randint(3, 7)
        total_rows = chunk_size * gen.randint(2, 4) + gen.randint(1, chunk_size - 1)
        temp_suffix = gen.randint(0, int(1e12))
        conn, calls = self._make_counting_conn(total_rows)

        with (
            mock.patch.object(self.module.duckdb, "connect", return_value=conn),
            mock.patch.object(self.module.random, "randint", return_value=temp_suffix),
            mock.patch.object(self.module.os, "makedirs"),
            mock.patch.object(self.module.os.path, "exists",
                              side_effect=lambda p: p == f"temp_{temp_suffix}.db"),
            mock.patch.object(self.module.os, "remove"),
            mock.patch.object(self.module.time, "sleep"),
        ):
            result = self.module.process_single_tile(
                tile, "/tmp/saving", "/tmp/osm", 8, chunk_size=chunk_size, retries=1
            )

        self.assertTrue(result)
        expected_chunks = (total_rows + chunk_size - 1) // chunk_size
        copy_queries = [c for c in calls if "COPY" in c.upper()]
        self.assertEqual(len(copy_queries), expected_chunks)

    def test_cleans_up_temp_db_after_processing(self):
        gen = random.Random(3012)
        tile = f"{gen.randint(0, 100)}-{gen.randint(0, 100)}-8"
        temp_suffix = gen.randint(0, int(1e12))
        conn, _ = self._make_counting_conn(0)

        removed = []

        with (
            mock.patch.object(self.module.duckdb, "connect", return_value=conn),
            mock.patch.object(self.module.random, "randint", return_value=temp_suffix),
            mock.patch.object(self.module.os, "makedirs"),
            mock.patch.object(self.module.os.path, "exists",
                              side_effect=lambda p: p == f"temp_{temp_suffix}.db"),
            mock.patch.object(self.module.os, "remove", side_effect=removed.append),
            mock.patch.object(self.module.time, "sleep"),
        ):
            self.module.process_single_tile(tile, "/tmp/saving", "/tmp/osm", 8)

        self.assertIn(f"temp_{temp_suffix}.db", removed)
        self.assertTrue(conn.closed)

    def test_returns_false_on_connection_error(self):
        gen = random.Random(3013)
        tile = f"{gen.randint(0, 100)}-{gen.randint(0, 100)}-8"
        temp_suffix = gen.randint(0, int(1e12))

        with (
            mock.patch.object(self.module.duckdb, "connect", side_effect=RuntimeError("no db")),
            mock.patch.object(self.module.random, "randint", return_value=temp_suffix),
            mock.patch.object(self.module.os, "makedirs"),
            mock.patch.object(self.module.os.path, "exists", return_value=False),
            mock.patch.object(self.module.os, "remove"),
        ):
            result = self.module.process_single_tile(tile, "/tmp/saving", "/tmp/osm", 8)

        self.assertFalse(result)


class ProcessFileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_highways_sort()

    def _args(self, gen, is_first=False):
        filename = f"osm_{gen.randint(1000, 9999)}.parquet"
        return (
            filename, is_first,
            f"/ohsome_{gen.randint(100, 999)}",
            f"/osm_save_{gen.randint(100, 999)}",
            f"/conts_{gen.randint(100, 999)}",
            f"/proc_{gen.randint(100, 999)}",
            8,
            f"/cont_{gen.randint(100, 999)}.parquet",
            f"/cntry_{gen.randint(100, 999)}.parquet",
            f"conts_{gen.randint(100, 999)}.parquet",
            f"cntry_{gen.randint(100, 999)}.parquet",
            f"s3://bucket_{gen.randint(100, 999)}",
            f"ghsl_{gen.randint(100, 999)}.gpkg",
            f"afric_{gen.randint(100, 999)}.shp",
            gen.randint(1, 5),
            0.1,
        )

    def test_non_first_file_calls_filter_and_copy_returns_none(self):
        gen = random.Random(3020)
        args = self._args(gen, is_first=False)

        with mock.patch.object(self.module, "filter_and_copy_file", return_value=True) as mock_fcf:
            result = self.module.process_file(args)

        self.assertIsNone(result)
        mock_fcf.assert_called_once()

    def test_first_file_calls_layer_intersections_and_filter_and_copy(self):
        gen = random.Random(3021)
        args = self._args(gen, is_first=True)
        urban_fps = [f"/ghsl_{gen.randint(100, 999)}.parquet"]

        with (
            mock.patch.object(self.module, "layer_intersections", return_value=urban_fps) as mock_li,
            mock.patch.object(self.module, "filter_and_copy_file", return_value=True) as mock_fcf,
        ):
            result = self.module.process_file(args)

        mock_li.assert_called_once()
        mock_fcf.assert_called_once()
        self.assertIs(result, urban_fps)

    def test_non_first_file_passes_correct_osm_filepath_to_filter(self):
        gen = random.Random(3022)
        args = self._args(gen, is_first=False)
        filename = args[0]
        ohsome_dir = args[2]
        expected_path = os.path.join(ohsome_dir, filename)

        captured = []

        def capture_fcf(osm_fp, *a, **k):
            captured.append(osm_fp)
            return True

        with mock.patch.object(self.module, "filter_and_copy_file", side_effect=capture_fcf):
            self.module.process_file(args)

        self.assertEqual(captured[0], expected_path)
