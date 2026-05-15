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
    fake_duckdb = types.ModuleType("duckdb")

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
