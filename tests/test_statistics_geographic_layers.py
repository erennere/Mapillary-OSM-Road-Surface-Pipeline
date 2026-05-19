import importlib
import os
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

    def test_load_statistics_runtime_config_uses_required_values(self):
        cfg = {
            "paths": {
                "stats_dir": "/tmp/stats",
                "osm_partitioned_dir": "/tmp/osm_partitioned",
                "final_filtered_dir": "/tmp/final_filtered",
            },
            "params": {"seed": "17", "zoom_level": "9"},
            "statistics": {
                "geographic_layers": {
                    "osm_distance": "20",
                    "pred_distance": "12",
                    "sigma": "1.2",
                    "score": "0.95",
                    "threshold": "0.25",
                    "max_workers": 3,
                    "data_input_pattern": "data_*.parquet",
                    "urban_area_layers": ["CUSTOM_LAYER"],
                    "urban_area_cols": ["urban_id"],
                }
            },
        }

        runtime = self.module.load_statistics_runtime_config(cfg)

        self.assertEqual(runtime["osm_distance"], 20)
        self.assertEqual(runtime["pred_distance"], 12)
        self.assertEqual(runtime["sigma"], 1.2)
        self.assertEqual(runtime["score"], 0.95)
        self.assertEqual(runtime["threshold"], 0.25)
        self.assertEqual(runtime["max_workers"], 3)
        self.assertEqual(runtime["seed"], 17)
        self.assertEqual(runtime["zoom_level"], 9)
        self.assertEqual(runtime["urban_area_layers"], ["CUSTOM_LAYER"])
        self.assertEqual(runtime["urban_area_cols"], ["urban_id"])
        self.assertEqual(runtime["osm_partitioned_dir"], os.path.abspath("/tmp/osm_partitioned"))
        self.assertEqual(runtime["final_filtered_dir"], os.path.abspath("/tmp/final_filtered"))
        expected_suffix = os.path.normpath(os.path.join("/tmp/stats", "geographic_layers"))
        self.assertTrue(os.path.normpath(runtime["results_dir"]).endswith(expected_suffix))

    def test_load_statistics_runtime_config_raises_when_max_workers_is_zero(self):
        cfg = {
            "paths": {
                "stats_dir": "/tmp/stats",
                "osm_partitioned_dir": "/tmp/osm_partitioned",
                "final_filtered_dir": "/tmp/final_filtered",
            },
            "params": {"seed": "17", "zoom_level": "8"},
            "statistics": {
                "geographic_layers": {
                    "osm_distance": 15,
                    "pred_distance": 10,
                    "sigma": 1.0,
                    "score": 0.8,
                    "threshold": 0.3,
                    "max_workers": 0,
                    "data_input_pattern": "data_*.parquet",
                    "urban_area_layers": ["GHSL", "AFRICAPOLIS"],
                    "urban_area_cols": ["ID_HDC_G0", "agglosID"],
                }
            },
        }

        with self.assertRaises(ValueError):
            self.module.load_statistics_runtime_config(cfg)

    def test_load_statistics_runtime_config_raises_on_invalid_numeric_values(self):
        cfg = {
            "paths": {
                "stats_dir": "/tmp/stats",
                "osm_partitioned_dir": "/tmp/osm_partitioned",
                "final_filtered_dir": "/tmp/final_filtered",
            },
            "params": {"seed": "17", "zoom_level": "bad"},
            "statistics": {
                "geographic_layers": {
                    "osm_distance": "x",
                    "pred_distance": None,
                    "sigma": "nan-not-number",
                    "score": "oops",
                    "threshold": "invalid",
                    "max_workers": "not-int",
                    "data_input_pattern": "data_*.parquet",
                    "urban_area_layers": ["GHSL", "AFRICAPOLIS"],
                    "urban_area_cols": ["ID_HDC_G0", "agglosID"],
                }
            },
        }

        with self.assertRaises(ValueError):
            self.module.load_statistics_runtime_config(cfg)

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

    def test_urban_query_embeds_seeded_random_parameters_and_aliases(self):
        generator = random.Random(606)
        col = f"layer_{generator.randint(10, 99)}"
        sigma = round(generator.uniform(0.2, 1.4), 3)
        score = round(generator.uniform(0.5, 0.99), 3)
        threshold = round(generator.uniform(0.1, 0.4), 3)
        osm_distance = generator.randint(5, 25)
        pred_distance = generator.randint(5, 20)
        output_filepath = f"/tmp/urban_{generator.randint(100, 999)}.parquet"

        with mock.patch.multiple(
            self.module,
            road_classes={"sample": ["tag_a", "tag_b"]},
            paved_tags=["sample_paved"],
            id_tags=["sample_id"],
            length_tags=["sample_length"],
        ):
            query = self.module.urban_query(
                col,
                sigma,
                score,
                threshold,
                osm_distance,
                pred_distance,
                output_filepath,
            )

        self.assertIn(f"TO '{output_filepath}'", query)
        self.assertIn(f"{col}, ANY_VALUE(osm_id) as osm_id", query)
        self.assertIn(f"zs_pred_score < {sigma}", query)
        self.assertIn(f"pred_score >= {score}", query)
        self.assertIn(f"AND distance_meter < {pred_distance}", query)
        self.assertIn(f"WHERE distance_meter < {osm_distance} and osm_id IS NOT NULL", query)
        self.assertIn(f"LIST(DISTINCT CASE WHEN distance_meter <= {osm_distance} THEN osm_id END) AS osm_ids", query)
        self.assertIn(f"LEFT JOIN pred_stats b ON CAST(a.{col} as INT) = CAST(b.{col} as INT)", query)
        self.assertIn("osm_tags_highway IN ('tag_a', 'tag_b')", query)
        self.assertIn("b.sample_paved", query)
        self.assertIn("b.sample_id as pred_sample_id", query)
        self.assertIn("c.sample_length as osm_sample_length", query)
        self.assertIn("d.sample_length", query)

    def test_process_file_executes_seeded_random_query_pipeline_and_cleans_up(self):
        generator = random.Random(607)

        class FakeResult:
            def __init__(self, payload):
                self.payload = payload

            def df(self):
                return self.payload

        class RecordingConnection:
            def __init__(self):
                self.execute_calls = []
                self.create_function_calls = []
                self.closed = False

            def execute(self, query):
                self.execute_calls.append(query)
                return FakeResult({"query": query})

            def create_function(self, *args):
                self.create_function_calls.append(args)

            def close(self):
                self.closed = True

        connection = RecordingConnection()
        tile = generator.randint(10, 99)
        sigma = round(generator.uniform(0.2, 1.4), 3)
        score = round(generator.uniform(0.5, 0.99), 3)
        threshold = round(generator.uniform(0.1, 0.4), 3)
        osm_distance = generator.randint(5, 25)
        pred_distance = generator.randint(5, 20)
        filedir = f"/tmp/inputs/tile={tile}"
        results_dir = f"/tmp/results_{generator.randint(100, 999)}"
        osm_filedir = f"/tmp/osm_{generator.randint(100, 999)}"
        data_input_filepath = f"/tmp/data_{generator.randint(100, 999)}.parquet"
        cols = [f"col_{generator.randint(1, 50)}", f"col_{generator.randint(51, 99)}"]
        urban_areas = [f"urban_{generator.randint(1, 9)}", f"urban_{generator.randint(10, 19)}"]
        temp_suffix = generator.randint(10_000, 99_999)

        def fake_exists(path):
            return path == f"temp_{temp_suffix}.db"

        with (
            mock.patch.object(self.module.duckdb, "connect", return_value=connection, create=True) as connect_mock,
            mock.patch.object(self.module.random, "randint", return_value=temp_suffix),
            mock.patch.object(self.module.os, "chdir") as chdir_mock,
            mock.patch.object(self.module.os, "makedirs") as makedirs_mock,
            mock.patch.object(self.module.os.path, "exists", side_effect=fake_exists),
            mock.patch.object(self.module.os, "remove") as remove_mock,
            mock.patch.object(
                self.module,
                "urban_query",
                side_effect=[
                    f"URBAN_QUERY::{cols[0]}",
                    f"URBAN_QUERY::{cols[1]}",
                ],
            ) as urban_query_mock,
        ):
            self.module.process_file(
                filedir,
                sigma,
                score,
                threshold,
                results_dir,
                osm_distance,
                pred_distance,
                osm_filedir,
                data_input_filepath,
                cols,
                urban_areas,
            )

        connect_mock.assert_called_once_with(f"temp_{temp_suffix}.db")
        chdir_mock.assert_called_once_with(filedir)
        self.assertEqual(connection.execute_calls[0], "INSTALL spatial; LOAD spatial;")
        self.assertEqual(
            [call[0] for call in connection.create_function_calls],
            ["create_tile", "calculate_length", "correct_z14_tiles_osm"],
        )
        self.assertIn(data_input_filepath, connection.execute_calls[1])
        self.assertIn(f"{osm_filedir}/tile={tile}/*.parquet", connection.execute_calls[3])
        self.assertIn(f"WHERE {self.module.zoom_level}_tiles = {tile}", connection.execute_calls[3])
        self.assertIn(f"{results_dir}/{self.module.zoom_level}_tiles/{self.module.zoom_level}_tiles_with_stats_{tile}.parquet", connection.execute_calls[5])
        self.assertIn(f"{results_dir}/world/world_with_stats_{tile}.parquet", connection.execute_calls[9])
        self.assertEqual(connection.execute_calls[-2:], [f"URBAN_QUERY::{cols[0]}", f"URBAN_QUERY::{cols[1]}"])
        self.assertEqual(urban_query_mock.call_count, 2)
        self.assertTrue(connection.closed)
        remove_mock.assert_called_once_with(f"temp_{temp_suffix}.db")
        self.assertGreaterEqual(makedirs_mock.call_count, 8)

    def test_process_file_closes_and_removes_temp_db_when_query_execution_fails(self):
        generator = random.Random(608)

        class FailingConnection:
            def __init__(self):
                self.execute_calls = []
                self.closed = False

            def execute(self, query):
                self.execute_calls.append(query)
                if len(self.execute_calls) == 2:
                    raise RuntimeError("boom")
                return self

            def df(self):
                return {"ok": True}

            def create_function(self, *args):
                pass

            def close(self):
                self.closed = True

        connection = FailingConnection()
        tile = generator.randint(10, 99)
        temp_suffix = generator.randint(10_000, 99_999)

        with (
            mock.patch.object(self.module.duckdb, "connect", return_value=connection, create=True),
            mock.patch.object(self.module.random, "randint", return_value=temp_suffix),
            mock.patch.object(self.module.os, "chdir"),
            mock.patch.object(self.module.os, "makedirs"),
            mock.patch.object(self.module.os.path, "exists", side_effect=lambda path: path == f"temp_{temp_suffix}.db"),
            mock.patch.object(self.module.os, "remove") as remove_mock,
        ):
            self.module.process_file(
                f"/tmp/inputs/tile={tile}",
                round(generator.uniform(0.2, 1.4), 3),
                round(generator.uniform(0.5, 0.99), 3),
                round(generator.uniform(0.1, 0.4), 3),
                f"/tmp/results_{generator.randint(100, 999)}",
                generator.randint(5, 25),
                generator.randint(5, 20),
                f"/tmp/osm_{generator.randint(100, 999)}",
                f"/tmp/data_{generator.randint(100, 999)}.parquet",
                [f"col_{generator.randint(1, 50)}"],
                [f"urban_{generator.randint(1, 9)}"],
            )

        self.assertEqual(len(connection.execute_calls), 2)
        self.assertTrue(connection.closed)
        remove_mock.assert_called_once_with(f"temp_{temp_suffix}.db")

    def test_main_runs_parallel_processing_without_cli_sharding_args(self):
        cfg = {
            "params": {"seed": 42, "zoom_level": 8},
            "paths": {
                "osm_partitioned_dir": "/tmp/osm_partitioned",
                "final_filtered_dir": "/tmp/final_filtered",
                "stats_dir": "/tmp/stats",
            },
            "statistics": {
                "geographic_layers": {
                    "urban_area_cols": ["ID_HDC_G0", "agglosID"],
                    "urban_area_layers": ["GHSL", "AFRICAPOLIS"],
                    "max_workers": 4,
                    "data_input_pattern": "data_*.parquet",
                }
            },
        }

        runtime_cfg = {
            "seed": 42,
            "urban_area_cols": ["ID_HDC_G0", "agglosID"],
            "urban_area_layers": ["GHSL", "AFRICAPOLIS"],
            "osm_distance": 15,
            "pred_distance": 10,
            "sigma": 1.0,
            "score": 0.8,
            "threshold": 0.3,
            "max_workers": 4,
            "osm_partitioned_dir": "/tmp/osm_partitioned",
            "final_filtered_dir": "/tmp/final_filtered",
            "results_dir": "/tmp/stats/geographic_layers",
            "zoom_level": 8,
            "data_input_pattern": "data_*.parquet",
        }

        with (
            mock.patch.object(self.module, "load_config", return_value=runtime_cfg),
            mock.patch.object(self.module, "load_statistics_runtime_config", return_value=runtime_cfg),
            mock.patch.object(self.module.os, "chdir"),
            mock.patch.object(self.module.os.path, "abspath", side_effect=lambda p: p),
            mock.patch.object(self.module.os, "listdir", return_value=["tile=1", "tile=2"]),
            mock.patch.object(self.module.os.path, "isdir", return_value=True),
            mock.patch.object(self.module.sys, "argv", ["statistics_geographic_layers.py"]),
            mock.patch.object(self.module, "run_parallel_processing") as run_mock,
        ):
            self.module.main()

        run_mock.assert_called_once()

    def test_main_returns_when_filtered_input_directory_missing(self):
        cfg = {
            "params": {"seed": 42, "zoom_level": 8},
            "paths": {
                "osm_partitioned_dir": "/tmp/osm_partitioned",
                "final_filtered_dir": "/tmp/final_filtered",
                "stats_dir": "/tmp/stats",
            },
            "statistics": {
                "geographic_layers": {
                    "urban_area_cols": ["ID_HDC_G0", "agglosID"],
                    "urban_area_layers": ["GHSL", "AFRICAPOLIS"],
                    "max_workers": 4,
                    "data_input_pattern": "data_*.parquet",
                }
            },
        }

        runtime_cfg = {
            "seed": 42,
            "urban_area_cols": ["ID_HDC_G0", "agglosID"],
            "urban_area_layers": ["GHSL", "AFRICAPOLIS"],
            "osm_distance": 15,
            "pred_distance": 10,
            "sigma": 1.0,
            "score": 0.8,
            "threshold": 0.3,
            "max_workers": 4,
            "osm_partitioned_dir": "/tmp/osm_partitioned",
            "final_filtered_dir": "/tmp/final_filtered",
            "results_dir": "/tmp/stats/geographic_layers",
            "zoom_level": 8,
            "data_input_pattern": "data_*.parquet",
        }

        with (
            mock.patch.object(self.module, "load_config", return_value=runtime_cfg),
            mock.patch.object(self.module, "load_statistics_runtime_config", return_value=runtime_cfg),
            mock.patch.object(self.module.os, "chdir"),
            mock.patch.object(self.module.os.path, "abspath", side_effect=lambda p: p),
            mock.patch.object(self.module.os.path, "isdir", return_value=False),
            mock.patch.object(self.module.os, "listdir") as listdir_mock,
            mock.patch.object(self.module.sys, "argv", ["statistics_geographic_layers.py"]),
            mock.patch.object(self.module, "run_parallel_processing") as run_mock,
        ):
            self.module.main()

        run_mock.assert_not_called()
        listdir_mock.assert_not_called()

    def test_main_handles_invalid_seed_value(self):
        with (
            mock.patch.object(self.module, "load_config", side_effect=ValueError("bad seed")),
            mock.patch.object(self.module.os, "chdir"),
            mock.patch.object(self.module.os.path, "abspath", side_effect=lambda p: p),
            mock.patch.object(self.module.os, "listdir", return_value=["tile=1"]),
            mock.patch.object(self.module.os.path, "isdir", return_value=True),
            mock.patch.object(self.module.sys, "argv", ["statistics_geographic_layers.py"]),
            mock.patch.object(self.module, "run_parallel_processing") as run_mock,
        ):
            with self.assertRaises(ValueError):
                self.module.main()

        run_mock.assert_not_called()

    def test_main_runs_unsharded_when_instances_non_positive(self):
        cfg = {
            "params": {"seed": 42, "zoom_level": 8},
            "paths": {
                "osm_partitioned_dir": "/tmp/osm_partitioned",
                "final_filtered_dir": "/tmp/final_filtered",
                "stats_dir": "/tmp/stats",
            },
            "statistics": {
                "geographic_layers": {
                    "urban_area_cols": ["ID_HDC_G0", "agglosID"],
                    "urban_area_layers": ["GHSL", "AFRICAPOLIS"],
                    "max_workers": 4,
                    "data_input_pattern": "data_*.parquet",
                }
            },
        }

        runtime_cfg = {
            "seed": 42,
            "urban_area_cols": ["ID_HDC_G0", "agglosID"],
            "urban_area_layers": ["GHSL", "AFRICAPOLIS"],
            "osm_distance": 15,
            "pred_distance": 10,
            "sigma": 1.0,
            "score": 0.8,
            "threshold": 0.3,
            "max_workers": 4,
            "osm_partitioned_dir": "/tmp/osm_partitioned",
            "final_filtered_dir": "/tmp/final_filtered",
            "results_dir": "/tmp/stats/geographic_layers",
            "zoom_level": 8,
            "data_input_pattern": "data_*.parquet",
        }

        with (
            mock.patch.object(self.module, "load_config", return_value=runtime_cfg),
            mock.patch.object(self.module, "load_statistics_runtime_config", return_value=runtime_cfg),
            mock.patch.object(self.module.os, "chdir"),
            mock.patch.object(self.module.os.path, "abspath", side_effect=lambda p: p),
            mock.patch.object(self.module.os, "listdir", return_value=["tile=1", "tile=2"]),
            mock.patch.object(self.module.os.path, "isdir", return_value=True),
            mock.patch.object(self.module.sys, "argv", ["statistics_geographic_layers.py", "0", "0"]),
            mock.patch.object(self.module, "run_parallel_processing") as run_mock,
        ):
            self.module.main()

        run_mock.assert_called_once()
        processed_dirs = run_mock.call_args[0][0]
        self.assertEqual(len(processed_dirs), 2)
