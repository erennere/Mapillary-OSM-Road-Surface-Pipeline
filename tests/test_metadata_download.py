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

    def test_segmented_bboxes_normalizes_zero_subdivisions_to_single_box(self):
        west, south, east, north = -10.0, -5.0, 10.0, 5.0

        boxes = self.module.segmented_bboxes([west, south, east, north], n=0)

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
                return responses.pop(0), 0, 3, 0, 0.0
            return None, 1, 3, 0, 0.0

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


class MetadataDownloadOrchestrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_metadata_download_module()

    def test_get_metadata_orchestrates_workers_and_flushes(self):
        calls = {"thread_targets": [], "worker_calls": [], "flush_calls": []}

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
                    calls["worker_calls"].append(args)
                    fn(*args)
                return []

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

        class FakeThread:
            def __init__(self, target=None, args=(), daemon=None):
                self.target = target
                self.args = args

            def start(self):
                pass

            def join(self, timeout=None):
                pass

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

        class FakeThread:
            def __init__(self, target=None, args=(), daemon=None):
                self.target = target
                self.args = args

            def start(self):
                pass

            def join(self, timeout=None):
                pass

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

        class FakeThread:
            def __init__(self, target=None, args=(), daemon=None):
                self.target = target
                self.args = args

            def start(self):
                pass

            def join(self, timeout=None):
                pass

            def is_alive(self):
                return False

        class FakeExecutor:
            def __init__(self, max_workers):
                calls["executor_workers"] = max_workers

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def map(self, fn, *iterables):
                for args in zip(*iterables):
                    fn(*args)
                return []

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

        class FakeThread:
            def __init__(self, target=None, args=(), daemon=None):
                self.target = target
                self.args = args

            def start(self):
                pass

            def join(self, timeout=None):
                pass

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
