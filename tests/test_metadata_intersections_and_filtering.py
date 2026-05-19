import importlib
import random
import runpy
import sys
import types
import unittest
from pathlib import Path
from unittest import mock


RESEARCH_CODE_DIR = Path(__file__).resolve().parents[1] / "research_code"
if str(RESEARCH_CODE_DIR) not in sys.path:
    sys.path.insert(0, str(RESEARCH_CODE_DIR))

import start as real_start


class FakeNumericArray:
    def __init__(self, values):
        self.values = list(values)

    def __add__(self, other):
        return FakeNumericArray([left + right for left, right in zip(self.values, other.values)])

    def astype(self, _type):
        return FakeNumericArray([_type(value) for value in self.values])

    def __iter__(self):
        return iter(self.values)

    def __len__(self):
        return len(self.values)

    def __getitem__(self, index):
        return self.values[index]

    def tolist(self):
        return list(self.values)


class FakeNumpy(types.ModuleType):
    def __init__(self):
        super().__init__("numpy")

    @staticmethod
    def array(values):
        return FakeNumericArray(values)

    @staticmethod
    def ones(count):
        return FakeNumericArray([1] * count)


class FakeTile:
    def __init__(self, x, y, z):
        self.x = x
        self.y = y
        self.z = z


class FakePolygon:
    def __init__(self, bounds):
        self.bounds = bounds


def import_metadata_intersections_module():
    sys.modules.pop("metadata_intersections_and_filtering", None)

    fake_numpy = FakeNumpy()
    fake_pandas = types.ModuleType("pandas")
    fake_geopandas = types.ModuleType("geopandas")
    fake_geopandas.GeoDataFrame = type("GeoDataFrame", (), {"__init__": lambda s, *a, **k: None})
    fake_duckdb = types.ModuleType("duckdb")
    fake_duckdb.connect = None

    fake_mercantile = types.ModuleType("mercantile")
    fake_mercantile.tile = lambda longitude, latitude, zoom: FakeTile(
        int((longitude + 180) * 10),
        int((latitude + 90) * 10),
        zoom,
    )
    fake_mercantile.tiles = lambda west, south, east, north, zoom: [
        FakeTile(int(west * 10), int(south * 10), zoom),
        FakeTile(int(east * 10), int(north * 10), zoom),
    ]

    fake_shapely = types.ModuleType("shapely")

    def fake_from_wkt(value):
        west, south, east, north = [float(part) for part in value.split(":")[1].split(",")]
        return FakePolygon((west, south, east, north))

    fake_shapely.from_wkt = fake_from_wkt

    fake_simplify = types.ModuleType("pygeodesy.simplify")
    fake_simplify.simplify1 = lambda points, indices, distance, limit: [0, len(points) // 2, len(points) - 1]
    fake_simplify.simplifyRDP = lambda points, indices, distance: [0, len(points) - 1]

    fake_points = types.ModuleType("pygeodesy.points")
    fake_points.Numpy2LatLon = lambda values: list(values)

    fake_shutil = types.ModuleType("shutil")
    fake_shutil.copy2 = lambda src, dst: None

    with mock.patch.dict(
        sys.modules,
        {
            "numpy": fake_numpy,
            "pandas": fake_pandas,
            "geopandas": fake_geopandas,
            "mercantile": fake_mercantile,
            "shapely": fake_shapely,
            "pygeodesy.simplify": fake_simplify,
            "pygeodesy.points": fake_points,
            "duckdb": fake_duckdb,
            "shutil": fake_shutil,
        },
    ):
        return importlib.import_module("metadata_intersections_and_filtering")


class MetadataIntersectionsAndFilteringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_metadata_intersections_module()

    def test_filtering_simple_offsets_seeded_random_indices_to_one_based(self):
        generator = random.Random(501)
        latlong = [[generator.uniform(-20, 20), generator.uniform(-20, 20)] for _ in range(7)]

        result = self.module.filtering_simple(latlong, distance=generator.uniform(1, 50))

        self.assertEqual(list(result), [1, 4, 7])

    def test_filtering_rdp_offsets_seeded_random_indices_to_one_based(self):
        generator = random.Random(502)
        latlong = [[generator.uniform(-20, 20), generator.uniform(-20, 20)] for _ in range(6)]

        result = self.module.filtering_RDP(latlong, distance=generator.uniform(1, 50))

        self.assertEqual(list(result), [1, 6])

    def test_finding_tiles_for_points_formats_seeded_random_tile_triplets(self):
        generator = random.Random(503)
        longitude = generator.uniform(-100, 100)
        latitude = generator.uniform(-50, 50)
        zoom_level = generator.randint(1, 14)

        tile_label = self.module.finding_tiles_for_points([longitude, latitude], zoom_level)

        self.assertEqual(
            tile_label,
            f"{int((longitude + 180) * 10)}-{int((latitude + 90) * 10)}-{zoom_level}",
        )

    def test_finding_tiles_list_for_urban_areas_uses_seeded_random_bounds(self):
        generator = random.Random(504)
        west = round(generator.uniform(-5, 5), 3)
        south = round(generator.uniform(-5, 5), 3)
        east = round(west + generator.uniform(0.5, 3), 3)
        north = round(south + generator.uniform(0.5, 3), 3)
        zoom_level = generator.randint(1, 14)

        polygon = f"BBOX:{west},{south},{east},{north}"
        tiles = self.module.finding_tiles_list_for_urban_areas(polygon, zoom_level)

        self.assertEqual(
            tiles,
            [
                f"{int(west * 10)}-{int(south * 10)}-{zoom_level}",
                f"{int(east * 10)}-{int(north * 10)}-{zoom_level}",
            ],
        )


# ---------------------------------------------------------------------------
# download_overture_maps
# ---------------------------------------------------------------------------

class DownloadOvertureMapsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_metadata_intersections_module()

    def _make_conn(self, fail_at=None):
        calls = []

        class Conn:
            def __init__(self):
                self.closed = False
                self._n = 0

            def execute(self, q):
                calls.append(q)
                self._n += 1
                if fail_at is not None and self._n >= fail_at:
                    raise RuntimeError("exec fail")

            def close(self):
                self.closed = True

        return Conn(), calls

    def test_executes_install_and_copy_queries(self):
        gen = random.Random(3101)
        url = f"s3://bucket/{gen.randint(100, 999)}"
        filepath = f"/tmp/out_{gen.randint(100, 999)}.parquet"
        temp_suffix = gen.randint(0, int(1e12))
        conn, calls = self._make_conn()

        with (
            mock.patch.object(self.module.duckdb, "connect", return_value=conn),
            mock.patch.object(self.module.random, "randint", return_value=temp_suffix),
            mock.patch.object(self.module.os.path, "exists",
                              side_effect=lambda p: p == f"temp_{temp_suffix}.db"),
            mock.patch.object(self.module.os, "remove"),
        ):
            self.module.download_overture_maps(url, filepath)

        self.assertTrue(any("SPATIAL" in c.upper() for c in calls))
        self.assertTrue(any(url in c for c in calls))
        self.assertTrue(any(filepath in c for c in calls))
        self.assertTrue(conn.closed)

    def test_cleans_up_on_exception(self):
        gen = random.Random(3102)
        temp_suffix = gen.randint(0, int(1e12))
        conn, _ = self._make_conn(fail_at=1)
        removed = []

        with (
            mock.patch.object(self.module.duckdb, "connect", return_value=conn),
            mock.patch.object(self.module.random, "randint", return_value=temp_suffix),
            mock.patch.object(self.module.os.path, "exists",
                              side_effect=lambda p: p == f"temp_{temp_suffix}.db"),
            mock.patch.object(self.module.os, "remove", side_effect=removed.append),
        ):
            self.module.download_overture_maps("s3://bucket", "/tmp/out.parquet")

        self.assertIn(f"temp_{temp_suffix}.db", removed)
        self.assertTrue(conn.closed)

    def test_does_not_remove_temp_db_if_it_does_not_exist(self):
        gen = random.Random(3103)
        temp_suffix = gen.randint(0, int(1e12))
        conn, _ = self._make_conn()
        removed = []

        with (
            mock.patch.object(self.module.duckdb, "connect", return_value=conn),
            mock.patch.object(self.module.random, "randint", return_value=temp_suffix),
            mock.patch.object(self.module.os.path, "exists", return_value=False),
            mock.patch.object(self.module.os, "remove", side_effect=removed.append),
        ):
            self.module.download_overture_maps("s3://bucket", "/tmp/out.parquet")

        self.assertNotIn(f"temp_{temp_suffix}.db", removed)

    def test_connect_failure_does_not_attempt_temp_remove_when_file_missing(self):
        gen = random.Random(3104)
        temp_suffix = gen.randint(0, int(1e12))

        with (
            mock.patch.object(self.module.duckdb, "connect", side_effect=RuntimeError("connect fail")),
            mock.patch.object(self.module.random, "randint", return_value=temp_suffix),
            mock.patch.object(self.module.os.path, "exists", return_value=False),
            mock.patch.object(self.module.os, "remove") as remove_mock,
        ):
            self.module.download_overture_maps("s3://bucket", "/tmp/out.parquet")

        remove_mock.assert_not_called()


# ---------------------------------------------------------------------------
# intersection
# ---------------------------------------------------------------------------

class IntersectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_metadata_intersections_module()

    def _make_conn(self, fail_at=None):
        calls = []

        class Conn:
            def __init__(self):
                self.closed = False
                self._n = 0

            def execute(self, q):
                calls.append(q)
                self._n += 1
                if fail_at is not None and self._n >= fail_at:
                    raise RuntimeError("exec fail")

            def close(self):
                self.closed = True

        return Conn(), calls

    def test_query_contains_all_file_paths_and_column(self):
        gen = random.Random(3201)
        intersected = f"/data/a_{gen.randint(100, 999)}.parquet"
        intersecting = f"/data/b_{gen.randint(100, 999)}.parquet"
        column = f"col_{gen.randint(10, 99)}"
        output = f"/data/out_{gen.randint(100, 999)}.parquet"
        temp_suffix = gen.randint(0, int(1e12))
        conn, calls = self._make_conn()

        with (
            mock.patch.object(self.module.duckdb, "connect", return_value=conn),
            mock.patch.object(self.module.random, "randint", return_value=temp_suffix),
            mock.patch.object(self.module.os.path, "exists",
                              side_effect=lambda p: p == f"temp_{temp_suffix}.db"),
            mock.patch.object(self.module.os, "remove"),
        ):
            self.module.intersection(intersected, intersecting, column, output)

        exec_q = " ".join(calls)
        self.assertIn(intersected, exec_q)
        self.assertIn(intersecting, exec_q)
        self.assertIn(column, exec_q)
        self.assertIn(output, exec_q)
        self.assertTrue(conn.closed)

    def test_cleans_up_temp_db_on_exception(self):
        gen = random.Random(3202)
        temp_suffix = gen.randint(0, int(1e12))
        conn, _ = self._make_conn(fail_at=1)
        removed = []

        with (
            mock.patch.object(self.module.duckdb, "connect", return_value=conn),
            mock.patch.object(self.module.random, "randint", return_value=temp_suffix),
            mock.patch.object(self.module.os.path, "exists",
                              side_effect=lambda p: p == f"temp_{temp_suffix}.db"),
            mock.patch.object(self.module.os, "remove", side_effect=removed.append),
        ):
            self.module.intersection("/a.parquet", "/b.parquet", "col", "/out.parquet")

        self.assertIn(f"temp_{temp_suffix}.db", removed)
        self.assertTrue(conn.closed)

    def test_uses_st_intersects_for_spatial_join(self):
        gen = random.Random(3203)
        temp_suffix = gen.randint(0, int(1e12))
        conn, calls = self._make_conn()

        with (
            mock.patch.object(self.module.duckdb, "connect", return_value=conn),
            mock.patch.object(self.module.random, "randint", return_value=temp_suffix),
            mock.patch.object(self.module.os.path, "exists", return_value=False),
            mock.patch.object(self.module.os, "remove"),
        ):
            self.module.intersection("/a.parquet", "/b.parquet", "col", "/out.parquet")

        joined = " ".join(calls)
        self.assertIn("ST_Intersects", joined)
        self.assertIn("LEFT JOIN", joined)

    def test_connect_failure_does_not_attempt_temp_remove_when_file_missing(self):
        gen = random.Random(3204)
        temp_suffix = gen.randint(0, int(1e12))

        with (
            mock.patch.object(self.module.duckdb, "connect", side_effect=RuntimeError("connect fail")),
            mock.patch.object(self.module.random, "randint", return_value=temp_suffix),
            mock.patch.object(self.module.os.path, "exists", return_value=False),
            mock.patch.object(self.module.os, "remove") as remove_mock,
        ):
            self.module.intersection("/a.parquet", "/b.parquet", "col", "/out.parquet")

        remove_mock.assert_not_called()


# ---------------------------------------------------------------------------
# layer_intersections (path-building logic, no filesystem side-effects)
# ---------------------------------------------------------------------------

class LayerIntersectionsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_metadata_intersections_module()

    def test_returns_list_including_country_filename_when_is_first_false(self):
        gen = random.Random(3301)
        output_dir = f"/tmp/proc_{gen.randint(100, 999)}"
        continents_dir = f"/tmp/conts_{gen.randint(100, 999)}"
        ghsl = f"ghsl_{gen.randint(100, 999)}.gpkg"
        afric = None  # no africapolis
        country = f"countries_{gen.randint(100, 999)}.parquet"
        conts_file = f"/data/continents_{gen.randint(100, 999)}.parquet"

        expected_country_new = f"{output_dir}/intersected_{country}"

        # cond1 (country_intersected_*) must exist → True
        # cond2 (tmp_country_intersected_*) must NOT exist → False (so while loop exits)
        def exists_mock(p):
            basename = p.replace("\\", "/").split("/")[-1]
            if basename.startswith("tmp_"):
                return False   # temp file gone → exit second while loop
            return True        # all other files present → skip creation, exit first while loop

        with (
            mock.patch.object(self.module.os.path, "exists", side_effect=exists_mock),
            mock.patch.object(self.module.time, "sleep"),
        ):
            result = self.module.layer_intersections(
                False, output_dir, continents_dir, conts_file, country,
                "s3://bucket", ghsl, afric
            )

        # Last entry is always the country_filename_new
        self.assertEqual(
            result[-1].replace("\\", "/"),
            expected_country_new.replace("\\", "/"),
        )

    def test_africapolis_none_produces_shorter_path_list(self):
        gen = random.Random(3302)
        output_dir = f"/tmp/proc_{gen.randint(100, 999)}"
        ghsl = f"ghsl_{gen.randint(100, 999)}.gpkg"

        def exists_mock(p):
            basename = p.replace("\\", "/").split("/")[-1]
            return not basename.startswith("tmp_")

        with (
            mock.patch.object(self.module.os.path, "exists", side_effect=exists_mock),
            mock.patch.object(self.module.time, "sleep"),
        ):
            result_no_afric = self.module.layer_intersections(
                False, output_dir, "/conts", "/conts.parquet",
                "cntry.parquet", "s3://bucket", ghsl, None
            )

        with (
            mock.patch.object(self.module.os.path, "exists", side_effect=exists_mock),
            mock.patch.object(self.module.time, "sleep"),
        ):
            result_with_afric = self.module.layer_intersections(
                False, output_dir, "/conts", "/conts.parquet",
                "cntry.parquet", "s3://bucket", ghsl, "afric.shp"
            )

        self.assertLess(len(result_no_afric), len(result_with_afric))

    def test_intersected_ghsl_path_replaces_gpkg_extension(self):
        gen = random.Random(3303)
        output_dir = f"/tmp/proc_{gen.randint(100, 999)}"
        ghsl = f"ghsl_{gen.randint(100, 999)}.gpkg"
        expected_ghsl_intersected = f"{output_dir}/country_intersected_intersected_{ghsl.replace('.gpkg', '.parquet')}"

        def exists_mock(p):
            basename = p.replace("\\", "/").split("/")[-1]
            return not basename.startswith("tmp_")

        with (
            mock.patch.object(self.module.os.path, "exists", side_effect=exists_mock),
            mock.patch.object(self.module.time, "sleep"),
        ):
            result = self.module.layer_intersections(
                False, output_dir, "/conts", "/conts.parquet",
                "cntry.parquet", "s3://bucket", ghsl, None
            )

        self.assertEqual(
            result[0].replace("\\", "/"),
            expected_ghsl_intersected.replace("\\", "/"),
        )

    def test_is_first_true_runs_download_and_layer_conversions(self):
        output_dir = "/tmp/proc"
        continents_filename = "/tmp/continents.parquet"
        country_filename = "countries.parquet"
        ghsl_filename = "ghsl.gpkg"
        africapolis_filename = "africa.shp"

        ghsl_new = f"{output_dir}/intersected_ghsl.parquet"
        afric_new = f"{output_dir}/intersected_africa.parquet"
        country_new = f"{output_dir}/intersected_{country_filename}"

        ghsl_country_inter = f"{output_dir}/country_intersected_intersected_ghsl.parquet"
        afric_country_inter = f"{output_dir}/country_intersected_intersected_africa.parquet"
        afric_tmp = f"{output_dir}/tmp_country_intersected_intersected_africa.parquet"

        intersection_calls = []

        class FakeCols:
            @property
            def str(self):
                return self

            def lstrip(self, _value):
                return self

        class FakeLayer:
            def __init__(self):
                self.columns = FakeCols()
                self.saved = []

            def to_crs(self, _epsg):
                return self

            def to_parquet(self, path, compression=None, index=None):
                self.saved.append(path)

        def exists_mock(path):
            norm = str(path).replace("\\", "/")
            true_set = {
                continents_filename,
                ghsl_country_inter,
                afric_country_inter,
            }
            if norm in true_set:
                return True
            if norm == afric_tmp:
                return False
            return False

        with (
            mock.patch.object(self.module.os.path, "exists", side_effect=exists_mock),
            mock.patch.object(self.module, "download_overture_maps") as dl_mock,
            mock.patch.object(self.module.gpd, "read_file", return_value=FakeLayer(), create=True),
            mock.patch.object(
                self.module,
                "intersection",
                side_effect=lambda *args, **kwargs: intersection_calls.append(args),
            ),
            mock.patch.object(self.module.time, "sleep"),
        ):
            result = self.module.layer_intersections(
                True,
                output_dir,
                "/tmp/continents",
                continents_filename,
                country_filename,
                "s3://bucket/divisions",
                ghsl_filename,
                africapolis_filename,
            )

        dl_mock.assert_called_once()
        self.assertEqual(len(intersection_calls), 2)
        self.assertEqual(result[-1].replace("\\", "/"), country_new.replace("\\", "/"))

    def test_layer_intersections_times_out_when_sync_file_never_appears(self):
        def exists_mock(path):
            norm = str(path).replace("\\", "/")
            if "tmp_country_intersected_" in norm:
                return False
            return False

        with (
            mock.patch.object(self.module.os.path, "exists", side_effect=exists_mock),
            mock.patch.object(self.module.time, "sleep"),
            mock.patch.object(self.module.time, "monotonic", side_effect=[0.0, 2.0]),
        ):
            with self.assertRaises(TimeoutError):
                self.module.layer_intersections(
                    False,
                    "/tmp/proc",
                    "/tmp/continents",
                    "/tmp/continents.parquet",
                    "countries.parquet",
                    "s3://bucket/divisions",
                    "ghsl.gpkg",
                    None,
                    wait_timeout_seconds=1,
                    wait_poll_seconds=0,
                )

    def test_layer_intersections_raises_clear_error_when_no_continent_geojson_files_exist(self):
        with (
            mock.patch.object(self.module.os.path, "exists", return_value=False),
            mock.patch.object(self.module.os, "listdir", return_value=[]),
        ):
            with self.assertRaises(FileNotFoundError):
                self.module.layer_intersections(
                    True,
                    "/tmp/proc",
                    "/tmp/continents",
                    "/tmp/continents.parquet",
                    "countries.parquet",
                    "s3://bucket/divisions",
                    "ghsl.gpkg",
                    None,
                )

    def test_layer_intersections_copies_existing_country_file_when_country_output_missing(self):
        calls = {"copy": 0}

        def fake_exists(path):
            norm = str(path).replace("\\", "/")
            if norm.endswith("/tmp/proc/intersected_countries.parquet"):
                return False
            if norm.endswith("/tmp/countries.parquet"):
                return True
            if "tmp_country_intersected_" in norm:
                return False
            return True

        with (
            mock.patch.object(self.module.os.path, "exists", side_effect=fake_exists),
            mock.patch.object(self.module.shutil, "copy2", side_effect=lambda s, d: calls.__setitem__("copy", calls["copy"] + 1)),
            mock.patch.object(self.module.time, "sleep"),
        ):
            result = self.module.layer_intersections(
                True,
                "/tmp/proc",
                "/tmp/continents",
                "/tmp/continents.parquet",
                "countries.parquet",
                "s3://bucket/divisions",
                "ghsl.gpkg",
                None,
            )

        self.assertEqual(calls["copy"], 1)
        self.assertTrue(result[-1].replace("\\", "/").endswith("/tmp/proc/intersected_countries.parquet"))

    def test_layer_intersections_skips_ghsl_conversion_for_non_gpkg_file(self):
        def fake_exists(path):
            norm = str(path).replace("\\", "/")
            if "tmp_country_intersected_" in norm:
                return False
            if norm.endswith("/tmp/proc/intersected_countries.parquet"):
                return True
            return True

        with (
            mock.patch.object(self.module.os.path, "exists", side_effect=fake_exists),
            mock.patch.object(self.module.gpd, "read_file", side_effect=AssertionError("should not read ghsl"), create=True),
            mock.patch.object(self.module.time, "sleep"),
        ):
            self.module.layer_intersections(
                True,
                "/tmp/proc",
                "/tmp/continents",
                "/tmp/continents.parquet",
                "countries.parquet",
                "s3://bucket/divisions",
                "ghsl.parquet",
                None,
            )

    def test_layer_intersections_merges_unknown_continent_filename_without_label_match(self):
        class FakeGdf:
            crs = "EPSG:4326"

            def __setitem__(self, key, value):
                return None

            def to_parquet(self, *args, **kwargs):
                return None

        def fake_exists(path):
            norm = str(path).replace("\\", "/")
            if norm.endswith("/tmp/continents.parquet"):
                return False
            if "tmp_country_intersected_" in norm:
                return False
            return True

        with (
            mock.patch.object(self.module.os.path, "exists", side_effect=fake_exists),
            mock.patch.object(self.module.os, "listdir", return_value=["unknown.geojson"]),
            mock.patch.object(self.module.gpd, "read_file", return_value=FakeGdf(), create=True),
            mock.patch.object(self.module.pd, "concat", return_value=[], create=True),
            mock.patch.object(self.module.gpd, "GeoDataFrame", return_value=FakeGdf(), create=True),
            mock.patch.object(self.module.time, "sleep"),
        ):
            result = self.module.layer_intersections(
                True,
                "/tmp/proc",
                "/tmp/continents",
                "/tmp/continents.parquet",
                "countries.parquet",
                "s3://bucket/divisions",
                "ghsl.gpkg",
                None,
            )

        self.assertEqual(len(result), 2)

    def test_layer_intersections_waits_for_temp_cleanup_once(self):
        state = {"count": 0}

        def fake_exists(path):
            norm = str(path).replace("\\", "/")
            if "tmp_country_intersected_intersected_ghsl.parquet" in norm:
                state["count"] += 1
                return state["count"] == 1
            if norm.endswith("country_intersected_intersected_ghsl.parquet"):
                return True
            return True

        sleep_calls = []
        with (
            mock.patch.object(self.module.os.path, "exists", side_effect=fake_exists),
            mock.patch.object(self.module.time, "sleep", side_effect=lambda t: sleep_calls.append(t)),
        ):
            self.module.layer_intersections(
                False,
                "/tmp/proc",
                "/tmp/continents",
                "/tmp/continents.parquet",
                "countries.parquet",
                "s3://bucket/divisions",
                "ghsl.gpkg",
                None,
                wait_timeout_seconds=10,
                wait_poll_seconds=0,
            )

        self.assertEqual(len(sleep_calls), 1)

    def test_layer_intersections_sets_continent_label_when_filename_matches(self):
        calls = {"set": 0}

        class FakeGdf:
            crs = "EPSG:4326"

            def __setitem__(self, key, value):
                calls["set"] += 1

            def to_parquet(self, *args, **kwargs):
                return None

        def fake_exists(path):
            norm = str(path).replace("\\", "/")
            if norm.endswith("/tmp/continents.parquet"):
                return False
            if "tmp_country_intersected_" in norm:
                return False
            return True

        with (
            mock.patch.object(self.module.os.path, "exists", side_effect=fake_exists),
            mock.patch.object(self.module.os, "listdir", return_value=["africa_outline.geojson"]),
            mock.patch.object(self.module.gpd, "read_file", return_value=FakeGdf(), create=True),
            mock.patch.object(self.module.pd, "concat", return_value=[], create=True),
            mock.patch.object(self.module.gpd, "GeoDataFrame", return_value=FakeGdf(), create=True),
            mock.patch.object(self.module.time, "sleep"),
        ):
            self.module.layer_intersections(
                True,
                "/tmp/proc",
                "/tmp/continents",
                "/tmp/continents.parquet",
                "countries.parquet",
                "s3://bucket/divisions",
                "ghsl.gpkg",
                None,
            )

        self.assertGreaterEqual(calls["set"], 1)

    def test_layer_intersections_skips_africapolis_conversion_when_output_exists(self):
        africapolis_name = "africapolis.shp"

        def fake_exists(path):
            norm = str(path).replace("\\", "/")
            if norm.endswith("/tmp/proc/intersected_africapolis.parquet"):
                return True
            if "tmp_country_intersected_" in norm:
                return False
            return True

        with (
            mock.patch.object(self.module.os.path, "exists", side_effect=fake_exists),
            mock.patch.object(self.module.gpd, "read_file", side_effect=AssertionError("unexpected conversion read"), create=True),
            mock.patch.object(self.module.time, "sleep"),
        ):
            self.module.layer_intersections(
                True,
                "/tmp/proc",
                "/tmp/continents",
                "/tmp/continents.parquet",
                "countries.parquet",
                "s3://bucket/divisions",
                "ghsl.parquet",
                africapolis_name,
            )

    def test_layer_intersections_calls_country_intersection_when_country_output_missing(self):
        intersection_calls = []
        state = {"country_exists_calls": 0}

        def fake_exists(path):
            norm = str(path).replace("\\", "/")
            if "tmp_country_intersected_" in norm:
                return False
            if norm.endswith("country_intersected_intersected_ghsl.parquet"):
                state["country_exists_calls"] += 1
                return state["country_exists_calls"] > 1
            if norm.endswith("continent_intersected_intersected_ghsl.parquet"):
                return False
            return True

        with (
            mock.patch.object(self.module.os.path, "exists", side_effect=fake_exists),
            mock.patch.object(self.module, "intersection", side_effect=lambda *args, **kwargs: intersection_calls.append(args)),
            mock.patch.object(self.module.time, "sleep"),
        ):
            self.module.layer_intersections(
                True,
                "/tmp/proc",
                "/tmp/continents",
                "/tmp/continents.parquet",
                "countries.parquet",
                "s3://bucket/divisions",
                "ghsl.gpkg",
                None,
            )

        self.assertTrue(any(call[2] == "country" for call in intersection_calls))

    def test_layer_intersections_waits_for_cond1_without_timeout(self):
        state = {"country": 0}

        def fake_exists(path):
            norm = str(path).replace("\\", "/")
            if "tmp_country_intersected_intersected_ghsl.parquet" in norm:
                return False
            if norm.endswith("country_intersected_intersected_ghsl.parquet"):
                state["country"] += 1
                # First call comes from the pre-wait intersection check (return True).
                # Then force one wait-loop iteration (False), then allow completion (True).
                if state["country"] == 2:
                    return False
                return True
            return True

        with (
            mock.patch.object(self.module.os.path, "exists", side_effect=fake_exists),
            mock.patch.object(self.module.time, "sleep"),
        ):
            self.module.layer_intersections(
                False,
                "/tmp/proc",
                "/tmp/continents",
                "/tmp/continents.parquet",
                "countries.parquet",
                "s3://bucket/divisions",
                "ghsl.gpkg",
                None,
                wait_timeout_seconds=2,
                wait_poll_seconds=0,
            )

    def test_layer_intersections_raises_timeout_when_temp_cleanup_never_finishes(self):
        def fake_exists(path):
            norm = str(path).replace("\\", "/")
            if norm.endswith("country_intersected_intersected_ghsl.parquet"):
                return True
            if "tmp_country_intersected_intersected_ghsl.parquet" in norm:
                return True
            return True

        with (
            mock.patch.object(self.module.os.path, "exists", side_effect=fake_exists),
            mock.patch.object(self.module.time, "sleep"),
            mock.patch.object(self.module.time, "monotonic", side_effect=[0.0, 2.0]),
        ):
            with self.assertRaises(TimeoutError):
                self.module.layer_intersections(
                    False,
                    "/tmp/proc",
                    "/tmp/continents",
                    "/tmp/continents.parquet",
                    "countries.parquet",
                    "s3://bucket/divisions",
                    "ghsl.gpkg",
                    None,
                    wait_timeout_seconds=1,
                    wait_poll_seconds=0,
                )


class IntersectionsWithMetadataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_metadata_intersections_module()

    class _FakeColumns:
        @property
        def str(self):
            return self

        def lstrip(self, _value):
            return self

    class _FakeGhsDf:
        def __init__(self):
            self.columns = IntersectionsWithMetadataTests._FakeColumns()

    def _make_conn(self, fail_on=None):
        calls = []

        class ExecResult:
            def df(self):
                return IntersectionsWithMetadataTests._FakeGhsDf()

        class Conn:
            def __init__(self):
                self.closed = False

            def create_function(self, *args, **kwargs):
                return None

            def execute(self, query):
                calls.append(query)
                if fail_on is not None and fail_on in query:
                    raise RuntimeError("query fail")
                if "SELECT * REPLACE(ST_AsText(geometry) AS geometry)" in query:
                    return ExecResult()
                return None

            def close(self):
                self.closed = True

        return Conn(), calls

    def test_intersections_with_metadata_success_without_africapolis(self):
        gen = random.Random(3401)
        temp_suffix = gen.randint(0, int(1e12))
        conn, calls = self._make_conn()

        with (
            mock.patch.object(self.module.duckdb, "connect", return_value=conn),
            mock.patch.object(self.module.random, "randint", return_value=temp_suffix),
            mock.patch.object(self.module.os.path, "exists", side_effect=lambda p: p == f"temp_{temp_suffix}.db"),
            mock.patch.object(self.module.os, "remove"),
        ):
            result = self.module.intersections_with_metadata(
                metadata_filename="/tmp/meta.parquet",
                continent_filename="/tmp/continents.parquet",
                country_filename="/tmp/countries.parquet",
                ghsl_filename="/tmp/ghsl.parquet",
                africapolis_filename=None,
                unfiltered_output_filename="/tmp/unfiltered.parquet",
                filtered_output_filename="/tmp/filtered.parquet",
                ghsl_string="d.ghsl_a, d.ghsl_b",
                africapolis_string="e.af_a, e.af_b",
                zoom_level=8,
                filter_list=[100, 500],
            )

        self.assertTrue(result)
        self.assertTrue(any("TO '/tmp/unfiltered.parquet'" in q for q in calls))
        self.assertTrue(any("TO '/tmp/filtered.parquet'" in q for q in calls))
        self.assertTrue(conn.closed)

    def test_intersections_with_metadata_success_with_africapolis(self):
        gen = random.Random(3402)
        temp_suffix = gen.randint(0, int(1e12))
        conn, calls = self._make_conn()

        with (
            mock.patch.object(self.module.duckdb, "connect", return_value=conn),
            mock.patch.object(self.module.random, "randint", return_value=temp_suffix),
            mock.patch.object(self.module.os.path, "exists", side_effect=lambda p: p == f"temp_{temp_suffix}.db"),
            mock.patch.object(self.module.os, "remove"),
        ):
            result = self.module.intersections_with_metadata(
                metadata_filename="/tmp/meta.parquet",
                continent_filename="/tmp/continents.parquet",
                country_filename="/tmp/countries.parquet",
                ghsl_filename="/tmp/ghsl.parquet",
                africapolis_filename="/tmp/africa.parquet",
                unfiltered_output_filename="/tmp/unfiltered.parquet",
                filtered_output_filename="/tmp/filtered.parquet",
                ghsl_string="d.ghsl_a, d.ghsl_b",
                africapolis_string="e.af_a, e.af_b",
                zoom_level=8,
                filter_list=[100, 500],
            )

        self.assertTrue(result)
        self.assertTrue(any("read_parquet('/tmp/africa.parquet')" in q for q in calls))
        self.assertTrue(conn.closed)

    def test_intersections_with_metadata_returns_false_on_query_error(self):
        gen = random.Random(3403)
        temp_suffix = gen.randint(0, int(1e12))
        conn, _ = self._make_conn(fail_on="COPY(")

        with (
            mock.patch.object(self.module.duckdb, "connect", return_value=conn),
            mock.patch.object(self.module.random, "randint", return_value=temp_suffix),
            mock.patch.object(self.module.os.path, "exists", side_effect=lambda p: p == f"temp_{temp_suffix}.db"),
            mock.patch.object(self.module.os, "remove"),
        ):
            result = self.module.intersections_with_metadata(
                metadata_filename="/tmp/meta.parquet",
                continent_filename="/tmp/continents.parquet",
                country_filename="/tmp/countries.parquet",
                ghsl_filename="/tmp/ghsl.parquet",
                africapolis_filename=None,
                unfiltered_output_filename="/tmp/unfiltered.parquet",
                filtered_output_filename="/tmp/filtered.parquet",
                ghsl_string="d.ghsl_a, d.ghsl_b",
                africapolis_string="e.af_a, e.af_b",
                zoom_level=8,
                filter_list=[100, 500],
            )

        self.assertFalse(result)

    def test_intersections_with_metadata_returns_false_when_connect_fails(self):
        gen = random.Random(3404)
        temp_suffix = gen.randint(0, int(1e12))

        with (
            mock.patch.object(self.module.duckdb, "connect", side_effect=RuntimeError("connect fail")),
            mock.patch.object(self.module.random, "randint", return_value=temp_suffix),
            mock.patch.object(self.module.os.path, "exists", return_value=False),
            mock.patch.object(self.module.os, "remove") as remove_mock,
        ):
            result = self.module.intersections_with_metadata(
                metadata_filename="/tmp/meta.parquet",
                continent_filename="/tmp/continents.parquet",
                country_filename="/tmp/countries.parquet",
                ghsl_filename="/tmp/ghsl.parquet",
                africapolis_filename=None,
                unfiltered_output_filename="/tmp/unfiltered.parquet",
                filtered_output_filename="/tmp/filtered.parquet",
                ghsl_string="d.ghsl_a, d.ghsl_b",
                africapolis_string="e.af_a, e.af_b",
                zoom_level=8,
                filter_list=[100, 500],
            )

        self.assertFalse(result)
        remove_mock.assert_not_called()


class MetadataIntersectionsMainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_metadata_intersections_module()

    def _cfg(self):
        return {
            "paths": {
                "tile_partitioned_parquet_raw_metadata_dir": "/tmp/root",
                "continents_dir": "/tmp/continents",
                "processed_dir": "/tmp/processed",
                "unfiltered_metadata_dir": "/tmp/unfiltered",
                "filtered_metadata_dir": "/tmp/filtered",
            },
            "metadata_params": {"updated_after": "2000-01-01T00:00:00"},
            "params": {
                "zoom_level": 8,
                "urban_threshold": 100,
                "rural_threshold": 500,
                "ghsl_col_1": "d.a",
                "ghsl_col_2": "d.b",
                "africapolis_col_1": "e.a",
                "africapolis_col_2": "e.b",
            },
            "filenames": {
                "continents_filename": "continents.parquet",
                "overture_url": "s3://overture/divisions",
                "country_filename": "countries.parquet",
                "ghsl_filename": "ghsl.gpkg",
                "africapolis_filename": "africa.shp",
            },
        }
        fake_start.__getattr__ = lambda name: getattr(real_start, name)

    def test_main_exits_when_no_input_argument(self):
        with (
            mock.patch.object(self.module, "load_config", return_value=self._cfg()),
            mock.patch.object(self.module.sys, "argv", ["metadata_intersections_and_filtering.py"]),
            mock.patch.object(self.module.os, "chdir"),
        ):
            with self.assertRaises(SystemExit):
                self.module.main()

    def test_main_returns_early_when_file_too_old(self):
        cfg = self._cfg()
        cfg["metadata_params"]["updated_after"] = "2100-01-01T00:00:00"

        with (
            mock.patch.object(self.module, "load_config", return_value=cfg),
            mock.patch.object(self.module.sys, "argv", ["metadata_intersections_and_filtering.py", "/tmp/metadata_unfiltered_159-145-8.parquet"]),
            mock.patch.object(self.module.os, "chdir"),
            mock.patch.object(self.module.os.path, "getmtime", return_value=946684800),
            mock.patch.object(self.module, "layer_intersections") as layer_mock,
        ):
            self.module.main()

        layer_mock.assert_not_called()

    def test_main_parses_tile_from_non_prefixed_filename_branch(self):
        cfg = self._cfg()
        cfg["metadata_params"]["updated_after"] = "2100-01-01T00:00:00"

        with (
            mock.patch.object(self.module, "load_config", return_value=cfg),
            mock.patch.object(self.module.sys, "argv", ["metadata_intersections_and_filtering.py", "/tmp/abc_def_ghi_159-145-8.parquet"]),
            mock.patch.object(self.module.os, "chdir"),
            mock.patch.object(self.module.os.path, "getmtime", return_value=946684800),
            mock.patch.object(self.module, "layer_intersections") as layer_mock,
        ):
            self.module.main()

        layer_mock.assert_not_called()

    def test_main_uses_datetime_min_when_updated_after_invalid(self):
        cfg = self._cfg()
        cfg["metadata_params"]["updated_after"] = "not-a-date"
        metadata_path = "/tmp/metadata_unfiltered_159-145-8.parquet"

        with (
            mock.patch.object(self.module, "load_config", return_value=cfg),
            mock.patch.object(self.module.sys, "argv", ["metadata_intersections_and_filtering.py", metadata_path]),
            mock.patch.object(self.module.os, "chdir"),
            mock.patch.object(self.module.os.path, "getmtime", return_value=32503680000),
            mock.patch.object(self.module.os.path, "exists", return_value=False),
            mock.patch.object(self.module.os.path, "isdir", return_value=True),
            mock.patch.object(self.module.os, "listdir", return_value=[]),
            mock.patch.object(self.module, "layer_intersections", return_value=["/tmp/ghsl.parquet", "/tmp/africa.parquet", "/tmp/country.parquet"]),
            mock.patch.object(self.module, "intersections_with_metadata", return_value=True),
            mock.patch.object(self.module.os, "makedirs"),
        ):
            with self.assertRaises(ValueError):
                self.module.main()

    def test_main_raises_on_invalid_zoom_and_threshold_values(self):
        cfg = self._cfg()
        cfg["params"]["zoom_level"] = "bad"
        cfg["params"]["urban_threshold"] = "bad"
        cfg["params"]["rural_threshold"] = None
        metadata_path = "/tmp/metadata_unfiltered_159-145-8.parquet"
        calls = []

        def fake_intersections(*args, **kwargs):
            calls.append(args)
            return True

        with (
            mock.patch.object(self.module, "load_config", return_value=cfg),
            mock.patch.object(self.module.sys, "argv", ["metadata_intersections_and_filtering.py", metadata_path]),
            mock.patch.object(self.module.os, "chdir"),
            mock.patch.object(self.module.os.path, "getmtime", return_value=32503680000),
            mock.patch.object(self.module.os.path, "exists", return_value=False),
            mock.patch.object(self.module.os.path, "isdir", return_value=True),
            mock.patch.object(self.module.os, "listdir", return_value=[]),
            mock.patch.object(self.module, "layer_intersections", return_value=["/tmp/ghsl.parquet", "/tmp/africa.parquet", "/tmp/country.parquet"]),
            mock.patch.object(self.module, "intersections_with_metadata", side_effect=fake_intersections),
            mock.patch.object(self.module.os, "makedirs"),
        ):
            with self.assertRaises(ValueError):
                self.module.main()

        self.assertEqual(len(calls), 0)

    def test_main_raises_when_filenames_section_missing(self):
        cfg = self._cfg()
        cfg.pop("filenames", None)
        metadata_path = "/tmp/metadata_unfiltered_159-145-8.parquet"
        calls = []

        def fake_intersections(*args, **kwargs):
            calls.append(args)
            return True

        with (
            mock.patch.object(self.module, "load_config", return_value=cfg),
            mock.patch.object(self.module.sys, "argv", ["metadata_intersections_and_filtering.py", metadata_path]),
            mock.patch.object(self.module.os, "chdir"),
            mock.patch.object(self.module.os.path, "getmtime", return_value=32503680000),
            mock.patch.object(self.module.os.path, "exists", return_value=False),
            mock.patch.object(self.module.os.path, "isdir", return_value=True),
            mock.patch.object(self.module.os, "listdir", return_value=[]),
            mock.patch.object(self.module, "layer_intersections", return_value=["/tmp/ghsl.parquet", "/tmp/africa.parquet", "/tmp/country.parquet"]),
            mock.patch.object(self.module, "intersections_with_metadata", side_effect=fake_intersections),
            mock.patch.object(self.module.os, "makedirs"),
        ):
            with self.assertRaises(KeyError):
                self.module.main()

        self.assertEqual(len(calls), 0)

    def test_main_returns_when_getmtime_raises_oserror(self):
        cfg = self._cfg()
        metadata_path = "/tmp/metadata_unfiltered_159-145-8.parquet"

        with (
            mock.patch.object(self.module, "load_config", return_value=cfg),
            mock.patch.object(self.module.sys, "argv", ["metadata_intersections_and_filtering.py", metadata_path]),
            mock.patch.object(self.module.os, "chdir"),
            mock.patch.object(self.module.os.path, "getmtime", side_effect=OSError("gone")),
            mock.patch.object(self.module, "layer_intersections") as layer_mock,
        ):
            self.module.main()

        layer_mock.assert_not_called()

    def test_main_retries_intersections_until_success(self):
        cfg = self._cfg()
        metadata_path = "/tmp/metadata_unfiltered_159-145-8.parquet"

        calls = []

        def fake_intersections(*args, **kwargs):
            calls.append(args)
            return len(calls) >= 2

        def fake_exists(path):
            norm = str(path).replace("\\", "/")
            if norm.endswith("/tmp/root"):
                return True
            return False

        def fake_isdir(path):
            return True

        with (
            mock.patch.object(self.module, "load_config", return_value=cfg),
            mock.patch.object(self.module.sys, "argv", ["metadata_intersections_and_filtering.py", metadata_path]),
            mock.patch.object(self.module.os, "chdir"),
            mock.patch.object(self.module.os.path, "getmtime", return_value=32503680000),
            mock.patch.object(self.module.os.path, "exists", side_effect=fake_exists),
            mock.patch.object(self.module.os.path, "isdir", side_effect=fake_isdir),
            mock.patch.object(self.module.os, "listdir", side_effect=lambda p: ["tile=159-145-8"] if str(p).replace("\\", "/").endswith("/tmp/root") else ["metadata_unfiltered_159-145-8.parquet"]),
            mock.patch.object(self.module, "layer_intersections", return_value=["/tmp/ghsl.parquet", "/tmp/africa.parquet", "/tmp/country.parquet"]),
            mock.patch.object(self.module, "intersections_with_metadata", side_effect=fake_intersections),
            mock.patch.object(self.module.os, "makedirs"),
            mock.patch.object(self.module.time, "sleep"),
        ):
            self.module.main()

        self.assertEqual(len(calls), 2)

    def test_main_ignores_non_directory_entries_in_root_scan(self):
        cfg = self._cfg()
        metadata_path = "/tmp/metadata_unfiltered_159-145-8.parquet"
        calls = []

        def fake_intersections(*args, **kwargs):
            calls.append(args)
            return True

        def fake_exists(path):
            norm = str(path).replace("\\", "/")
            if norm.endswith("/tmp/root"):
                return True
            return False

        def fake_isdir(path):
            norm = str(path).replace("\\", "/")
            return norm.endswith("/tmp/root/tile=159-145-8")

        def fake_listdir(path):
            norm = str(path).replace("\\", "/")
            if norm.endswith("/tmp/root"):
                return ["not_a_dir.txt", "tile=159-145-8"]
            if norm.endswith("/tmp/root/tile=159-145-8"):
                return ["metadata_unfiltered_159-145-8.parquet"]
            return []

        with (
            mock.patch.object(self.module, "load_config", return_value=cfg),
            mock.patch.object(self.module.sys, "argv", ["metadata_intersections_and_filtering.py", metadata_path]),
            mock.patch.object(self.module.os, "chdir"),
            mock.patch.object(self.module.os.path, "getmtime", return_value=32503680000),
            mock.patch.object(self.module.os.path, "exists", side_effect=fake_exists),
            mock.patch.object(self.module.os.path, "isdir", side_effect=fake_isdir),
            mock.patch.object(self.module.os, "listdir", side_effect=fake_listdir),
            mock.patch.object(self.module, "layer_intersections", return_value=["/tmp/ghsl.parquet", "/tmp/africa.parquet", "/tmp/country.parquet"]),
            mock.patch.object(self.module, "intersections_with_metadata", side_effect=fake_intersections),
            mock.patch.object(self.module.os, "makedirs"),
            mock.patch.object(self.module.time, "sleep"),
        ):
            self.module.main()

        self.assertEqual(len(calls), 1)

    def test_main_handles_empty_first_directory_without_index_error(self):
        cfg = self._cfg()
        metadata_path = "/tmp/metadata_unfiltered_159-145-8.parquet"
        calls = []

        def fake_intersections(*args, **kwargs):
            calls.append(args)
            return True

        def fake_exists(path):
            norm = str(path).replace("\\", "/")
            return norm.endswith("/tmp/root")

        def fake_isdir(path):
            norm = str(path).replace("\\", "/")
            return norm.endswith("/tmp/root/tile=empty") or norm.endswith("/tmp/root/tile=159-145-8")

        def fake_listdir(path):
            norm = str(path).replace("\\", "/")
            if norm.endswith("/tmp/root"):
                return ["tile=empty", "tile=159-145-8"]
            if norm.endswith("/tmp/root/tile=empty"):
                return []
            if norm.endswith("/tmp/root/tile=159-145-8"):
                return ["metadata_unfiltered_159-145-8.parquet"]
            return []

        with (
            mock.patch.object(self.module, "load_config", return_value=cfg),
            mock.patch.object(self.module.sys, "argv", ["metadata_intersections_and_filtering.py", metadata_path]),
            mock.patch.object(self.module.os, "chdir"),
            mock.patch.object(self.module.os.path, "getmtime", return_value=32503680000),
            mock.patch.object(self.module.os.path, "exists", side_effect=fake_exists),
            mock.patch.object(self.module.os.path, "isdir", side_effect=fake_isdir),
            mock.patch.object(self.module.os, "listdir", side_effect=fake_listdir),
            mock.patch.object(self.module, "layer_intersections", return_value=["/tmp/ghsl.parquet", "/tmp/africa.parquet", "/tmp/country.parquet"]),
            mock.patch.object(self.module, "intersections_with_metadata", side_effect=fake_intersections),
            mock.patch.object(self.module.os, "makedirs"),
            mock.patch.object(self.module.time, "sleep"),
        ):
            self.module.main()

        self.assertEqual(len(calls), 1)

    def test_main_logs_failure_after_all_retry_attempts(self):
        cfg = self._cfg()
        metadata_path = "/tmp/metadata_unfiltered_159-145-8.parquet"
        calls = []

        def fake_intersections(*args, **kwargs):
            calls.append(1)
            return False

        def fake_exists(path):
            norm = str(path).replace("\\", "/")
            return norm.endswith("/tmp/root")

        with (
            mock.patch.object(self.module, "load_config", return_value=cfg),
            mock.patch.object(self.module.sys, "argv", ["metadata_intersections_and_filtering.py", metadata_path]),
            mock.patch.object(self.module.os, "chdir"),
            mock.patch.object(self.module.os.path, "getmtime", return_value=32503680000),
            mock.patch.object(self.module.os.path, "exists", side_effect=fake_exists),
            mock.patch.object(self.module.os.path, "isdir", return_value=True),
            mock.patch.object(self.module.os, "listdir", side_effect=lambda p: ["tile=159-145-8"] if str(p).replace("\\", "/").endswith("/tmp/root") else ["metadata_unfiltered_159-145-8.parquet"]),
            mock.patch.object(self.module, "layer_intersections", return_value=["/tmp/ghsl.parquet", "/tmp/africa.parquet", "/tmp/country.parquet"]),
            mock.patch.object(self.module, "intersections_with_metadata", side_effect=fake_intersections),
            mock.patch.object(self.module.os, "makedirs"),
            mock.patch.object(self.module.time, "sleep") as sleep_mock,
        ):
            self.module.main()

        self.assertEqual(len(calls), 3)
        self.assertEqual(sleep_mock.call_count, 2)

    def test_main_exits_when_tile_cannot_be_extracted_from_filename(self):
        cfg = self._cfg()

        with (
            mock.patch.object(self.module, "load_config", return_value=cfg),
            mock.patch.object(self.module.sys, "argv", ["metadata_intersections_and_filtering.py", "/tmp/metadata_invalid.parquet"]),
            mock.patch.object(self.module.os, "chdir"),
        ):
            with self.assertRaises(SystemExit):
                self.module.main()

    def test_module_entrypoint_executes_main_when_run_as_script(self):
        fake_start = types.ModuleType("start")
        fake_start.load_config = lambda filepath="./config.yaml": {
            "paths": {},
            "filenames": {},
            "parameters": {},
            "metadata_filtering": {},
            "columns": {},
        }
        fake_start.__getattr__ = lambda name: getattr(real_start, name)

        fake_numpy = FakeNumpy()
        fake_pandas = types.ModuleType("pandas")
        fake_geopandas = types.ModuleType("geopandas")
        fake_geopandas.GeoDataFrame = type("GeoDataFrame", (), {"__init__": lambda s, *a, **k: None})
        fake_duckdb = types.ModuleType("duckdb")
        fake_duckdb.connect = None

        fake_mercantile = types.ModuleType("mercantile")
        fake_mercantile.tile = lambda longitude, latitude, zoom: FakeTile(int((longitude + 180) * 10), int((latitude + 90) * 10), zoom)
        fake_mercantile.tiles = lambda west, south, east, north, zoom: [FakeTile(int(west * 10), int(south * 10), zoom)]

        fake_shapely = types.ModuleType("shapely")
        fake_shapely.from_wkt = lambda value: FakePolygon((0.0, 0.0, 1.0, 1.0))

        fake_simplify = types.ModuleType("pygeodesy.simplify")
        fake_simplify.simplify1 = lambda points, indices, distance, limit: [0, len(points) - 1]
        fake_simplify.simplifyRDP = lambda points, indices, distance: [0, len(points) - 1]

        fake_points = types.ModuleType("pygeodesy.points")
        fake_points.Numpy2LatLon = lambda values: list(values)

        fake_shutil = types.ModuleType("shutil")
        fake_shutil.copy2 = lambda src, dst: None

        with (
            mock.patch.dict(
                sys.modules,
                {
                    "numpy": fake_numpy,
                    "pandas": fake_pandas,
                    "geopandas": fake_geopandas,
                    "start": fake_start,
                    "mercantile": fake_mercantile,
                    "shapely": fake_shapely,
                    "pygeodesy.simplify": fake_simplify,
                    "pygeodesy.points": fake_points,
                    "duckdb": fake_duckdb,
                    "shutil": fake_shutil,
                },
            ),
            mock.patch("os.chdir"),
            mock.patch.object(sys, "argv", ["metadata_intersections_and_filtering.py"]),
        ):
            with self.assertRaises(SystemExit):
                runpy.run_module("metadata_intersections_and_filtering", run_name="__main__")

