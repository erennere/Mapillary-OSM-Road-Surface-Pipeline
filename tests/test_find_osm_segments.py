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


class FakeNumpy(types.ModuleType):
    def __init__(self):
        super().__init__("numpy")

    @staticmethod
    def radians(values):
        return [math.radians(value) for value in values]

    @staticmethod
    def sin(value):
        return math.sin(value)

    @staticmethod
    def cos(value):
        return math.cos(value)

    @staticmethod
    def arctan2(left, right):
        return math.atan2(left, right)

    @staticmethod
    def sqrt(value):
        return math.sqrt(value)


def import_find_osm_segments_module():
    sys.modules.pop("find_osm_segments", None)

    fake_duckdb = types.ModuleType("duckdb")

    with mock.patch.dict(
        sys.modules,
        {
            "numpy": FakeNumpy(),
            "duckdb": fake_duckdb,
        },
    ):
        return importlib.import_module("find_osm_segments")


class FindOsmSegmentsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_find_osm_segments_module()

    @staticmethod
    def _wkt(longitude, latitude):
        return f"POINT ({longitude} {latitude})"

    @staticmethod
    def _expected_haversine(point1, point2, earth_radius=6371008):
        lon1, lat1 = point1
        lon2, lat2 = point2
        lat1 = math.radians(lat1)
        lon1 = math.radians(lon1)
        lat2 = math.radians(lat2)
        lon2 = math.radians(lon2)
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return earth_radius * c

    def test_haversine_returns_zero_for_identical_random_points(self):
        generator = random.Random(401)

        for _ in range(20):
            point = (
                generator.uniform(-179.0, 179.0),
                generator.uniform(-80.0, 80.0),
            )
            distance = self.module.haversine(self._wkt(*point), self._wkt(*point))
            self.assertEqual(distance, 0.0)

    def test_haversine_matches_independent_formula_for_seeded_random_pairs(self):
        generator = random.Random(402)

        for _ in range(25):
            point1 = (
                generator.uniform(-179.0, 179.0),
                generator.uniform(-80.0, 80.0),
            )
            point2 = (
                generator.uniform(-179.0, 179.0),
                generator.uniform(-80.0, 80.0),
            )

            observed = self.module.haversine(self._wkt(*point1), self._wkt(*point2))
            expected = self._expected_haversine(point1, point2)

            self.assertAlmostEqual(observed, expected, places=9)
            self.assertAlmostEqual(
                observed,
                self.module.haversine(self._wkt(*point2), self._wkt(*point1)),
                places=9,
            )

