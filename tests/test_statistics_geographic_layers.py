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


def import_statistics_module():
    sys.modules.pop("statistics_geographic_layers", None)

    fake_numpy = FakeNumpy()
    fake_pandas = types.ModuleType("pandas")
    fake_duckdb = types.ModuleType("duckdb")
    fake_mercantile = types.ModuleType("mercantile")
    fake_mercantile.bounds = lambda x, y, z: (x, y, x + 1, y + 1)
    fake_shapely = types.ModuleType("shapely")
    fake_shapely.to_wkb = lambda geometry: geometry + ("wkb",)
    fake_shapely.box = lambda *args: args

    with mock.patch.dict(
        sys.modules,
        {
            "numpy": fake_numpy,
            "pandas": fake_pandas,
            "duckdb": fake_duckdb,
            "mercantile": fake_mercantile,
            "shapely": fake_shapely,
        },
    ):
        return importlib.import_module("statistics_geographic_layers")


class FakeVector:
    def __init__(self, values):
        self.values = list(values)

    def _coerce(self, other):
        if isinstance(other, FakeVector):
            return other.values
        return [other] * len(self.values)

    def _binary(self, other, operation):
        other_values = self._coerce(other)
        return FakeVector([operation(left, right) for left, right in zip(self.values, other_values)])

    def __sub__(self, other):
        return self._binary(other, lambda left, right: left - right)

    def __rsub__(self, other):
        if isinstance(other, FakeVector):
            return other.__sub__(self)
        return FakeVector([other - value for value in self.values])

    def __add__(self, other):
        return self._binary(other, lambda left, right: left + right)

    def __mul__(self, other):
        return self._binary(other, lambda left, right: left * right)

    def __rmul__(self, other):
        return self.__mul__(other)

    def __truediv__(self, other):
        return self._binary(other, lambda left, right: left / right)

    def __pow__(self, other):
        return self._binary(other, lambda left, right: left ** right)

    def __getitem__(self, index):
        result = self.values[index]
        if isinstance(index, slice):
            return FakeVector(result)
        return result

    def __iter__(self):
        return iter(self.values)

    def __len__(self):
        return len(self.values)

    def tolist(self):
        return list(self.values)


class FakeMatrix:
    def __init__(self, rows):
        self.rows = [row if isinstance(row, FakeVector) else FakeVector(row) for row in rows]

    def __getitem__(self, index):
        return self.rows[index]


class FakeNumpy(types.ModuleType):
    def __init__(self):
        super().__init__("numpy")

    def array(self, values):
        if isinstance(values, (FakeVector, FakeMatrix)):
            return values
        if values and isinstance(values[0], (list, tuple, FakeVector)):
            return FakeMatrix(values)
        return FakeVector(values)

    def radians(self, values):
        return self._apply(values, math.radians)

    def sin(self, values):
        return self._apply(values, math.sin)

    def cos(self, values):
        return self._apply(values, math.cos)

    def sqrt(self, values):
        return self._apply(values, math.sqrt)

    def arcsin(self, values):
        return self._apply(values, math.asin)

    @staticmethod
    def sum(values):
        if isinstance(values, FakeVector):
            return sum(values.values)
        return sum(values)

    def _apply(self, values, operation):
        if isinstance(values, FakeMatrix):
            return FakeMatrix([self._apply(row, operation).values for row in values.rows])
        if isinstance(values, FakeVector):
            return FakeVector([operation(value) for value in values.values])
        return operation(values)


class StatisticsGeographicLayersTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_statistics_module()

    def test_load_statistics_runtime_config_uses_defaults_and_overrides(self):
        cfg = {
            "paths": {"stats_dir": "/tmp/stats"},
            "params": {"zoom_level": "9"},
            "statistics": {
                "geographic_layers": {
                    "osm_distance": "20",
                    "score": "0.95",
                    "urban_area_layers": ["CUSTOM_LAYER"],
                    "urban_area_cols": ["urban_id"],
                }
            },
        }

        runtime = self.module.load_statistics_runtime_config(cfg)

        self.assertEqual(runtime["osm_distance"], 20)
        self.assertEqual(runtime["pred_distance"], 10)
        self.assertEqual(runtime["score"], 0.95)
        self.assertEqual(runtime["threshold"], 0.3)
        self.assertEqual(runtime["zoom_level"], 9)
        self.assertEqual(runtime["urban_area_layers"], ["CUSTOM_LAYER"])
        self.assertEqual(runtime["urban_area_cols"], ["urban_id"])
        self.assertEqual(runtime["results_dir"], "/tmp/stats/geographic_layers")

    def test_sql_in_list_escapes_quotes_and_rejects_empty_input(self):
        self.assertEqual(
            self.module._sql_in_list(["primary", "trunk's"]),
            "('primary', 'trunk''s')",
        )

        with self.assertRaises(ValueError):
            self.module._sql_in_list([])

    def test_create_osm_general_strings_builds_expected_aliases(self):
        result = self.module.create_osm_general_strings(
            {"primary": ["primary", "primary_link"]},
            suffix="_summary",
            alias_prefix="pred_",
        )

        self.assertIn("COUNT(DISTINCT CASE WHEN osm_tags_highway IN ('primary', 'primary_link')", result)
        self.assertIn("as pred_primary_id_summary", result)
        self.assertIn("as pred_primary_length_summary", result)

    def test_create_surface_urban_rural_strings_covers_all_metric_variants(self):
        result = self.module.create_surface_urban_rural_strings(
            {"residential": ["residential"]},
            pred_col="predicted_surface",
            suffix="_tile",
            alias_prefix="agg_",
        )

        self.assertIn("agg_residential_urban_unpaved_tile", result)
        self.assertIn("agg_residential_rural_unpaved_tile", result)
        self.assertIn("agg_residential_urban_paved_tile", result)
        self.assertIn("agg_residential_rural_paved_tile", result)
        self.assertIn("THEN predicted_surface ELSE 0 END", result)

    def test_build_metric_catalog_respects_custom_shared_configuration(self):
        metrics = self.module.build_metric_catalog(
            {
                "shared": {
                    "highways": ["primary"],
                    "areas": ["urban", "rural"],
                    "road_types": ["paved"],
                    "road_classes": {"primary": ["primary"]},
                }
            }
        )

        self.assertEqual(metrics["highways"], ["primary"])
        self.assertEqual(metrics["length_tags"], ["primary_length", "primary_length_urban", "primary_length_rural"])
        self.assertEqual(metrics["pred_id_tags"], ["pred_primary_id", "pred_primary_id_urban", "pred_primary_id_rural"])
        self.assertEqual(metrics["paved_tags"], ["primary_urban_paved", "primary_rural_paved", "primary_paved"])
        self.assertEqual(metrics["osm_total_cols"], ["b.osm_primary_length", "a.osm_primary_length_urban", "a.osm_primary_length_rural", "b.osm_primary_id", "a.osm_primary_id_urban", "a.osm_primary_id_rural", "b.number_of_osm_ids", "a.number_of_osm_ids_urban", "a.number_of_osm_ids_rural"])

    def test_correct_z14_tiles_osm_parses_triplets(self):
        parsed = self.module.correct_z14_tiles_osm([["1 2 14"], ["30 40 14"]])

        self.assertEqual(parsed, [[1, 2, 14], [30, 40, 14]])

    def test_create_paved_and_ratio_helpers_preserve_seeded_random_order(self):
        generator = random.Random(601)
        highways = [f"h{generator.randint(10, 99)}", f"h{generator.randint(100, 199)}"]
        areas = [f"_{generator.choice(['urban', 'rural'])}", ""]
        road_types = [generator.choice(["paved", "unpaved"]), generator.choice(["paved", "unpaved"])]
        columns = [f"col_{generator.randint(1, 50)}" for _ in range(3)]
        factor = generator.randint(2, 9)

        paved_tags = self.module.create_paved_tags(highways, areas, road_types)
        agg_string = self.module.create_agg_highway_road_type_strings(highways, areas, road_types, aggregation_type="AVG")
        ratio_string = self.module.agg_ratio_strings(columns, factor=factor, agg_type="MAX")
        paired_ratio_string = self.module.create_ratio_strings(columns[:2], columns[1:], factor=factor)
        paved_ratio_string = self.module.create_paved_ratio_strings(highways, areas, aggregation_type="COUNT")
        prefixed = self.module.add_prefix(columns, "x.")
        aliased = self.module.add_prefix_and_suffix(columns, "x.", "alias_")

        self.assertEqual(
            paved_tags,
            [f"{highway}{area}_{road_type}" for highway in highways for area in areas for road_type in road_types],
        )
        self.assertIn(f"AVG({highways[0]}_{areas[0]}_{road_types[0]}) as {highways[0]}_{areas[0]}_{road_types[0]}", agg_string)
        self.assertIn(f"MAX({columns[0]})/{factor} as {columns[0]}", ratio_string)
        self.assertIn(
            f"SUM({columns[0]})/NULLIF(SUM({columns[1]})*{factor}, 0) as {columns[0]}_ratio",
            paired_ratio_string,
        )
        self.assertIn(
            f"COUNT({highways[0]}{areas[0]}_paved)/NULLIF(COUNT({highways[0]}{areas[0]}_paved) + COUNT({highways[0]}{areas[0]}_unpaved), 0) as {highways[0]}{areas[0]}_paved_ratio",
            paved_ratio_string,
        )
        self.assertEqual(prefixed, ", \n".join(f"x.{column}" for column in columns))
        self.assertEqual(aliased, ", \n".join(f"x.{column} as alias_{column}" for column in columns))

    def test_create_tile_uses_seeded_random_tile_bounds(self):
        generator = random.Random(602)
        x = generator.randint(1, 20)
        y = generator.randint(1, 20)
        z = generator.randint(1, 14)

        result = self.module.create_tile([x, y, z])

        self.assertEqual(result, (x, y, x + 1, y + 1, "wkb"))

    def test_create_surface_and_osm_urban_rural_strings_include_seeded_random_aliases(self):
        generator = random.Random(603)
        highway = f"road_{generator.randint(10, 99)}"
        tag = f"tag_{generator.randint(100, 999)}"
        suffix = f"_s{generator.randint(1, 9)}"
        alias_prefix = f"alias_{generator.randint(1, 9)}_"

        surface_string = self.module.create_surface_general_strings(
            {highway: [tag]},
            pred_col="score_col",
            suffix=suffix,
            alias_prefix=alias_prefix,
        )
        osm_string = self.module.create_osm_urban_rural_strings(
            {highway: [tag]},
            suffix=suffix,
            alias_prefix=alias_prefix,
        )

        self.assertIn(f"as {alias_prefix}{highway}_unpaved{suffix}", surface_string)
        self.assertIn(f"as {alias_prefix}{highway}_paved{suffix}", surface_string)
        self.assertIn(f"as {alias_prefix}{highway}_id_urban{suffix}", osm_string)
        self.assertIn(f"as {alias_prefix}{highway}_length_rural{suffix}", osm_string)

    def test_haversine_matches_independent_formula_for_seeded_random_points(self):
        generator = random.Random(604)

        for _ in range(20):
            point1 = (
                generator.uniform(-179.0, 179.0),
                generator.uniform(-80.0, 80.0),
            )
            point2 = (
                generator.uniform(-179.0, 179.0),
                generator.uniform(-80.0, 80.0),
            )

            observed = self.module.haversine(point1, point2)

            lat1 = math.radians(point1[1])
            lon1 = math.radians(point1[0])
            lat2 = math.radians(point2[1])
            lon2 = math.radians(point2[0])
            delta_lat = lat2 - lat1
            delta_long = lon2 - lon1
            a = math.sin(delta_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(delta_long / 2) ** 2
            expected = 6371008 * (2 * math.asin(math.sqrt(a)))

            self.assertAlmostEqual(observed, expected, places=9)

    def test_calculate_length_sums_seeded_random_segment_distances(self):
        generator = random.Random(605)
        longs = [generator.uniform(-20, 20) for _ in range(5)]
        lats = [generator.uniform(-20, 20) for _ in range(5)]

        observed = self.module.calculate_length(longs, lats)

        expected = 0.0
        for index in range(len(longs) - 1):
            lon1, lat1 = longs[index], lats[index]
            lon2, lat2 = longs[index + 1], lats[index + 1]
            lat1 = math.radians(lat1)
            lon1 = math.radians(lon1)
            lat2 = math.radians(lat2)
            lon2 = math.radians(lon2)
            delta_lat = lat2 - lat1
            delta_long = lon2 - lon1
            a = math.sin(delta_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(delta_long / 2) ** 2
            expected += 6371008 * (2 * math.asin(math.sqrt(a)))

        self.assertEqual(observed, round(expected, 3))
