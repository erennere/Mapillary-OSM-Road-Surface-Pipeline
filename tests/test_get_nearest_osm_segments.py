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


class FakeMask:
    def __init__(self, values):
        self.values = list(values)

    def __and__(self, other):
        return FakeMask([left and right for left, right in zip(self.values, other.values)])

    def tolist(self):
        return list(self.values)


class FakeArray:
    def __init__(self, values):
        self.values = list(values)

    def __lt__(self, other):
        return FakeMask([value < other for value in self.values])

    def __gt__(self, other):
        return FakeMask([value > other for value in self.values])


def import_get_nearest_module():
    sys.modules.pop("get_nearest_osm_segments", None)

    fake_numpy = types.ModuleType("numpy")
    fake_numpy.array = lambda values: FakeArray(values)

    fake_duckdb = types.ModuleType("duckdb")

    with mock.patch.dict(
        sys.modules,
        {
            "numpy": fake_numpy,
            "duckdb": fake_duckdb,
        },
    ):
        return importlib.import_module("get_nearest_osm_segments")


class GetNearestOsmSegmentsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_get_nearest_module()

    def test_create_mask_uses_exclusive_thresholds(self):
        mask = self.module.create_mask([0, 5, 10, 15, 20], threshold_up=20, threshold_down=5)

        self.assertEqual(mask, [False, False, True, True, False])

    def test_create_mask_defaults_to_zero_lower_bound(self):
        mask = self.module.create_mask([0, 1, 9, 10], threshold_up=10)

        self.assertEqual(mask, [False, True, True, False])

    def test_extract_first_wraps_only_the_first_value(self):
        self.assertEqual(self.module.extract_first(["first", "second", "third"]), ["first"])

    def test_create_mask_matches_python_reference_for_seeded_random_cases(self):
        generator = random.Random(301)

        for _ in range(20):
            threshold_down = generator.randint(-10, 10)
            threshold_up = threshold_down + generator.randint(1, 20)
            values = [generator.randint(-20, 30) for _ in range(generator.randint(1, 8))]

            observed = self.module.create_mask(
                values,
                threshold_up=threshold_up,
                threshold_down=threshold_down,
            )
            expected = [threshold_down < value < threshold_up for value in values]

            self.assertEqual(observed, expected)

    def test_create_mask_returns_empty_list_for_seeded_empty_input(self):
        generator = random.Random(302)

        self.assertEqual(
            self.module.create_mask([], threshold_up=generator.randint(1, 20)),
            [],
        )
