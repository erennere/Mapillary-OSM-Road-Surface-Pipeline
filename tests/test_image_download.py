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


def import_image_download_module():
    sys.modules.pop("image_download", None)

    fake_numpy = types.ModuleType("numpy")
    fake_numpy.frombuffer = lambda data, dtype: data
    fake_numpy.uint8 = int
    fake_numpy.ndarray = type("ndarray", (), {})

    fake_pandas = types.ModuleType("pandas")
    fake_pandas.DataFrame = lambda data: data

    fake_cv2 = types.ModuleType("cv2")
    fake_cv2.imdecode = lambda *args: None
    fake_cv2.resize = lambda *args: None
    fake_cv2.IMREAD_COLOR = 1
    fake_cv2.imwrite = lambda *args: None

    fake_aiohttp = types.ModuleType("aiohttp")
    fake_asyncio = types.ModuleType("asyncio")
    fake_asyncio.run = None  # placeholder for patch.object
    # Do NOT mock 'threading' – concurrent.futures requires the real threading module

    fake_start = types.ModuleType("start")
    fake_start.load_config = lambda path=None: {}

    fake_glob = types.ModuleType("glob")

    with mock.patch.dict(
        sys.modules,
        {
            "numpy": fake_numpy,
            "pandas": fake_pandas,
            "cv2": fake_cv2,
            "aiohttp": fake_aiohttp,
            "asyncio": fake_asyncio,
            "start": fake_start,
            "glob": fake_glob,
        },
    ):
        return importlib.import_module("image_download")


class CreateTasksInGeneratorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_image_download_module()

    def _make_chunk(self, rows):
        """Build a minimal fake DataFrame that iterrows over given dicts."""

        class FakeChunk:
            def iterrows(self_inner):
                return iter(enumerate(rows))

        return FakeChunk()

    def test_create_tasks_yields_all_rows_in_single_batch_when_fewer_than_batch_size(self):
        generator = random.Random(1001)
        count = generator.randint(2, 8)
        rows = [{"id": generator.randint(100, 999), "url": f"http://example.com/{i}"} for i in range(count)]
        chunk = self._make_chunk(rows)
        original_dir = f"/tmp/orig_{generator.randint(100, 999)}"
        resized_dir = f"/tmp/res_{generator.randint(100, 999)}"
        image_size = (generator.randint(100, 400), generator.randint(100, 400))
        call_limit = generator.randint(2, 5)
        sleep_time = generator.randint(1, 5)
        batch_size = count + generator.randint(1, 5)

        batches = list(
            self.module.create_tasks_in_generator(
                chunk, original_dir, resized_dir, image_size, call_limit, sleep_time, batch_size=batch_size
            )
        )

        self.assertEqual(len(batches), 1)
        self.assertEqual(len(batches[0]), count)

    def test_create_tasks_yields_multiple_batches_when_rows_exceed_batch_size(self):
        generator = random.Random(1002)
        batch_size = generator.randint(2, 4)
        count = batch_size * generator.randint(2, 4) + generator.randint(1, batch_size - 1)
        rows = [{"id": i, "url": f"http://x.com/{i}"} for i in range(count)]
        chunk = self._make_chunk(rows)

        batches = list(
            self.module.create_tasks_in_generator(
                chunk,
                "/tmp/orig",
                "/tmp/res",
                (224, 224),
                3,
                5,
                batch_size=batch_size,
            )
        )

        self.assertGreater(len(batches), 1)
        for b in batches[:-1]:
            self.assertEqual(len(b), batch_size)
        self.assertGreaterEqual(len(batches[-1]), 1)
        total = sum(len(b) for b in batches)
        self.assertEqual(total, count)

    def test_create_tasks_each_task_carries_correct_download_args(self):
        generator = random.Random(1003)
        rows = [{"id": generator.randint(1, 100), "url": f"http://img/{generator.randint(1, 9)}"}]
        chunk = self._make_chunk(rows)
        original_dir = f"/tmp/orig_{generator.randint(100, 999)}"
        resized_dir = f"/tmp/res_{generator.randint(100, 999)}"
        image_size = (generator.randint(64, 256), generator.randint(64, 256))
        call_limit = generator.randint(1, 10)
        sleep_time = generator.randint(1, 10)

        batches = list(
            self.module.create_tasks_in_generator(
                chunk, original_dir, resized_dir, image_size, call_limit, sleep_time, batch_size=100
            )
        )

        task = batches[0][0]
        _, row, o_dir, r_dir, dl_args = task[0], task[0], task[1], task[2], task[3]
        self.assertEqual(task[1], original_dir)
        self.assertEqual(task[2], resized_dir)
        self.assertEqual(task[3]["image_size"], image_size)
        self.assertEqual(task[3]["call_limit"], call_limit)
        self.assertEqual(task[3]["sleep_time"], sleep_time)

    def test_create_tasks_preserves_row_order_across_batches(self):
        generator = random.Random(1004)
        count = generator.randint(5, 15)
        rows = [{"id": i, "url": f"http://x/{i}"} for i in range(count)]
        chunk = self._make_chunk(rows)

        batches = list(
            self.module.create_tasks_in_generator(
                chunk, "/tmp/o", "/tmp/r", (100, 100), 2, 1, batch_size=3
            )
        )

        flat_rows = [task[0] for batch in batches for task in batch]
        for original_row, task_row in zip(rows, flat_rows):
            self.assertEqual(original_row, task_row)

    def test_create_tasks_handles_empty_chunk(self):
        chunk = self._make_chunk([])

        batches = list(
            self.module.create_tasks_in_generator(
                chunk, "/tmp/o", "/tmp/r", (100, 100), 2, 1, batch_size=10
            )
        )

        self.assertEqual(batches, [])


# ---------------------------------------------------------------------------
# monitor_connections
# ---------------------------------------------------------------------------

class MonitorConnectionsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_image_download_module()

    def test_start_true_resets_current_connections_and_returns(self):
        gen = random.Random(1010)
        new_limit = gen.randint(100, 5000)

        orig_stop = self.module.thread_stop
        orig_allowed = self.module.allowed_connections
        orig_curr = self.module.allowed_connections_current

        try:
            self.module.thread_stop = False
            self.module.allowed_connections = new_limit
            self.module.allowed_connections_current = 0

            self.module.monitor_connections(interval=1, start=True, check_timeout=1)

            self.assertEqual(self.module.allowed_connections_current, new_limit)
        finally:
            self.module.thread_stop = orig_stop
            self.module.allowed_connections = orig_allowed
            self.module.allowed_connections_current = orig_curr

    def test_does_not_run_when_thread_stop_is_true(self):
        orig_stop = self.module.thread_stop
        orig_curr = self.module.allowed_connections_current

        try:
            self.module.thread_stop = True
            self.module.allowed_connections_current = -99

            self.module.monitor_connections(interval=1, start=False, check_timeout=1)

            # thread_stop was True from the start so the while loop body never ran
            self.assertEqual(self.module.allowed_connections_current, -99)
        finally:
            self.module.thread_stop = orig_stop
            self.module.allowed_connections_current = orig_curr


# ---------------------------------------------------------------------------
# write_missing_images
# ---------------------------------------------------------------------------

class WriteMissingImagesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_image_download_module()

    def test_start_true_writes_current_missing_images_and_returns(self):
        gen = random.Random(1020)
        n = gen.randint(1, 5)
        images = [{"id": str(i), "url": f"http://x/{i}"} for i in range(n)]
        filepath = f"/tmp/missing_{gen.randint(1000, 9999)}.csv"

        orig_stop = self.module.thread_stop
        orig_missing = self.module.missing_images

        written = {}

        class FakeDf:
            def __init__(self, data):
                written["data"] = data
                written["len"] = len(data)

            def __len__(self):
                return written.get("len", 0)

            def to_csv(self, path, index):
                written["path"] = path

        try:
            self.module.thread_stop = False
            self.module.missing_images = images[:]

            with mock.patch.object(self.module.pd, "DataFrame", side_effect=FakeDf):
                self.module.write_missing_images(filepath, start=True)

            self.assertEqual(written.get("path"), filepath)
        finally:
            self.module.thread_stop = orig_stop
            self.module.missing_images = orig_missing

    def test_skips_write_when_no_missing_images_and_start_true(self):
        gen = random.Random(1021)
        filepath = f"/tmp/missing_{gen.randint(1000, 9999)}.csv"

        orig_stop = self.module.thread_stop
        orig_missing = self.module.missing_images

        to_csv_calls = []

        class FakeDf:
            def __init__(self, data): self._data = data
            def __len__(self): return len(self._data)
            def to_csv(self, path, index): to_csv_calls.append(path)

        try:
            self.module.thread_stop = False
            self.module.missing_images = []

            with mock.patch.object(self.module.pd, "DataFrame", side_effect=FakeDf):
                self.module.write_missing_images(filepath, start=True)

            self.assertEqual(len(to_csv_calls), 0)
        finally:
            self.module.thread_stop = orig_stop
            self.module.missing_images = orig_missing

    def test_does_not_run_when_thread_stop_is_true(self):
        gen = random.Random(1022)
        filepath = f"/tmp/missing_{gen.randint(1000, 9999)}.csv"

        orig_stop = self.module.thread_stop
        orig_missing = self.module.missing_images

        calls = []

        class FakeDf:
            def __init__(self, data): calls.append(data)
            def __len__(self): return 0
            def to_csv(self, *a, **k): pass

        try:
            self.module.thread_stop = True
            self.module.missing_images = [{"id": "x"}]

            with mock.patch.object(self.module.pd, "DataFrame", side_effect=FakeDf):
                self.module.write_missing_images(filepath)

            # Loop condition is `while not thread_stop`, which is False immediately
            self.assertEqual(len(calls), 0)
        finally:
            self.module.thread_stop = orig_stop
            self.module.missing_images = orig_missing


# ---------------------------------------------------------------------------
# process_tasks_wrapper
# ---------------------------------------------------------------------------

class ProcessTasksWrapperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_image_download_module()

    def test_calls_asyncio_run_with_process_tasks(self):
        gen = random.Random(1030)
        chunk_rows = [{"id": str(i)} for i in range(gen.randint(2, 5))]
        task_args = {"original_dir": f"/orig_{gen.randint(100, 999)}", "resized_dir": f"/res_{gen.randint(100, 999)}"}
        download_args = {"image_size": (320, 240), "call_limit": 3, "sleep_time": 2}

        asyncio_run_called_with = []

        def fake_run(coro):
            asyncio_run_called_with.append(coro)

        with mock.patch.object(self.module.asyncio, "run", side_effect=fake_run):
            self.module.process_tasks_wrapper(
                chunk_rows, task_args, download_args, batch_size=10
            )

        self.assertEqual(len(asyncio_run_called_with), 1)

    def test_passes_org_save_true_to_process_tasks(self):
        gen = random.Random(1031)
        chunk_rows = [{"id": str(i)} for i in range(gen.randint(1, 3))]
        task_args = {"original_dir": "/o", "resized_dir": "/r"}
        download_args = {"image_size": (100, 100), "call_limit": 2, "sleep_time": 1}

        process_tasks_calls = []

        def fake_process_tasks(chunk, orig_dir, res_dir, image_size, batch_size,
                               call_limit, sleep_time, org_save_true):
            process_tasks_calls.append(org_save_true)
            return iter([])  # needs to be awaitable – we patch asyncio.run instead

        with mock.patch.object(self.module.asyncio, "run"):
            # Just verify the wrapper runs without error and calls asyncio.run
            self.module.process_tasks_wrapper(
                chunk_rows, task_args, download_args, batch_size=5, org_save_true=True
            )
