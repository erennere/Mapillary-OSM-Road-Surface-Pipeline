import importlib
import math
import random
import sys
import types
import unittest
from pathlib import Path
from unittest import mock


RESEARCH_CODE_DIR = Path(__file__).resolve().parents[1] / "research_code"
if str(RESEARCH_CODE_DIR) not in sys.path:
    sys.path.insert(0, str(RESEARCH_CODE_DIR))


class FakeNumpy(types.ModuleType):
    def __init__(self):
        super().__init__("numpy")

    @staticmethod
    def radians(values):
        return [math.radians(value) for value in values]

    @staticmethod
    def sin(value):
        return math.sin(value)

    @staticmethod
    def cos(value):
        return math.cos(value)

    @staticmethod
    def arctan2(left, right):
        return math.atan2(left, right)

    @staticmethod
    def sqrt(value):
        return math.sqrt(value)


def import_find_osm_segments_module():
    sys.modules.pop("find_osm_segments", None)

    fake_duckdb = types.ModuleType("duckdb")

    with mock.patch.dict(
        sys.modules,
        {
            "numpy": FakeNumpy(),
            "duckdb": fake_duckdb,
        },
    ):
        return importlib.import_module("find_osm_segments")


class FindOsmSegmentsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_find_osm_segments_module()

    @staticmethod
    def _wkt(longitude, latitude):
        return f"POINT ({longitude} {latitude})"

    @staticmethod
    def _expected_haversine(point1, point2, earth_radius=6371008):
        lon1, lat1 = point1
        lon2, lat2 = point2
        lat1 = math.radians(lat1)
        lon1 = math.radians(lon1)
        lat2 = math.radians(lat2)
        lon2 = math.radians(lon2)
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return earth_radius * c

    def test_haversine_returns_zero_for_identical_random_points(self):
        generator = random.Random(401)

        for _ in range(20):
            point = (
                generator.uniform(-179.0, 179.0),
                generator.uniform(-80.0, 80.0),
            )
            distance = self.module.haversine(self._wkt(*point), self._wkt(*point))
            self.assertEqual(distance, 0.0)

    def test_haversine_matches_independent_formula_for_seeded_random_pairs(self):
        generator = random.Random(402)

        for _ in range(25):
            point1 = (
                generator.uniform(-179.0, 179.0),
                generator.uniform(-80.0, 80.0),
            )
            point2 = (
                generator.uniform(-179.0, 179.0),
                generator.uniform(-80.0, 80.0),
            )

            observed = self.module.haversine(self._wkt(*point1), self._wkt(*point2))
            expected = self._expected_haversine(point1, point2)

            self.assertAlmostEqual(observed, expected, places=9)
            self.assertAlmostEqual(
                observed,
                self.module.haversine(self._wkt(*point2), self._wkt(*point1)),
                places=9,
            )

    def test_calculate_distance_registers_haversine_and_cleans_up_with_seeded_random_inputs(self):
        generator = random.Random(701)

        class RecordingConnection:
            def __init__(self):
                self.execute_calls = []
                self.create_function_calls = []
                self.closed = False

            def execute(self, query):
                self.execute_calls.append(query)

            def create_function(self, *args):
                self.create_function_calls.append(args)

            def close(self):
                self.closed = True

        connection = RecordingConnection()
        points_filepath = f"/tmp/points_{generator.randint(100, 999)}.parquet"
        osm_filepath = f"/tmp/osm_{generator.randint(100, 999)}.parquet"
        saving_filedir = f"/tmp/output_{generator.randint(100, 999)}"
        index = generator.randint(1, 9)
        delta_x = generator.randint(10, 90)
        delta_y = generator.randint(10, 90)
        zoom_level = generator.randint(1, 14)
        distance_threshold = generator.randint(5, 40)
        temp_suffix = generator.randint(10_000, 99_999)
        fake_haversine = lambda *args: 0.0

        with (
            mock.patch.object(self.module.duckdb, "connect", return_value=connection, create=True) as connect_mock,
            mock.patch.object(self.module.random, "randint", return_value=temp_suffix),
            mock.patch.object(self.module.os.path, "exists", side_effect=lambda path: path == f"temp_{temp_suffix}.db"),
            mock.patch.object(self.module.os, "remove") as remove_mock,
        ):
            self.module.calculate_distance(
                points_filepath,
                osm_filepath,
                saving_filedir,
                index,
                delta_x,
                delta_y,
                zoom_level=zoom_level,
                distance_threshold=distance_threshold,
                func=fake_haversine,
            )

        connect_mock.assert_called_once_with(f"temp_{temp_suffix}.db")
        self.assertEqual(connection.execute_calls[0], "install spatial; load spatial;")
        self.assertIn(points_filepath, connection.execute_calls[1])
        self.assertIn(osm_filepath, connection.execute_calls[1])
        self.assertIn(f"z{zoom_level}_tiles", connection.execute_calls[1])
        self.assertIn(f"WHERE distance_meter < {distance_threshold}", connection.execute_calls[1])
        self.assertIn(f"{saving_filedir}/osm_{index}_", connection.execute_calls[1])
        self.assertEqual(
            connection.create_function_calls,
            [("haversine", fake_haversine, ["VARCHAR", "VARCHAR", "DOUBLE"], "DOUBLE")],
        )
        self.assertTrue(connection.closed)
        remove_mock.assert_called_once_with(f"temp_{temp_suffix}.db")

    def test_calculate_distance_still_closes_and_removes_temp_db_when_query_fails(self):
        generator = random.Random(702)

        class FailingConnection:
            def __init__(self):
                self.execute_calls = []
                self.closed = False

            def execute(self, query):
                self.execute_calls.append(query)
                if len(self.execute_calls) == 2:
                    raise RuntimeError("boom")

            def create_function(self, *args):
                pass

            def close(self):
                self.closed = True

        connection = FailingConnection()
        temp_suffix = generator.randint(10_000, 99_999)

        with (
            mock.patch.object(self.module.duckdb, "connect", return_value=connection, create=True),
            mock.patch.object(self.module.random, "randint", return_value=temp_suffix),
            mock.patch.object(self.module.os.path, "exists", side_effect=lambda path: path == f"temp_{temp_suffix}.db"),
            mock.patch.object(self.module.os, "remove") as remove_mock,
        ):
            self.module.calculate_distance(
                f"/tmp/points_{generator.randint(100, 999)}.parquet",
                f"/tmp/osm_{generator.randint(100, 999)}.parquet",
                f"/tmp/output_{generator.randint(100, 999)}",
                generator.randint(1, 9),
                generator.randint(10, 90),
                generator.randint(10, 90),
            )

        self.assertEqual(len(connection.execute_calls), 2)
        self.assertTrue(connection.closed)
        remove_mock.assert_called_once_with(f"temp_{temp_suffix}.db")


class FindOsmSegmentsMainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_find_osm_segments_module()

    def _cfg(self):
        return {
            "params": {
                "earth_radius": 6371008,
                "zoom_level": 8,
                "distance_threshold": 20,
            },
            "paths": {
                "unfiltered_metadata_dir": "/tmp/unfiltered",
                "osm_partitioned_dir": "/tmp/osm",
                "osm_intersections_dir": "/tmp/intersections",
            },
            "metadata_params": {"updated_after": "2000-01-01T00:00:00"},
        }

    def test_main_exits_when_no_input_argument(self):
        with (
            mock.patch.object(self.module, "load_config", return_value=self._cfg(), create=True),
            mock.patch.object(self.module.sys, "argv", ["find_osm_segments.py"]),
            mock.patch.object(self.module.os, "chdir"),
        ):
            with self.assertRaises(SystemExit):
                self.module.main()

    def test_main_skips_old_metadata_file(self):
        cfg = self._cfg()
        cfg["metadata_params"]["updated_after"] = "2100-01-01T00:00:00"
        filename = "metadata_unfiltered_159-145-8_part.parquet"

        with (
            mock.patch.object(self.module, "load_config", return_value=cfg, create=True),
            mock.patch.object(self.module.sys, "argv", ["find_osm_segments.py", filename]),
            mock.patch.object(self.module.os, "chdir"),
            mock.patch.object(self.module.os.path, "getmtime", return_value=946684800),
            mock.patch.object(self.module, "calculate_distance") as calc_mock,
        ):
            self.module.main()

        calc_mock.assert_not_called()

    def test_main_processes_each_osm_file_for_recent_metadata(self):
        filename = "metadata_unfiltered_159-145-8_part.parquet"
        calls = []

        def fake_exists(path):
            norm = str(path).replace("\\", "/")
            return not norm.endswith("/tmp/intersections/tile=159-145-8")

        with (
            mock.patch.object(self.module, "load_config", return_value=self._cfg(), create=True),
            mock.patch.object(self.module.sys, "argv", ["find_osm_segments.py", filename]),
            mock.patch.object(self.module.os, "chdir"),
            mock.patch.object(self.module.os.path, "getmtime", return_value=32503680000),
            mock.patch.object(self.module.os.path, "exists", side_effect=fake_exists),
            mock.patch.object(self.module.os.path, "isdir", return_value=True),
            mock.patch.object(self.module.os, "makedirs") as makedirs_mock,
            mock.patch.object(self.module.os, "listdir", return_value=["a.parquet", "b.parquet", "x.txt"]),
            mock.patch.object(self.module, "calculate_distance", side_effect=lambda *a, **k: calls.append((a, k))),
        ):
            self.module.main()

        makedirs_mock.assert_called_once()
        self.assertEqual(len(calls), 2)

    def test_main_extracts_tile_from_filename_without_suffix(self):
        filename = "metadata_unfiltered_159-145-8.parquet"
        calls = []

        def fake_exists(path):
            norm = str(path).replace("\\", "/")
            if norm.endswith("/tmp/unfiltered/tile=159-145-8/metadata_unfiltered_159-145-8.parquet"):
                return True
            return not norm.endswith("/tmp/intersections/tile=159-145-8")

        with (
            mock.patch.object(self.module, "load_config", return_value=self._cfg(), create=True),
            mock.patch.object(self.module.sys, "argv", ["find_osm_segments.py", filename]),
            mock.patch.object(self.module.os, "chdir"),
            mock.patch.object(self.module.os.path, "getmtime", return_value=32503680000),
            mock.patch.object(self.module.os.path, "exists", side_effect=fake_exists),
            mock.patch.object(self.module.os.path, "isdir", return_value=True),
            mock.patch.object(self.module.os, "makedirs"),
            mock.patch.object(self.module.os, "listdir", return_value=["a.parquet"]),
            mock.patch.object(self.module, "calculate_distance", side_effect=lambda *a, **k: calls.append((a, k))),
        ):
            self.module.main()

        self.assertEqual(len(calls), 1)
        self.assertIn("tile=159-145-8", calls[0][0][2].replace("\\", "/"))

    def test_main_returns_when_metadata_input_file_missing(self):
        filename = "metadata_unfiltered_159-145-8.parquet"

        def fake_exists(path):
            norm = str(path).replace("\\", "/")
            if norm.endswith("/tmp/unfiltered/tile=159-145-8/metadata_unfiltered_159-145-8.parquet"):
                return False
            return True

        with (
            mock.patch.object(self.module, "load_config", return_value=self._cfg(), create=True),
            mock.patch.object(self.module.sys, "argv", ["find_osm_segments.py", filename]),
            mock.patch.object(self.module.os, "chdir"),
            mock.patch.object(self.module.os.path, "exists", side_effect=fake_exists),
            mock.patch.object(self.module.os.path, "getmtime") as mtime_mock,
            mock.patch.object(self.module, "calculate_distance") as calc_mock,
        ):
            self.module.main()

        calc_mock.assert_not_called()
        mtime_mock.assert_not_called()

    def test_main_returns_when_osm_directory_missing(self):
        filename = "metadata_unfiltered_159-145-8.parquet"

        def fake_exists(path):
            norm = str(path).replace("\\", "/")
            if norm.endswith("/tmp/unfiltered/tile=159-145-8/metadata_unfiltered_159-145-8.parquet"):
                return True
            return True

        def fake_isdir(path):
            norm = str(path).replace("\\", "/")
            if norm.endswith("/tmp/osm/tile=159-145-8"):
                return False
            return True

        with (
            mock.patch.object(self.module, "load_config", return_value=self._cfg(), create=True),
            mock.patch.object(self.module.sys, "argv", ["find_osm_segments.py", filename]),
            mock.patch.object(self.module.os, "chdir"),
            mock.patch.object(self.module.os.path, "exists", side_effect=fake_exists),
            mock.patch.object(self.module.os.path, "isdir", side_effect=fake_isdir),
            mock.patch.object(self.module.os.path, "getmtime") as mtime_mock,
            mock.patch.object(self.module.os, "listdir") as listdir_mock,
            mock.patch.object(self.module, "calculate_distance") as calc_mock,
        ):
            self.module.main()

        calc_mock.assert_not_called()
        listdir_mock.assert_not_called()
        mtime_mock.assert_not_called()
