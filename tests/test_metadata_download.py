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


def import_metadata_download_module():
    sys.modules.pop("metadata_download", None)

    fake_numpy = types.ModuleType("numpy")
    fake_numpy.array = lambda x: x

    fake_pandas = types.ModuleType("pandas")
    fake_pandas.DataFrame = type("DataFrame", (), {"__init__": lambda s, *a, **k: None})

    fake_geopandas = types.ModuleType("geopandas")
    fake_geopandas.GeoDataFrame = type("GeoDataFrame", (), {})
    fake_shapely_geometry = types.ModuleType("shapely.geometry")
    fake_shapely_geometry.box = lambda w, s, e, n: (w, s, e, n)
    fake_shapely = types.ModuleType("shapely")
    fake_shapely.Point = lambda *args: args
    fake_aiohttp = types.ModuleType("aiohttp")
    fake_aiohttp.ClientSession = type("ClientSession", (), {})
    fake_tqdm = types.ModuleType("tqdm")
    fake_tqdm.tqdm = lambda iterable, **kwargs: iterable
    fake_start = types.ModuleType("start")
    fake_start.load_config = lambda path=None: {}

    with mock.patch.dict(
        sys.modules,
        {
            "numpy": fake_numpy,
            "pandas": fake_pandas,
            "geopandas": fake_geopandas,
            "shapely.geometry": fake_shapely_geometry,
            "shapely": fake_shapely,
            "aiohttp": fake_aiohttp,
            "tqdm": fake_tqdm,
            "start": fake_start,
        },
    ):
        return importlib.import_module("metadata_download")


class MetadataDownloadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_metadata_download_module()

    # -----------------------------------------------------------------------
    # check_timeout_function
    # -----------------------------------------------------------------------

    def test_check_timeout_function_returns_minus_one_when_start_is_true(self):
        result = self.module.check_timeout_function(start=True, interval=60, check_timeout=10)

        self.assertEqual(result, -1)

    def test_check_timeout_function_returns_zero_when_thread_stop_set(self):
        original = self.module.thread_stop

        try:
            self.module.thread_stop = True
            with mock.patch.object(self.module.time, "sleep"):
                result = self.module.check_timeout_function(start=False, interval=5, check_timeout=1)

            self.assertEqual(result, 0)
        finally:
            self.module.thread_stop = original

    def test_check_timeout_function_returns_one_after_normal_completion(self):
        original = self.module.thread_stop

        try:
            self.module.thread_stop = False
            with mock.patch.object(self.module.time, "sleep"):
                result = self.module.check_timeout_function(start=False, interval=5, check_timeout=100)

            self.assertEqual(result, 1)
        finally:
            self.module.thread_stop = original

    # -----------------------------------------------------------------------
    # segmented_bboxes
    # -----------------------------------------------------------------------

    def test_segmented_bboxes_returns_n_squared_sub_boxes_for_seeded_random_input(self):
        generator = random.Random(901)

        west = round(generator.uniform(-100, 0), 3)
        south = round(generator.uniform(-50, 0), 3)
        east = round(west + generator.uniform(1, 10), 3)
        north = round(south + generator.uniform(1, 10), 3)
        n = generator.randint(4, 9)

        boxes = self.module.segmented_bboxes([west, south, east, north], n)

        num_rows_cols = math.ceil(math.sqrt(n))
        self.assertEqual(len(boxes), num_rows_cols * num_rows_cols)
        for box in boxes:
            self.assertEqual(len(box), 4)
            bw, bs, be, bn = box
            self.assertGreaterEqual(bw, west)
            self.assertLessEqual(be, east + 0.0001)
            self.assertGreaterEqual(bs, south)
            self.assertLessEqual(bn, north + 0.0001)

    def test_segmented_bboxes_first_and_last_sub_box_cover_full_range(self):
        generator = random.Random(902)
        west = round(generator.uniform(-80, -10), 3)
        south = round(generator.uniform(-30, 0), 3)
        east = round(west + generator.uniform(5, 20), 3)
        north = round(south + generator.uniform(5, 20), 3)

        boxes = self.module.segmented_bboxes([west, south, east, north], n=1)

        self.assertEqual(len(boxes), 1)
        bw, bs, be, bn = boxes[0]
        self.assertAlmostEqual(bw, west, places=5)
        self.assertAlmostEqual(bs, south, places=5)
        self.assertAlmostEqual(be, east, places=5)
        self.assertAlmostEqual(bn, north, places=5)

    def test_segmented_bboxes_total_area_matches_original(self):
        generator = random.Random(903)
        west = round(generator.uniform(-50, 0), 4)
        south = round(generator.uniform(-20, 0), 4)
        east = round(west + generator.uniform(2, 8), 4)
        north = round(south + generator.uniform(2, 8), 4)
        n = generator.randint(2, 16)

        boxes = self.module.segmented_bboxes([west, south, east, north], n)

        total_area = sum((be - bw) * (bn - bs) for bw, bs, be, bn in boxes)
        expected_area = (east - west) * (north - south)
        self.assertAlmostEqual(total_area, expected_area, places=4)

    # -----------------------------------------------------------------------
    # process_generator
    # -----------------------------------------------------------------------

    def test_process_generator_yields_batches_of_correct_size(self):
        generator = random.Random(904)
        batch_size = generator.randint(3, 8)
        total = generator.randint(10, 30)
        sequences = [f"seq_{i}" for i in range(total)]

        batches = list(self.module.process_generator(sequences, batch_size=batch_size))

        for batch in batches[:-1]:
            self.assertEqual(len(batch), batch_size)
        self.assertLessEqual(len(batches[-1]), batch_size)
        self.assertEqual(sum(len(b) for b in batches), total)

    def test_process_generator_preserves_all_sequences_in_order(self):
        generator = random.Random(905)
        batch_size = generator.randint(2, 5)
        sequences = [f"seq_{generator.randint(0, 999)}" for _ in range(generator.randint(8, 20))]

        flat = [seq for batch in self.module.process_generator(sequences, batch_size=batch_size) for seq in batch]

        self.assertEqual(flat, sequences)

    def test_process_generator_handles_empty_sequence_list(self):
        batches = list(self.module.process_generator([], batch_size=10))

        self.assertEqual(batches, [])

    def test_process_generator_handles_exactly_one_batch(self):
        generator = random.Random(906)
        batch_size = generator.randint(5, 10)
        count = generator.randint(1, batch_size)
        sequences = [f"s{i}" for i in range(count)]

        batches = list(self.module.process_generator(sequences, batch_size=batch_size))

        self.assertEqual(len(batches), 1)
        self.assertEqual(batches[0], sequences)

    # -----------------------------------------------------------------------
    # write_data
    # -----------------------------------------------------------------------

    def test_write_data_creates_new_file_when_it_does_not_exist(self):
        generator = random.Random(907)
        filepath = f"/tmp/meta_{generator.randint(1000, 9999)}.csv"

        written_args = {}

        class FakeDf:
            def __len__(self):
                return 3

            def reset_index(self, drop, inplace):
                pass

            def to_csv(self, path, **kwargs):
                written_args.update(kwargs)
                written_args["path"] = path

        with mock.patch.object(self.module.os.path, "isfile", return_value=False):
            self.module.write_data(FakeDf(), filepath)

        self.assertEqual(written_args["path"], filepath)
        self.assertFalse(written_args.get("mode") == "a")

    def test_write_data_appends_to_existing_file(self):
        generator = random.Random(908)
        filepath = f"/tmp/meta_{generator.randint(1000, 9999)}.csv"

        written_args = {}

        class FakeDf:
            def __len__(self):
                return 5

            def reset_index(self, drop, inplace):
                pass

            def to_csv(self, path, **kwargs):
                written_args.update(kwargs)
                written_args["path"] = path

        with mock.patch.object(self.module.os.path, "isfile", return_value=True):
            self.module.write_data(FakeDf(), filepath)

        self.assertEqual(written_args["path"], filepath)
        self.assertEqual(written_args.get("mode"), "a")
        self.assertFalse(written_args.get("header", True))
