import importlib
import math
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


def import_metadata_download_module():
    sys.modules.pop("metadata_download", None)

    fake_numpy = types.ModuleType("numpy")
    fake_numpy.array = lambda x: x

    fake_pandas = types.ModuleType("pandas")
    fake_pandas.DataFrame = type("DataFrame", (), {"__init__": lambda s, *a, **k: None})
    fake_pandas.concat = lambda frames, *args, **kwargs: frames[0] if frames else None

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
    fake_start.__getattr__ = lambda name: getattr(real_start, name)

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

    def test_parse_positive_int_accepts_valid_positive_values(self):
        self.assertEqual(
            self.module.parse_positive_int(7, "metadata_download.int_value", 4),
            7,
        )

    def test_parse_positive_int_clamps_non_positive_values(self):
        self.assertEqual(
            self.module.parse_positive_int(0, "metadata_download.int_value", 4),
            1,
        )
        self.assertEqual(
            self.module.parse_positive_int(-2, "metadata_download.int_value", 4),
            1,
        )

    def test_parse_positive_int_returns_default_for_invalid_value(self):
        self.assertEqual(
            self.module.parse_positive_int("bad", "metadata_download.int_value", 4),
            4,
        )

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

    def test_segmented_bboxes_normalizes_zero_subdivisions_to_single_box(self):
        west, south, east, north = -10.0, -5.0, 10.0, 5.0

        boxes = self.module.segmented_bboxes([west, south, east, north], n=0)

        self.assertEqual(len(boxes), 1)
        self.assertEqual(boxes[0], [west, south, east, north])

    def test_segmented_bboxes_normalizes_invalid_subdivisions_to_single_box(self):
        west, south, east, north = -10.0, -5.0, 10.0, 5.0

        boxes = self.module.segmented_bboxes([west, south, east, north], n="bad")

        self.assertEqual(len(boxes), 1)
        self.assertEqual(boxes[0], [west, south, east, north])

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


# ---------------------------------------------------------------------------
# monitor_connections
# ---------------------------------------------------------------------------

class MonitorConnectionsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_metadata_download_module()

    def test_start_true_resets_connection_quota_and_returns_immediately(self):
        orig_stop = self.module.thread_stop
        orig_conn = self.module.allowed_connection
        orig_curr = self.module.allowed_connection_current

        try:
            self.module.thread_stop = False
            self.module.allowed_connection = 500
            self.module.allowed_connection_current = 0

            self.module.monitor_connections(interval=1, start=True, check_timeout=1)

            self.assertEqual(self.module.allowed_connection_current, 500)
        finally:
            self.module.thread_stop = orig_stop
            self.module.allowed_connection = orig_conn
            self.module.allowed_connection_current = orig_curr

    def test_sets_current_connections_to_allowed_connections_value(self):
        gen = random.Random(910)
        orig_stop = self.module.thread_stop
        orig_conn = self.module.allowed_connection
        orig_curr = self.module.allowed_connection_current

        try:
            self.module.thread_stop = False
            value = gen.randint(50, 500)
            self.module.allowed_connection = value
            self.module.allowed_connection_current = 0

            self.module.monitor_connections(interval=0.1, start=True, check_timeout=0.1)

            self.assertEqual(self.module.allowed_connection_current, value)
        finally:
            self.module.thread_stop = orig_stop
            self.module.allowed_connection = orig_conn
            self.module.allowed_connection_current = orig_curr


# ---------------------------------------------------------------------------
# write_sequences
# ---------------------------------------------------------------------------

class WriteSequencesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_metadata_download_module()

    def test_writes_global_sequences_to_csv_and_exits_when_start_true(self):
        gen = random.Random(911)
        n = gen.randint(3, 10)
        sequences = {f"seq_{i}" for i in range(n)}

        orig_stop = self.module.thread_stop
        orig_seqs = self.module.global_sequences

        written = {}

        class FakeDf:
            def __init__(self, data):
                written["data"] = data

            def to_csv(self, path, index):
                written["path"] = path
                written["index"] = index

        try:
            self.module.thread_stop = False
            self.module.global_sequences = sequences.copy()
            filepath = f"/tmp/seqs_{gen.randint(1000, 9999)}.csv"

            with mock.patch.object(self.module.pd, "DataFrame", side_effect=FakeDf):
                self.module.write_sequences(filepath, start=True)

            self.assertEqual(written.get("path"), filepath)
            self.assertEqual(set(written["data"]["sequences"]), sequences)
        finally:
            self.module.thread_stop = orig_stop
            self.module.global_sequences = orig_seqs

    def test_exits_when_thread_stop_signal_received(self):
        gen = random.Random(912)
        orig_stop = self.module.thread_stop
        orig_seqs = self.module.global_sequences

        try:
            self.module.thread_stop = True
            self.module.global_sequences = {f"s{i}" for i in range(gen.randint(2, 5))}

            written_paths = []

            class FakeDf:
                def __init__(self, data): pass
                def to_csv(self, path, index): written_paths.append(path)

            with (
                mock.patch.object(self.module.pd, "DataFrame", side_effect=FakeDf),
                mock.patch.object(self.module.time, "sleep"),
            ):
                self.module.write_sequences("/tmp/seqs.csv")

            # Should not have looped at all since thread_stop is True from the start
            self.assertEqual(len(written_paths), 0)
        finally:
            self.module.thread_stop = orig_stop
            self.module.global_sequences = orig_seqs


# ---------------------------------------------------------------------------
# flush_metadata_buffer
# ---------------------------------------------------------------------------

class FlushMetadataBufferTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_metadata_download_module()

    def test_clears_metadata_list_after_flush(self):
        gen = random.Random(913)
        orig_list = self.module.metadata_list

        class FakeDf:
            def __init__(self): self._n = gen.randint(1, 5)
            def __len__(self): return self._n
            def reset_index(self, drop, inplace=False): pass
            def to_csv(self, path, **kwargs): pass

        try:
            self.module.metadata_list = [FakeDf() for _ in range(gen.randint(1, 3))]

            concat_result = FakeDf()

            with (
                mock.patch.object(self.module.pd, "concat", return_value=concat_result),
                mock.patch.object(self.module, "write_data"),
            ):
                self.module.flush_metadata_buffer("/tmp/meta.csv")

            self.assertEqual(len(self.module.metadata_list), 0)
        finally:
            self.module.metadata_list = orig_list

    def test_does_nothing_when_list_empty(self):
        orig_list = self.module.metadata_list

        try:
            self.module.metadata_list = []

            with mock.patch.object(self.module, "write_data") as mock_wd:
                self.module.flush_metadata_buffer("/tmp/meta.csv")

            mock_wd.assert_not_called()
        finally:
            self.module.metadata_list = orig_list


# ---------------------------------------------------------------------------
# flush_missing_sequences_buffer
# ---------------------------------------------------------------------------

class FlushMissingSequencesBufferTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_metadata_download_module()

    def test_flushes_and_clears_missing_sequences_list(self):
        gen = random.Random(914)
        n = gen.randint(2, 6)
        sequences = [f"s{i}" for i in range(n)]
        orig_list = self.module.missing_sequences_list

        written = {}

        class FakeDf:
            def __init__(self, data): written["data"] = data
            def __len__(self): return n
            def reset_index(self, drop, inplace=False): pass
            def to_csv(self, path, **kwargs): written["path"] = path

        try:
            self.module.missing_sequences_list = sequences.copy()

            with (
                mock.patch.object(self.module.pd, "DataFrame", side_effect=FakeDf),
                mock.patch.object(self.module, "write_data"),
            ):
                self.module.flush_missing_sequences_buffer("/tmp/missing.csv")

            self.assertEqual(len(self.module.missing_sequences_list), 0)
        finally:
            self.module.missing_sequences_list = orig_list

    def test_does_nothing_when_missing_sequences_empty(self):
        orig_list = self.module.missing_sequences_list

        try:
            self.module.missing_sequences_list = []

            with mock.patch.object(self.module, "write_data") as mock_wd:
                self.module.flush_missing_sequences_buffer("/tmp/missing.csv")

            mock_wd.assert_not_called()
        finally:
            self.module.missing_sequences_list = orig_list


# ---------------------------------------------------------------------------
# write_data_on_the_fly
# ---------------------------------------------------------------------------

class WriteDataOnTheFlyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_metadata_download_module()

    def test_calls_flush_func_with_filepath_and_exits_when_end_true(self):
        gen = random.Random(915)
        filepath = f"/tmp/data_{gen.randint(1000, 9999)}.csv"
        calls = []
        orig_write = self.module.write_true

        try:
            self.module.write_true = True

            def fake_flush(fp):
                calls.append(fp)

            self.module.write_data_on_the_fly(filepath, fake_flush, end=True)

            self.assertIn(filepath, calls)
        finally:
            self.module.write_true = orig_write

    def test_still_calls_flush_when_end_true_and_write_true_is_false(self):
        gen = random.Random(916)
        filepath = f"/tmp/data_{gen.randint(1000, 9999)}.csv"
        calls = []
        orig_write = self.module.write_true

        try:
            self.module.write_true = False

            def fake_flush(fp):
                calls.append(fp)

            self.module.write_data_on_the_fly(filepath, fake_flush, end=True)

            self.assertEqual(calls, [filepath])
        finally:
            self.module.write_true = orig_write

    def test_when_end_true_calls_flush_exactly_once(self):
        filepath = "/tmp/data_end_once.csv"
        calls = []
        orig_write = self.module.write_true

        try:
            self.module.write_true = True

            def fake_flush(fp):
                calls.append(fp)

            self.module.write_data_on_the_fly(filepath, fake_flush, end=True)

            self.assertEqual(calls, [filepath])
        finally:
            self.module.write_true = orig_write

    def test_non_end_mode_flushes_again_when_write_flag_turns_false_during_wait(self):
        filepath = "/tmp/data_non_end.csv"
        calls = []
        orig_write = self.module.write_true

        try:
            self.module.write_true = True

            def fake_flush(fp):
                calls.append(fp)

            def fake_sleep(_t):
                self.module.write_true = False

            with mock.patch.object(self.module.time, "sleep", side_effect=fake_sleep):
                self.module.write_data_on_the_fly(
                    filepath,
                    fake_flush,
                    end=False,
                    interval=3,
                    check_timeout=1,
                )

            self.assertEqual(calls, [filepath, filepath])
        finally:
            self.module.write_true = orig_write

    def test_non_end_mode_exits_immediately_when_write_flag_is_false(self):
        filepath = "/tmp/data_non_end_false.csv"
        calls = []
        orig_write = self.module.write_true

        try:
            self.module.write_true = False

            def fake_flush(fp):
                calls.append(fp)

            self.module.write_data_on_the_fly(filepath, fake_flush, end=False, interval=2, check_timeout=1)

            self.assertEqual(calls, [])
        finally:
            self.module.write_true = orig_write

    def test_non_end_mode_can_loop_into_second_cycle(self):
        filepath = "/tmp/data_non_end_loop.csv"
        calls = []
        sleep_calls = {"n": 0}
        orig_write = self.module.write_true

        try:
            self.module.write_true = True

            def fake_flush(fp):
                calls.append(fp)

            def fake_sleep(_t):
                sleep_calls["n"] += 1
                if sleep_calls["n"] >= 3:
                    self.module.write_true = False

            with mock.patch.object(self.module.time, "sleep", side_effect=fake_sleep):
                self.module.write_data_on_the_fly(
                    filepath,
                    fake_flush,
                    end=False,
                    interval=2,
                    check_timeout=1,
                )

            self.assertGreaterEqual(len(calls), 3)
        finally:
            self.module.write_true = orig_write


# ---------------------------------------------------------------------------
# create_geodataframe_from_bboxes
# ---------------------------------------------------------------------------

class CreateGeoDataframeFromBboxesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_metadata_download_module()

    def test_produces_one_polygon_per_bbox(self):
        gen = random.Random(920)
        n = gen.randint(2, 6)
        bboxes = []
        for _ in range(n):
            w = gen.uniform(-100, -10)
            s = gen.uniform(-50, -5)
            e = w + gen.uniform(1, 10)
            no = s + gen.uniform(1, 10)
            bboxes.append([w, s, e, no])

        created_polygons = []

        def fake_box(w, s, e, n):
            poly = (w, s, e, n)
            created_polygons.append(poly)
            return poly

        class FakeGdf:
            def __init__(self, data): self.data = data

        with (
            mock.patch.object(self.module, "box", fake_box),
            mock.patch.object(self.module.gpd, "GeoDataFrame", side_effect=FakeGdf),
        ):
            result = self.module.create_geodataframe_from_bboxes(bboxes)

        self.assertEqual(len(created_polygons), n)
        for i, (w, s, e, no) in enumerate(bboxes):
            self.assertEqual(created_polygons[i], (w, s, e, no))

    def test_empty_bbox_list_produces_empty_geodataframe(self):
        class FakeGdf:
            def __init__(self, data): self.data = data

        with mock.patch.object(self.module.gpd, "GeoDataFrame", side_effect=FakeGdf):
            result = self.module.create_geodataframe_from_bboxes([])

        self.assertEqual(result.data["geometry"], [])


class MetadataDownloadMonitoringAndApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_metadata_download_module()

    def test_monitor_jobs_updates_allowed_connections_from_matching_files(self):
        orig_thread_stop = self.module.thread_stop
        orig_allowed = self.module.allowed_connection
        orig_jobs = self.module.number_of_jobs_running

        try:
            self.module.thread_stop = False
            now = 1000.0

            with (
                mock.patch.object(self.module.glob, "glob", return_value=["/tmp/a.csv", "/tmp/b.csv"], create=True),
                mock.patch.object(self.module.os.path, "isfile", return_value=True),
                mock.patch.object(self.module.os.path, "getmtime", return_value=995.0),
                mock.patch.object(self.module.time, "time", return_value=now),
                mock.patch.object(self.module, "check_timeout_function", return_value=-1),
            ):
                self.module.monitor_jobs(
                    patterns=[{"pattern": "/tmp/*.csv", "threshold": 10}],
                    interval=1,
                    start=False,
                    check_timeout=1,
                    max_connections=100,
                )

            self.assertEqual(self.module.number_of_jobs_running, 2)
            self.assertEqual(self.module.allowed_connection, round(100 / (2 + self.module.ZERO_DIVISION_SAFETY_FACTOR)))
        finally:
            self.module.thread_stop = orig_thread_stop
            self.module.allowed_connection = orig_allowed
            self.module.number_of_jobs_running = orig_jobs

    def test_monitor_jobs_ignores_single_file_stat_error_and_counts_remaining_files(self):
        orig_thread_stop = self.module.thread_stop
        orig_allowed = self.module.allowed_connection
        orig_jobs = self.module.number_of_jobs_running

        try:
            self.module.thread_stop = False
            now = 1000.0

            def fake_getmtime(path):
                if path.endswith("b.csv"):
                    raise OSError("gone")
                return 995.0

            with (
                mock.patch.object(self.module.glob, "glob", return_value=["/tmp/a.csv", "/tmp/b.csv"], create=True),
                mock.patch.object(self.module.os.path, "isfile", return_value=True),
                mock.patch.object(self.module.os.path, "getmtime", side_effect=fake_getmtime),
                mock.patch.object(self.module.time, "time", return_value=now),
                mock.patch.object(self.module, "check_timeout_function", return_value=-1),
            ):
                self.module.monitor_jobs(
                    patterns=[{"pattern": "/tmp/*.csv", "threshold": 10}],
                    interval=1,
                    start=False,
                    check_timeout=1,
                    max_connections=100,
                )

            self.assertEqual(self.module.number_of_jobs_running, 1)
            self.assertEqual(self.module.allowed_connection, round(100 / (1 + self.module.ZERO_DIVISION_SAFETY_FACTOR)))
        finally:
            self.module.thread_stop = orig_thread_stop
            self.module.allowed_connection = orig_allowed
            self.module.number_of_jobs_running = orig_jobs

    def test_monitor_jobs_falls_back_on_invalid_threshold_and_max_connections(self):
        orig_thread_stop = self.module.thread_stop
        orig_allowed = self.module.allowed_connection
        orig_jobs = self.module.number_of_jobs_running

        try:
            self.module.thread_stop = False
            now = 1000.0

            with (
                mock.patch.object(self.module.glob, "glob", return_value=["/tmp/a.csv"], create=True),
                mock.patch.object(self.module.os.path, "isfile", return_value=True),
                mock.patch.object(self.module.os.path, "getmtime", return_value=995.0),
                mock.patch.object(self.module.time, "time", return_value=now),
                mock.patch.object(self.module, "check_timeout_function", return_value=-1),
            ):
                self.module.monitor_jobs(
                    patterns=[{"pattern": "/tmp/*.csv", "threshold": "invalid"}],
                    interval=1,
                    start=False,
                    check_timeout=1,
                    max_connections="invalid",
                )

            self.assertEqual(self.module.number_of_jobs_running, 1)
            expected = round(10000 / (1 + self.module.ZERO_DIVISION_SAFETY_FACTOR))
            self.assertEqual(self.module.allowed_connection, expected)
        finally:
            self.module.thread_stop = orig_thread_stop
            self.module.allowed_connection = orig_allowed
            self.module.number_of_jobs_running = orig_jobs

    def test_monitor_jobs_skips_non_files_and_old_files(self):
        orig_thread_stop = self.module.thread_stop
        orig_allowed = self.module.allowed_connection
        orig_jobs = self.module.number_of_jobs_running

        try:
            self.module.thread_stop = False
            now = 1000.0

            def fake_isfile(path):
                return not path.endswith("skip.txt")

            def fake_getmtime(path):
                if path.endswith("old.csv"):
                    return 900.0
                return 995.0

            with (
                mock.patch.object(self.module.glob, "glob", return_value=["/tmp/skip.txt", "/tmp/old.csv", "/tmp/new.csv"], create=True),
                mock.patch.object(self.module.os.path, "isfile", side_effect=fake_isfile),
                mock.patch.object(self.module.os.path, "getmtime", side_effect=fake_getmtime),
                mock.patch.object(self.module.time, "time", return_value=now),
                mock.patch.object(self.module, "check_timeout_function", return_value=-1),
            ):
                self.module.monitor_jobs(
                    patterns=[{"pattern": "/tmp/*", "threshold": 10}],
                    interval=1,
                    start=False,
                    check_timeout=1,
                    max_connections=100,
                )

            self.assertEqual(self.module.number_of_jobs_running, 1)
        finally:
            self.module.thread_stop = orig_thread_stop
            self.module.allowed_connection = orig_allowed
            self.module.number_of_jobs_running = orig_jobs

    def test_monitor_jobs_returns_when_timeout_helper_returns_zero(self):
        orig_thread_stop = self.module.thread_stop
        try:
            self.module.thread_stop = False
            with (
                mock.patch.object(self.module.glob, "glob", return_value=[], create=True),
                mock.patch.object(self.module, "check_timeout_function", return_value=0),
            ):
                self.module.monitor_jobs(
                    patterns=[{"pattern": "/tmp/*", "threshold": 10}],
                    interval=1,
                    start=False,
                    check_timeout=1,
                    max_connections=100,
                )
        finally:
            self.module.thread_stop = orig_thread_stop

    def test_monitor_jobs_exits_immediately_when_thread_stop_true(self):
        orig_thread_stop = self.module.thread_stop
        try:
            self.module.thread_stop = True
            with mock.patch.object(self.module.glob, "glob", return_value=["/tmp/a.csv"], create=True) as glob_mock:
                self.module.monitor_jobs(
                    patterns=[{"pattern": "/tmp/*", "threshold": 10}],
                    interval=1,
                    start=False,
                    check_timeout=1,
                    max_connections=100,
                )
            glob_mock.assert_not_called()
        finally:
            self.module.thread_stop = orig_thread_stop

    def test_monitor_jobs_loops_again_when_timeout_helper_returns_one(self):
        orig_thread_stop = self.module.thread_stop
        calls = {"loops": 0}
        try:
            self.module.thread_stop = False

            def fake_timeout(*args, **kwargs):
                calls["loops"] += 1
                return 1 if calls["loops"] == 1 else 0

            with (
                mock.patch.object(self.module.glob, "glob", return_value=[], create=True),
                mock.patch.object(self.module, "check_timeout_function", side_effect=fake_timeout),
            ):
                self.module.monitor_jobs(
                    patterns=[{"pattern": "/tmp/*", "threshold": 10}],
                    interval=1,
                    start=False,
                    check_timeout=1,
                    max_connections=100,
                )

            self.assertEqual(calls["loops"], 2)
        finally:
            self.module.thread_stop = orig_thread_stop

    def test_monitor_connections_returns_when_timeout_helper_returns_zero(self):
        orig_thread_stop = self.module.thread_stop
        try:
            self.module.thread_stop = False
            with mock.patch.object(self.module, "check_timeout_function", return_value=0):
                self.module.monitor_connections(interval=1, start=False, check_timeout=1)
        finally:
            self.module.thread_stop = orig_thread_stop

    def test_monitor_connections_exits_immediately_when_thread_stop_true(self):
        orig_thread_stop = self.module.thread_stop
        orig_curr = self.module.allowed_connection_current
        try:
            self.module.thread_stop = True
            self.module.allowed_connection_current = 7
            self.module.monitor_connections(interval=1, start=False, check_timeout=1)
            self.assertEqual(self.module.allowed_connection_current, 7)
        finally:
            self.module.thread_stop = orig_thread_stop
            self.module.allowed_connection_current = orig_curr

    def test_monitor_connections_loops_again_when_timeout_helper_returns_one(self):
        orig_thread_stop = self.module.thread_stop
        calls = {"loops": 0}
        try:
            self.module.thread_stop = False

            def fake_timeout(*args, **kwargs):
                calls["loops"] += 1
                return 1 if calls["loops"] == 1 else 0

            with mock.patch.object(self.module, "check_timeout_function", side_effect=fake_timeout):
                self.module.monitor_connections(interval=1, start=False, check_timeout=1)

            self.assertEqual(calls["loops"], 2)
        finally:
            self.module.thread_stop = orig_thread_stop

    def test_write_sequences_returns_when_timeout_helper_returns_zero(self):
        orig_thread_stop = self.module.thread_stop
        try:
            self.module.thread_stop = False
            with (
                mock.patch.object(self.module.pd, "DataFrame", return_value=type("DF", (), {"to_csv": lambda s, *a, **k: None})(), create=True),
                mock.patch.object(self.module, "check_timeout_function", return_value=0),
            ):
                self.module.write_sequences("/tmp/seq.csv", interval=1, start=False, check_timeout=1)
        finally:
            self.module.thread_stop = orig_thread_stop

    def test_write_sequences_loops_again_when_timeout_helper_returns_one(self):
        orig_thread_stop = self.module.thread_stop
        calls = {"loops": 0}
        try:
            self.module.thread_stop = False

            def fake_timeout(*args, **kwargs):
                calls["loops"] += 1
                return 1 if calls["loops"] == 1 else 0

            with (
                mock.patch.object(self.module.pd, "DataFrame", return_value=type("DF", (), {"to_csv": lambda s, *a, **k: None})(), create=True),
                mock.patch.object(self.module, "check_timeout_function", side_effect=fake_timeout),
            ):
                self.module.write_sequences("/tmp/seq.csv", interval=1, start=False, check_timeout=1)

            self.assertEqual(calls["loops"], 2)
        finally:
            self.module.thread_stop = orig_thread_stop

    def test_write_bbox_exits_immediately_when_thread_stop_true(self):
        orig_thread_stop = self.module.thread_stop
        try:
            self.module.thread_stop = True
            with mock.patch.object(self.module, "create_geodataframe_from_bboxes") as gdf_mock:
                self.module.write_bbox("/tmp/bbox.gpkg", interval=1, start=False, check_timeout=1)
            gdf_mock.assert_not_called()
        finally:
            self.module.thread_stop = orig_thread_stop

    def test_write_bbox_loops_and_returns_when_timeout_transitions_from_one_to_zero(self):
        orig_thread_stop = self.module.thread_stop
        calls = {"loops": 0}

        class FakeGdf:
            def __len__(self):
                return 0

        try:
            self.module.thread_stop = False

            def fake_timeout(*args, **kwargs):
                calls["loops"] += 1
                return 1 if calls["loops"] == 1 else 0

            with (
                mock.patch.object(self.module, "create_geodataframe_from_bboxes", return_value=FakeGdf()),
                mock.patch.object(self.module, "check_timeout_function", side_effect=fake_timeout),
            ):
                self.module.write_bbox("/tmp/bbox.gpkg", interval=1, start=False, check_timeout=1)

            self.assertEqual(calls["loops"], 2)
        finally:
            self.module.thread_stop = orig_thread_stop

    def test_write_bbox_writes_when_bboxes_available(self):
        orig_thread_stop = self.module.thread_stop
        orig_bboxes = self.module.global_bboxes

        class FakeGdf:
            def __len__(self):
                return 1

            def to_file(self, path, driver=None, index=None):
                self.path = path

        fake_gdf = FakeGdf()

        try:
            self.module.thread_stop = False
            self.module.global_bboxes = {(1, 2, 3, 4)}

            with (
                mock.patch.object(self.module, "create_geodataframe_from_bboxes", return_value=fake_gdf),
                mock.patch.object(self.module, "check_timeout_function", return_value=-1),
            ):
                self.module.write_bbox("/tmp/bboxes.gpkg", interval=1, start=False, check_timeout=1)

            self.assertEqual(getattr(fake_gdf, "path", None), "/tmp/bboxes.gpkg")
        finally:
            self.module.thread_stop = orig_thread_stop
            self.module.global_bboxes = orig_bboxes

    def test_async_get_response_handles_non_200(self):
        orig_requests = self.module.number_of_requests

        class FakeResponse:
            status = 500

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def json(self):
                return {"error": "x"}

        class FakeSession:
            def get(self, _url):
                return FakeResponse()

        try:
            self.module.number_of_requests = 0
            result = self.module.asyncio.run(self.module.async_get_response(FakeSession(), "http://x"))
            self.assertIsNone(result)
            self.assertEqual(self.module.number_of_requests, 1)
        finally:
            self.module.number_of_requests = orig_requests

    def test_async_get_response_handles_none_response_object(self):
        class FakeResponseCtx:
            async def __aenter__(self):
                return None

            async def __aexit__(self, exc_type, exc, tb):
                return False

        class FakeSession:
            def get(self, _url):
                return FakeResponseCtx()

        result = self.module.asyncio.run(self.module.async_get_response(FakeSession(), "http://x"))
        self.assertIsNone(result)

    def test_async_get_response_handles_error_field_in_json_payload(self):
        class FakeResponse:
            status = 200

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def json(self):
                return {"error": {"message": "bad"}}

        class FakeSession:
            def get(self, _url):
                return FakeResponse()

        result = self.module.asyncio.run(self.module.async_get_response(FakeSession(), "http://x"))
        self.assertIsNone(result)

    def test_async_get_response_handles_null_json_payload(self):
        class FakeResponse:
            status = 200

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def json(self):
                return None

        class FakeSession:
            def get(self, _url):
                return FakeResponse()

        result = self.module.asyncio.run(self.module.async_get_response(FakeSession(), "http://x"))
        self.assertIsNone(result)

    def test_async_get_response_returns_json_payload_when_valid(self):
        payload = {"data": [{"id": 1}]}

        class FakeResponse:
            status = 200

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def json(self):
                return payload

        class FakeSession:
            def get(self, _url):
                return FakeResponse()

        result = self.module.asyncio.run(self.module.async_get_response(FakeSession(), "http://x"))
        self.assertEqual(result, payload)

    def test_data_handling_returns_dataframe_on_valid_payload(self):
        class FakeDf:
            def __init__(self, data):
                self.data = data
                self.empty = len(data) == 0

            def __len__(self):
                return len(self.data)

        async def fake_sleep(_t):
            return None

        orig_allowed_current = self.module.allowed_connection_current
        orig_jobs = self.module.number_of_jobs_running

        try:
            self.module.allowed_connection_current = 2
            self.module.number_of_jobs_running = 1

            with (
                mock.patch.object(self.module, "async_get_response", return_value={"data": [{"id": 1}]}, create=True),
                mock.patch.object(self.module.pd, "DataFrame", side_effect=lambda data: FakeDf(data)),
                mock.patch.object(self.module.asyncio, "sleep", side_effect=fake_sleep),
            ):
                data, attempt, empty_limit, is_empty, delay = self.module.asyncio.run(
                    self.module.data_handling(
                        session=object(),
                        url="http://x",
                        attempt=0,
                        empty_data_attempts=3,
                        is_data_empty=0,
                        sleep_time=1,
                        max_connections=100,
                    )
                )

            self.assertIsNotNone(data)
            self.assertEqual(attempt, 0)
            self.assertEqual(is_empty, 0)
        finally:
            self.module.allowed_connection_current = orig_allowed_current
            self.module.number_of_jobs_running = orig_jobs

    def test_data_handling_increments_attempt_when_no_json(self):
        async def fake_sleep(_t):
            return None

        orig_allowed_current = self.module.allowed_connection_current
        orig_jobs = self.module.number_of_jobs_running

        try:
            self.module.allowed_connection_current = 1
            self.module.number_of_jobs_running = 1

            with (
                mock.patch.object(self.module, "async_get_response", return_value=None, create=True),
                mock.patch.object(self.module.asyncio, "sleep", side_effect=fake_sleep),
            ):
                data, attempt, _, is_empty, _ = self.module.asyncio.run(
                    self.module.data_handling(
                        session=object(),
                        url="http://x",
                        attempt=2,
                        empty_data_attempts=3,
                        is_data_empty=0,
                        sleep_time=1,
                        max_connections=100,
                    )
                )

            self.assertIsNone(data)
            self.assertEqual(attempt, 3)
            self.assertEqual(is_empty, 0)
        finally:
            self.module.allowed_connection_current = orig_allowed_current
            self.module.number_of_jobs_running = orig_jobs

    def test_data_handling_increments_attempt_when_payload_is_not_dict(self):
        async def fake_sleep(_t):
            return None

        orig_allowed_current = self.module.allowed_connection_current
        orig_jobs = self.module.number_of_jobs_running

        try:
            self.module.allowed_connection_current = 1
            self.module.number_of_jobs_running = 1

            with (
                mock.patch.object(self.module, "async_get_response", return_value=[{"id": 1}], create=True),
                mock.patch.object(self.module.asyncio, "sleep", side_effect=fake_sleep),
            ):
                data, attempt, _, is_empty, _ = self.module.asyncio.run(
                    self.module.data_handling(
                        session=object(),
                        url="http://x",
                        attempt=1,
                        empty_data_attempts=3,
                        is_data_empty=0,
                        sleep_time=1,
                        max_connections=100,
                    )
                )

            self.assertIsNone(data)
            self.assertEqual(attempt, 2)
            self.assertEqual(is_empty, 0)
        finally:
            self.module.allowed_connection_current = orig_allowed_current
            self.module.number_of_jobs_running = orig_jobs

    def test_data_handling_handles_missing_data_key_in_payload(self):
        async def fake_sleep(_t):
            return None

        orig_allowed_current = self.module.allowed_connection_current
        orig_jobs = self.module.number_of_jobs_running

        try:
            self.module.allowed_connection_current = 1
            self.module.number_of_jobs_running = 1

            with (
                mock.patch.object(self.module, "async_get_response", return_value={"foo": "bar"}, create=True),
                mock.patch.object(self.module.asyncio, "sleep", side_effect=fake_sleep),
            ):
                data, attempt, _, is_empty, _ = self.module.asyncio.run(
                    self.module.data_handling(
                        session=object(),
                        url="http://x",
                        attempt=0,
                        empty_data_attempts=3,
                        is_data_empty=0,
                        sleep_time=1,
                        max_connections=100,
                    )
                )

            self.assertIsNone(data)
            self.assertEqual(attempt, 1)
            self.assertEqual(is_empty, 0)
        finally:
            self.module.allowed_connection_current = orig_allowed_current
            self.module.number_of_jobs_running = orig_jobs

    def test_data_handling_empty_data_reaches_limit_without_incrementing_empty_counter(self):
        class FakeDf:
            def __init__(self, data):
                self.data = data
                self.empty = True

        async def fake_sleep(_t):
            return None

        orig_allowed_current = self.module.allowed_connection_current
        orig_jobs = self.module.number_of_jobs_running

        try:
            self.module.allowed_connection_current = 1
            self.module.number_of_jobs_running = 1

            with (
                mock.patch.object(self.module, "async_get_response", return_value={"data": []}, create=True),
                mock.patch.object(self.module.pd, "DataFrame", side_effect=lambda data: FakeDf(data)),
                mock.patch.object(self.module.asyncio, "sleep", side_effect=fake_sleep),
            ):
                data, attempt, _, is_empty, _ = self.module.asyncio.run(
                    self.module.data_handling(
                        session=object(),
                        url="http://x",
                        attempt=0,
                        empty_data_attempts=1,
                        is_data_empty=1,
                        sleep_time=1,
                        max_connections=100,
                    )
                )

            self.assertIsNone(data)
            self.assertEqual(attempt, 0)
            self.assertEqual(is_empty, 1)
        finally:
            self.module.allowed_connection_current = orig_allowed_current
            self.module.number_of_jobs_running = orig_jobs

    def test_data_handling_empty_data_below_limit_increments_counter(self):
        class FakeDf:
            def __init__(self, data):
                self.data = data
                self.empty = True

        async def fake_sleep(_t):
            return None

        orig_allowed_current = self.module.allowed_connection_current
        orig_jobs = self.module.number_of_jobs_running

        try:
            self.module.allowed_connection_current = 1
            self.module.number_of_jobs_running = 1

            with (
                mock.patch.object(self.module, "async_get_response", return_value={"data": []}, create=True),
                mock.patch.object(self.module.pd, "DataFrame", side_effect=lambda data: FakeDf(data)),
                mock.patch.object(self.module.asyncio, "sleep", side_effect=fake_sleep),
            ):
                data, attempt, _, is_empty, _ = self.module.asyncio.run(
                    self.module.data_handling(
                        session=object(),
                        url="http://x",
                        attempt=0,
                        empty_data_attempts=3,
                        is_data_empty=0,
                        sleep_time=1,
                        max_connections=100,
                    )
                )

            self.assertIsNone(data)
            self.assertEqual(attempt, 0)
            self.assertEqual(is_empty, 1)
        finally:
            self.module.allowed_connection_current = orig_allowed_current
            self.module.number_of_jobs_running = orig_jobs

    def test_data_handling_waits_until_connection_becomes_available(self):
        class FakeDf:
            def __init__(self, data):
                self.data = data
                self.empty = False

            def __len__(self):
                return len(self.data)

        orig_allowed_current = self.module.allowed_connection_current
        orig_jobs = self.module.number_of_jobs_running

        async def fake_sleep(_t):
            self.module.allowed_connection_current = 1

        try:
            self.module.allowed_connection_current = 0
            self.module.number_of_jobs_running = 1

            with (
                mock.patch.object(self.module, "async_get_response", return_value={"data": [{"id": 1}]}, create=True),
                mock.patch.object(self.module.pd, "DataFrame", side_effect=lambda data: FakeDf(data)),
                mock.patch.object(self.module.asyncio, "sleep", side_effect=fake_sleep),
            ):
                data, attempt, _, is_empty, _ = self.module.asyncio.run(
                    self.module.data_handling(
                        session=object(),
                        url="http://x",
                        attempt=0,
                        empty_data_attempts=3,
                        is_data_empty=0,
                        sleep_time=1,
                        max_connections=100,
                    )
                )

            self.assertIsNotNone(data)
            self.assertEqual(attempt, 0)
            self.assertEqual(is_empty, 0)
        finally:
            self.module.allowed_connection_current = orig_allowed_current
            self.module.number_of_jobs_running = orig_jobs


class MetadataSequenceProcessingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_metadata_download_module()

    class FakeMask:
        def __init__(self, values):
            self.values = values

        def __invert__(self):
            return MetadataSequenceProcessingTests.FakeMask([not x for x in self.values])

    class FakeSeries:
        def __init__(self, values):
            self.values = values

        def isin(self, seen):
            return MetadataSequenceProcessingTests.FakeMask([v in seen for v in self.values])

        def tolist(self):
            return list(self.values)

        def apply(self, func):
            return [func(v) for v in self.values]

    class FakeDf:
        def __init__(self, rows):
            self.rows = list(rows)
            self._sync_columns()

        def _sync_columns(self):
            cols = set()
            for r in self.rows:
                cols.update(r.keys())
            self.columns = list(cols)

        @property
        def empty(self):
            return len(self.rows) == 0

        def __len__(self):
            return len(self.rows)

        def apply(self, func, axis=1):
            return MetadataSequenceProcessingTests.FakeMask([bool(func(r)) for r in self.rows])

        def __getitem__(self, key):
            if isinstance(key, MetadataSequenceProcessingTests.FakeMask):
                return MetadataSequenceProcessingTests.FakeDf([r for r, keep in zip(self.rows, key.values) if keep])
            if isinstance(key, str):
                return MetadataSequenceProcessingTests.FakeSeries([r.get(key) for r in self.rows])
            if isinstance(key, list):
                return MetadataSequenceProcessingTests.FakeDf([{k: r.get(k) for k in key} for r in self.rows])
            raise TypeError("unsupported key")

        def __setitem__(self, key, value):
            if isinstance(value, list):
                for row, v in zip(self.rows, value):
                    row[key] = v
            else:
                for row in self.rows:
                    row[key] = value
            self._sync_columns()

        def drop(self, cols, inplace=True, axis=1):
            for row in self.rows:
                for c in cols:
                    row.pop(c, None)
            self._sync_columns()
            if not inplace:
                return self

        def rename(self, mapper, axis=1, inplace=True):
            for row in self.rows:
                for old, new in mapper.items():
                    if old in row:
                        row[new] = row.pop(old)
            self._sync_columns()
            if not inplace:
                return self

    def test_fetch_sequence_paginated_images_stops_after_tracker_retries(self):
        batch = self.FakeDf([
            {
                "id": "img1",
                "thumb_original_url": "u1",
                "computed_geometry": {"coordinates": [1.0, 2.0]},
                "captured_at": 10,
            }
        ])

        responses = [batch, batch, batch]

        async def fake_data_handling(*_args, **_kwargs):
            if responses:
                return responses.pop(0), 0, 3, 0, 0.0, {"next": "http://next"}
            return None, 1, 3, 0, 0.0, {}

        with (
            mock.patch.object(self.module, "data_handling", side_effect=fake_data_handling),
            mock.patch.object(self.module.pd, "concat", side_effect=lambda frames, **kwargs: self.FakeDf([r for f in frames for r in f.rows])),
        ):
            data, missing = self.module.asyncio.run(
                self.module.fetch_sequence_paginated_images(
                    sequence="seq1",
                    url="http://x",
                    session=object(),
                    call_limit=5,
                    empty_data_attempts=3,
                    retries=2,
                    sleep_time=0,
                    max_connections=100,
                )
            )

        self.assertFalse(data.empty)
        self.assertIsNone(missing)
        self.assertEqual(len(data), 1)

    def test_process_one_sequence_transforms_and_fills_columns(self):
        raw = self.FakeDf([
            {
                "id": "i1",
                "thumb_original_url": "http://img",
                "computed_geometry": {"coordinates": [8.5, 49.4]},
                "captured_at": 123,
                "height": 100,
                "width": 200,
            }
        ])

        async def fake_fetch(*_args, **_kwargs):
            return raw, None

        def fake_dataframe(data):
            if isinstance(data, MetadataSequenceProcessingTests.FakeDf):
                return MetadataSequenceProcessingTests.FakeDf(data.rows)
            return MetadataSequenceProcessingTests.FakeDf(data)

        with (
            mock.patch.object(self.module, "fetch_sequence_paginated_images", side_effect=fake_fetch),
            mock.patch.object(self.module.pd, "DataFrame", side_effect=fake_dataframe),
            mock.patch.object(self.module, "Point", side_effect=lambda coords: tuple(coords)),
            mock.patch.object(self.module.np, "nan", None, create=True),
        ):
            df, missing = self.module.asyncio.run(
                self.module.process_one_sequence(
                    session=object(),
                    sequence="seq-x",
                    mly_key="k",
                    columns=[
                        "sequence", "id", "url", "long", "lat", "geometry",
                        "height", "width", "altitude", "make", "model",
                        "creator", "is_pano", "timestamp",
                    ],
                    args_dict={"call_limit": 1},
                )
            )

        self.assertIsNone(missing)
        self.assertEqual(len(df), 1)
        self.assertEqual(df.rows[0]["sequence"], "seq-x")
        self.assertEqual(df.rows[0]["url"], "http://img")
        self.assertEqual(df.rows[0]["timestamp"], 123)
        self.assertEqual(df.rows[0]["geometry"], (8.5, 49.4))
        self.assertEqual(df.rows[0]["is_pano"], False)

    def test_process_one_sequence_with_partial_columns_still_returns_canonical_schema(self):
        raw = self.FakeDf([
            {
                "id": "i1",
                "thumb_original_url": "http://img",
                "computed_geometry": {"coordinates": [8.5, 49.4]},
                "captured_at": 123,
            }
        ])

        async def fake_fetch(*_args, **_kwargs):
            return raw, None

        def fake_dataframe(data):
            if isinstance(data, MetadataSequenceProcessingTests.FakeDf):
                return MetadataSequenceProcessingTests.FakeDf(data.rows)
            return MetadataSequenceProcessingTests.FakeDf(data)

        with (
            mock.patch.object(self.module, "fetch_sequence_paginated_images", side_effect=fake_fetch),
            mock.patch.object(self.module.pd, "DataFrame", side_effect=fake_dataframe),
            mock.patch.object(self.module, "Point", side_effect=lambda coords: tuple(coords)),
            mock.patch.object(self.module.np, "nan", None, create=True),
        ):
            df, missing = self.module.asyncio.run(
                self.module.process_one_sequence(
                    session=object(),
                    sequence="seq-x",
                    mly_key="k",
                    columns=["id"],
                    args_dict={"call_limit": 1},
                )
            )

        self.assertIsNone(missing)
        self.assertEqual(len(df), 1)
        self.assertEqual(
            sorted(df.columns),
            sorted([
                "sequence", "id", "url", "long", "lat", "geometry",
                "height", "width", "altitude", "make", "model",
                "creator", "is_pano", "timestamp",
            ]),
        )

    def test_fetch_sequence_paginated_images_returns_missing_when_call_limit_zero(self):
        data, missing = self.module.asyncio.run(
            self.module.fetch_sequence_paginated_images(
                sequence="seq0",
                url="http://x",
                session=object(),
                call_limit=0,
                empty_data_attempts=3,
                retries=2,
                sleep_time=0,
                max_connections=100,
            )
        )

        self.assertIsNotNone(data)
        self.assertEqual(missing, "seq0")

    def test_process_one_sequence_keeps_geometry_column_when_missing_in_input(self):
        raw = self.FakeDf([
            {
                "id": "i1",
                "thumb_original_url": "http://img",
                "captured_at": 123,
            }
        ])

        async def fake_fetch(*_args, **_kwargs):
            return raw, None

        def fake_dataframe(data):
            if isinstance(data, MetadataSequenceProcessingTests.FakeDf):
                return MetadataSequenceProcessingTests.FakeDf(data.rows)
            return MetadataSequenceProcessingTests.FakeDf(data)

        with (
            mock.patch.object(self.module, "fetch_sequence_paginated_images", side_effect=fake_fetch),
            mock.patch.object(self.module.pd, "DataFrame", side_effect=fake_dataframe),
            mock.patch.object(self.module, "Point", side_effect=lambda coords: tuple(coords)),
            mock.patch.object(self.module.np, "nan", None, create=True),
        ):
            df, missing = self.module.asyncio.run(
                self.module.process_one_sequence(
                    session=object(),
                    sequence="seq-x",
                    mly_key="k",
                    columns=["id"],
                    args_dict={"call_limit": 1},
                )
            )

        self.assertIsNone(missing)
        self.assertEqual(len(df), 1)
        self.assertIn("geometry", df.columns)

    def test_fetch_sequence_paginated_images_handles_initial_none_then_valid_batch(self):
        rows = [
            {
                "id": "img1",
                "thumb_original_url": "u1",
                "computed_geometry": {"coordinates": [1.0, 2.0]},
                "captured_at": 10,
            }
        ]
        valid_batch = self.FakeDf(rows)
        calls = {"n": 0}

        async def fake_data_handling(*_args, **_kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                return None, 0, 3, 0, 0.0, {}
            return valid_batch, 1, 3, 0, 0.0, {}

        with (
            mock.patch.object(self.module, "data_handling", side_effect=fake_data_handling),
            mock.patch.object(self.module.pd, "concat", side_effect=lambda frames, **kwargs: self.FakeDf([r for f in frames for r in f.rows])),
        ):
            data, missing = self.module.asyncio.run(
                self.module.fetch_sequence_paginated_images(
                    sequence="seq1",
                    url="http://x",
                    session=object(),
                    call_limit=2,
                    empty_data_attempts=3,
                    retries=2,
                    sleep_time=0,
                    max_connections=100,
                )
            )

        self.assertIsNone(missing)
        self.assertFalse(data.empty)

    def test_fetch_sequence_paginated_images_hits_tracker_retry_stop_after_first_full_batch(self):
        row = {
            "id": "img1",
            "thumb_original_url": "u1",
            "computed_geometry": {"coordinates": [1.0, 2.0]},
            "captured_at": 10,
        }
        full_batch = self.FakeDf([row] * self.module.API_MAX_RESULTS_PER_BBOX)
        calls = {"n": 0}

        async def fake_data_handling(*_args, **_kwargs):
            calls["n"] += 1
            return full_batch, 0, 3, 0, 0.0, {"next": "http://next"}

        with (
            mock.patch.object(self.module, "data_handling", side_effect=fake_data_handling),
            mock.patch.object(self.module.pd, "concat", side_effect=lambda frames, **kwargs: self.FakeDf([r for f in frames for r in f.rows])),
        ):
            data, missing = self.module.asyncio.run(
                self.module.fetch_sequence_paginated_images(
                    sequence="seq_retry",
                    url="http://x",
                    session=object(),
                    call_limit=2,
                    empty_data_attempts=3,
                    retries=1,
                    sleep_time=0,
                    max_connections=100,
                )
            )

        self.assertIsNone(missing)
        self.assertFalse(data.empty)

    def test_process_one_sequence_returns_empty_columns_when_fetch_returns_empty(self):
        class EmptyDf:
            empty = True

        async def fake_fetch(*_args, **_kwargs):
            return EmptyDf(), "seq-empty"

        with mock.patch.object(self.module, "fetch_sequence_paginated_images", side_effect=fake_fetch):
            df, missing = self.module.asyncio.run(
                self.module.process_one_sequence(
                    session=object(),
                    sequence="seq-empty",
                    mly_key="k",
                    columns=["id", "sequence"],
                    args_dict={"call_limit": 1},
                )
            )

        self.assertEqual(missing, "seq-empty")
        self.assertIsNotNone(df)

    def test_fetch_sequence_paginated_images_follows_paging_next_url(self):
        page_1 = self.FakeDf([
            {
                "id": "img1",
                "thumb_original_url": "u1",
                "computed_geometry": {"coordinates": [1.0, 2.0]},
                "captured_at": 10,
            }
        ])
        page_2 = self.FakeDf([
            {
                "id": "img2",
                "thumb_original_url": "u2",
                "computed_geometry": {"coordinates": [3.0, 4.0]},
                "captured_at": 11,
            }
        ])

        requested_urls = []

        async def fake_data_handling(_session, current_url, *_args, **_kwargs):
            requested_urls.append(current_url)
            if current_url == "http://page-1":
                return page_1, 0, 3, 0, 0.0, {"next": "http://page-2"}
            return page_2, 0, 3, 0, 0.0, {}

        with (
            mock.patch.object(self.module, "data_handling", side_effect=fake_data_handling),
            mock.patch.object(self.module.pd, "concat", side_effect=lambda frames, **kwargs: self.FakeDf([r for f in frames for r in f.rows])),
        ):
            data, missing = self.module.asyncio.run(
                self.module.fetch_sequence_paginated_images(
                    sequence="seq_pages",
                    url="http://page-1",
                    session=object(),
                    call_limit=3,
                    empty_data_attempts=3,
                    retries=2,
                    sleep_time=0,
                    max_connections=100,
                )
            )

        self.assertIsNone(missing)
        self.assertFalse(data.empty)
        self.assertEqual(len(data), 2)
        self.assertEqual(requested_urls, ["http://page-1", "http://page-2"])


# ---------------------------------------------------------------------------
# metadata_download / wrappers / orchestration
# ---------------------------------------------------------------------------

class MetadataDownloadAsyncTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_metadata_download_module()

    def test_metadata_download_collects_non_empty_and_missing_sequences(self):
        class FakeDf:
            def __init__(self, empty):
                self.empty = empty

        class FakeSession:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

        async def fake_process_one_sequence(session, seq, mly_key, columns, args_dict):
            if seq == "s1":
                return FakeDf(False), None
            return FakeDf(True), "missing_s2"

        self.module.metadata_list = []
        self.module.missing_sequences_list = []

        with (
            mock.patch.object(self.module, "process_generator", return_value=[["s1", "s2", None]]),
            mock.patch.object(self.module.aiohttp, "ClientSession", return_value=FakeSession()),
            mock.patch.object(self.module, "process_one_sequence", side_effect=fake_process_one_sequence),
            mock.patch.object(self.module, "tqdm", side_effect=lambda it, **kwargs: it),
        ):
            self.module.asyncio.run(
                self.module.metadata_download("key", ["s1", "s2"], ["id"], {"x": 1}, batch_size=2)
            )

        self.assertEqual(len(self.module.metadata_list), 1)
        self.assertIn("missing_s2", self.module.missing_sequences_list)

    def test_metadata_download_wrapping_calls_asyncio_run(self):
        captured = {}

        def fake_run(coro):
            captured["coro"] = coro
            coro.close()

        with mock.patch.object(self.module.asyncio, "run", side_effect=fake_run) as run_mock:
            self.module.metadata_download_wrapping("key", ["s1"], ["id"], {}, batch_size=1, windows=False)

        run_mock.assert_called_once()
        self.assertIn("coro", captured)

    def test_metadata_download_continues_when_one_sequence_raises(self):
        class FakeDf:
            def __init__(self, empty):
                self.empty = empty

        class FakeSession:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

        async def fake_process_one_sequence(session, seq, mly_key, columns, args_dict):
            if seq == "s1":
                return FakeDf(False), None
            if seq == "s2":
                raise RuntimeError("boom")
            return FakeDf(True), "missing_s3"

        self.module.metadata_list = []
        self.module.missing_sequences_list = []

        with (
            mock.patch.object(self.module, "process_generator", return_value=[["s1", "s2", "s3"]]),
            mock.patch.object(self.module.aiohttp, "ClientSession", return_value=FakeSession()),
            mock.patch.object(self.module, "process_one_sequence", side_effect=fake_process_one_sequence),
            mock.patch.object(self.module, "tqdm", side_effect=lambda it, **kwargs: it),
        ):
            self.module.asyncio.run(
                self.module.metadata_download("key", ["s1", "s2", "s3"], ["id"], {"x": 1}, batch_size=3)
            )

        self.assertEqual(len(self.module.metadata_list), 1)
        self.assertIn("missing_s3", self.module.missing_sequences_list)

    def test_metadata_download_ignores_none_result_entries(self):
        class FakeSession:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

        async def fake_process_one_sequence(session, seq, mly_key, columns, args_dict):
            return None

        self.module.metadata_list = []
        self.module.missing_sequences_list = []

        with (
            mock.patch.object(self.module, "process_generator", return_value=[["s1"]]),
            mock.patch.object(self.module.aiohttp, "ClientSession", return_value=FakeSession()),
            mock.patch.object(self.module, "process_one_sequence", side_effect=fake_process_one_sequence),
            mock.patch.object(self.module, "tqdm", side_effect=lambda it, **kwargs: it),
        ):
            self.module.asyncio.run(
                self.module.metadata_download("key", ["s1"], ["id"], {"x": 1}, batch_size=1)
            )

        self.assertEqual(self.module.metadata_list, [])
        self.assertEqual(self.module.missing_sequences_list, [])

    def test_metadata_download_wrapping_sets_windows_policy(self):
        captured = {}

        def fake_run(coro):
            captured["coro"] = coro
            coro.close()

        with (
            mock.patch.object(self.module.asyncio, "WindowsSelectorEventLoopPolicy", return_value="policy", create=True),
            mock.patch.object(self.module.asyncio, "set_event_loop_policy") as set_policy_mock,
            mock.patch.object(self.module.asyncio, "run", side_effect=fake_run),
        ):
            self.module.metadata_download_wrapping("key", ["s1"], ["id"], {}, batch_size=1, windows=True)

        set_policy_mock.assert_called_once_with("policy")
        self.assertIn("coro", captured)


class MetadataDownloadOrchestrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_metadata_download_module()

    def _fake_thread_class(self, on_init=None, on_join=None, alive=False):
        class FakeThread:
            def __init__(self, target=None, args=(), daemon=None):
                self.target = target
                self.args = args
                if on_init is not None:
                    on_init(target, args, daemon)

            def start(self):
                return None

            def join(self, timeout=None):
                if on_join is not None:
                    on_join(timeout)

            def is_alive(self):
                return alive

        return FakeThread

    def _fake_executor_class(self, on_map=None):
        class FakeExecutor:
            def __init__(self, max_workers):
                self.max_workers = max_workers

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def map(self, fn, *iterables):
                if on_map is not None:
                    return on_map(fn, *iterables)
                for args in zip(*iterables):
                    fn(*args)
                return []

        return FakeExecutor

    def test_get_metadata_orchestrates_workers_and_flushes(self):
        calls = {"thread_targets": [], "worker_calls": [], "flush_calls": []}

        FakeThread = self._fake_thread_class(
            on_init=lambda target, args, daemon: calls["thread_targets"].append(getattr(target, "__name__", str(target)))
        )

        def on_map(fn, *iterables):
            for args in zip(*iterables):
                calls["worker_calls"].append(args)
                fn(*args)
            return []

        FakeExecutor = self._fake_executor_class(on_map=on_map)

        def fake_flush_metadata(_path):
            calls["flush_calls"].append("metadata")

        def fake_flush_missing(_path):
            calls["flush_calls"].append("missing")

        with (
            mock.patch.object(self.module.os, "makedirs"),
            mock.patch.object(self.module, "monitor_jobs"),
            mock.patch.object(self.module, "monitor_connections"),
            mock.patch.object(self.module, "flush_metadata_buffer", side_effect=fake_flush_metadata),
            mock.patch.object(self.module, "flush_missing_sequences_buffer", side_effect=fake_flush_missing),
            mock.patch.object(self.module.threading, "Thread", side_effect=FakeThread),
            mock.patch.object(self.module.np, "array_split", return_value=[["s1"], ["s2"]], create=True),
            mock.patch.object(self.module, "metadata_download_wrapping"),
            mock.patch.object(self.module, "ThreadPoolExecutor", side_effect=FakeExecutor),
        ):
            self.module.get_metadata(
                sequence_list=["s1", "s2"],
                missing_sequences_file="/tmp/missing.csv",
                metadata_file="/tmp/metadata.csv",
                mly_key="key",
                columns=["id"],
                params={"max_connections": 100},
                job_patterns=[{"pattern": "*.csv", "threshold": 10}],
                max_workers=2,
                batch_size=5,
                windows=False,
                monitoring={
                    "monitor_interval": 1,
                    "monitor_check_timeout": 1,
                    "write_interval": 1,
                    "write_check_timeout": 1,
                },
            )

        self.assertEqual(len(calls["worker_calls"]), 2)
        self.assertEqual(len(calls["flush_calls"]), 2)

    def test_get_metadata_accepts_basename_metadata_file_path(self):
        calls = {"makedirs": []}

        FakeThread = self._fake_thread_class()
        FakeExecutor = self._fake_executor_class()

        def fake_makedirs(path, exist_ok=False):
            calls["makedirs"].append(path)
            if path == "":
                raise ValueError("empty path")

        with (
            mock.patch.object(self.module.os, "makedirs", side_effect=fake_makedirs),
            mock.patch.object(self.module, "monitor_jobs"),
            mock.patch.object(self.module, "monitor_connections"),
            mock.patch.object(self.module.threading, "Thread", side_effect=FakeThread),
            mock.patch.object(self.module.np, "array_split", return_value=[["s1"]], create=True),
            mock.patch.object(self.module, "metadata_download_wrapping"),
            mock.patch.object(self.module, "ThreadPoolExecutor", side_effect=FakeExecutor),
            mock.patch.object(self.module, "flush_metadata_buffer"),
            mock.patch.object(self.module, "flush_missing_sequences_buffer"),
        ):
            self.module.get_metadata(
                sequence_list=["s1"],
                missing_sequences_file="missing.csv",
                metadata_file="metadata.csv",
                mly_key="key",
                columns=["id"],
                params={"max_connections": 100},
                job_patterns=[{"pattern": "*.csv", "threshold": 10}],
                max_workers=1,
                batch_size=1,
                windows=False,
                monitoring={
                    "monitor_interval": 1,
                    "monitor_check_timeout": 1,
                    "write_interval": 1,
                    "write_check_timeout": 1,
                },
            )

        self.assertIn(".", calls["makedirs"])

    def test_get_metadata_creates_parent_dirs_for_both_output_files(self):
        calls = {"makedirs": []}

        FakeThread = self._fake_thread_class()
        FakeExecutor = self._fake_executor_class()

        def fake_makedirs(path, exist_ok=False):
            calls["makedirs"].append(path)

        with (
            mock.patch.object(self.module.os, "makedirs", side_effect=fake_makedirs),
            mock.patch.object(self.module, "monitor_jobs"),
            mock.patch.object(self.module, "monitor_connections"),
            mock.patch.object(self.module.threading, "Thread", side_effect=FakeThread),
            mock.patch.object(self.module.np, "array_split", return_value=[["s1"]], create=True),
            mock.patch.object(self.module, "metadata_download_wrapping"),
            mock.patch.object(self.module, "ThreadPoolExecutor", side_effect=FakeExecutor),
            mock.patch.object(self.module, "flush_metadata_buffer"),
            mock.patch.object(self.module, "flush_missing_sequences_buffer"),
        ):
            self.module.get_metadata(
                sequence_list=["s1"],
                missing_sequences_file="/tmp/missing_dir/missing.csv",
                metadata_file="/tmp/metadata_dir/metadata.csv",
                mly_key="key",
                columns=["id"],
                params={"max_connections": 100},
                job_patterns=[{"pattern": "*.csv", "threshold": 10}],
                max_workers=1,
                batch_size=1,
                windows=False,
                monitoring={
                    "monitor_interval": 1,
                    "monitor_check_timeout": 1,
                    "write_interval": 1,
                    "write_check_timeout": 1,
                },
            )

        self.assertIn("/tmp/metadata_dir", calls["makedirs"])
        self.assertIn("/tmp/missing_dir", calls["makedirs"])

    def test_get_metadata_stops_and_joins_threads_when_worker_raises(self):
        calls = {"joined": 0, "flush": 0}

        class FakeThread:
            def __init__(self, target=None, args=(), daemon=None):
                self.target = target
                self.args = args

            def start(self):
                pass

            def join(self, timeout=None):
                calls["joined"] += 1

            def is_alive(self):
                return False

        class FakeExecutor:
            def __init__(self, max_workers):
                self.max_workers = max_workers

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def map(self, fn, *iterables):
                for args in zip(*iterables):
                    fn(*args)
                return []

        def raise_worker(*args, **kwargs):
            raise ValueError("boom")

        with (
            mock.patch.object(self.module.os, "makedirs"),
            mock.patch.object(self.module, "monitor_jobs"),
            mock.patch.object(self.module, "monitor_connections"),
            mock.patch.object(self.module.threading, "Thread", side_effect=FakeThread),
            mock.patch.object(self.module.np, "array_split", return_value=[["s1"], ["s2"]], create=True),
            mock.patch.object(self.module, "metadata_download_wrapping", side_effect=raise_worker),
            mock.patch.object(self.module, "ThreadPoolExecutor", side_effect=FakeExecutor),
            mock.patch.object(self.module, "flush_metadata_buffer", side_effect=lambda _p: calls.__setitem__("flush", calls["flush"] + 1)),
            mock.patch.object(self.module, "flush_missing_sequences_buffer", side_effect=lambda _p: calls.__setitem__("flush", calls["flush"] + 1)),
        ):
            with self.assertRaises(ValueError):
                self.module.get_metadata(
                    sequence_list=["s1", "s2"],
                    missing_sequences_file="/tmp/missing.csv",
                    metadata_file="/tmp/metadata.csv",
                    mly_key="key",
                    columns=["id"],
                    params={"max_connections": 100},
                    job_patterns=[{"pattern": "*.csv", "threshold": 10}],
                    max_workers=2,
                    batch_size=5,
                    windows=False,
                    monitoring={
                        "monitor_interval": 1,
                        "monitor_check_timeout": 1,
                        "write_interval": 1,
                        "write_check_timeout": 1,
                    },
                )

        self.assertTrue(self.module.thread_stop)
        self.assertFalse(self.module.write_true)
        self.assertEqual(calls["flush"], 2)
        self.assertEqual(calls["joined"], 4)

    def test_get_metadata_normalizes_zero_max_workers_to_one(self):
        calls = {"executor_workers": None, "array_split_workers": None}

        FakeThread = self._fake_thread_class()

        class FakeExecutor(self._fake_executor_class()):
            def __init__(self, max_workers):
                calls["executor_workers"] = max_workers
                super().__init__(max_workers)

        def fake_array_split(values, workers):
            calls["array_split_workers"] = workers
            return [values]

        with (
            mock.patch.object(self.module.os, "makedirs"),
            mock.patch.object(self.module, "monitor_jobs"),
            mock.patch.object(self.module, "monitor_connections"),
            mock.patch.object(self.module.threading, "Thread", side_effect=FakeThread),
            mock.patch.object(self.module.np, "array_split", side_effect=fake_array_split, create=True),
            mock.patch.object(self.module, "metadata_download_wrapping"),
            mock.patch.object(self.module, "ThreadPoolExecutor", side_effect=FakeExecutor),
            mock.patch.object(self.module, "flush_metadata_buffer"),
            mock.patch.object(self.module, "flush_missing_sequences_buffer"),
        ):
            self.module.get_metadata(
                sequence_list=["s1"],
                missing_sequences_file="/tmp/missing.csv",
                metadata_file="/tmp/metadata.csv",
                mly_key="key",
                columns=["id"],
                params={"max_connections": 100},
                job_patterns=[{"pattern": "*.csv", "threshold": 10}],
                max_workers=0,
                batch_size=1,
                windows=False,
                monitoring={
                    "monitor_interval": 1,
                    "monitor_check_timeout": 1,
                    "write_interval": 1,
                    "write_check_timeout": 1,
                },
            )

        self.assertEqual(calls["executor_workers"], 1)
        self.assertEqual(calls["array_split_workers"], 1)

    def test_get_metadata_uses_default_max_connections_when_param_missing(self):
        calls = {"monitor_max_connections": []}

        FakeThread = self._fake_thread_class()
        FakeExecutor = self._fake_executor_class()

        def fake_monitor_jobs(patterns, interval=10, start=False, check_timeout=10, max_connections=10000):
            calls["monitor_max_connections"].append(max_connections)

        with (
            mock.patch.object(self.module.os, "makedirs"),
            mock.patch.object(self.module, "monitor_jobs", side_effect=fake_monitor_jobs),
            mock.patch.object(self.module, "monitor_connections"),
            mock.patch.object(self.module.threading, "Thread", side_effect=FakeThread),
            mock.patch.object(self.module.np, "array_split", return_value=[["s1"]], create=True),
            mock.patch.object(self.module, "metadata_download_wrapping"),
            mock.patch.object(self.module, "ThreadPoolExecutor", side_effect=FakeExecutor),
            mock.patch.object(self.module, "flush_metadata_buffer"),
            mock.patch.object(self.module, "flush_missing_sequences_buffer"),
        ):
            self.module.get_metadata(
                sequence_list=["s1"],
                missing_sequences_file="/tmp/missing.csv",
                metadata_file="/tmp/metadata.csv",
                mly_key="key",
                columns=["id"],
                params={},
                job_patterns=[{"pattern": "*.csv", "threshold": 10}],
                max_workers=1,
                batch_size=1,
                windows=False,
                monitoring={
                    "monitor_interval": 1,
                    "monitor_check_timeout": 1,
                    "write_interval": 1,
                    "write_check_timeout": 1,
                },
            )

        self.assertTrue(calls["monitor_max_connections"])
        self.assertTrue(all(v == 10000 for v in calls["monitor_max_connections"]))

    def test_get_metadata_falls_back_on_invalid_worker_and_connection_values(self):
        calls = {"executor_workers": None, "monitor_max_connections": []}

        FakeThread = self._fake_thread_class()

        class FakeExecutor(self._fake_executor_class()):
            def __init__(self, max_workers):
                calls["executor_workers"] = max_workers
                super().__init__(max_workers)

        def fake_monitor_jobs(patterns, interval=10, start=False, check_timeout=10, max_connections=10000):
            calls["monitor_max_connections"].append(max_connections)

        with (
            mock.patch.object(self.module.os, "makedirs"),
            mock.patch.object(self.module, "monitor_jobs", side_effect=fake_monitor_jobs),
            mock.patch.object(self.module, "monitor_connections"),
            mock.patch.object(self.module.threading, "Thread", side_effect=FakeThread),
            mock.patch.object(self.module.np, "array_split", return_value=[["s1"]], create=True),
            mock.patch.object(self.module, "metadata_download_wrapping"),
            mock.patch.object(self.module, "ThreadPoolExecutor", side_effect=FakeExecutor),
            mock.patch.object(self.module, "flush_metadata_buffer"),
            mock.patch.object(self.module, "flush_missing_sequences_buffer"),
        ):
            self.module.get_metadata(
                sequence_list=["s1"],
                missing_sequences_file="/tmp/missing.csv",
                metadata_file="/tmp/metadata.csv",
                mly_key="key",
                columns=["id"],
                params={"max_connections": "bad"},
                job_patterns=[{"pattern": "*.csv", "threshold": 10}],
                max_workers="bad",
                batch_size=1,
                windows=False,
                monitoring={
                    "monitor_interval": 1,
                    "monitor_check_timeout": 1,
                    "write_interval": 1,
                    "write_check_timeout": 1,
                },
            )

        self.assertEqual(calls["executor_workers"], 4)
        self.assertTrue(calls["monitor_max_connections"])
        self.assertTrue(all(v == 10000 for v in calls["monitor_max_connections"]))

    def test_get_metadata_uses_defaults_when_params_is_none(self):
        calls = {"monitor_max_connections": []}

        FakeThread = self._fake_thread_class()
        FakeExecutor = self._fake_executor_class()

        def fake_monitor_jobs(patterns, interval=10, start=False, check_timeout=10, max_connections=10000):
            calls["monitor_max_connections"].append(max_connections)

        with (
            mock.patch.object(self.module.os, "makedirs"),
            mock.patch.object(self.module, "monitor_jobs", side_effect=fake_monitor_jobs),
            mock.patch.object(self.module, "monitor_connections"),
            mock.patch.object(self.module.threading, "Thread", side_effect=FakeThread),
            mock.patch.object(self.module.np, "array_split", return_value=[["s1"]], create=True),
            mock.patch.object(self.module, "metadata_download_wrapping"),
            mock.patch.object(self.module, "ThreadPoolExecutor", side_effect=FakeExecutor),
            mock.patch.object(self.module, "flush_metadata_buffer"),
            mock.patch.object(self.module, "flush_missing_sequences_buffer"),
        ):
            self.module.get_metadata(
                sequence_list=["s1"],
                missing_sequences_file="/tmp/missing.csv",
                metadata_file="/tmp/metadata.csv",
                mly_key="key",
                columns=["id"],
                params=None,
                job_patterns=[{"pattern": "*.csv", "threshold": 10}],
                max_workers=1,
                batch_size=1,
                windows=False,
                monitoring={
                    "monitor_interval": 1,
                    "monitor_check_timeout": 1,
                    "write_interval": 1,
                    "write_check_timeout": 1,
                },
            )

        self.assertTrue(calls["monitor_max_connections"])
        self.assertTrue(all(v == 10000 for v in calls["monitor_max_connections"]))

    def test_get_metadata_uses_default_monitoring_when_none(self):
        calls = {"monitor_interval": [], "monitor_timeout": []}

        FakeThread = self._fake_thread_class()
        FakeExecutor = self._fake_executor_class()

        def fake_monitor_jobs(patterns, interval=10, start=False, check_timeout=10, max_connections=10000):
            calls["monitor_interval"].append(interval)
            calls["monitor_timeout"].append(check_timeout)

        with (
            mock.patch.object(self.module.os, "makedirs"),
            mock.patch.object(self.module, "monitor_jobs", side_effect=fake_monitor_jobs),
            mock.patch.object(self.module, "monitor_connections"),
            mock.patch.object(self.module.threading, "Thread", side_effect=FakeThread),
            mock.patch.object(self.module.np, "array_split", return_value=[["s1"]], create=True),
            mock.patch.object(self.module, "metadata_download_wrapping"),
            mock.patch.object(self.module, "ThreadPoolExecutor", side_effect=FakeExecutor),
            mock.patch.object(self.module, "flush_metadata_buffer"),
            mock.patch.object(self.module, "flush_missing_sequences_buffer"),
        ):
            self.module.get_metadata(
                sequence_list=["s1"],
                missing_sequences_file="/tmp/missing.csv",
                metadata_file="/tmp/metadata.csv",
                mly_key="key",
                columns=["id"],
                params=None,
                job_patterns=[{"pattern": "*.csv", "threshold": 10}],
                max_workers=1,
                batch_size=1,
                windows=False,
                monitoring=None,
            )

        self.assertIn(10, calls["monitor_interval"])
        self.assertIn(10, calls["monitor_timeout"])

    def test_get_sequences_orchestrates_discovery_and_persists_outputs(self):
        calls = {"removed": [], "thread_targets": []}

        class FakeThread:
            def __init__(self, target=None, args=(), daemon=None):
                self.target = target
                self.args = args
                calls["thread_targets"].append(getattr(target, "__name__", str(target)))

            def start(self):
                pass

            def join(self, timeout=None):
                pass

        class FakeExecutor:
            def __init__(self, max_workers):
                self.max_workers = max_workers

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def map(self, fn, *iterables):
                for args in zip(*iterables):
                    fn(*args)
                return []

        class FakeGeoDf:
            def __len__(self):
                return 1

            def to_file(self, *args, **kwargs):
                pass

        def fake_get_bboxes(*args, **kwargs):
            self.module.global_bboxes.add((1.0, 2.0, 3.0, 4.0))
            self.module.global_sequences.add("seq_1")

        class FakeDf:
            def __init__(self, data):
                self.data = data

            def to_csv(self, *args, **kwargs):
                pass

        with (
            mock.patch.object(self.module.os, "makedirs"),
            mock.patch.object(self.module.os.path, "exists", return_value=True),
            mock.patch.object(self.module.os, "remove", side_effect=lambda p: calls["removed"].append(p)),
            mock.patch.object(self.module, "write_sequences"),
            mock.patch.object(self.module, "write_bbox"),
            mock.patch.object(self.module, "monitor_jobs"),
            mock.patch.object(self.module, "monitor_connections"),
            mock.patch.object(self.module.threading, "Thread", side_effect=FakeThread),
            mock.patch.object(self.module, "segmented_bboxes", return_value=[[0, 0, 1, 1], [1, 1, 2, 2]]),
            mock.patch.object(self.module, "get_bboxes_and_sequences_wrapping", side_effect=fake_get_bboxes),
            mock.patch.object(self.module, "ThreadPoolExecutor", side_effect=FakeExecutor),
            mock.patch.object(self.module.pd, "DataFrame", side_effect=FakeDf),
            mock.patch.object(self.module, "create_geodataframe_from_bboxes", return_value=FakeGeoDf()),
        ):
            bboxes, sequences = self.module.get_sequences(
                bbox=[0, 0, 2, 2],
                mly_key="key",
                n=2,
                output_dir="/tmp/out",
                number_of_initial_bboxes=2,
                params={"max_connections": 100},
                job_patterns=[{"pattern": "*.csv", "threshold": 10}],
                job_id=5,
                max_workers=2,
                windows=False,
                monitoring={
                    "monitor_interval": 1,
                    "monitor_check_timeout": 1,
                    "write_interval": 1,
                    "write_check_timeout": 1,
                },
            )

        self.assertGreaterEqual(len(calls["removed"]), 2)
        self.assertIn("seq_1", sequences)
        self.assertIn((1.0, 2.0, 3.0, 4.0), bboxes)

    def test_get_sequences_stops_and_joins_threads_when_worker_raises(self):
        calls = {"joined": 0}

        class FakeThread:
            def __init__(self, target=None, args=(), daemon=None):
                self.target = target
                self.args = args

            def start(self):
                pass

            def join(self, timeout=None):
                calls["joined"] += 1

            def is_alive(self):
                return False

        class FakeExecutor:
            def __init__(self, max_workers):
                self.max_workers = max_workers

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def map(self, fn, *iterables):
                for args in zip(*iterables):
                    fn(*args)
                return []

        def raise_worker(*args, **kwargs):
            raise ValueError("boom")

        with (
            mock.patch.object(self.module.os, "makedirs"),
            mock.patch.object(self.module.os.path, "exists", return_value=False),
            mock.patch.object(self.module, "write_sequences"),
            mock.patch.object(self.module, "write_bbox"),
            mock.patch.object(self.module, "monitor_jobs"),
            mock.patch.object(self.module, "monitor_connections"),
            mock.patch.object(self.module.threading, "Thread", side_effect=FakeThread),
            mock.patch.object(self.module, "segmented_bboxes", return_value=[[0, 0, 1, 1], [1, 1, 2, 2]]),
            mock.patch.object(self.module, "get_bboxes_and_sequences_wrapping", side_effect=raise_worker),
            mock.patch.object(self.module, "ThreadPoolExecutor", side_effect=FakeExecutor),
        ):
            with self.assertRaises(ValueError):
                self.module.get_sequences(
                    bbox=[0, 0, 2, 2],
                    mly_key="key",
                    n=2,
                    output_dir="/tmp/out",
                    number_of_initial_bboxes=2,
                    params={"max_connections": 100},
                    job_patterns=[{"pattern": "*.csv", "threshold": 10}],
                    job_id=5,
                    max_workers=2,
                    windows=False,
                    monitoring={
                        "monitor_interval": 1,
                        "monitor_check_timeout": 1,
                        "write_interval": 1,
                        "write_check_timeout": 1,
                    },
                )

        self.assertTrue(self.module.thread_stop)
        self.assertEqual(calls["joined"], 4)

    def test_get_sequences_uses_default_monitoring_when_none(self):
        calls = {"monitor_interval": [], "monitor_timeout": []}

        FakeThread = self._fake_thread_class()

        def on_map(fn, *iterables):
            return []

        FakeExecutor = self._fake_executor_class(on_map=on_map)

        class FakeGeoDf:
            def __len__(self):
                return 0

        def fake_monitor_jobs(patterns, interval=10, start=False, check_timeout=10, max_connections=10000):
            calls["monitor_interval"].append(interval)
            calls["monitor_timeout"].append(check_timeout)

        with (
            mock.patch.object(self.module.os, "makedirs"),
            mock.patch.object(self.module.os.path, "exists", return_value=False),
            mock.patch.object(self.module, "write_sequences"),
            mock.patch.object(self.module, "write_bbox"),
            mock.patch.object(self.module, "monitor_jobs", side_effect=fake_monitor_jobs),
            mock.patch.object(self.module, "monitor_connections"),
            mock.patch.object(self.module.threading, "Thread", side_effect=FakeThread),
            mock.patch.object(self.module, "segmented_bboxes", return_value=[[0, 0, 1, 1]]),
            mock.patch.object(self.module, "ThreadPoolExecutor", side_effect=FakeExecutor),
            mock.patch.object(self.module.pd, "DataFrame", return_value=type("DF", (), {"to_csv": lambda s, *a, **k: None})(), create=True),
            mock.patch.object(self.module, "create_geodataframe_from_bboxes", return_value=FakeGeoDf()),
        ):
            self.module.get_sequences(
                bbox=[0, 0, 2, 2],
                mly_key="key",
                n=2,
                output_dir="/tmp/out",
                number_of_initial_bboxes=2,
                params={"max_connections": 100},
                job_patterns=[{"pattern": "*.csv", "threshold": 10}],
                job_id=5,
                max_workers=1,
                windows=False,
                monitoring=None,
            )

        self.assertIn(10, calls["monitor_interval"])
        self.assertIn(10, calls["monitor_timeout"])

    def test_get_sequences_computes_nonzero_request_average_path(self):
        FakeThread = self._fake_thread_class()
        FakeExecutor = self._fake_executor_class()

        class FakeGeoDf:
            def __len__(self):
                return 0

        def fake_get_bboxes(*args, **kwargs):
            self.module.number_of_requests += 1

        with (
            mock.patch.object(self.module.os, "makedirs"),
            mock.patch.object(self.module.os.path, "exists", return_value=False),
            mock.patch.object(self.module, "write_sequences"),
            mock.patch.object(self.module, "write_bbox"),
            mock.patch.object(self.module, "monitor_jobs"),
            mock.patch.object(self.module, "monitor_connections"),
            mock.patch.object(self.module.threading, "Thread", side_effect=FakeThread),
            mock.patch.object(self.module, "segmented_bboxes", return_value=[[0, 0, 1, 1]]),
            mock.patch.object(self.module, "get_bboxes_and_sequences_wrapping", side_effect=fake_get_bboxes),
            mock.patch.object(self.module, "ThreadPoolExecutor", side_effect=FakeExecutor),
            mock.patch.object(self.module.pd, "DataFrame", return_value=type("DF", (), {"to_csv": lambda s, *a, **k: None})(), create=True),
            mock.patch.object(self.module, "create_geodataframe_from_bboxes", return_value=FakeGeoDf()),
            mock.patch.object(self.module.time, "time", side_effect=[10.0, 10.0, 12.0, 12.0, 12.0, 12.0]),
        ):
            self.module.get_sequences(
                bbox=[0, 0, 2, 2],
                mly_key="key",
                n=2,
                output_dir="/tmp/out",
                number_of_initial_bboxes=2,
                params={"max_connections": 100},
                job_patterns=[{"pattern": "*.csv", "threshold": 10}],
                job_id=5,
                max_workers=1,
                windows=False,
                monitoring={
                    "monitor_interval": 1,
                    "monitor_check_timeout": 1,
                    "write_interval": 1,
                    "write_check_timeout": 1,
                },
            )

    def test_get_metadata_computes_nonzero_request_average_path(self):
        FakeThread = self._fake_thread_class()
        FakeExecutor = self._fake_executor_class()

        def fake_worker(*args, **kwargs):
            self.module.number_of_requests += 1

        with (
            mock.patch.object(self.module.os, "makedirs"),
            mock.patch.object(self.module, "monitor_jobs"),
            mock.patch.object(self.module, "monitor_connections"),
            mock.patch.object(self.module.threading, "Thread", side_effect=FakeThread),
            mock.patch.object(self.module.np, "array_split", return_value=[["s1"]], create=True),
            mock.patch.object(self.module, "metadata_download_wrapping", side_effect=fake_worker),
            mock.patch.object(self.module, "ThreadPoolExecutor", side_effect=FakeExecutor),
            mock.patch.object(self.module, "flush_metadata_buffer"),
            mock.patch.object(self.module, "flush_missing_sequences_buffer"),
            mock.patch.object(self.module.time, "time", side_effect=[20.0, 20.0, 22.0, 22.0, 22.0, 22.0]),
        ):
            self.module.get_metadata(
                sequence_list=["s1"],
                missing_sequences_file="/tmp/missing.csv",
                metadata_file="/tmp/metadata.csv",
                mly_key="key",
                columns=["id"],
                params={"max_connections": 100},
                job_patterns=[{"pattern": "*.csv", "threshold": 10}],
                max_workers=1,
                batch_size=1,
                windows=False,
                monitoring={
                    "monitor_interval": 1,
                    "monitor_check_timeout": 1,
                    "write_interval": 1,
                    "write_check_timeout": 1,
                },
            )

    def test_main_skips_metadata_download_when_disabled(self):
        with (
            mock.patch.object(self.module.os.path, "exists", return_value=False),
            mock.patch.object(self.module, "get_sequences", return_value=([("b",)], ["s1"])),
            mock.patch.object(self.module, "get_metadata") as get_metadata_mock,
        ):
            self.module.main(
                bbox=[0, 0, 1, 1],
                mly_key="key",
                columns=["id"],
                n=2,
                output_dir="/tmp/out",
                job_id=1,
                metadata_basename="meta",
                missing_basename="missing",
                initial_subdivisions=2,
                params={"retries": 2},
                max_workers=2,
                enable_download=False,
                batch_size=10,
                windows=False,
            )

        get_metadata_mock.assert_not_called()

    def test_main_calls_metadata_download_when_enabled(self):
        with (
            mock.patch.object(self.module.os.path, "exists", return_value=False),
            mock.patch.object(self.module, "get_sequences", return_value=([("b",)], ["s1", "s2"])),
            mock.patch.object(self.module, "get_metadata") as get_metadata_mock,
        ):
            self.module.main(
                bbox=[0, 0, 1, 1],
                mly_key="key",
                columns=["id"],
                n=2,
                output_dir="/tmp/out",
                job_id=2,
                metadata_basename="meta",
                missing_basename="missing",
                initial_subdivisions=2,
                params={"retries": 2},
                max_workers=2,
                enable_download=True,
                batch_size=10,
                windows=False,
            )

        get_metadata_mock.assert_called_once()

    def test_main_skips_metadata_download_when_no_sequences_found(self):
        with (
            mock.patch.object(self.module.os.path, "exists", return_value=False),
            mock.patch.object(self.module, "get_sequences", return_value=([("b",)], [])),
            mock.patch.object(self.module, "get_metadata") as get_metadata_mock,
        ):
            self.module.main(
                bbox=[0, 0, 1, 1],
                mly_key="key",
                columns=["id"],
                n=2,
                output_dir="/tmp/out",
                job_id=3,
                metadata_basename="meta",
                missing_basename="missing",
                initial_subdivisions=2,
                params={"retries": 2},
                max_workers=2,
                enable_download=True,
                batch_size=10,
                windows=False,
            )

        get_metadata_mock.assert_not_called()

    def test_main_normalizes_invalid_worker_and_batch_values(self):
        captured = {"workers": None, "batch_size": None}

        def fake_get_sequences(*args, **kwargs):
            captured["workers"] = args[8]
            return ([('b',)], ["s1"])

        def fake_get_metadata(*args, **kwargs):
            captured["batch_size"] = args[8]

        with (
            mock.patch.object(self.module.os.path, "exists", return_value=False),
            mock.patch.object(self.module, "get_sequences", side_effect=fake_get_sequences),
            mock.patch.object(self.module, "get_metadata", side_effect=fake_get_metadata),
        ):
            self.module.main(
                bbox=[0, 0, 1, 1],
                mly_key="key",
                columns=["id"],
                n=2,
                output_dir="/tmp/out",
                job_id=4,
                metadata_basename="meta",
                missing_basename="missing",
                initial_subdivisions=2,
                params={"retries": 2},
                max_workers="bad",
                enable_download=True,
                batch_size=0,
                windows=False,
            )

        self.assertEqual(captured["workers"], 4)
        self.assertEqual(captured["batch_size"], 1)


class MetadataDownloadGeneratorEdgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_metadata_download_module()

    class _FakeSeqCol:
        def __init__(self, vals):
            self._vals = vals

        def unique(self):
            return self._vals

    class _FakeDf:
        def __init__(self, n, with_sequence=True):
            self._n = n
            self.empty = n == 0
            self.columns = ["sequence"] if with_sequence else ["id"]

        def __len__(self):
            return self._n

        def __getitem__(self, key):
            if key == "sequence":
                return MetadataDownloadGeneratorEdgeTests._FakeSeqCol(["s1"])
            raise KeyError(key)

    def test_generator_recurses_when_bbox_hits_api_limit(self):
        orig_sequences = self.module.global_sequences
        orig_bboxes = self.module.global_bboxes

        async def fake_data_handling(*args, **kwargs):
            call = fake_data_handling.calls
            fake_data_handling.calls += 1
            if call == 0:
                return MetadataDownloadGeneratorEdgeTests._FakeDf(self.module.API_MAX_RESULTS_PER_BBOX), 0, 3, 0, 0.0
            return MetadataDownloadGeneratorEdgeTests._FakeDf(1), 0, 3, 0, 0.0

        fake_data_handling.calls = 0

        try:
            self.module.global_sequences = set()
            self.module.global_bboxes = set()

            with (
                mock.patch.object(self.module, "data_handling", side_effect=fake_data_handling),
                mock.patch.object(self.module, "segmented_bboxes", return_value=[[0.0, 0.0, 1.0, 1.0]]),
            ):
                async def run_it():
                    out = []
                    async for _ in self.module.generator_get_bboxes_and_sequences(
                        session=object(),
                        bbox=[0.0, 0.0, 2.0, 2.0],
                        n=1,
                        mly_key="key",
                        call_limit=1,
                    ):
                        out.append(1)
                    return out

                yielded = self.module.asyncio.run(run_it())

            self.assertGreaterEqual(len(yielded), 1)
            self.assertIn("s1", self.module.global_sequences)
            self.assertIn((0.0, 0.0, 1.0, 1.0), self.module.global_bboxes)
        finally:
            self.module.global_sequences = orig_sequences
            self.module.global_bboxes = orig_bboxes

    def test_generator_handles_missing_sequence_column(self):
        async def fake_sleep(_t):
            return None

        async def fake_data_handling(*args, **kwargs):
            return MetadataDownloadGeneratorEdgeTests._FakeDf(5, with_sequence=False), 0, 3, 0, 0.0

        with (
            mock.patch.object(self.module, "data_handling", side_effect=fake_data_handling),
            mock.patch.object(self.module.asyncio, "sleep", side_effect=fake_sleep),
        ):
            async def run_it():
                out = []
                async for _ in self.module.generator_get_bboxes_and_sequences(
                    session=object(),
                    bbox=[0.0, 0.0, 1.0, 1.0],
                    n=1,
                    mly_key="key",
                    call_limit=1,
                ):
                    out.append(1)
                return out

            yielded = self.module.asyncio.run(run_it())

        self.assertEqual(len(yielded), 1)

    def test_get_bboxes_and_sequences_wrapping_sets_windows_policy(self):
        captured = {}

        def fake_run(coro):
            captured["called"] = True
            coro.close()

        with (
            mock.patch.object(self.module.asyncio, "WindowsSelectorEventLoopPolicy", return_value="policy", create=True),
            mock.patch.object(self.module.asyncio, "set_event_loop_policy") as set_policy_mock,
            mock.patch.object(self.module.asyncio, "run", side_effect=fake_run),
        ):
            self.module.get_bboxes_and_sequences_wrapping(
                bbox=[0, 0, 1, 1], n=1, mly_key="k", args={}, windows=True
            )

        set_policy_mock.assert_called_once_with("policy")
        self.assertTrue(captured.get("called", False))

    def test_get_bboxes_and_sequences_uses_session_and_consumes_generator(self):
        consumed = {"n": 0}

        class FakeSession:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

        async def fake_generator(*args, **kwargs):
            consumed["n"] += 1
            yield None
            yield None

        with (
            mock.patch.object(self.module.aiohttp, "ClientSession", return_value=FakeSession(), create=True),
            mock.patch.object(self.module, "generator_get_bboxes_and_sequences", side_effect=fake_generator),
        ):
            self.module.asyncio.run(
                self.module.get_bboxes_and_sequences([0.0, 0.0, 1.0, 1.0], 1, "k", {})
            )

        self.assertEqual(consumed["n"], 1)

    def test_generator_continues_when_first_data_fetch_is_none_then_processes_second(self):
        class _SeqCol:
            def unique(self):
                return ["s1"]

        class _Df:
            def __init__(self):
                self.columns = ["sequence"]
                self.empty = False

            def __len__(self):
                return 1

            def __getitem__(self, key):
                if key == "sequence":
                    return _SeqCol()
                raise KeyError(key)

        calls = {"n": 0}
        orig_sequences = self.module.global_sequences
        orig_bboxes = self.module.global_bboxes

        async def fake_data_handling(*args, **kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                return None, 0, 3, 0, 0.0
            return _Df(), 1, 3, 0, 0.0

        try:
            self.module.global_sequences = set()
            self.module.global_bboxes = set()
            with mock.patch.object(self.module, "data_handling", side_effect=fake_data_handling):
                async def run_it():
                    out = []
                    async for _ in self.module.generator_get_bboxes_and_sequences(
                        session=object(),
                        bbox=[0.0, 0.0, 1.0, 1.0],
                        n=1,
                        mly_key="key",
                        call_limit=2,
                    ):
                        out.append(1)
                    return out

                yielded = self.module.asyncio.run(run_it())

            self.assertEqual(len(yielded), 1)
            self.assertIn("s1", self.module.global_sequences)
        finally:
            self.module.global_sequences = orig_sequences
            self.module.global_bboxes = orig_bboxes

    def test_generator_handles_empty_sequence_set_without_updating_globals(self):
        class _SeqCol:
            def unique(self):
                return []

        class _Df:
            def __init__(self):
                self.columns = ["sequence"]
                self.empty = False

            def __len__(self):
                return 1

            def __getitem__(self, key):
                if key == "sequence":
                    return _SeqCol()
                raise KeyError(key)

        orig_sequences = self.module.global_sequences
        orig_bboxes = self.module.global_bboxes

        async def fake_data_handling(*args, **kwargs):
            return _Df(), 0, 3, 0, 0.0

        try:
            self.module.global_sequences = set()
            self.module.global_bboxes = set()
            with mock.patch.object(self.module, "data_handling", side_effect=fake_data_handling):
                async def run_it():
                    out = []
                    async for _ in self.module.generator_get_bboxes_and_sequences(
                        session=object(),
                        bbox=[0.0, 0.0, 1.0, 1.0],
                        n=1,
                        mly_key="key",
                        call_limit=1,
                    ):
                        out.append(1)
                    return out

                yielded = self.module.asyncio.run(run_it())

            self.assertEqual(len(yielded), 1)
            self.assertEqual(self.module.global_sequences, set())
        finally:
            self.module.global_sequences = orig_sequences
            self.module.global_bboxes = orig_bboxes

    def test_get_bboxes_and_sequences_wrapping_runs_without_windows_policy_when_false(self):
        captured = {}

        def fake_run(coro):
            captured["called"] = True
            coro.close()

        with (
            mock.patch.object(self.module.asyncio, "set_event_loop_policy") as set_policy_mock,
            mock.patch.object(self.module.asyncio, "run", side_effect=fake_run),
        ):
            self.module.get_bboxes_and_sequences_wrapping(
                bbox=[0, 0, 1, 1], n=1, mly_key="k", args={}, windows=False
            )

        set_policy_mock.assert_not_called()
        self.assertTrue(captured.get("called", False))


class MetadataMainBranchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_metadata_download_module()

    def test_main_removes_existing_output_files_before_run(self):
        removed = []

        def fake_exists(path):
            norm = str(path).replace("\\", "/")
            return norm.endswith("meta.csv") or norm.endswith("missing.csv")

        with (
            mock.patch.object(self.module.os.path, "exists", side_effect=fake_exists),
            mock.patch.object(self.module.os, "remove", side_effect=lambda p: removed.append(str(p).replace("\\", "/"))),
            mock.patch.object(self.module, "get_sequences", return_value=([("b",)], ["s1"])),
            mock.patch.object(self.module, "get_metadata"),
        ):
            self.module.main(
                bbox=[0, 0, 1, 1],
                mly_key="key",
                columns=["id"],
                n=2,
                output_dir="/tmp/out",
                job_id=1,
                metadata_basename="meta",
                missing_basename="missing",
                initial_subdivisions=2,
                params={"retries": 2},
                max_workers=2,
                enable_download=False,
                batch_size=10,
                windows=False,
            )

        self.assertTrue(any(p.endswith("meta.csv") for p in removed))
        self.assertTrue(any(p.endswith("missing.csv") for p in removed))

    def test_main_uses_default_monitoring_and_computes_avg_when_requests_positive(self):
        orig_requests = self.module.number_of_requests
        captured = {"monitoring": None}

        def fake_get_sequences(*args, **kwargs):
            captured["monitoring"] = args[10]
            self.module.number_of_requests = 5
            return ([('b',)], [])

        try:
            self.module.number_of_requests = 0
            with (
                mock.patch.object(self.module.os.path, "exists", return_value=False),
                mock.patch.object(self.module, "get_sequences", side_effect=fake_get_sequences),
                mock.patch.object(self.module, "get_metadata"),
            ):
                self.module.main(
                    bbox=[0, 0, 1, 1],
                    mly_key="key",
                    columns=["id"],
                    n=2,
                    output_dir="/tmp/out",
                    job_id=4,
                    metadata_basename="meta",
                    missing_basename="missing",
                    initial_subdivisions=2,
                    params={"retries": 2},
                    max_workers=2,
                    enable_download=False,
                    batch_size=10,
                    windows=False,
                    monitoring=None,
                )
        finally:
            self.module.number_of_requests = orig_requests

        self.assertIsNotNone(captured["monitoring"])
        self.assertEqual(captured["monitoring"]["monitor_interval"], 10)

    def test_main_accepts_explicit_monitoring_without_defaulting(self):
        custom = {
            "monitor_interval": 3,
            "monitor_check_timeout": 1,
            "write_interval": 4,
            "write_check_timeout": 1,
        }
        captured = {"monitoring": None}

        def fake_get_sequences(*args, **kwargs):
            captured["monitoring"] = args[10]
            return ([('b',)], [])

        with (
            mock.patch.object(self.module.os.path, "exists", return_value=False),
            mock.patch.object(self.module, "get_sequences", side_effect=fake_get_sequences),
            mock.patch.object(self.module, "get_metadata"),
        ):
            self.module.main(
                bbox=[0, 0, 1, 1],
                mly_key="key",
                columns=["id"],
                n=2,
                output_dir="/tmp/out",
                job_id=4,
                metadata_basename="meta",
                missing_basename="missing",
                initial_subdivisions=2,
                params={"retries": 2},
                max_workers=2,
                enable_download=False,
                batch_size=10,
                windows=False,
                monitoring=custom,
            )

        self.assertEqual(captured["monitoring"], custom)


class MetadataThreadJoinTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_metadata_download_module()

    def test_join_threads_with_timeout_raises_when_threads_still_alive(self):
        class FakeThread:
            def __init__(self, alive=True):
                self._alive = alive
                self.name = "fake-thread"

            def join(self, timeout=None):
                return None

            def is_alive(self):
                return self._alive

        with self.assertRaises(RuntimeError):
            self.module.join_threads_with_timeout([FakeThread(alive=True)], timeout=1)

    def test_join_threads_with_timeout_succeeds_when_all_threads_stopped(self):
        class FakeThread:
            def join(self, timeout=None):
                return None

            def is_alive(self):
                return False

        self.module.join_threads_with_timeout([FakeThread(), FakeThread()], timeout=1)
