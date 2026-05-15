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


class FakeSeries:
    """Minimal Series-like object."""

    def __init__(self, values):
        self._values = list(values)

    def astype(self, dtype):
        return FakeSeries([str(v) if dtype == str else dtype(v) for v in self._values])

    def unique(self):
        seen = []
        for v in self._values:
            if v not in seen:
                seen.append(v)
        return FakeSeries(seen)

    def tolist(self):
        return list(self._values)

    def __iter__(self):
        return iter(self._values)

    def __eq__(self, other):
        if isinstance(other, FakeSeries):
            return FakeMask([v == o for v, o in zip(self._values, other._values)])
        return FakeMask([v == other for v in self._values])


class FakeMask:
    def __init__(self, values):
        self._values = values


class FakeTilesGdf:
    """Minimal GeoDataFrame that supports filtering and column access."""

    def __init__(self, tiles_col, data):
        self._tiles_col = tiles_col
        self._data = data  # list of dicts with 'tile' and 'id' keys

    def __getitem__(self, mask_or_col):
        if isinstance(mask_or_col, str):
            return FakeSeries([row[mask_or_col] for row in self._data])
        if isinstance(mask_or_col, FakeMask):
            return FakeTilesGdf(
                self._tiles_col,
                [row for row, keep in zip(self._data, mask_or_col._values) if keep],
            )
        raise TypeError(f"Unexpected key type: {type(mask_or_col)}")


class FakeOldMetadata:
    """Fake return value of pd.read_csv."""

    def __init__(self, sequences):
        self._sequences = sequences

    def __getitem__(self, col):
        if col == "sequence":
            return FakeSeries(self._sequences)
        raise KeyError(col)


def import_get_metadata_module():
    sys.modules.pop("get_metadata", None)

    fake_pandas = types.ModuleType("pandas")
    fake_pandas.read_csv = None  # placeholder for patching
    fake_geopandas = types.ModuleType("geopandas")
    fake_metadata_download = types.ModuleType("metadata_download")
    fake_metadata_download.get_metadata = lambda *args, **kwargs: None
    fake_start = types.ModuleType("start")
    fake_start.load_config = lambda path=None: {}

    with mock.patch.dict(
        sys.modules,
        {
            "pandas": fake_pandas,
            "geopandas": fake_geopandas,
            "metadata_download": fake_metadata_download,
            "start": fake_start,
        },
    ):
        return importlib.import_module("get_metadata")


class ProcessSingleTileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_get_metadata_module()

    def _make_gdf(self, tile, sequences, tiles_col):
        data = [{"id": seq, tiles_col: tile} for seq in sequences]
        return FakeTilesGdf(tiles_col, data)

    def test_process_single_tile_calls_get_metadata_with_all_new_sequences(self):
        generator = random.Random(1201)
        tile = f"{generator.randint(0, 100)}-{generator.randint(0, 100)}-8"
        tiles_col = "z8_tiles"
        data_dir = f"/tmp/data_{generator.randint(100, 999)}"
        sequences = [str(generator.randint(1000, 9999)) for _ in range(4)]
        metadata_args = {"mly_key": f"key_{generator.randint(100, 999)}"}

        gdf = self._make_gdf(tile, sequences, tiles_col)
        received_sequences = []

        def fake_get_metadata(seqs, *args, **kwargs):
            received_sequences.extend(seqs)

        with (
            mock.patch.object(self.module.os.path, "exists", return_value=False),
            mock.patch.object(self.module, "get_metadata", side_effect=fake_get_metadata),
            mock.patch.object(self.module.random, "shuffle"),
        ):
            self.module.process_single_tile(tile, gdf, tiles_col, data_dir, metadata_args)

        self.assertEqual(sorted(received_sequences), sorted(sequences))

    def test_process_single_tile_skips_already_downloaded_sequences(self):
        generator = random.Random(1202)
        tile = f"{generator.randint(0, 100)}-{generator.randint(0, 100)}-8"
        tiles_col = "z8_tiles"
        data_dir = f"/tmp/data_{generator.randint(100, 999)}"
        all_sequences = [str(generator.randint(1000, 9999)) for _ in range(5)]
        old_sequences = all_sequences[:2]
        new_sequences = all_sequences[2:]
        metadata_args = {}

        gdf = self._make_gdf(tile, all_sequences, tiles_col)
        received_sequences = []

        def fake_get_metadata(seqs, *args, **kwargs):
            received_sequences.extend(seqs)

        def fake_read_csv(path, usecols=None):
            return FakeOldMetadata(old_sequences)

        unfiltered_path = f"{data_dir}/metadata_unfiltered_{tile}.csv"

        with (
            mock.patch.object(
                self.module.os.path,
                "exists",
                side_effect=lambda p: p == unfiltered_path,
            ),
            mock.patch.object(self.module.pd, "read_csv", side_effect=fake_read_csv),
            mock.patch.object(self.module, "get_metadata", side_effect=fake_get_metadata),
            mock.patch.object(self.module.random, "shuffle"),
        ):
            self.module.process_single_tile(tile, gdf, tiles_col, data_dir, metadata_args)

        self.assertEqual(sorted(received_sequences), sorted(new_sequences))

    def test_process_single_tile_returns_without_calling_get_metadata_when_all_already_downloaded(self):
        generator = random.Random(1203)
        tile = f"{generator.randint(0, 100)}-{generator.randint(0, 100)}-8"
        tiles_col = "z8_tiles"
        data_dir = f"/tmp/data_{generator.randint(100, 999)}"
        sequences = [str(generator.randint(1000, 9999)) for _ in range(3)]
        metadata_args = {}

        gdf = self._make_gdf(tile, sequences, tiles_col)
        unfiltered_path = f"{data_dir}/metadata_unfiltered_{tile}.csv"

        def fake_read_csv(path, usecols=None):
            return FakeOldMetadata(sequences)

        get_metadata_called = []

        with (
            mock.patch.object(
                self.module.os.path,
                "exists",
                side_effect=lambda p: p == unfiltered_path,
            ),
            mock.patch.object(self.module.pd, "read_csv", side_effect=fake_read_csv),
            mock.patch.object(
                self.module,
                "get_metadata",
                side_effect=lambda *a, **k: get_metadata_called.append(True),
            ),
        ):
            self.module.process_single_tile(tile, gdf, tiles_col, data_dir, metadata_args)

        self.assertEqual(get_metadata_called, [])

    def test_process_single_tile_removes_stale_missing_sequences_file(self):
        generator = random.Random(1204)
        tile = f"{generator.randint(0, 100)}-{generator.randint(0, 100)}-8"
        tiles_col = "z8_tiles"
        data_dir = f"/tmp/data_{generator.randint(100, 999)}"
        sequences = [str(generator.randint(1000, 9999)) for _ in range(2)]
        metadata_args = {}

        gdf = self._make_gdf(tile, sequences, tiles_col)
        missing_path = f"{data_dir}/missing_sequences_{tile}.csv"

        with (
            mock.patch.object(
                self.module.os.path,
                "exists",
                side_effect=lambda p: p == missing_path,
            ),
            mock.patch.object(self.module.os, "remove") as remove_mock,
            mock.patch.object(self.module, "get_metadata"),
            mock.patch.object(self.module.random, "shuffle"),
        ):
            self.module.process_single_tile(tile, gdf, tiles_col, data_dir, metadata_args)

        remove_mock.assert_called_once_with(missing_path)

    def test_process_single_tile_passes_correct_file_paths_to_get_metadata(self):
        generator = random.Random(1205)
        tile = f"{generator.randint(0, 100)}-{generator.randint(0, 100)}-8"
        tiles_col = "z8_tiles"
        data_dir = f"/tmp/data_{generator.randint(100, 999)}"
        sequences = [str(generator.randint(1000, 9999)) for _ in range(2)]
        metadata_args = {"mly_key": "k", "extra": "val"}

        gdf = self._make_gdf(tile, sequences, tiles_col)
        expected_missing = f"{data_dir}/missing_sequences_{tile}.csv"
        expected_meta = f"{data_dir}/metadata_unfiltered_{tile}.csv"

        captured = {}

        def fake_get_metadata(seqs, missing_path, meta_path, **kwargs):
            captured["seqs"] = seqs
            captured["missing"] = missing_path
            captured["meta"] = meta_path
            captured["kwargs"] = kwargs

        with (
            mock.patch.object(self.module.os.path, "exists", return_value=False),
            mock.patch.object(self.module, "get_metadata", side_effect=fake_get_metadata),
            mock.patch.object(self.module.random, "shuffle"),
        ):
            self.module.process_single_tile(tile, gdf, tiles_col, data_dir, metadata_args)

        self.assertEqual(captured["missing"], expected_missing)
        self.assertEqual(captured["meta"], expected_meta)
        self.assertEqual(captured["kwargs"]["mly_key"], "k")
        self.assertEqual(captured["kwargs"]["extra"], "val")
