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


def import_statistics_aggregation_module():
    """Import statistics_aggregation with all heavy dependencies mocked."""
    for mod in ["statistics_aggregation", "statistics_geographic_layers"]:
        sys.modules.pop(mod, None)

    fake_duckdb = types.ModuleType("duckdb")
    fake_numpy = types.ModuleType("numpy")
    fake_pandas = types.ModuleType("pandas")
    fake_pandas.DataFrame = None  # placeholder
    fake_pandas.Series = None     # placeholder
    fake_mercantile = types.ModuleType("mercantile")
    fake_mercantile.bounds = lambda x, y, z: (x, y, x + 1, y + 1)
    fake_shapely = types.ModuleType("shapely")
    fake_shapely.to_wkb = lambda geometry: geometry + ("wkb",)
    fake_shapely.box = lambda *args: args

    fake_start = types.ModuleType("start")
    fake_start.load_config = lambda path=None: {}

    # Provide a fake statistics_geographic_layers with all symbols that
    # statistics_aggregation imports at module level, including zoom_level in
    # the build_metric_catalog return so that the module-level
    # `zoom_level = _METRICS['zoom_level']` assignment succeeds.
    _default_highways = ["motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential"]
    _default_areas = ["urban", "rural"]
    _default_road_types = ["paved", "unpaved"]
    _default_road_classes = {
        "motorway": ["motorway", "motorway_link"],
        "primary": ["primary", "primary_link"],
    }
    _areas_2 = ["_urban", "_rural", ""]
    _paved_tags = [f"{h}{a}_{rt}" for h in _default_highways for a in _areas_2 for rt in _default_road_types]

    def fake_build_metric_catalog(stats_cfg=None):
        return {
            "highways": _default_highways,
            "areas": _default_areas,
            "road_types": _default_road_types,
            "length_tags": [f"{h}_length" for h in _default_highways],
            "pred_length_tags": [f"pred_{h}_length" for h in _default_highways],
            "osm_length_tags": [f"osm_{h}_length" for h in _default_highways],
            "id_tags": [f"{h}_id" for h in _default_highways],
            "pred_id_tags": [f"pred_{h}_id" for h in _default_highways],
            "osm_id_tags": [f"osm_{h}_id" for h in _default_highways],
            "areas_2": _areas_2,
            "rest": ["count_ID_HDC_G0", "count_agglosID"],
            "n_osms": ["number_of_osm_ids"],
            "rest_length_road": ["length_unpaved", "length_paved"],
            "rest_country_onwards": ["number_of_sequences"],
            "road_classes": _default_road_classes,
            "osm_total_cols": [f"b.osm_{h}_length" for h in _default_highways],
            "osm_total_cols_string": ", ".join(f"b.osm_{h}_length" for h in _default_highways),
            "all_cols": [],
            "paved_tags": _paved_tags,
            "paved_strings": ", ".join(_paved_tags),
            "zoom_level": 8,
        }

    fake_sgl = types.ModuleType("statistics_geographic_layers")
    fake_sgl.build_metric_catalog = fake_build_metric_catalog
    fake_sgl.create_agg_highway_road_type_strings = lambda *a, **k: ""
    fake_sgl.agg_ratio_strings = lambda *a, **k: ""
    fake_sgl.create_ratio_strings = lambda *a, **k: ""
    fake_sgl.create_paved_ratio_strings = lambda *a, **k: ""
    fake_sgl.create_osm_general_strings = lambda *a, **k: ""
    fake_sgl.create_osm_urban_rural_strings = lambda *a, **k: ""
    fake_sgl.create_tile = lambda tiles_info: tiles_info

    with mock.patch.dict(
        sys.modules,
        {
            "duckdb": fake_duckdb,
            "numpy": fake_numpy,
            "pandas": fake_pandas,
            "mercantile": fake_mercantile,
            "shapely": fake_shapely,
            "start": fake_start,
            "statistics_geographic_layers": fake_sgl,
        },
    ):
        return importlib.import_module("statistics_aggregation")


class BuildRuntimeConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_statistics_aggregation_module()

    def test_build_runtime_config_extracts_all_keys_from_config(self):
        generator = random.Random(1101)
        stats_dir = f"/tmp/stats_{generator.randint(100, 999)}"
        osm_dir = f"/tmp/osm_{generator.randint(100, 999)}"
        processed_dir = f"/tmp/proc_{generator.randint(100, 999)}"
        continents_file = f"continents_{generator.randint(100, 999)}.parquet"
        country_file = f"countries_{generator.randint(100, 999)}.parquet"
        ghsl_file = f"ghsl_{generator.randint(100, 999)}.gpkg"
        africapolis_file = f"africapolis_{generator.randint(100, 999)}.shp"
        overture_url = f"s3://bucket_{generator.randint(100, 999)}"
        max_workers = generator.randint(2, 16)
        n_cpus = generator.randint(4, 64)
        mem_limit = generator.randint(100, 2000)

        cfg = {
            "paths": {
                "stats_dir": stats_dir,
                "osm_saving_dir": osm_dir,
                "processed_dir": processed_dir,
                "continents_dir": "/tmp/continents",
            },
            "filenames": {
                "continents_filename": continents_file,
                "country_filename": country_file,
                "ghsl_filename": ghsl_file,
                "africapolis_filename": africapolis_file,
                "overture_url": overture_url,
            },
            "statistics": {
                "aggregation": {
                    "max_workers": max_workers,
                    "number_of_cpus": n_cpus,
                    "memory_limit_gb": mem_limit,
                }
            },
            "geographic_layers": {
                "urban_area_layers": ["GHS_STAT_UCDB2015MT_GLOBE_R2019A", "AFRICAPOLIS2020"]
            },
        }

        result = self.module.build_runtime_config(cfg)

        self.assertIn("results_dir", result)
        self.assertIn(stats_dir, result["results_dir"])
        self.assertEqual(result["max_workers"], max_workers)
        self.assertEqual(result["memory_limit_gb"], mem_limit)
        self.assertIn(continents_file, result["continent_layer"])
        self.assertIn(country_file, result["country_layer"])
        self.assertIn(ghsl_file.replace(".gpkg", ".parquet"), result["urban_layers"][0])
        self.assertIn(africapolis_file.replace(".shp", ".parquet"), result["urban_layers"][1])

    def test_build_runtime_config_calculates_sub_threads_as_cpus_divided_by_workers(self):
        generator = random.Random(1102)
        max_workers = generator.randint(2, 8)
        n_cpus = max_workers * generator.randint(2, 8)

        cfg = {
            "paths": {
                "stats_dir": "/tmp/s",
                "osm_saving_dir": "/tmp/o",
                "processed_dir": "/tmp/p",
                "continents_dir": "/tmp/c",
            },
            "filenames": {
                "continents_filename": "c.parquet",
                "country_filename": "co.parquet",
                "ghsl_filename": "g.gpkg",
                "africapolis_filename": "a.shp",
                "overture_url": "s3://bucket",
            },
            "statistics": {
                "aggregation": {
                    "max_workers": max_workers,
                    "number_of_cpus": n_cpus,
                }
            },
            "geographic_layers": {
                "urban_area_layers": []
            },
        }

        result = self.module.build_runtime_config(cfg)

        self.assertEqual(result["sub_threads"], n_cpus // max_workers)


class BuildQueriesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_statistics_aggregation_module()

    def _make_filepaths(self, generator, prefix):
        return {
            level: f"/tmp/{prefix}_{level}_{generator.randint(100, 999)}.parquet"
            for level in ["z14", "z8", "country", "continent", "world"]
        }

    def test_build_queries_returns_five_queries(self):
        generator = random.Random(1103)
        input_fps = self._make_filepaths(generator, "in")
        output_fps = self._make_filepaths(generator, "out")
        osm_fp = f"/tmp/osm_{generator.randint(100, 999)}.parquet"
        country_fp = f"/tmp/country_{generator.randint(100, 999)}.parquet"
        continent_fp = f"/tmp/continent_{generator.randint(100, 999)}.parquet"

        result = self.module.build_queries(input_fps, output_fps, osm_fp, country_fp, continent_fp)

        self.assertEqual(len(result), 5)
        for query in result:
            self.assertIsInstance(query, str)
            self.assertGreater(len(query), 0)

    def test_build_queries_each_query_contains_its_input_and_output_paths(self):
        generator = random.Random(1104)
        input_fps = self._make_filepaths(generator, "inp")
        output_fps = self._make_filepaths(generator, "outp")
        osm_fp = f"/tmp/osm_{generator.randint(100, 999)}.parquet"
        country_fp = f"/tmp/country_{generator.randint(100, 999)}.parquet"
        continent_fp = f"/tmp/continent_{generator.randint(100, 999)}.parquet"

        q_z14, q_z8, q_country, q_continent, q_world = self.module.build_queries(
            input_fps, output_fps, osm_fp, country_fp, continent_fp
        )

        self.assertIn(input_fps["z14"], q_z14)
        self.assertIn(output_fps["z14"], q_z14)
        self.assertIn(input_fps["z8"], q_z8)
        self.assertIn(output_fps["z8"], q_z8)
        self.assertIn(input_fps["country"], q_country)
        self.assertIn(output_fps["country"], q_country)
        self.assertIn(input_fps["continent"], q_continent)
        self.assertIn(output_fps["continent"], q_continent)
        self.assertIn(input_fps["world"], q_world)
        self.assertIn(output_fps["world"], q_world)

    def test_build_queries_each_query_is_a_copy_statement(self):
        generator = random.Random(1105)
        input_fps = self._make_filepaths(generator, "i")
        output_fps = self._make_filepaths(generator, "o")

        queries = self.module.build_queries(
            input_fps,
            output_fps,
            f"/tmp/osm_{generator.randint(100, 999)}.parquet",
            f"/tmp/c_{generator.randint(100, 999)}.parquet",
            f"/tmp/cont_{generator.randint(100, 999)}.parquet",
        )

        for query in queries:
            self.assertIn("COPY", query.upper())
            self.assertIn("FORMAT", query.upper())
            self.assertIn("parquet", query.lower())

    def test_build_queries_country_and_continent_queries_reference_osm_filepath(self):
        generator = random.Random(1106)
        input_fps = self._make_filepaths(generator, "inp2")
        output_fps = self._make_filepaths(generator, "outp2")
        osm_fp = f"/tmp/osm_special_{generator.randint(100, 999)}.parquet"
        country_fp = f"/tmp/c_{generator.randint(100, 999)}.parquet"
        continent_fp = f"/tmp/cont_{generator.randint(100, 999)}.parquet"

        _, _, q_country, q_continent, q_world = self.module.build_queries(
            input_fps, output_fps, osm_fp, country_fp, continent_fp
        )

        self.assertIn(osm_fp, q_country)
        self.assertIn(osm_fp, q_continent)
        self.assertIn(osm_fp, q_world)

    def test_build_queries_z14_query_groups_by_z14_tiles(self):
        generator = random.Random(1107)
        input_fps = self._make_filepaths(generator, "ig")
        output_fps = self._make_filepaths(generator, "og")

        q_z14, _, _, _, _ = self.module.build_queries(
            input_fps,
            output_fps,
            f"/tmp/osm_{generator.randint(100, 999)}.parquet",
            f"/tmp/c_{generator.randint(100, 999)}.parquet",
            f"/tmp/cont_{generator.randint(100, 999)}.parquet",
        )

        self.assertIn("z14_tiles", q_z14)
        self.assertIn("GROUP BY z14_tiles", q_z14)


# ---------------------------------------------------------------------------
# create_connections
# ---------------------------------------------------------------------------

class CreateConnectionsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_statistics_aggregation_module()

    def test_creates_one_connection_per_worker(self):
        gen = random.Random(1201)
        max_workers = gen.randint(2, 6)
        threads = gen.randint(1, 4)

        conns_created = []
        temps_created = []

        class FakeConn:
            def __init__(self, name):
                self.name = name
                self.calls = []
                conns_created.append(self)

            def execute(self, q):
                self.calls.append(q)

            def create_function(self, *a, **k):
                pass

        def fake_connect(name):
            temps_created.append(name)
            return FakeConn(name)

        with mock.patch.object(self.module.duckdb, "connect", side_effect=fake_connect):
            conns, temps = self.module.create_connections(max_workers, threads)

        self.assertEqual(len(conns_created), max_workers)
        self.assertEqual(len(temps), max_workers)

    def test_each_connection_sets_thread_count(self):
        gen = random.Random(1202)
        max_workers = gen.randint(2, 4)
        threads = gen.randint(1, 8)
        call_log = []

        class FakeConn:
            def execute(self, q):
                call_log.append(q)

            def create_function(self, *a, **k):
                pass

        with mock.patch.object(self.module.duckdb, "connect", side_effect=lambda n: FakeConn()):
            self.module.create_connections(max_workers, threads)

        thread_queries = [q for q in call_log if "threads" in q.lower()]
        self.assertEqual(len(thread_queries), max_workers)
        for q in thread_queries:
            self.assertIn(str(threads), q)

    def test_returns_two_lists_of_equal_length(self):
        gen = random.Random(1203)
        max_workers = gen.randint(2, 5)

        class FakeConn:
            def execute(self, q): pass
            def create_function(self, *a, **k): pass

        with mock.patch.object(self.module.duckdb, "connect", side_effect=lambda n: FakeConn()):
            conns, temps = self.module.create_connections(max_workers, 2)

        self.assertEqual(len(conns), len(temps))
        self.assertEqual(len(conns), max_workers)


# ---------------------------------------------------------------------------
# process_osm_chunk
# ---------------------------------------------------------------------------

class ProcessOsmChunkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_statistics_aggregation_module()

    def test_processes_each_unique_country_once(self):
        gen = random.Random(1210)
        countries = [f"Country{i}" for i in range(gen.randint(2, 5))]
        # DataFrame-like with duplicates
        import collections
        FakeSeries = collections.namedtuple("FakeSeries", [])

        class FakeDf:
            def __init__(self, countries):
                self._countries = countries

            def iloc(self):
                pass

            @property
            def iloc(self):
                return _Iloc(self._countries)

        class _Iloc:
            def __init__(self, countries):
                self._countries = countries

            def __getitem__(self, key):
                return type("Col", (), {
                    "dropna": lambda s: s,
                    "unique": lambda s: list(dict.fromkeys(s._countries)),
                    "_countries": self._countries
                })()

        chunk = FakeDf(countries * 2)  # intentional duplicates
        pattern = f"/data/osm_{gen.randint(100, 999)}.parquet"

        called_countries = []
        fake_result = type("DF", (), {"empty": False})()

        def fake_process(country, pattern, conn):
            called_countries.append(country)
            return fake_result

        with mock.patch.object(self.module, "process_osm_by_country", side_effect=fake_process):
            results = self.module.process_osm_chunk(chunk, pattern, None)

        self.assertEqual(sorted(called_countries), sorted(countries))
        self.assertEqual(len(results), len(countries))

    def test_list_input_also_works(self):
        gen = random.Random(1211)
        countries = [f"C{i}" for i in range(gen.randint(2, 4))]
        pattern = "/data/osm.parquet"

        called = []
        fake_result = type("DF", (), {"empty": False})()

        def fake_process(country, pat, conn):
            called.append(country)
            return fake_result

        with mock.patch.object(self.module, "process_osm_by_country", side_effect=fake_process):
            results = self.module.process_osm_chunk(countries, pattern, None)

        self.assertEqual(sorted(called), sorted(countries))
        self.assertEqual(len(results), len(countries))

    def test_none_results_are_excluded_from_output(self):
        gen = random.Random(1212)
        countries = [f"C{i}" for i in range(gen.randint(3, 5))]
        # Make half return None
        none_countries = countries[::2]
        ok_result = type("DF", (), {"empty": False})()

        def fake_process(country, pat, conn):
            if country in none_countries:
                return None
            return ok_result

        with mock.patch.object(self.module, "process_osm_by_country", side_effect=fake_process):
            results = self.module.process_osm_chunk(countries, "/d/osm.parquet", None)

        expected = len([c for c in countries if c not in none_countries])
        self.assertEqual(len(results), expected)


# ---------------------------------------------------------------------------
# process_urban_areas
# ---------------------------------------------------------------------------

class ProcessUrbanAreasTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_statistics_aggregation_module()

    def test_does_nothing_when_process_urban_false(self):
        gen = random.Random(1220)
        conn_calls = []

        class FakeConn:
            def execute(self, q):
                conn_calls.append(q)

        self.module.process_urban_areas(
            False, ["ID_HDC_G0"], ["/in.parquet"], ["/out.parquet"], ["/urban.parquet"],
            FakeConn()
        )

        self.assertEqual(len(conn_calls), 0)

    def test_executes_one_query_per_column_when_process_urban_true(self):
        gen = random.Random(1221)
        n = gen.randint(1, 3)
        cols = [f"col_{i}" for i in range(n)]
        inputs = [f"/in_{i}.parquet" for i in range(n)]
        outputs = [f"/out_{i}.parquet" for i in range(n)]
        urbans = [f"/urban_{i}.parquet" for i in range(n)]

        conn_calls = []

        class FakeConn:
            def execute(self, q):
                conn_calls.append(q)

        self.module.process_urban_areas(True, cols, inputs, outputs, urbans, FakeConn())

        self.assertEqual(len(conn_calls), n)
        for col, q in zip(cols, conn_calls):
            self.assertIn(col, q)

    def test_query_references_input_and_output_paths(self):
        gen = random.Random(1222)
        input_fp = f"/data/in_{gen.randint(100, 999)}.parquet"
        output_fp = f"/data/out_{gen.randint(100, 999)}.parquet"
        urban_fp = f"/data/urban_{gen.randint(100, 999)}.parquet"

        conn_calls = []

        class FakeConn:
            def execute(self, q):
                conn_calls.append(q)

        self.module.process_urban_areas(
            True, ["agglosID"], [input_fp], [output_fp], [urban_fp], FakeConn()
        )

        self.assertEqual(len(conn_calls), 1)
        q = conn_calls[0]
        self.assertIn(input_fp, q)
        self.assertIn(output_fp, q)
        self.assertIn(urban_fp, q)
