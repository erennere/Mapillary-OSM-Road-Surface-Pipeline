import importlib
import sys
import types
import unittest
from pathlib import Path
from unittest import mock


RESEARCH_CODE_DIR = Path(__file__).resolve().parents[1] / "research_code"
if str(RESEARCH_CODE_DIR) not in sys.path:
    sys.path.insert(0, str(RESEARCH_CODE_DIR))


class FakeGeoDataFrame:
    def __init__(self, geometry=None, crs=None):
        self.data = {"geometry": list(geometry or [])}
        self.crs = crs

    def __setitem__(self, key, value):
        self.data[key] = list(value)

    def __getitem__(self, key):
        return self.data[key]

    def __len__(self):
        return len(self.data["geometry"])


class FakePolygon:
    def __init__(self, bounds):
        self.bounds = bounds


class FakeTile:
    def __init__(self, x, y, z):
        self.x = x
        self.y = y
        self.z = z


class FakeBounds:
    def __init__(self, west, south, east, north):
        self.west = west
        self.south = south
        self.east = east
        self.north = north


def import_create_tiles_module():
    sys.modules.pop("create_tiles", None)

    fake_mercantile = types.ModuleType("mercantile")
    fake_mercantile.tiles_calls = []

    def fake_tiles(west, south, east, north, zoom_level):
        fake_mercantile.tiles_calls.append((west, south, east, north, zoom_level))
        return [FakeTile(1, 2, zoom_level), FakeTile(3, 4, zoom_level)]

    def fake_bounds(tile):
        return FakeBounds(tile.x, tile.y, tile.x + 0.5, tile.y + 0.5)

    fake_mercantile.tiles = fake_tiles
    fake_mercantile.bounds = fake_bounds

    fake_geopandas = types.ModuleType("geopandas")
    fake_geopandas.GeoDataFrame = FakeGeoDataFrame

    fake_shapely_geometry = types.ModuleType("shapely.geometry")

    def fake_box(west, south, east, north):
        return FakePolygon((west, south, east, north))

    fake_shapely_geometry.box = fake_box

    with mock.patch.dict(
        sys.modules,
        {
            "mercantile": fake_mercantile,
            "geopandas": fake_geopandas,
            "shapely.geometry": fake_shapely_geometry,
        },
    ):
        module = importlib.import_module("create_tiles")

    return module, fake_mercantile


class CreateTilesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module, cls.fake_mercantile = import_create_tiles_module()

    def test_get_tiles_from_polygon_uses_polygon_bounds_and_populates_columns(self):
        polygon = FakePolygon((10, 20, 30, 40))

        result = self.module.get_tiles_from_polygon(polygon=polygon, zoom_level=7)

        self.assertEqual(self.fake_mercantile.tiles_calls[-1], (10, 20, 30, 40, 7))
        self.assertEqual(result.crs, "EPSG:4326")
        self.assertEqual(result["id"], [0, 1])
        self.assertEqual(result["x"], [1, 3])
        self.assertEqual(result["y"], [2, 4])
        self.assertEqual(result["z"], [7, 7])
        self.assertEqual(
            [geom.bounds for geom in result["geometry"]],
            [(1, 2, 1.5, 2.5), (3, 4, 3.5, 4.5)],
        )

    def test_get_tiles_from_polygon_defaults_to_world_bounds(self):
        self.module.get_tiles_from_polygon(polygon=None, zoom_level=5)

        self.assertEqual(self.fake_mercantile.tiles_calls[-1], (-180, -90, 180, 90, 5))

