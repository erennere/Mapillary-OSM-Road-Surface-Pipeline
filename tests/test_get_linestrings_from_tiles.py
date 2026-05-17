import importlib
import runpy
import random
import sys
import types
import unittest
from pathlib import Path
from unittest import mock


RESEARCH_CODE_DIR = Path(__file__).resolve().parents[1] / "research_code"
if str(RESEARCH_CODE_DIR) not in sys.path:
    sys.path.insert(0, str(RESEARCH_CODE_DIR))


class FakeRow:
    """Simulate a pandas-style row with dict-like access."""

    def __init__(self, x, y, z):
        self._data = {"x": x, "y": y, "z": z}

    def __getitem__(self, key):
        return self._data[key]


class FakeGeoDataFrame:
    """Minimal GeoDataFrame stand-in that records columns set on it."""

    def __init__(self, features=None, columns=None):
        self._features = features or []
        self._cols = {}
        self.columns = columns or ["x", "y", "z", "geometry"]

    def __setitem__(self, key, value):
        self._cols[key] = value

    def __getitem__(self, key):
        return self._cols.get(key)

    def __len__(self):
        return len(self._features)

    def drop_duplicates(self, subset=None, inplace=False):
        return self

    def reset_index(self, drop=False, inplace=False):
        return self

    def to_file(self, path, driver=None):
        self._cols.setdefault("_saved", []).append((path, driver))

    def iterrows(self):
        return enumerate(self._features)

    @staticmethod
    def from_features(features):
        return FakeGeoDataFrame(features)


def import_get_linestrings_module():
    sys.modules.pop("get_linestrings_from_tiles", None)

    fake_requests = types.ModuleType("requests")
    fake_requests.get = None  # placeholder so patch.object can find and replace it
    fake_vt2geojson = types.ModuleType("vt2geojson")
    fake_vt2geojson_tools = types.ModuleType("vt2geojson.tools")
    fake_vt2geojson_tools.vt_bytes_to_geojson = lambda *args: []

    fake_geopandas = types.ModuleType("geopandas")
    fake_geopandas.GeoDataFrame = FakeGeoDataFrame

    fake_pandas = types.ModuleType("pandas")
    fake_pandas.DataFrame = lambda *args, **kwargs: None
    fake_pandas.concat = lambda frames, **kwargs: frames[0] if frames else None

    fake_tqdm = types.ModuleType("tqdm")
    fake_tqdm.tqdm = lambda iterable, **kwargs: iterable

    fake_start = types.ModuleType("start")
    fake_start.load_config = lambda path=None: {}

    with mock.patch.dict(
        sys.modules,
        {
            "requests": fake_requests,
            "vt2geojson": fake_vt2geojson,
            "vt2geojson.tools": fake_vt2geojson_tools,
            "geopandas": fake_geopandas,
            "pandas": fake_pandas,
            "tqdm": fake_tqdm,
            "start": fake_start,
        },
    ):
        return importlib.import_module("get_linestrings_from_tiles")


class GetLinestringsFromTilesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_get_linestrings_module()

    def test_download_and_process_tile_returns_gdf_and_none_on_success(self):
        generator = random.Random(851)
        z = generator.randint(1, 14)
        x = generator.randint(0, 100)
        y = generator.randint(0, 100)
        mly_key = f"key_{generator.randint(1000, 9999)}"

        row = FakeRow(x=x, y=y, z=z)
        fake_content = b"fake_tile_content"
        fake_features = [{"type": "Feature"}]

        class FakeResponse:
            status_code = 200
            content = fake_content

        with (
            mock.patch.object(self.module.requests, "get", return_value=FakeResponse()) as get_mock,
            mock.patch.object(self.module.vt2geojson_tools, "vt_bytes_to_geojson", return_value=fake_features),
        ):
            gdf, failed = self.module.download_and_process_tile(row, mly_key, retries=3)

        self.assertIsNone(failed)
        self.assertIsNotNone(gdf)
        called_url = get_mock.call_args[0][0]
        self.assertIn(str(z), called_url)
        self.assertIn(str(x), called_url)
        self.assertIn(str(y), called_url)
        self.assertIn(mly_key, called_url)
        self.assertEqual(gdf[f"z{z}_tiles"], f"{x}-{y}-{z}")

    def test_download_and_process_tile_returns_none_gdf_and_row_after_all_retries_fail(self):
        generator = random.Random(852)
        z = generator.randint(1, 14)
        x = generator.randint(0, 100)
        y = generator.randint(0, 100)
        retries = generator.randint(2, 4)
        row = FakeRow(x=x, y=y, z=z)

        class BadResponse:
            status_code = 500
            content = b"error"

        with mock.patch.object(self.module.requests, "get", return_value=BadResponse()):
            gdf, failed = self.module.download_and_process_tile(row, "key", retries=retries)

        self.assertIsNone(gdf)
        self.assertIs(failed, row)

    def test_download_and_process_tile_retries_before_giving_up(self):
        generator = random.Random(853)
        z = generator.randint(1, 14)
        x = generator.randint(0, 100)
        y = generator.randint(0, 100)
        retries = 3
        row = FakeRow(x=x, y=y, z=z)
        attempt_count = []

        class AlwaysFailResponse:
            status_code = 500
            content = b"error"

        def failing_get(url, **kwargs):
            attempt_count.append(1)
            return AlwaysFailResponse()

        with mock.patch.object(self.module.requests, "get", side_effect=failing_get):
            gdf, failed = self.module.download_and_process_tile(row, "key", retries=retries)

        self.assertEqual(len(attempt_count), retries)
        self.assertIsNone(gdf)
        self.assertIs(failed, row)

    def test_process_tile_file_collects_successful_tiles_and_discards_failed_ones(self):
        generator = random.Random(854)
        mly_key = f"key_{generator.randint(1000, 9999)}"

        fake_gdf_a = FakeGeoDataFrame(["feature_a"])
        fake_gdf_b = FakeGeoDataFrame(["feature_b"])

        rows = [
            FakeRow(x=generator.randint(0, 50), y=generator.randint(0, 50), z=8),
            FakeRow(x=generator.randint(51, 100), y=generator.randint(51, 100), z=8),
            FakeRow(x=generator.randint(0, 50), y=generator.randint(0, 50), z=8),
        ]

        return_values = [(fake_gdf_a, None), (None, rows[1]), (fake_gdf_b, None)]

        file = FakeGeoDataFrame(rows)
        file.iterrows = lambda: iter(enumerate(rows))

        combined = FakeGeoDataFrame(["feature_a", "feature_b"])

        class FakeFailedDf:
            def reset_index(self, drop):
                return self

        fake_failed_df = FakeFailedDf()

        with (
            mock.patch.object(
                self.module,
                "download_and_process_tile",
                side_effect=return_values,
            ),
            mock.patch.object(self.module.pd, "concat", return_value=combined),
            mock.patch.object(self.module.pd, "DataFrame", return_value=fake_failed_df),
            mock.patch.object(self.module.gpd, "GeoDataFrame", side_effect=[combined, FakeGeoDataFrame(["failed"])]),
        ):
            result_gdf, result_failed = self.module.process_tile_file(file, mly_key, retries=3)

        self.assertIs(result_gdf, combined)
        self.assertIsNotNone(result_failed)

    def test_process_tile_file_returns_none_continent_when_all_tiles_fail(self):
        generator = random.Random(855)
        mly_key = f"key_{generator.randint(1000, 9999)}"

        rows = [
            FakeRow(x=generator.randint(0, 50), y=generator.randint(0, 50), z=8),
            FakeRow(x=generator.randint(51, 100), y=generator.randint(51, 100), z=8),
        ]

        file = FakeGeoDataFrame(rows)
        file.iterrows = lambda: iter(enumerate(rows))

        class FakeFailedDf:
            def reset_index(self, drop):
                return self

        fake_failed_df = FakeFailedDf()
        fake_failed_gdf = FakeGeoDataFrame(rows)

        with (
            mock.patch.object(
                self.module,
                "download_and_process_tile",
                side_effect=[(None, rows[0]), (None, rows[1])],
            ),
            mock.patch.object(self.module.pd, "DataFrame", return_value=fake_failed_df),
            mock.patch.object(self.module.gpd, "GeoDataFrame", return_value=fake_failed_gdf),
        ):
            result_gdf, result_failed = self.module.process_tile_file(file, mly_key, retries=3)

        self.assertIsNone(result_gdf)
        self.assertIsNotNone(result_failed)


class GetLinestringsMainTests(unittest.TestCase):
    def _cfg(self):
        return {
            "metadata_params": {"retries": 2},
            "params": {"zoom_level": 8, "mly_key": "k"},
            "paths": {
                "tiles_save_dir": "/tmp/tiles",
                "completed_tiles_dir": "/tmp/completed",
                "failed_tiles_dir": "/tmp/failed",
            },
        }

    def _fake_modules(self, read_file_fn):
        fake_requests = types.ModuleType("requests")
        fake_vt2geojson = types.ModuleType("vt2geojson")
        fake_vt2geojson_tools = types.ModuleType("vt2geojson.tools")
        fake_vt2geojson_tools.vt_bytes_to_geojson = lambda *args: []
        fake_geopandas = types.ModuleType("geopandas")
        fake_geopandas.GeoDataFrame = FakeGeoDataFrame
        fake_geopandas.read_file = read_file_fn
        fake_pandas = types.ModuleType("pandas")
        fake_pandas.DataFrame = lambda *args, **kwargs: None
        fake_pandas.concat = lambda frames, **kwargs: frames[0] if frames else None
        fake_tqdm = types.ModuleType("tqdm")
        fake_tqdm.tqdm = lambda iterable, **kwargs: iterable
        fake_start = types.ModuleType("start")
        fake_start.load_config = lambda path=None: self._cfg()
        return {
            "requests": fake_requests,
            "vt2geojson": fake_vt2geojson,
            "vt2geojson.tools": fake_vt2geojson_tools,
            "geopandas": fake_geopandas,
            "pandas": fake_pandas,
            "tqdm": fake_tqdm,
            "start": fake_start,
        }

    def test_main_creates_directories_and_handles_empty_tile_list(self):

        def fake_exists(path):
            norm = str(path).replace("\\", "/")
            return not (norm.endswith("/tmp/tiles") or norm.endswith("/tmp/completed") or norm.endswith("/tmp/failed"))

        with (
            mock.patch.dict(sys.modules, self._fake_modules(lambda _p: None)),
            mock.patch("os.chdir"),
            mock.patch("os.path.exists", side_effect=fake_exists),
            mock.patch("os.makedirs") as makedirs_mock,
            mock.patch("os.listdir", return_value=["other.txt"]),
        ):
            runpy.run_module("get_linestrings_from_tiles", run_name="__main__")

        self.assertGreaterEqual(makedirs_mock.call_count, 3)

    def test_main_continues_when_read_file_raises(self):
        with (
            mock.patch.dict(sys.modules, self._fake_modules(lambda _p: (_ for _ in ()).throw(RuntimeError("boom")))),
            mock.patch("os.chdir"),
            mock.patch("os.path.exists", return_value=True),
            mock.patch("os.listdir", return_value=["tiles_z8.gpkg"]),
        ):
            runpy.run_module("get_linestrings_from_tiles", run_name="__main__")

    def test_main_writes_both_completed_and_failed_outputs_when_both_exist(self):
        class MainGeoDf(FakeGeoDataFrame):
            saved_paths = []

            def __init__(self, features=None, columns=None, geometry=None, **kwargs):
                if hasattr(features, "rows"):
                    features = features.rows
                super().__init__(features=features, columns=columns)

            @staticmethod
            def from_features(features):
                return MainGeoDf(features)

            def to_file(self, path, driver=None):
                MainGeoDf.saved_paths.append((path, driver))

        fake_requests = types.ModuleType("requests")

        class Resp200:
            status_code = 200
            content = b"ok"

        class Resp500:
            status_code = 500
            content = b"bad"

        fake_requests_calls = {"n": 0}

        def fake_get(url, timeout=10):
            fake_requests_calls["n"] += 1
            return Resp200() if fake_requests_calls["n"] == 1 else Resp500()

        fake_requests.get = fake_get

        fake_vt2geojson = types.ModuleType("vt2geojson")
        fake_vt2geojson_tools = types.ModuleType("vt2geojson.tools")
        fake_vt2geojson_tools.vt_bytes_to_geojson = lambda *args: [{"type": "Feature"}]

        fake_geopandas = types.ModuleType("geopandas")
        fake_geopandas.GeoDataFrame = MainGeoDf
        fake_geopandas.read_file = lambda _p: MainGeoDf([{"x": 1, "y": 2, "z": 8}, {"x": 3, "y": 4, "z": 8}])

        class FakeDf:
            def __init__(self, rows=None):
                self.rows = rows or []

            def reset_index(self, drop=True):
                return self

        fake_pandas = types.ModuleType("pandas")
        fake_pandas.DataFrame = lambda rows, columns=None: FakeDf(rows)
        fake_pandas.concat = lambda frames, **kwargs: frames[0] if frames else MainGeoDf([])

        fake_tqdm = types.ModuleType("tqdm")
        fake_tqdm.tqdm = lambda iterable, **kwargs: iterable

        fake_start = types.ModuleType("start")
        fake_start.load_config = lambda path=None: self._cfg()

        with (
            mock.patch.dict(
                sys.modules,
                {
                    "requests": fake_requests,
                    "vt2geojson": fake_vt2geojson,
                    "vt2geojson.tools": fake_vt2geojson_tools,
                    "geopandas": fake_geopandas,
                    "pandas": fake_pandas,
                    "tqdm": fake_tqdm,
                    "start": fake_start,
                },
            ),
            mock.patch("os.chdir"),
            mock.patch("os.path.exists", return_value=True),
            mock.patch("os.listdir", return_value=["tiles_z8.gpkg"]),
        ):
            MainGeoDf.saved_paths = []
            runpy.run_module("get_linestrings_from_tiles", run_name="__main__")

        saved_normalized = [p[0].replace("\\", "/") for p in MainGeoDf.saved_paths]
        self.assertTrue(any("/tmp/completed/finished_tiles_z8.gpkg" in p for p in saved_normalized))
        self.assertTrue(any("/tmp/failed/failed_tiles_z8.gpkg" in p for p in saved_normalized))

    def test_main_deduplicates_failed_tiles_with_existing_xyz_columns(self):
        class StrictGeoDf(FakeGeoDataFrame):
            saved_paths = []

            def __init__(self, features=None, columns=None, geometry=None, **kwargs):
                if hasattr(features, "rows"):
                    features = features.rows
                super().__init__(features=features, columns=columns or ["x", "y", "z", "geometry"])

            @staticmethod
            def from_features(features):
                return StrictGeoDf(features)

            def drop_duplicates(self, subset=None, inplace=False):
                if subset is not None:
                    for col in subset:
                        if col not in self.columns:
                            raise AssertionError(f"Unexpected subset column: {col}")
                return self

            def to_file(self, path, driver=None):
                StrictGeoDf.saved_paths.append((path, driver))

        fake_requests = types.ModuleType("requests")

        class Resp500:
            status_code = 500
            content = b"bad"

        fake_requests.get = lambda url, timeout=10: Resp500()

        fake_vt2geojson = types.ModuleType("vt2geojson")
        fake_vt2geojson_tools = types.ModuleType("vt2geojson.tools")
        fake_vt2geojson_tools.vt_bytes_to_geojson = lambda *args: []

        fake_geopandas = types.ModuleType("geopandas")
        fake_geopandas.GeoDataFrame = StrictGeoDf
        fake_geopandas.read_file = lambda _p: StrictGeoDf([{"x": 1, "y": 2, "z": 8}])

        class FakeDf:
            def __init__(self, rows=None):
                self.rows = rows or []

            def reset_index(self, drop=True):
                return self

        fake_pandas = types.ModuleType("pandas")
        fake_pandas.DataFrame = lambda rows, columns=None: FakeDf(rows)
        fake_pandas.concat = lambda frames, **kwargs: frames[0] if frames else StrictGeoDf([])

        fake_tqdm = types.ModuleType("tqdm")
        fake_tqdm.tqdm = lambda iterable, **kwargs: iterable

        fake_start = types.ModuleType("start")
        fake_start.load_config = lambda path=None: self._cfg()

        with (
            mock.patch.dict(
                sys.modules,
                {
                    "requests": fake_requests,
                    "vt2geojson": fake_vt2geojson,
                    "vt2geojson.tools": fake_vt2geojson_tools,
                    "geopandas": fake_geopandas,
                    "pandas": fake_pandas,
                    "tqdm": fake_tqdm,
                    "start": fake_start,
                },
            ),
            mock.patch("os.chdir"),
            mock.patch("os.path.exists", return_value=True),
            mock.patch("os.listdir", return_value=["tiles_z8.gpkg"]),
        ):
            StrictGeoDf.saved_paths = []
            runpy.run_module("get_linestrings_from_tiles", run_name="__main__")

        saved_normalized = [p[0].replace("\\", "/") for p in StrictGeoDf.saved_paths]
        self.assertTrue(any("/tmp/failed/failed_tiles_z8.gpkg" in p for p in saved_normalized))
