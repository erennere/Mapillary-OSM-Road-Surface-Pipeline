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
            basename = p.split("/")[-1] if "/" in p else p
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
        self.assertEqual(result[-1], expected_country_new)

    def test_africapolis_none_produces_shorter_path_list(self):
        gen = random.Random(3302)
        output_dir = f"/tmp/proc_{gen.randint(100, 999)}"
        ghsl = f"ghsl_{gen.randint(100, 999)}.gpkg"

        def exists_mock(p):
            basename = p.split("/")[-1] if "/" in p else p
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
            basename = p.split("/")[-1] if "/" in p else p
            return not basename.startswith("tmp_")

        with (
            mock.patch.object(self.module.os.path, "exists", side_effect=exists_mock),
            mock.patch.object(self.module.time, "sleep"),
        ):
            result = self.module.layer_intersections(
                False, output_dir, "/conts", "/conts.parquet",
                "cntry.parquet", "s3://bucket", ghsl, None
            )

        self.assertEqual(result[0], expected_ghsl_intersected)

