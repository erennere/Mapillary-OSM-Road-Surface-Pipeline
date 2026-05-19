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

import start as real_start


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
    fake_start.__getattr__ = lambda name: getattr(real_start, name)

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

    def test_returns_false_when_all_copy_query_retries_fail(self):
        gen = random.Random(3005)
        temp_suffix = gen.randint(0, int(1e12))

        class Conn:
            def __init__(self):
                self._calls = 0
                self.closed = False

            def execute(self, query):
                self._calls += 1
                if self._calls >= 2:
                    raise RuntimeError("copy fail")

            def create_function(self, *args, **kwargs):
                pass

            def close(self):
                self.closed = True

        conn = Conn()

        with (
            mock.patch.object(self.module.duckdb, "connect", return_value=conn),
            mock.patch.object(self.module.random, "randint", return_value=temp_suffix),
            mock.patch.object(self.module.os, "makedirs"),
            mock.patch.object(self.module.os.path, "exists", return_value=False),
            mock.patch.object(self.module.os, "remove"),
            mock.patch.object(self.module.time, "sleep"),
        ):
            result = self.module.filter_and_copy_file(
                "/data/osm.parquet", "/tmp/out", 8, "/c.parquet", "/cntry.parquet", retries=2
            )

        self.assertFalse(result)
        self.assertTrue(conn.closed)

    def test_does_not_execute_debug_side_effect_query(self):
        gen = random.Random(3006)
        temp_suffix = gen.randint(0, int(1e12))

        class Conn:
            def __init__(self):
                self.calls = []
                self.closed = False

            def execute(self, query):
                self.calls.append(query)
                if "FROM (SELECT * FROM read_parquet" in query:
                    raise RuntimeError("unexpected debug query")

            def create_function(self, *args, **kwargs):
                pass

            def close(self):
                self.closed = True

        conn = Conn()

        with (
            mock.patch.object(self.module.duckdb, "connect", return_value=conn),
            mock.patch.object(self.module.random, "randint", return_value=temp_suffix),
            mock.patch.object(self.module.os, "makedirs"),
            mock.patch.object(self.module.os.path, "exists", return_value=False),
            mock.patch.object(self.module.os, "remove"),
        ):
            result = self.module.filter_and_copy_file(
                "/data/osm.parquet", "/tmp/out", 8, "/c.parquet", "/cntry.parquet", retries=1
            )

        self.assertTrue(result)
        self.assertTrue(conn.closed)


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

    def test_returns_false_when_count_query_retries_exhausted(self):
        gen = random.Random(3014)
        tile = f"{gen.randint(0, 100)}-{gen.randint(0, 100)}-8"
        temp_suffix = gen.randint(0, int(1e12))
        conn, _ = self._make_counting_conn(total_rows=5, fail_count=True)

        with (
            mock.patch.object(self.module.duckdb, "connect", return_value=conn),
            mock.patch.object(self.module.random, "randint", return_value=temp_suffix),
            mock.patch.object(self.module.os, "makedirs"),
            mock.patch.object(self.module.os.path, "exists", side_effect=lambda p: p == f"temp_{temp_suffix}.db"),
            mock.patch.object(self.module.os, "remove"),
            mock.patch.object(self.module.time, "sleep"),
        ):
            result = self.module.process_single_tile(tile, "/tmp/saving", "/tmp/osm", 8, retries=1)

        self.assertFalse(result)

    def test_returns_false_when_chunk_write_retries_exhausted(self):
        gen = random.Random(3015)
        tile = f"{gen.randint(0, 100)}-{gen.randint(0, 100)}-8"
        temp_suffix = gen.randint(0, int(1e12))

        class FetchResult:
            def fetchone(self):
                return (3,)

        class Conn:
            def __init__(self):
                self.closed = False

            def execute(self, query):
                if "COUNT(*)" in query:
                    return FetchResult()
                raise RuntimeError("copy fail")

            def close(self):
                self.closed = True

        conn = Conn()

        with (
            mock.patch.object(self.module.duckdb, "connect", return_value=conn),
            mock.patch.object(self.module.random, "randint", return_value=temp_suffix),
            mock.patch.object(self.module.os, "makedirs"),
            mock.patch.object(self.module.os.path, "exists", side_effect=lambda p: p == f"temp_{temp_suffix}.db"),
            mock.patch.object(self.module.os, "remove"),
            mock.patch.object(self.module.time, "sleep"),
        ):
            result = self.module.process_single_tile(tile, "/tmp/saving", "/tmp/osm", 8, chunk_size=2, retries=1)

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


class HiveAndMainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_highways_sort()

    def _cfg(self):
        return {
            "paths": {
                "ohsome_osm_dir": "/tmp/ohsome",
                "osm_saving_dir": "/tmp/osm_saving",
                "osm_partitioned_dir": "/tmp/osm_partitioned",
                "processed_dir": "/tmp/processed",
                "continents_dir": "/tmp/continents",
            },
            "params": {
                "zoom_level": 8,
                "n_max_rows_parquet": 1000,
            },
            "metadata_params": {
                "retries": 2,
                "sleep_time": 1,
                "max_workers": 2,
            },
            "filenames": {
                "continents_filename": "continents.parquet",
                "overture_url": "s3://bucket/divisions",
                "country_filename": "countries.parquet",
                "ghsl_filename": "ghsl.gpkg",
                "africapolis_filename": "africa.shp",
            },
        }

    def test_hive_partition_osm_processes_tiles(self):
        class FakeFuture:
            def __init__(self, value):
                self._value = value

            def result(self):
                return self._value

        class FakeExecutor:
            def __init__(self, max_workers=None):
                pass

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def submit(self, fn, *args, **kwargs):
                return FakeFuture(True)

        class FakeDf:
            def __getitem__(self, key):
                return type("Col", (), {"tolist": lambda self: ["1-2-8", "2-3-8"]})()

        with (
            mock.patch.object(self.module.duckdb, "sql", return_value=type("R", (), {"df": lambda self: FakeDf()})()),
            mock.patch.object(self.module, "ProcessPoolExecutor", side_effect=FakeExecutor),
            mock.patch.object(self.module, "as_completed", side_effect=lambda futures: futures),
        ):
            self.module.hive_partition_osm("/tmp/osm", "/tmp/out", 8, 2, {"chunk_size": 100, "retries": 1, "sleep_time": 1})

    def test_main_returns_when_no_input_files(self):
        with (
            mock.patch.object(self.module, "load_config", return_value=self._cfg()),
            mock.patch.object(self.module.os, "chdir"),
            mock.patch.object(self.module.os, "listdir", return_value=["nope.txt"]),
            mock.patch.object(self.module, "hive_partition_osm") as hive_mock,
        ):
            self.module.main()

        hive_mock.assert_not_called()

    def test_main_processes_files_and_calls_hive_partition(self):
        class FakeExecutor:
            def __init__(self, max_workers=None):
                pass

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def map(self, fn, tasks):
                return [fn(task) for task in tasks]

        with (
            mock.patch.object(self.module, "load_config", return_value=self._cfg()),
            mock.patch.object(self.module.os, "chdir"),
            mock.patch.object(self.module.os, "listdir", return_value=["way_a.parquet", "way_b.parquet"]),
            mock.patch.object(self.module, "ProcessPoolExecutor", side_effect=FakeExecutor),
            mock.patch.object(self.module, "process_file", return_value=None),
            mock.patch.object(self.module, "hive_partition_osm") as hive_mock,
        ):
            self.module.main()

        hive_mock.assert_called_once()

    def test_main_passes_resolved_continent_filepath_to_tasks(self):
        task_capture = {}

        class FakeExecutor:
            def __init__(self, max_workers=None):
                pass

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def map(self, fn, tasks):
                task_capture["tasks"] = list(tasks)
                return [None for _ in task_capture["tasks"]]

        with (
            mock.patch.object(self.module, "load_config", return_value=self._cfg()),
            mock.patch.object(self.module.os, "chdir"),
            mock.patch.object(self.module.os, "listdir", return_value=["way_a.parquet"]),
            mock.patch.object(self.module, "ProcessPoolExecutor", side_effect=FakeExecutor),
            mock.patch.object(self.module, "hive_partition_osm"),
        ):
            self.module.main()

        self.assertTrue(task_capture["tasks"])
        continent_filepath = task_capture["tasks"][0][7]
        self.assertTrue(continent_filepath.endswith("continents.parquet"))

    def test_main_raises_when_max_workers_is_zero(self):
        cfg = self._cfg()
        cfg["metadata_params"]["max_workers"] = 0

        class FakeExecutor:
            def __init__(self, max_workers=None):
                raise AssertionError("executor should not be constructed")

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def map(self, fn, tasks):
                return [None for _ in tasks]

        with (
            mock.patch.object(self.module, "load_config", return_value=cfg),
            mock.patch.object(self.module.os, "chdir"),
            mock.patch.object(self.module.os, "listdir", return_value=["way_a.parquet"]),
            mock.patch.object(self.module, "ProcessPoolExecutor", side_effect=FakeExecutor),
            mock.patch.object(self.module, "hive_partition_osm"),
        ):
            with self.assertRaises(ValueError):
                self.module.main()

    def test_main_raises_when_max_workers_is_invalid(self):
        cfg = self._cfg()
        cfg["metadata_params"]["max_workers"] = "bad"

        class FakeExecutor:
            def __init__(self, max_workers=None):
                raise AssertionError("executor should not be constructed")

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def map(self, fn, tasks):
                return [None for _ in tasks]

        with (
            mock.patch.object(self.module, "load_config", return_value=cfg),
            mock.patch.object(self.module.os, "chdir"),
            mock.patch.object(self.module.os, "listdir", return_value=["way_a.parquet"]),
            mock.patch.object(self.module, "ProcessPoolExecutor", side_effect=FakeExecutor),
            mock.patch.object(self.module, "hive_partition_osm"),
        ):
            with self.assertRaises(ValueError):
                self.module.main()
