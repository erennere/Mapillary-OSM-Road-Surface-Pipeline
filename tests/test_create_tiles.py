import importlib
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


class FakeGeoDataFrame:
    def __init__(self, geometry=None, crs=None):
        self.data = {"geometry": list(geometry or [])}
        self.crs = crs
        self.saved = None

        class _ILoc:
            def __init__(self, parent):
                self.parent = parent

            def __getitem__(self, _idx):
                return self.parent

        self.iloc = _ILoc(self)

    def __setitem__(self, key, value):
        self.data[key] = list(value)

    def __getitem__(self, key):
        return self.data[key]

    def __len__(self):
        return len(self.data["geometry"])

    def to_file(self, path, driver=None, index=None):
        self.saved = (path, driver, index)


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


class CreateTilesMainExecutionTests(unittest.TestCase):
    def _install_fake_modules(self, read_parquet_side_effect=None):
        fake_mercantile = types.ModuleType("mercantile")
        fake_mercantile.tiles = lambda west, south, east, north, zoom: [FakeTile(1, 2, zoom), FakeTile(3, 4, zoom)]
        fake_mercantile.bounds = lambda tile: FakeBounds(tile.x, tile.y, tile.x + 0.5, tile.y + 0.5)

        fake_geopandas = types.ModuleType("geopandas")
        fake_geopandas.GeoDataFrame = FakeGeoDataFrame

        if read_parquet_side_effect is None:
            read_parquet_side_effect = lambda _path: None
        fake_geopandas.read_parquet = read_parquet_side_effect

        fake_shapely_geometry = types.ModuleType("shapely.geometry")
        fake_shapely_geometry.box = lambda west, south, east, north: FakePolygon((west, south, east, north))

        fake_start = types.ModuleType("start")
        fake_start.load_config = lambda path=None: {
            "params": {"zoom_level": 8},
            "paths": {"tiles_save_dir": "/tmp/tiles", "starter_dir": "/tmp/starter"},
            "filenames": {"starter_polygon_fn": "", "country_filename": "country.parquet"},
        }
        fake_start.__getattr__ = lambda name: getattr(real_start, name)

        fake_numpy = types.ModuleType("numpy")
        fake_numpy.random = types.SimpleNamespace(randint=lambda low, high, size: [0, 1])

        return {
            "mercantile": fake_mercantile,
            "geopandas": fake_geopandas,
            "shapely.geometry": fake_shapely_geometry,
            "start": fake_start,
            "numpy": fake_numpy,
        }

    def test_main_executes_with_country_polygon_loaded(self):
        class FakeCountryGeom:
            def __init__(self):
                self.values = [FakePolygon((10, 20, 30, 40))]

        class FakeCountryData:
            def __getitem__(self, key):
                if key == "country":
                    return types.SimpleNamespace(__eq__=lambda _self, val: [val == "MG"])
                if isinstance(key, list):
                    return self
                raise KeyError(key)

            @property
            def geometry(self):
                return FakeCountryGeom()

        fake_modules = self._install_fake_modules(read_parquet_side_effect=lambda _path: FakeCountryData())

        with (
            mock.patch.dict(sys.modules, fake_modules),
            mock.patch("os.chdir"),
            mock.patch("os.path.exists", side_effect=lambda p: False if str(p).replace("\\", "/").endswith("/tmp/tiles") else True),
            mock.patch("os.makedirs"),
            mock.patch("builtins.print"),
        ):
            runpy.run_module("create_tiles", run_name="__main__")

    def test_main_falls_back_to_world_when_country_polygon_load_fails(self):
        fake_modules = self._install_fake_modules(read_parquet_side_effect=RuntimeError("boom"))

        with (
            mock.patch.dict(sys.modules, fake_modules),
            mock.patch("os.chdir"),
            mock.patch("os.path.exists", return_value=True),
            mock.patch("builtins.print"),
        ):
            runpy.run_module("create_tiles", run_name="__main__")

    def test_main_does_not_access_iloc_random_sampling_path(self):
        class NoIlocGeoDataFrame(FakeGeoDataFrame):
            def __init__(self, geometry=None, crs=None):
                self.data = {"geometry": list(geometry or [])}
                self.crs = crs
                self.saved = None

            @property
            def iloc(self):
                raise AssertionError("iloc should not be used in main")

        fake_modules = self._install_fake_modules(read_parquet_side_effect=RuntimeError("boom"))
        fake_modules["geopandas"].GeoDataFrame = NoIlocGeoDataFrame

        with (
            mock.patch.dict(sys.modules, fake_modules),
            mock.patch("os.chdir"),
            mock.patch("os.path.exists", return_value=True),
            mock.patch("builtins.print"),
        ):
            runpy.run_module("create_tiles", run_name="__main__")

    def test_main_falls_back_to_first_geometry_when_country_filter_not_available(self):
        class _GeometryValues:
            values = [FakePolygon((11, 22, 33, 44))]

        class _CountryDataNoFilter:
            def __getitem__(self, key):
                raise KeyError(key)

            @property
            def geometry(self):
                return _GeometryValues()

        fake_modules = self._install_fake_modules(read_parquet_side_effect=lambda _path: _CountryDataNoFilter())

        with (
            mock.patch.dict(sys.modules, fake_modules),
            mock.patch("os.chdir"),
            mock.patch("os.path.exists", return_value=True),
            mock.patch("builtins.print"),
        ):
            runpy.run_module("create_tiles", run_name="__main__")

    def test_main_uses_starter_polygon_when_country_polygon_load_fails(self):
        class _GeometryValues:
            values = [FakePolygon((7, 8, 9, 10))]

        class _StarterData:
            @property
            def geometry(self):
                return _GeometryValues()

        def _read_parquet(path):
            norm = str(path).replace("\\", "/")
            if norm.endswith("/tmp/starter/country.parquet"):
                raise RuntimeError("country missing")
            if norm.endswith("/tmp/starter/starter_fallback.parquet"):
                return _StarterData()
            raise AssertionError(f"Unexpected path: {path}")

        fake_modules = self._install_fake_modules(read_parquet_side_effect=_read_parquet)
        fake_modules["start"].load_config = lambda path=None: {
            "params": {"zoom_level": 8},
            "paths": {"tiles_save_dir": "/tmp/tiles", "starter_dir": "/tmp/starter"},
            "filenames": {"starter_polygon_fn": "starter_fallback.parquet", "country_filename": "country.parquet"},
        }

        with (
            mock.patch.dict(sys.modules, fake_modules),
            mock.patch("os.chdir"),
            mock.patch("os.path.exists", return_value=True),
            mock.patch("builtins.print"),
        ):
            runpy.run_module("create_tiles", run_name="__main__")

    def test_main_handles_missing_filenames_section(self):
        fake_modules = self._install_fake_modules(read_parquet_side_effect=RuntimeError("boom"))
        fake_modules["start"].load_config = lambda path=None: {
            "params": {"zoom_level": 8},
            "paths": {"tiles_save_dir": "/tmp/tiles", "starter_dir": "/tmp/starter"},
        }

        with (
            mock.patch.dict(sys.modules, fake_modules),
            mock.patch("os.chdir"),
            mock.patch("os.path.exists", return_value=True),
            mock.patch("builtins.print"),
        ):
            with self.assertRaises(KeyError):
                runpy.run_module("create_tiles", run_name="__main__")

