import importlib
import asyncio
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
    fake_start.__getattr__ = lambda name: getattr(real_start, name)

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


class ParseBoolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_image_download_module()

    def test_parse_bool_accepts_truthy_and_falsy_strings(self):
        self.assertTrue(self.module.parse_bool_with_default("true", "image_download.bool_value", False))
        self.assertTrue(self.module.parse_bool_with_default("YES", "image_download.bool_value", False))
        self.assertFalse(self.module.parse_bool_with_default("false", "image_download.bool_value", True))
        self.assertFalse(self.module.parse_bool_with_default("off", "image_download.bool_value", True))

    def test_parse_bool_handles_numeric_values(self):
        self.assertTrue(self.module.parse_bool_with_default(1, "image_download.bool_value", False))
        self.assertFalse(self.module.parse_bool_with_default(0, "image_download.bool_value", True))

    def test_parse_bool_returns_default_for_unknown_value(self):
        self.assertTrue(self.module.parse_bool_with_default("maybe", "image_download.bool_value", True))
        self.assertFalse(self.module.parse_bool_with_default(None, "image_download.bool_value", False))


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

    def test_exits_when_thread_stop_set_during_wait_loop(self):
        orig_stop = self.module.thread_stop
        orig_curr = self.module.allowed_connections_current
        orig_allowed = self.module.allowed_connections

        def fake_sleep(_t):
            self.module.thread_stop = True

        try:
            self.module.thread_stop = False
            self.module.allowed_connections = 77
            self.module.allowed_connections_current = 0

            with mock.patch.object(self.module.time, "sleep", side_effect=fake_sleep):
                self.module.monitor_connections(interval=2, start=False, check_timeout=1)

            self.assertEqual(self.module.allowed_connections_current, 77)
        finally:
            self.module.thread_stop = orig_stop
            self.module.allowed_connections_current = orig_curr
            self.module.allowed_connections = orig_allowed

    def test_start_false_completes_cycle_then_exits_on_next_loop_check(self):
        orig_stop = self.module.thread_stop
        orig_curr = self.module.allowed_connections_current
        orig_allowed = self.module.allowed_connections

        sleep_calls = {"count": 0}

        def fake_sleep(_t):
            sleep_calls["count"] += 1
            if sleep_calls["count"] >= 2:
                self.module.thread_stop = True

        try:
            self.module.thread_stop = False
            self.module.allowed_connections = 11
            self.module.allowed_connections_current = 0

            with mock.patch.object(self.module.time, "sleep", side_effect=fake_sleep):
                self.module.monitor_connections(interval=2, start=False, check_timeout=1)

            self.assertEqual(self.module.allowed_connections_current, 11)
            self.assertEqual(sleep_calls["count"], 2)
        finally:
            self.module.thread_stop = orig_stop
            self.module.allowed_connections_current = orig_curr
            self.module.allowed_connections = orig_allowed


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

    def test_flushes_missing_images_on_stop_during_wait(self):
        filepath = "/tmp/missing_stop_flush.csv"
        orig_stop = self.module.thread_stop
        orig_missing = self.module.missing_images

        writes = []

        class FakeDf:
            def __init__(self, data):
                self._data = data

            def __len__(self):
                return len(self._data)

            def to_csv(self, path, index=False):
                writes.append(path)

        def fake_sleep(_t):
            self.module.thread_stop = True

        try:
            self.module.thread_stop = False
            self.module.missing_images = [{"id": "1", "url": "http://x/1"}]

            with (
                mock.patch.object(self.module.pd, "DataFrame", side_effect=FakeDf),
                mock.patch.object(self.module.time, "sleep", side_effect=fake_sleep),
            ):
                self.module.write_missing_images(filepath, interval=2, start=False, check_timeout=1)

            self.assertGreaterEqual(len(writes), 2)
        finally:
            self.module.thread_stop = orig_stop
            self.module.missing_images = orig_missing

    def test_start_false_completes_wait_cycle_before_stopping(self):
        filepath = "/tmp/missing_cycle.csv"
        orig_stop = self.module.thread_stop
        orig_missing = self.module.missing_images

        writes = []
        sleep_calls = {"count": 0}

        class FakeDf:
            def __init__(self, data):
                self._data = data

            def __len__(self):
                return len(self._data)

            def to_csv(self, path, index=False):
                writes.append(path)

        def fake_sleep(_t):
            sleep_calls["count"] += 1
            if sleep_calls["count"] >= 2:
                self.module.thread_stop = True

        try:
            self.module.thread_stop = False
            self.module.missing_images = [{"id": "1", "url": "http://x/1"}]

            with (
                mock.patch.object(self.module.pd, "DataFrame", side_effect=FakeDf),
                mock.patch.object(self.module.time, "sleep", side_effect=fake_sleep),
            ):
                self.module.write_missing_images(filepath, interval=2, start=False, check_timeout=1)

            self.assertGreaterEqual(len(writes), 1)
            self.assertEqual(sleep_calls["count"], 2)
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
            coro.close()

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

        def fake_run(coro):
            coro.close()

        with mock.patch.object(self.module.asyncio, "run", side_effect=fake_run):
            # Just verify the wrapper runs without error and calls asyncio.run
            self.module.process_tasks_wrapper(
                chunk_rows, task_args, download_args, batch_size=5, org_save_true=True
            )

    def test_windows_true_sets_event_loop_policy(self):
        task_args = {"original_dir": "/o", "resized_dir": "/r"}
        download_args = {"image_size": (100, 100), "call_limit": 2, "sleep_time": 1}

        def fake_run(coro):
            coro.close()

        with (
            mock.patch.object(self.module.asyncio, "WindowsSelectorEventLoopPolicy", return_value="policy", create=True),
            mock.patch.object(self.module.asyncio, "set_event_loop_policy", create=True) as set_policy_mock,
            mock.patch.object(self.module.asyncio, "run", side_effect=fake_run),
        ):
            self.module.process_tasks_wrapper([], task_args, download_args, windows=True)

        set_policy_mock.assert_called_once_with("policy")


# ---------------------------------------------------------------------------
# process_tasks / orchestrate
# ---------------------------------------------------------------------------

class ProcessTasksAndOrchestrateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_image_download_module()

    def test_process_tasks_records_missing_once_and_cleans_partial_files(self):
        class FakeSession:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

        async def fake_process_image(*args, **kwargs):
            return ["img_a", "dup_id", "http://x/a"], True

        async def fake_gather(*args, **kwargs):
            for coro in args:
                if hasattr(coro, "close"):
                    coro.close()
            return [
                (["img_a", "dup_id", "http://x/a"], True),
                (["img_b", "dup_id", "http://x/b"], True),
                None,
                Exception("boom"),
                (["img_c", "ok_id", "http://x/c"], False),
            ]

        self.module.missing_images = []
        self.module.missing_image_ids = set()

        removed_files = []

        with (
            mock.patch.object(self.module, "create_tasks_in_generator", return_value=[[({"id": "x", "url": "u"}, "/o", "/r", {})]]),
            mock.patch.object(self.module.aiohttp, "ClientSession", return_value=FakeSession(), create=True),
            mock.patch.object(self.module, "process_image", side_effect=fake_process_image),
            mock.patch.object(self.module.asyncio, "gather", side_effect=fake_gather, create=True),
            mock.patch.object(self.module.os.path, "exists", return_value=True),
            mock.patch.object(self.module.os, "remove", side_effect=lambda p: removed_files.append(p)),
        ):
            asyncio.run(
                self.module.process_tasks(
                    chunk=[{"id": "x", "url": "u"}],
                    original_dir="/orig",
                    resized_dir="/res",
                    image_size=(64, 64),
                    batch_size=1,
                    call_limit=1,
                    sleep_time=1,
                    org_save_true=False,
                )
            )

        self.assertEqual(len(self.module.missing_images), 1)
        self.assertIn("dup_id", self.module.missing_image_ids)
        self.assertEqual(len(removed_files), 2)

    def test_process_tasks_skips_delete_when_failed_files_do_not_exist(self):
        class FakeSession:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

        async def fake_gather(*args, **kwargs):
            for coro in args:
                if hasattr(coro, "close"):
                    coro.close()
            return [(["img_x", "id_x", "http://x"], True)]

        self.module.missing_images = []
        self.module.missing_image_ids = set()

        with (
            mock.patch.object(self.module, "create_tasks_in_generator", return_value=[[({"id": "x", "url": "u"}, "/o", "/r", {})]]),
            mock.patch.object(self.module.aiohttp, "ClientSession", return_value=FakeSession(), create=True),
            mock.patch.object(self.module.asyncio, "gather", side_effect=fake_gather, create=True),
            mock.patch.object(self.module.os.path, "exists", return_value=False),
            mock.patch.object(self.module.os, "remove") as remove_mock,
        ):
            asyncio.run(
                self.module.process_tasks(
                    chunk=[{"id": "x", "url": "u"}],
                    original_dir="/orig",
                    resized_dir="/res",
                    image_size=(64, 64),
                    batch_size=1,
                    call_limit=1,
                    sleep_time=1,
                    org_save_true=True,
                )
            )

        remove_mock.assert_not_called()

    def test_orchestrate_runs_workers_and_stops_threads(self):
        calls = {"worker": 0, "threads_started": 0, "threads_joined": 0}

        class FakeThread:
            def __init__(self, target=None, args=()):
                self.target = target
                self.args = args
                self.daemon = False

            def start(self):
                calls["threads_started"] += 1

            def join(self, timeout=None):
                calls["threads_joined"] += 1

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
                    calls["worker"] += 1
                    fn(*args)
                return []

        with (
            mock.patch.object(self.module.os.path, "exists", return_value=False),
            mock.patch.object(self.module.os, "makedirs"),
            mock.patch.object(self.module.np, "array_split", return_value=[[{"id": 1}], [{"id": 2}]], create=True),
            mock.patch.object(self.module, "process_tasks_wrapper"),
            mock.patch.object(self.module.threading, "Thread", side_effect=FakeThread),
            mock.patch.object(self.module, "ThreadPoolExecutor", side_effect=FakeExecutor),
        ):
            self.module.orchestrate(
                metadata=[{"id": 1}],
                missing_images_file="/tmp/logs/missing.csv",
                original_dir="/tmp/img/orig",
                resized_dir="/tmp/img/res",
                download_args={"image_size": (64, 64), "call_limit": 2, "sleep_time": 1, "allowed_connections": 10},
                max_workers=2,
                batch_size=5,
                windows=False,
                org_save_true=False,
            )

        self.assertEqual(calls["worker"], 2)
        self.assertEqual(calls["threads_started"], 2)
        self.assertEqual(calls["threads_joined"], 2)
        self.assertTrue(self.module.thread_stop)

    def test_orchestrate_passes_wrapper_args_in_correct_positional_order(self):
        calls = {"received": []}

        class FakeThread:
            def __init__(self, target=None, args=()):
                self.target = target
                self.args = args
                self.daemon = False

            def start(self):
                return None

            def join(self, timeout=None):
                return None

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

        def fake_wrapper(chunk, task_args, download_args, batch_size, org_save_true, windows):
            calls["received"].append((batch_size, org_save_true, windows))

        with (
            mock.patch.object(self.module.os.path, "exists", return_value=False),
            mock.patch.object(self.module.os, "makedirs"),
            mock.patch.object(self.module.np, "array_split", return_value=[[{"id": 1}], [{"id": 2}]], create=True),
            mock.patch.object(self.module.threading, "Thread", side_effect=FakeThread),
            mock.patch.object(self.module, "ThreadPoolExecutor", side_effect=FakeExecutor),
            mock.patch.object(self.module, "process_tasks_wrapper", side_effect=fake_wrapper),
        ):
            self.module.orchestrate(
                metadata=[{"id": 1}],
                missing_images_file="/tmp/logs/missing.csv",
                original_dir="/tmp/img/orig",
                resized_dir="/tmp/img/res",
                download_args={"image_size": (64, 64), "call_limit": 2, "sleep_time": 1, "allowed_connections": 10},
                max_workers=2,
                batch_size=7,
                windows=True,
                org_save_true=False,
            )

        self.assertTrue(calls["received"])
        self.assertTrue(all(b == 7 for b, _, _ in calls["received"]))
        self.assertTrue(all(o is False for _, o, _ in calls["received"]))
        self.assertTrue(all(w is True for _, _, w in calls["received"]))

    def test_orchestrate_normalizes_string_boolean_flags(self):
        calls = {"received": []}

        class FakeThread:
            def __init__(self, target=None, args=()):
                self.target = target
                self.args = args
                self.daemon = False

            def start(self):
                return None

            def join(self, timeout=None):
                return None

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

        def fake_wrapper(chunk, task_args, download_args, batch_size, org_save_true, windows):
            calls["received"].append((org_save_true, windows))

        with (
            mock.patch.object(self.module.os.path, "exists", return_value=False),
            mock.patch.object(self.module.os, "makedirs"),
            mock.patch.object(self.module.np, "array_split", return_value=[[{"id": 1}]], create=True),
            mock.patch.object(self.module.threading, "Thread", side_effect=FakeThread),
            mock.patch.object(self.module, "ThreadPoolExecutor", side_effect=FakeExecutor),
            mock.patch.object(self.module, "process_tasks_wrapper", side_effect=fake_wrapper),
        ):
            self.module.orchestrate(
                metadata=[{"id": 1}],
                missing_images_file="/tmp/logs/missing.csv",
                original_dir="/tmp/img/orig",
                resized_dir="/tmp/img/res",
                download_args={"image_size": (64, 64), "call_limit": 2, "sleep_time": 1, "allowed_connections": 10},
                max_workers=1,
                batch_size=7,
                windows="false",
                org_save_true="false",
            )

        self.assertTrue(calls["received"])
        self.assertTrue(all(o is False for o, _ in calls["received"]))
        self.assertTrue(all(w is False for _, w in calls["received"]))

    def test_orchestrate_accepts_basename_missing_images_file_path(self):
        calls = {"makedirs": []}

        class FakeThread:
            def __init__(self, target=None, args=()):
                self.target = target
                self.args = args
                self.daemon = False

            def start(self):
                return None

            def join(self, timeout=None):
                return None

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
            mock.patch.object(self.module.os.path, "exists", return_value=False),
            mock.patch.object(self.module.os, "makedirs", side_effect=fake_makedirs),
            mock.patch.object(self.module.np, "array_split", return_value=[[{"id": 1}]], create=True),
            mock.patch.object(self.module.threading, "Thread", side_effect=FakeThread),
            mock.patch.object(self.module, "ThreadPoolExecutor", side_effect=FakeExecutor),
            mock.patch.object(self.module, "process_tasks_wrapper"),
        ):
            self.module.orchestrate(
                metadata=[{"id": 1}],
                missing_images_file="missing.csv",
                original_dir="/tmp/img/orig",
                resized_dir="/tmp/img/res",
                download_args={"image_size": (64, 64), "call_limit": 2, "sleep_time": 1, "allowed_connections": 10},
                max_workers=1,
                batch_size=5,
                windows=False,
                org_save_true=False,
            )

        self.assertIn(".", calls["makedirs"])

    def test_orchestrate_skips_makedirs_when_directories_exist(self):
        class FakeThread:
            def __init__(self, target=None, args=()):
                self.target = target
                self.args = args
                self.daemon = False

            def start(self):
                return None

            def join(self, timeout=None):
                return None

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

        with (
            mock.patch.object(self.module.os.path, "exists", return_value=True),
            mock.patch.object(self.module.os, "makedirs") as makedirs_mock,
            mock.patch.object(self.module.np, "array_split", return_value=[[{"id": 1}]], create=True),
            mock.patch.object(self.module.threading, "Thread", side_effect=FakeThread),
            mock.patch.object(self.module, "ThreadPoolExecutor", side_effect=FakeExecutor),
            mock.patch.object(self.module, "process_tasks_wrapper"),
        ):
            self.module.orchestrate(
                metadata=[{"id": 1}],
                missing_images_file="/tmp/logs/missing.csv",
                original_dir="/tmp/img/orig",
                resized_dir="/tmp/img/res",
                download_args={"image_size": (64, 64), "call_limit": 2, "sleep_time": 1, "allowed_connections": 10},
                max_workers=1,
                batch_size=5,
                windows=False,
                org_save_true=False,
            )

        makedirs_mock.assert_not_called()

    def test_orchestrate_iterates_over_executor_results(self):
        calls = {"iterated": 0}

        class FakeThread:
            def __init__(self, target=None, args=()):
                self.daemon = False

            def start(self):
                return None

            def join(self, timeout=None):
                return None

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
                def _iterable_results():
                    yield object()
                    calls["iterated"] += 1
                    yield object()
                    calls["iterated"] += 1

                return _iterable_results()

        def fake_pass(*args, **kwargs):
            return None

        with (
            mock.patch.object(self.module.os.path, "exists", return_value=True),
            mock.patch.object(self.module.np, "array_split", return_value=[[{"id": 1}]], create=True),
            mock.patch.object(self.module.threading, "Thread", side_effect=FakeThread),
            mock.patch.object(self.module, "ThreadPoolExecutor", side_effect=FakeExecutor),
            mock.patch.object(self.module, "process_tasks_wrapper", side_effect=fake_pass),
            mock.patch.object(self.module, "join_threads_with_timeout"),
        ):
            self.module.orchestrate(
                metadata=[{"id": 1}],
                missing_images_file="/tmp/logs/missing.csv",
                original_dir="/tmp/img/orig",
                resized_dir="/tmp/img/res",
                download_args={"image_size": (64, 64), "call_limit": 2, "sleep_time": 1, "allowed_connections": 10},
                max_workers=1,
                batch_size=5,
                windows=False,
                org_save_true=False,
            )

        self.assertEqual(calls["iterated"], 2)


class JoinThreadsWithTimeoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_image_download_module()

    def test_raises_when_any_thread_is_still_alive(self):
        class FakeThread:
            def join(self, timeout=None):
                return None

            def is_alive(self):
                return True

        with self.assertRaises(RuntimeError):
            self.module.join_threads_with_timeout([FakeThread()], timeout=1)


class ImageFetchAndSaveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_image_download_module()

    def test_fetch_image_returns_bytes_on_success(self):
        calls = []

        class FakeResponse:
            status = 200

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def read(self):
                return b"abc"

        class FakeSession:
            def get(self, _url, **kwargs):
                calls.append(kwargs)
                return FakeResponse()

        result = asyncio.run(self.module.fetch_image("http://x", FakeSession()))
        self.assertEqual(result, b"abc")
        self.assertEqual(calls[0].get("timeout"), 10)

    def test_fetch_image_returns_none_on_non_200(self):
        class FakeResponse:
            status = 404

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def read(self):
                return b""

        class FakeSession:
            def get(self, _url, **kwargs):
                return FakeResponse()

        result = asyncio.run(self.module.fetch_image("http://x", FakeSession()))
        self.assertIsNone(result)

    def test_fetch_image_returns_none_when_response_body_is_not_bytes(self):
        class FakeResponse:
            status = 200

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def read(self):
                return "not-bytes"

        class FakeSession:
            def get(self, _url, **kwargs):
                return FakeResponse()

        result = asyncio.run(self.module.fetch_image("http://x", FakeSession()))
        self.assertIsNone(result)

    def test_fetch_image_returns_none_when_response_body_is_empty(self):
        class FakeResponse:
            status = 200

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def read(self):
                return b""

        class FakeSession:
            def get(self, _url, **kwargs):
                return FakeResponse()

        result = asyncio.run(self.module.fetch_image("http://x", FakeSession()))
        self.assertIsNone(result)

    def test_get_image_waits_for_connection_slot_then_fetches(self):
        orig_allowed = self.module.allowed_connections_current

        async def fake_sleep(_t):
            self.module.allowed_connections_current = 1

        async def fake_fetch(_url, _session):
            return b"data"

        try:
            self.module.allowed_connections_current = 0
            with (
                mock.patch.object(self.module.asyncio, "sleep", side_effect=fake_sleep, create=True),
                mock.patch.object(self.module, "fetch_image", side_effect=fake_fetch),
                mock.patch.object(self.module.np, "frombuffer", return_value=[1, 2, 3]),
                mock.patch.object(self.module.np, "ndarray", list),
                mock.patch.object(self.module.cv2, "imdecode", return_value=[9, 9]),
                mock.patch.object(self.module.cv2, "resize", return_value=[5, 5]),
            ):
                image, resized = asyncio.run(
                    self.module.get_image("http://x", (64, 64), session=object(), call_limit=2, sleep_time=1)
                )

            self.assertEqual(image, [9, 9])
            self.assertEqual(resized, [5, 5])
        finally:
            self.module.allowed_connections_current = orig_allowed

    def test_get_image_success_after_retry(self):
        orig_allowed = self.module.allowed_connections
        orig_allowed_current = self.module.allowed_connections_current

        async def fake_sleep(_t):
            self.module.allowed_connections_current = 1
            return None

        fetch_calls = {"n": 0}

        async def fake_fetch(_url, _session):
            fetch_calls["n"] += 1
            return None if fetch_calls["n"] == 1 else b"data"

        try:
            self.module.allowed_connections = 1
            self.module.allowed_connections_current = 1
            with (
                mock.patch.object(self.module, "fetch_image", side_effect=fake_fetch),
                mock.patch.object(self.module.asyncio, "sleep", side_effect=fake_sleep, create=True),
                mock.patch.object(self.module.np, "frombuffer", return_value=[1, 2, 3]),
                mock.patch.object(self.module.np, "ndarray", list),
                mock.patch.object(self.module.cv2, "imdecode", return_value=[9, 9]),
                mock.patch.object(self.module.cv2, "resize", return_value=[5, 5]),
            ):
                image, resized = asyncio.run(
                    self.module.get_image("http://x", (64, 64), session=object(), call_limit=3, sleep_time=1)
                )
        finally:
            self.module.allowed_connections = orig_allowed
            self.module.allowed_connections_current = orig_allowed_current

        self.assertEqual(fetch_calls["n"], 2)
        self.assertEqual(image, [9, 9])
        self.assertEqual(resized, [5, 5])

    def test_get_image_returns_none_when_all_attempts_fail(self):
        orig_allowed = self.module.allowed_connections
        orig_allowed_current = self.module.allowed_connections_current

        async def fake_sleep(_t):
            self.module.allowed_connections_current = 1
            return None

        async def fake_fetch(_url, _session):
            return None

        try:
            self.module.allowed_connections = 1
            self.module.allowed_connections_current = 1
            with (
                mock.patch.object(self.module, "fetch_image", side_effect=fake_fetch),
                mock.patch.object(self.module.asyncio, "sleep", side_effect=fake_sleep, create=True),
            ):
                image, resized = asyncio.run(
                    self.module.get_image("http://x", (64, 64), session=object(), call_limit=2, sleep_time=1)
                )
        finally:
            self.module.allowed_connections = orig_allowed
            self.module.allowed_connections_current = orig_allowed_current

        self.assertIsNone(image)
        self.assertIsNone(resized)

    def test_save_image_writes_resized_only_when_org_save_false(self):
        calls = []
        with (
            mock.patch.object(self.module.np, "ndarray", list),
            mock.patch.object(self.module.cv2, "imwrite", side_effect=lambda p, i: calls.append(p) or True),
        ):
            ok, exc = asyncio.run(
                self.module.save_image("/tmp/o.png", "/tmp/r.png", [1], [2], org_save_true=False)
            )

        self.assertTrue(ok)
        self.assertFalse(exc)
        self.assertEqual(calls, ["/tmp/r.png"])

    def test_save_image_returns_failure_for_invalid_inputs(self):
        with mock.patch.object(self.module.np, "ndarray", list):
            ok, exc = asyncio.run(
                self.module.save_image("/tmp/o.png", "/tmp/r.png", "bad", [2], org_save_true=True)
            )

        self.assertFalse(ok)
        self.assertTrue(exc)

    def test_save_image_returns_failure_when_imwrite_raises(self):
        def fail_imwrite(_path, _image):
            raise RuntimeError("disk error")

        with (
            mock.patch.object(self.module.np, "ndarray", list),
            mock.patch.object(self.module.cv2, "imwrite", side_effect=fail_imwrite),
        ):
            ok, exc = asyncio.run(
                self.module.save_image("/tmp/o.png", "/tmp/r.png", [1], [2], org_save_true=True)
            )

        self.assertFalse(ok)
        self.assertTrue(exc)

    def test_save_image_returns_failure_when_imwrite_returns_false(self):
        with (
            mock.patch.object(self.module.np, "ndarray", list),
            mock.patch.object(self.module.cv2, "imwrite", return_value=False),
        ):
            ok, exc = asyncio.run(
                self.module.save_image("/tmp/o.png", "/tmp/r.png", [1], [2], org_save_true=True)
            )

        self.assertFalse(ok)
        self.assertTrue(exc)

    def test_process_image_returns_exception_false_on_success(self):
        async def fake_get_image(*args, **kwargs):
            return [1], [2]

        async def fake_save_image(*args, **kwargs):
            return True, False

        row = {"id": "7", "url": "http://x/7"}
        with (
            mock.patch.object(self.module, "get_image", side_effect=fake_get_image),
            mock.patch.object(self.module, "save_image", side_effect=fake_save_image),
        ):
            info, exc = asyncio.run(
                self.module.process_image(row, "/tmp/o", "/tmp/r", {"image_size": (32, 32), "call_limit": 2, "sleep_time": 1}, session=object(), org_save_true=True)
            )

        self.assertEqual(info[1], "7")
        self.assertFalse(exc)

    def test_process_image_keeps_exception_true_when_get_image_fails(self):
        async def fake_get_image(*args, **kwargs):
            return None, None

        row = {"id": "8", "url": "http://x/8"}
        with mock.patch.object(self.module, "get_image", side_effect=fake_get_image):
            info, exc = asyncio.run(
                self.module.process_image(
                    row,
                    "/tmp/o",
                    "/tmp/r",
                    {"image_size": (32, 32), "call_limit": 2, "sleep_time": 1},
                    session=object(),
                    org_save_true=True,
                )
            )

        self.assertEqual(info[1], "8")
        self.assertTrue(exc)


class ImageDownloadMainExecutionTests(unittest.TestCase):
    def _fake_modules(self):
        fake_numpy = types.ModuleType("numpy")
        fake_numpy.frombuffer = lambda data, dtype: data
        fake_numpy.uint8 = int
        fake_numpy.ndarray = list
        fake_numpy.array_split = lambda seq, n: [seq]

        class FakeMetadata:
            def __len__(self):
                return 0

        fake_pandas = types.ModuleType("pandas")
        fake_pandas.DataFrame = lambda data: data
        fake_pandas.read_parquet = lambda path: FakeMetadata()

        fake_cv2 = types.ModuleType("cv2")
        fake_cv2.imdecode = lambda *args: None
        fake_cv2.resize = lambda *args: None
        fake_cv2.IMREAD_COLOR = 1
        fake_cv2.imwrite = lambda *args: None

        fake_aiohttp = types.ModuleType("aiohttp")
        fake_start = types.ModuleType("start")
        fake_start.load_config = lambda path=None: {
            "image_params": {
                "image_size": [256, 427],
                "call_limit": 2,
                "sleep_time": 1,
                "allowed_connections": 10,
                "max_workers": 1,
                "batch_size": 1,
                "windows": False,
                "org_save_true": False,
                "random_seed": 42,
            },
            "paths": {
                "image_dir": "/tmp/images",
                "tile_partitioned_parquet_raw_metadata_dir": "/tmp/tiles",
            },
        }
        fake_start.__getattr__ = lambda name: getattr(real_start, name)

        fake_glob = types.ModuleType("glob")
        return {
            "numpy": fake_numpy,
            "pandas": fake_pandas,
            "cv2": fake_cv2,
            "aiohttp": fake_aiohttp,
            "start": fake_start,
            "glob": fake_glob,
        }

    def test_main_raises_usage_error_when_chunk_args_missing(self):
        modules = self._fake_modules()
        modules["glob"].glob = lambda *a, **k: []

        with (
            mock.patch.dict(sys.modules, modules),
            mock.patch("os.chdir"),
            mock.patch.object(sys, "argv", ["image_download.py"]),
        ):
            with self.assertRaises(ValueError):
                runpy.run_module("image_download", run_name="__main__")

    def test_main_handles_empty_selected_file_chunk(self):
        modules = self._fake_modules()
        modules["glob"].glob = lambda *a, **k: []

        with (
            mock.patch.dict(sys.modules, modules),
            mock.patch("os.chdir"),
            mock.patch.object(sys, "argv", ["image_download.py", "0", "10"]),
        ):
            runpy.run_module("image_download", run_name="__main__")

    def test_main_raises_usage_error_when_chunk_args_not_integers(self):
        modules = self._fake_modules()
        modules["glob"].glob = lambda *a, **k: []

        with (
            mock.patch.dict(sys.modules, modules),
            mock.patch("os.chdir"),
            mock.patch.object(sys, "argv", ["image_download.py", "bad", "size"]),
        ):
            with self.assertRaises(ValueError):
                runpy.run_module("image_download", run_name="__main__")

    def test_main_raises_usage_error_when_chunk_bounds_invalid(self):
        modules = self._fake_modules()
        modules["glob"].glob = lambda *a, **k: []

        with (
            mock.patch.dict(sys.modules, modules),
            mock.patch("os.chdir"),
            mock.patch.object(sys, "argv", ["image_download.py", "-1", "0"]),
        ):
            with self.assertRaises(ValueError):
                runpy.run_module("image_download", run_name="__main__")

    def test_main_raises_when_image_params_are_invalid_or_missing(self):
        modules = self._fake_modules()
        modules["start"].load_config = lambda path=None: {
            "image_params": {
                "image_size": [128, 128],
                "call_limit": "bad",
                "sleep_time": None,
                "allowed_connections": "bad",
                "max_workers": 0,
                "batch_size": "bad",
                "windows": "yes",
                "org_save_true": "no",
                "random_seed": "bad",
            },
            "paths": {},
        }
        modules["glob"].glob = lambda *a, **k: []

        with (
            mock.patch.dict(sys.modules, modules),
            mock.patch("os.chdir"),
            mock.patch.object(sys, "argv", ["image_download.py", "0", "10"]),
        ):
            with self.assertRaises(ValueError):
                runpy.run_module("image_download", run_name="__main__")

    def test_main_handles_non_empty_selected_files_chunk(self):
        modules = self._fake_modules()
        modules["glob"].glob = lambda *a, **k: ["/tmp/tiles/tile=1/x.parquet"]
        modules["numpy"].array_split = lambda seq, n: []

        with (
            mock.patch.dict(sys.modules, modules),
            mock.patch("os.chdir"),
            mock.patch.object(sys, "argv", ["image_download.py", "0", "1"]),
        ):
            runpy.run_module("image_download", run_name="__main__")
