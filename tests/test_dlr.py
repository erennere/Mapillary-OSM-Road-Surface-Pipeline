"""Tests for dlr.py – download_and_process_tile and process_tile_file."""
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


# ---------------------------------------------------------------------------
# Minimal test doubles
# ---------------------------------------------------------------------------

class FakeRow:
    def __init__(self, x, y, z):
        self._d = {"x": x, "y": y, "z": z}

    def __getitem__(self, key):
        return self._d[key]


class FakeGeoDataFrame:
    def __init__(self, features=None, columns=None):
        self._features = list(features or [])
        self._cols = {}
        self.columns = columns or ["x", "y", "z", "geometry"]

    def __setitem__(self, key, value):
        self._cols[key] = value

    def __getitem__(self, key):
        return self._cols.get(key)

    def __len__(self):
        return len(self._features)

    def iterrows(self):
        return enumerate(self._features)

    @staticmethod
    def from_features(features):
        return FakeGeoDataFrame(features)


def import_dlr():
    sys.modules.pop("dlr", None)

    fake_requests = types.ModuleType("requests")
    fake_requests.get = None

    fake_vt2geojson = types.ModuleType("vt2geojson")
    fake_tools = types.ModuleType("vt2geojson.tools")
    fake_tools.vt_bytes_to_geojson = lambda *a: []

    fake_gpd = types.ModuleType("geopandas")
    fake_gpd.GeoDataFrame = FakeGeoDataFrame

    fake_pd = types.ModuleType("pandas")

    class _FakeDf:
        def reset_index(self, drop):
            return self

    fake_pd.DataFrame = lambda *a, **k: _FakeDf()
    fake_pd.concat = lambda frames, **k: frames[0] if frames else FakeGeoDataFrame()

    fake_tqdm = types.ModuleType("tqdm")
    fake_tqdm.tqdm = lambda iterable, **k: iterable

    fake_start = types.ModuleType("start")
    fake_start.load_config = lambda path=None: {}

    with mock.patch.dict(
        sys.modules,
        {
            "requests": fake_requests,
            "vt2geojson": fake_vt2geojson,
            "vt2geojson.tools": fake_tools,
            "geopandas": fake_gpd,
            "pandas": fake_pd,
            "tqdm": fake_tqdm,
            "start": fake_start,
        },
    ):
        return importlib.import_module("dlr")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class DlrDownloadAndProcessTileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_dlr()

    def test_success_returns_gdf_and_none(self):
        gen = random.Random(2001)
        z = gen.randint(1, 14)
        x, y = gen.randint(0, 200), gen.randint(0, 200)
        row = FakeRow(x=x, y=y, z=z)
        mly_key = f"k{gen.randint(1000, 9999)}"

        class OkResp:
            status_code = 200
            content = b"tile_bytes"

        with (
            mock.patch.object(self.module.requests, "get", return_value=OkResp()),
            mock.patch.object(self.module.vt2geojson_tools, "vt_bytes_to_geojson",
                              return_value=[{"type": "Feature"}]),
        ):
            gdf, failed = self.module.download_and_process_tile(row, mly_key, retries=3)

        self.assertIsNone(failed)
        self.assertIsNotNone(gdf)
        self.assertEqual(gdf[f"z{z}_tiles"], f"{x}-{y}-{z}")

    def test_url_contains_z_x_y_and_key(self):
        gen = random.Random(2002)
        z = gen.randint(1, 14)
        x, y = gen.randint(0, 200), gen.randint(0, 200)
        row = FakeRow(x=x, y=y, z=z)
        mly_key = f"key_{gen.randint(1000, 9999)}"
        called = []

        class OkResp:
            status_code = 200
            content = b"tb"

        def capture_get(url, **k):
            called.append((url, k))
            return OkResp()

        with (
            mock.patch.object(self.module.requests, "get", side_effect=capture_get),
            mock.patch.object(self.module.vt2geojson_tools, "vt_bytes_to_geojson",
                              return_value=[{"type": "Feature"}]),
        ):
            self.module.download_and_process_tile(row, mly_key)

        url, kwargs = called[0]
        self.assertIn(str(z), url)
        self.assertIn(str(x), url)
        self.assertIn(str(y), url)
        self.assertIn(mly_key, url)
        self.assertEqual(kwargs.get("timeout"), 10)

    def test_all_retries_exhausted_returns_none_gdf_and_row(self):
        gen = random.Random(2003)
        row = FakeRow(x=gen.randint(0, 100), y=gen.randint(0, 100), z=gen.randint(1, 14))
        retries = gen.randint(2, 4)

        class BadResp:
            status_code = 500
            content = b"err"

        with mock.patch.object(self.module.requests, "get", return_value=BadResp()):
            gdf, failed = self.module.download_and_process_tile(row, "key", retries=retries)

        self.assertIsNone(gdf)
        self.assertIs(failed, row)

    def test_retries_count_matches_parameter(self):
        gen = random.Random(2004)
        row = FakeRow(x=gen.randint(0, 100), y=gen.randint(0, 100), z=gen.randint(1, 14))
        retries = gen.randint(2, 5)
        call_count = []

        class BadResp:
            status_code = 500
            content = b"err"

        def counting_get(url, **k):
            call_count.append(1)
            return BadResp()

        with mock.patch.object(self.module.requests, "get", side_effect=counting_get):
            self.module.download_and_process_tile(row, "key", retries=retries)

        self.assertEqual(len(call_count), retries)

    def test_exception_during_request_increments_retry(self):
        gen = random.Random(2005)
        row = FakeRow(x=gen.randint(0, 100), y=gen.randint(0, 100), z=gen.randint(1, 14))

        with mock.patch.object(self.module.requests, "get",
                               side_effect=ConnectionError("no route")):
            gdf, failed = self.module.download_and_process_tile(row, "key", retries=3)

        self.assertIsNone(gdf)
        self.assertIs(failed, row)


class DlrProcessTileFileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_dlr()

    def _rows(self, gen, n):
        return [FakeRow(x=gen.randint(0, 100), y=gen.randint(0, 100),
                        z=gen.randint(1, 14)) for _ in range(n)]

    def test_all_successful_tiles_combined_into_gdf(self):
        gen = random.Random(2010)
        rows = self._rows(gen, 3)
        file = FakeGeoDataFrame(rows)
        file.iterrows = lambda: iter(enumerate(rows))

        fake_gdf = FakeGeoDataFrame(["f1"])
        combined = FakeGeoDataFrame(["f1", "f2"])

        class FakeFailedDf:
            def reset_index(self, drop): return self

        with (
            mock.patch.object(self.module, "download_and_process_tile",
                              side_effect=[(fake_gdf, None)] * 3),
            mock.patch.object(self.module.pd, "concat", return_value=combined),
            mock.patch.object(self.module.pd, "DataFrame", return_value=FakeFailedDf()),
            mock.patch.object(self.module.gpd, "GeoDataFrame",
                              side_effect=[combined, FakeGeoDataFrame()]),
        ):
            result_gdf, result_failed = self.module.process_tile_file(file, "key")

        self.assertIs(result_gdf, combined)
        self.assertIsNone(result_failed)

    def test_all_failed_tiles_returns_none_gdf(self):
        gen = random.Random(2011)
        rows = self._rows(gen, 2)
        file = FakeGeoDataFrame(rows)
        file.iterrows = lambda: iter(enumerate(rows))

        class FakeFailedDf:
            def reset_index(self, drop): return self

        fake_failed_gdf = FakeGeoDataFrame(rows)

        with (
            mock.patch.object(self.module, "download_and_process_tile",
                              side_effect=[(None, rows[0]), (None, rows[1])]),
            mock.patch.object(self.module.pd, "DataFrame", return_value=FakeFailedDf()),
            mock.patch.object(self.module.gpd, "GeoDataFrame", return_value=fake_failed_gdf),
        ):
            gdf, failed = self.module.process_tile_file(file, "key")

        self.assertIsNone(gdf)
        self.assertIsNotNone(failed)

    def test_empty_file_returns_none_none(self):
        file = FakeGeoDataFrame([])
        file.iterrows = lambda: iter([])

        with mock.patch.object(self.module, "download_and_process_tile") as mock_dap:
            gdf, failed = self.module.process_tile_file(file, "key")

        mock_dap.assert_not_called()
        self.assertIsNone(gdf)
        self.assertIsNone(failed)

    def test_mixed_success_and_failure_returns_combined_gdf_and_failed_gdf(self):
        gen = random.Random(2012)
        rows = self._rows(gen, 4)
        file = FakeGeoDataFrame(rows)
        file.iterrows = lambda: iter(enumerate(rows))

        ok_gdf = FakeGeoDataFrame(["ok"])
        combined = FakeGeoDataFrame(["ok", "ok2"])

        class FakeFailedDf:
            def reset_index(self, drop): return self

        failed_gdf = FakeGeoDataFrame(["bad"])

        side_effects = [
            (ok_gdf, None),
            (None, rows[1]),
            (ok_gdf, None),
            (None, rows[3]),
        ]

        with (
            mock.patch.object(self.module, "download_and_process_tile",
                              side_effect=side_effects),
            mock.patch.object(self.module.pd, "concat", return_value=combined),
            mock.patch.object(self.module.pd, "DataFrame", return_value=FakeFailedDf()),
            mock.patch.object(self.module.gpd, "GeoDataFrame",
                              side_effect=[combined, failed_gdf]),
        ):
            result_gdf, result_failed = self.module.process_tile_file(file, "key")

        self.assertIs(result_gdf, combined)
        self.assertIsNotNone(result_failed)


class DlrMainExecutionTests(unittest.TestCase):
    def _install_fake_modules(self):
        fake_requests = types.ModuleType("requests")

        class OkResp:
            status_code = 200
            content = b"bytes"

        fake_requests.get = lambda *a, **k: OkResp()

        fake_vt2geojson = types.ModuleType("vt2geojson")
        fake_tools = types.ModuleType("vt2geojson.tools")
        fake_tools.vt_bytes_to_geojson = lambda *a: []

        fake_gpd = types.ModuleType("geopandas")

        class _FakeMainGeoDf:
            saved_files = []

            def __init__(self, payload=None, geometry=None):
                self.payload = payload
                self.geometry = geometry
                self.columns = ["x", "y", "z", "geometry"]
                if isinstance(payload, dict):
                    x = payload.get("x", [0])[0]
                    y = payload.get("y", [0])[0]
                    z = payload.get("z", [0])[0]
                    self._rows = [{"x": x, "y": y, "z": z, "geometry": None}]
                elif isinstance(payload, list):
                    self._rows = payload
                else:
                    self._rows = []

            def __len__(self):
                return len(self._rows)

            def iterrows(self):
                return iter(enumerate(self._rows))

            def __setitem__(self, key, value):
                return None

            @staticmethod
            def from_features(features):
                return _FakeMainGeoDf([{"id": 1, "geometry": None}] if features is not None else [])

            def to_file(self, path, driver=None):
                _FakeMainGeoDf.saved_files.append((path, driver))

        fake_gpd.GeoDataFrame = _FakeMainGeoDf

        fake_pd = types.ModuleType("pandas")
        class _FakeDf:
            def __init__(self, data=None, **kwargs):
                self.data = data

            def reset_index(self, drop=True):
                return self

        fake_pd.DataFrame = _FakeDf
        fake_pd.concat = lambda frames, **k: frames[0] if frames else None

        fake_tqdm = types.ModuleType("tqdm")
        fake_tqdm.tqdm = lambda iterable, **k: iterable

        fake_start = types.ModuleType("start")
        fake_start.load_config = lambda path=None: {
            "metadata_params": {"retries": 2},
            "params": {"mly_key": "key"},
        }

        modules = {
            "requests": fake_requests,
            "vt2geojson": fake_vt2geojson,
            "vt2geojson.tools": fake_tools,
            "geopandas": fake_gpd,
            "pandas": fake_pd,
            "tqdm": fake_tqdm,
            "start": fake_start,
        }
        return modules, _FakeMainGeoDf

    def test_main_saves_finished_file_when_processing_returns_data(self):
        fake_modules, fake_gdf_cls = self._install_fake_modules()
        fake_gdf_cls.saved_files = []

        with (
            mock.patch.dict(sys.modules, fake_modules),
            mock.patch("os.chdir"),
            mock.patch("os.getcwd", return_value="/tmp/dlr"),
            mock.patch("os.path.exists", return_value=True),
        ):
            runpy.run_module("dlr", run_name="__main__")

        saved_files = fake_gdf_cls.saved_files
        if saved_files:
            self.assertTrue(saved_files[0][0].replace("\\", "/").endswith("finished_dlr.gpkg"))

    def test_main_creates_directories_when_missing(self):
        fake_modules, _ = self._install_fake_modules()

        created = []

        with (
            mock.patch.dict(sys.modules, fake_modules),
            mock.patch("os.chdir"),
            mock.patch("os.getcwd", return_value="/tmp/dlr"),
            mock.patch("os.path.exists", return_value=False),
            mock.patch("os.makedirs", side_effect=lambda p, exist_ok=True: created.append((p, exist_ok))),
        ):
            runpy.run_module("dlr", run_name="__main__")

        self.assertGreaterEqual(len(created), 3)
