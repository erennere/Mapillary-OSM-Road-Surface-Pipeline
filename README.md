# Mapillary + OSM Road Surface Pipeline

## 1. What This Is

This repository is a tile-based geospatial pipeline for combining Mapillary street-level observations with OpenStreetMap road geometry and tags. It discovers Mapillary sequences, downloads image metadata, intersects points with administrative and urban-area layers, links points to nearby OSM segments, and computes road-surface statistics at multiple spatial levels.

The outputs are parquet datasets and image files organized by tile and aggregation level, designed for long-running batch processing on local machines and SLURM clusters. The code is optimized for chunked processing, resumability, and parallel execution rather than single-shot ad hoc analysis.

## 2. How the Pipeline Works

At a high level: tiles are generated first, then Mapillary sequence lines are downloaded, then sequence metadata is discovered and fetched. Raw CSV metadata is split and converted to tile-partitioned parquet, then spatially intersected and filtered. In parallel with metadata spatial filtering, OSM highways are cleaned and partitioned by tile. Finally, point-to-road matching and nearest-line resolution produce analysis-ready joins, while image download and statistics stages run from their own inputs.

```mermaid
graph TD
    subgraph A[Sequence Discovery]
      sh1([get_sequences_hpc.sh]) --> py1[create_tiles.py]
      py1 -- tiles gpkg --> d1[(data/processed/tiles/tiles_z<zoom>.gpkg)]
      sh1 --> py2[get_linestrings_from_tiles.py]
      d1 -- z/x/y tile coordinates --> py2
      py2 -- sequence lines --> d2[(data/processed/tiles/completed/finished_tiles_z<zoom>.gpkg)]
      py2 -- failed tiles --> d3[(data/processed/tiles/failed/failed_tiles_z<zoom>.gpkg)]
      py2 -- vector tile requests --> api1{{Mapillary vector tile API}}
    end

    subgraph B[Metadata Download]
      sh2([get_metadata_hpc.sh]) --> py3[get_metadata.py]
      py3 -- sequence ids by tile --> py4[metadata_download.py]
      d2 -- sequence ids --> py3
      py4 -- sequence discovery bbox queries --> api2{{Mapillary Graph API}}
      py4 -- metadata csv --> d4[(data/processed/mapillary_metadata/raw_metadata/metadata_unfiltered_<tile>.csv)]
      py4 -- missing sequence csv --> d5[(data/processed/mapillary_metadata/raw_metadata/missing_sequences_<tile>.csv)]
    end

    subgraph C[Parquet Build]
      sh3([split_csvs_and_to_parquet_hpc.sh]) --> py5[csv_to_parquet.py]
      d4 -- raw/split csv --> py5
      py5 -- tile parquet --> d6[(data/processed/mapillary_metadata/hive_partitioned_raw_metadata/tile=<tile>/*.parquet)]
    end

    subgraph D[Spatial Filtering]
      sh4([spatial_intersections_and_filtering_hpc.sh]) --> py6[metadata_intersections_and_filtering.py]
      d6 -- metadata parquet --> py6
      st1[(data/starter_files/GHS_UCDB_GLOBE_R2024A.gpkg)] --> py6
      st2[(data/starter_files/AFRICAPOLIS2020.shp optional)] --> py6
      st3[(data/starter_files/overture_divisions.parquet or Overture download)] --> py6
      py6 -- unfiltered intersected parquet --> d7[(data/processed/mapillary_metadata/spatial_intersections/intersected_unfiltered_metadata/tile=<tile>/*.parquet)]
      py6 -- filtered intersected parquet --> d8[(data/processed/mapillary_metadata/spatial_intersections/intersected_filtered_metadata/tile=<tile>/*.parquet)]
    end

    subgraph E[OSM Preparation]
      sh5([highways_sort_hpc.sh]) --> py7[highways_sort.py]
      osm1[(OSM parquet source files)] -- way parquet --> py7
      py7 -- tile OSM parquet --> d9[(data/osm_data/hive_partitioned_osm_data/tile=<tile>/*.parquet)]
    end

    subgraph F[OSM Matching]
      sh6([find_and_get_nearest_osm_segments.sh]) --> py8[find_osm_segments.py]
      sh6 --> py9[get_nearest_osm_segments.py]
      d7 -- metadata points --> py8
      d9 -- OSM segments --> py8
      py8 -- candidate matches --> d10[(data/processed/mapillary_metadata/spatial_intersections/found_osm_segments/tile=<tile>/*.parquet)]
      d10 -- per-id distance lists --> py9
      py9 -- nearest-line parquet --> d11[(data/processed/mapillary_metadata/spatial_intersections/nearest_lines/tile=<tile>/*.parquet)]
    end

    subgraph G[Images and Stats]
      sh7([image_download.sh]) --> py10[image_download.py]
      d6 -- id+url parquet shards --> py10
      py10 -- png files --> d12[(data/images/<tile>/originals and resized)]

      sh8([statistics_geographic_layers.sh]) --> py11[statistics_geographic_layers.py]
      d9 -- OSM partitioned parquet --> py11
      d13[(data/processed/final_filtered_metadata if present)] --> py11
      py11 -- geographic layer stats --> d14[(data/processed/stats/geographic_layers/...)]

      sh9([statistics_aggregation.sh]) --> py12[statistics_aggregation.py]
      d14 -- z14/z8/country/continent/world shards --> py12
      py12 -- compiled summary parquet --> d15[(data/processed/stats/summary/*.parquet)]
    end

    d2 --> sh2
    d4 --> sh3
    d6 --> sh4
    d6 --> sh7
    d7 --> sh6
    d9 --> sh6
    d9 --> sh8
    d14 --> sh9
```

## 3. Repository Layout

```text
mapillary_cleaned/
├─ README.md                               Definitive pipeline documentation.
├─ environment.yaml                        Conda environment definition for runtime/test dependencies.
├─ data/                                   Runtime inputs and outputs (not source code).
├─ research_code/
│  ├─ config.yaml                          Canonical configuration with section-order inheritance.
│  ├─ config_utils.py                      Strict config parsing/validation helpers.
│  ├─ start.py                             Public config loader/resolver and runtime config builders.
│  ├─ create_tiles.py                      Stage 1 worker: builds tiles_z<zoom>.gpkg.
│  ├─ get_linestrings_from_tiles.py        Stage 1 worker: pulls Mapillary vector tiles and sequence lines.
│  ├─ get_metadata.py                      Stage 2 worker/orchestrator: tile chunking + metadata jobs.
│  ├─ metadata_download.py                 Stage 2 core downloader: bbox subdivision and async API fetch.
│  ├─ csv_to_parquet.py                    Stage 3 worker: CSV to parquet conversion with geometry casting.
│  ├─ metadata_intersections_and_filtering.py  Stage 4 worker: spatial joins + distance-based thinning.
│  ├─ highways_sort.py                     Stage 5 worker: OSM highway filtering + tile partitioning.
│  ├─ find_osm_segments.py                 Stage 6 worker: candidate point-to-road matching.
│  ├─ get_nearest_osm_segments.py          Stage 6 worker: nearest-selection post processing.
│  ├─ image_download.py                    Stage 7 worker: async image download and resize.
│  ├─ statistics_geographic_layers.py      Stage 8 worker: per-layer and per-geography stats.
│  ├─ statistics_aggregation.py            Stage 9 worker: compile/aggregate summary outputs.
│  ├─ dlr.py                               Standalone utility for a single z14 tile fetch.
│  ├─ get_sequences_hpc.sh                 Launcher for Stage 1 workers.
│  ├─ get_metadata_hpc.sh                  Launcher for Stage 2 workers (10 parallel instances).
│  ├─ split_csvs_and_to_parquet_hpc.sh     Launcher for Stage 3 splitting + conversion.
│  ├─ spatial_intersections_and_filtering_hpc.sh  Launcher for Stage 4 local/HPC array execution.
│  ├─ highways_sort_hpc.sh                 Launcher for Stage 5 worker.
│  ├─ find_and_get_nearest_osm_segments.sh Launcher for Stage 6 workers.
│  ├─ image_download.sh                    Launcher for Stage 7 with array/sequential/parallel modes.
│  ├─ statistics_geographic_layers.sh      Launcher for Stage 8 (SLURM array task id passthrough).
│  ├─ statistics_aggregation.sh            Launcher for Stage 9 (SLURM array task id passthrough).
│  └─ test.sh                              Small shell snippet (not a pipeline stage).
└─ tests/
   ├─ test_create_tiles.py                 Unit tests for stage 1 tile generation behavior.
   ├─ test_get_linestrings_from_tiles.py   Unit tests for Mapillary tile download and dedupe logic.
   ├─ test_get_metadata.py                 Unit tests for chunking/resume orchestration.
   ├─ test_metadata_download.py            Extensive tests for API handling, retries, buffers, threads.
   ├─ test_csv_to_parquet.py               Unit tests for conversion query generation and fallback logic.
   ├─ test_metadata_intersections_and_filtering.py  Tests layer prep, intersection flow, retry/timeout.
   ├─ test_highways_sort.py                Tests OSM filtering, retry behavior, and tile partition outputs.
   ├─ test_find_osm_segments.py            Tests haversine and stage-6 matching orchestration.
   ├─ test_get_nearest_osm_segments.py     Tests nearest-selection masks and output generation.
   ├─ test_image_download.py               Tests async download orchestration and cleanup behavior.
   ├─ test_statistics_geographic_layers.py Tests SQL helper generation and geographic-stage orchestration.
   ├─ test_statistics_aggregation.py       Tests aggregation query builders and orchestration paths.
   ├─ test_start.py                        Tests config inheritance and strict loader behavior.
   └─ test_dlr.py                          Tests standalone z14 utility.
```

## 4. Setup

1. Create environment:

```bash
conda env create -f environment.yaml
conda activate mapillary-road-surface-pipeline
```

2. Put your Mapillary token in config (required):
- `research_code/config.yaml` -> `get_linestrings_from_tiles.params.mly_key` ⚠️

3. System/runtime requirements:
- Python 3.11
- GDAL stack available (for geopandas/io)
- DuckDB with SPATIAL extension (scripts run `INSTALL SPATIAL; LOAD SPATIAL;`)
- Bash for launchers
- SLURM only if running HPC modes

4. Minimum `config.yaml` changes before first run:
- `get_linestrings_from_tiles.params.mly_key` ⚠️
- `highways_sort.paths.ohsome_osm_dir` (or ensure `osm_saving_dir` has the expected input files) ⚠️
- `metadata_download.metadata_params.query_bbox` if you are not running the current default area ⚠️

Everything else is documented in the configuration reference below.

## 5. Running the Pipeline

### Stage 1 — Tile Creation + Sequence Lines (`get_sequences_hpc.sh` + `create_tiles.py` + `get_linestrings_from_tiles.py`)

This stage builds the spatial tile grid and downloads sequence line geometries from Mapillary vector tiles. The shell script runs both Python workers in sequence, stopping immediately if stage 1a fails.

**Run:**
```bash
# local
bash research_code/get_sequences_hpc.sh

# HPC
sbatch research_code/get_sequences_hpc.sh
```

**Execution modes:** single sequential flow in both local and HPC (SBATCH header is static).

**Smart behaviors:**
- Resume logic: existing output files are overwritten by worker writes; no explicit skip-by-exists in launcher.
- Retry logic: tile download retries in `get_linestrings_from_tiles.py` (`metadata_params.retries`).
- Parallelism: internal loop over tiles; no explicit multiprocessing in this stage.

**Inputs:**
- `data/starter_files/overture_divisions.parquet` if present (used as polygon source)
- fallback optional `filenames.starter_polygon_fn` if configured

**Outputs:**
- `data/processed/tiles/tiles_z<zoom>.gpkg` (GeoPackage)
- `data/processed/tiles/completed/finished_tiles_z<zoom>.gpkg` (GeoPackage)
- `data/processed/tiles/failed/failed_tiles_z<zoom>.gpkg` (GeoPackage)

**To re-run from scratch:**
- delete `data/processed/tiles/tiles_z<zoom>.gpkg`
- delete `data/processed/tiles/completed/finished_tiles_z<zoom>.gpkg`
- delete `data/processed/tiles/failed/failed_tiles_z<zoom>.gpkg`

---

### Stage 2 — Metadata Discovery + Download (`get_metadata_hpc.sh` + `get_metadata.py` + `metadata_download.py`)

This stage discovers sequence IDs within bounding boxes, then downloads per-image metadata for each sequence. The shell launcher starts 10 parallel Python instances; each instance processes a deterministic chunk of tiles.

**Run:**
```bash
# local
bash research_code/get_metadata_hpc.sh

# HPC
sbatch research_code/get_metadata_hpc.sh
```

**Execution modes:**
- launcher always starts 10 background jobs (`get_metadata.py 1..10`).
- same script can run on local or HPC; worker reads `SLURM_CPUS_PER_TASK` when present.

**Smart behaviors:**
- Resume logic: `get_metadata.py` skips sequence IDs already present in existing `metadata_unfiltered_<tile>.csv`.
- Retry logic: multiple layers:
  - sequence API calls in `metadata_download.py`
  - missing sequence reattempts via `missing_attempts`
  - thread-safe flush/retry guards
- Parallelism:
  - deterministic chunking by `DETERMINISTIC_SEED=42`, `NUM_CHUNKS=10`
  - async HTTP batch download in `metadata_download.py`
  - monitoring threads for dynamic connection limits and buffered writes
- Other smart behavior:
  - dynamic allowed-connections throttling based on active job file patterns
  - forced final buffer flush + deterministic thread joins on shutdown

**Inputs:**
- `data/processed/tiles/completed/finished_tiles_z<zoom>.gpkg`
- Mapillary API access

**Outputs:**
- `data/processed/mapillary_metadata/raw_metadata/metadata_unfiltered_<tile>.csv`
- `data/processed/mapillary_metadata/raw_metadata/missing_sequences_<tile>.csv`

**To re-run from scratch:**
- delete all `data/processed/mapillary_metadata/raw_metadata/metadata_unfiltered_*.csv`
- delete all `data/processed/mapillary_metadata/raw_metadata/missing_sequences_*.csv`

---

### Stage 3 — Split and Convert to Parquet (`split_csvs_and_to_parquet_hpc.sh` + `csv_to_parquet.py`)

This stage optionally splits large metadata CSV files and converts metadata into parquet with WKT geometry cast to WKB. The shell script reads configuration through `start.py`, performs incremental split-resume, then calls Python conversion per tile.

**Run:**
```bash
# local
bash research_code/split_csvs_and_to_parquet_hpc.sh

# HPC
sbatch research_code/split_csvs_and_to_parquet_hpc.sh
```

**Execution modes:** single shell flow; parallelism is at file-level iteration in shell, not process pool.

**Smart behaviors:**
- Resume logic:
  - split logic resumes from existing numbered chunks (`splitted_<name>_*.csv`)
  - conversion prefers recent split files, falls back to raw csv if no recent split found
- Retry logic: none at shell level; conversion logs errors per file.
- Parallelism: none explicit in launcher.
- Other smart behavior:
  - timestamp gating (`csv_split_params.updated_after`) to process only recent files

**Inputs:**
- `data/processed/mapillary_metadata/raw_metadata/metadata_unfiltered_*.csv`

**Outputs:**
- `data/processed/mapillary_metadata/splitted_raw_metadata/splitted_metadata_unfiltered_<tile>_*.csv`
- `data/processed/mapillary_metadata/hive_partitioned_raw_metadata/tile=<tile>/*.parquet`

**To re-run from scratch:**
- delete `data/processed/mapillary_metadata/splitted_raw_metadata/*`
- delete `data/processed/mapillary_metadata/hive_partitioned_raw_metadata/*`

---

### Stage 4 — Spatial Intersections + Filtering (`spatial_intersections_and_filtering_hpc.sh` + `metadata_intersections_and_filtering.py`)

This stage enriches metadata points with continent/country/urban-area context and applies distance-based sequence thinning (`urban_threshold`, `rural_threshold`). The launcher can self-submit an array job on HPC or run bounded parallel local workers.

**Run:**
```bash
# local
bash research_code/spatial_intersections_and_filtering_hpc.sh

# HPC
sbatch research_code/spatial_intersections_and_filtering_hpc.sh
```

**Execution modes:**
- HPC: self-submits SLURM array if not already in array task context.
- local: CPU-detected parallel loop with cap (`MAX_PARALLEL=6`).

**Smart behaviors:**
- Resume logic:
  - launcher selects input parquet files newer than `metadata_params.updated_after`
  - worker skips old files by mtime check
  - one-time layer preparation based on first-tile heuristic
- Retry logic:
  - worker wraps main intersection path in up to 3 attempts
- Parallelism:
  - file-level parallel processing in shell
  - spatial SQL done in DuckDB per file
- Other smart behavior:
  - on-demand Overture country download
  - conversion of GHSL/Africapolis to parquet when needed
  - bounded waits for synchronization and temp cleanup

**Inputs:**
- `data/processed/mapillary_metadata/hive_partitioned_raw_metadata/tile=<tile>/*.parquet`
- `data/starter_files/GHS_UCDB_GLOBE_R2024A.gpkg`
- optional `data/starter_files/AFRICAPOLIS2020.shp` set

**Outputs:**
- `data/processed/mapillary_metadata/spatial_intersections/intersected_unfiltered_metadata/tile=<tile>/*.parquet`
- `data/processed/mapillary_metadata/spatial_intersections/intersected_filtered_metadata/tile=<tile>/*.parquet`
- derived layer files under `data/processed/` (intersected country/urban helper parquet)

**To re-run from scratch:**
- delete both `intersected_unfiltered_metadata` and `intersected_filtered_metadata`
- if you want to rebuild derived geographic helper layers, also delete `data/processed/intersected_*.parquet` and `data/processed/country_intersected_*.parquet`

---

### Stage 5 — OSM Highway Preparation (`highways_sort_hpc.sh` + `highways_sort.py`)

This stage filters OSM way parquet files to highway LineStrings, joins continent/country attributes, and partitions output by tile. It is independent of Stage 4 once Stage 3 and required geographic layers are available, so Stage 4 and Stage 5 can run in parallel.

**Run:**
```bash
# local
bash research_code/highways_sort_hpc.sh

# HPC
sbatch research_code/highways_sort_hpc.sh
```

**Execution modes:** launcher is simple single-worker invocation; worker itself uses process pools.

**Smart behaviors:**
- Resume logic: output files are rewritten; no skip-by-exists in main flow.
- Retry logic:
  - copy/count/chunk operations have retry loops
  - hard failure if count or chunk retries are exhausted
- Parallelism:
  - process pool across OSM input files
  - process pool for tile partition writes

**Inputs:**
- OSM parquet files in `paths.ohsome_osm_dir` (must be configured)
- intersected geography files from layer setup (`continents`, `country`)

**Outputs:**
- `data/osm_data/ohsome_data/highways_*.parquet` (intermediate filtered)
- `data/osm_data/hive_partitioned_osm_data/tile=<tile>/osm_highways_<tile>_<chunk>.parquet`

**To re-run from scratch:**
- delete `data/osm_data/ohsome_data/*.parquet` generated by this stage
- delete `data/osm_data/hive_partitioned_osm_data/tile=*`

---

### Stage 6 — OSM Matching + Nearest Resolution (`find_and_get_nearest_osm_segments.sh` + `find_osm_segments.py` + `get_nearest_osm_segments.py`)

This stage links metadata points to nearby OSM segments and then resolves multiple candidates per image with threshold bands (`threshold_1`, `threshold_2`). The shell script processes each metadata parquet file by calling both workers sequentially.

**Run:**
```bash
# local
bash research_code/find_and_get_nearest_osm_segments.sh

# HPC
sbatch research_code/find_and_get_nearest_osm_segments.sh
```

**Execution modes:**
- HPC: self-submits array and runs one file per task.
- local: loop over files (current implementation calls workers synchronously).

**Smart behaviors:**
- Resume logic:
  - `find_osm_segments.py` skips old files using `metadata_params.updated_after`
  - both workers skip if expected input path is missing
- Retry logic: query-level retries are minimal; robustness is mostly guard/skip behavior.
- Parallelism:
  - HPC array-level parallelism
  - local mode currently mostly sequential per file
- Other smart behavior:
  - tile id extracted from filename tokens
  - DuckDB UDF for haversine distance

**Inputs:**
- `intersected_unfiltered_metadata/tile=<tile>/*.parquet`
- `hive_partitioned_osm_data/tile=<tile>/*.parquet`

**Outputs:**
- `data/processed/mapillary_metadata/spatial_intersections/found_osm_segments/tile=<tile>/osm_*_metadata_unfiltered_<tile>.parquet`
- `data/processed/mapillary_metadata/spatial_intersections/nearest_lines/tile=<tile>/closest_metadata_unfiltered_<tile>.parquet`

**To re-run from scratch:**
- delete `found_osm_segments/tile=*`
- delete `nearest_lines/tile=*`

---

### Stage 7 — Image Download (`image_download.sh` + `image_download.py`)

This stage downloads and resizes images from metadata URLs. The shell script reads execution mode from config and dispatches chunks accordingly.

**Run:**
```bash
# local
bash research_code/image_download.sh

# HPC
sbatch research_code/image_download.sh
```

**Execution modes:**
- `array`: HPC only, one chunk per SLURM task.
- `sequential`: one chunk at a time.
- `parallel`: multiple chunks concurrently.

**Smart behaviors:**
- Resume logic:
  - each file write path is deterministic by image id; failed downloads recorded in `logs/missing_*.csv`
  - missing-image writer thread continuously flushes failures
- Retry logic:
  - per-image retries with exponential backoff in async fetch path
- Parallelism:
  - shell chunk-level mode dispatch
  - Python thread pool + async HTTP batches inside each chunk
- Other smart behavior:
  - dynamic connection quota replenishment thread
  - cleanup of partially written files for failed images

**Inputs:**
- `data/processed/mapillary_metadata/hive_partitioned_raw_metadata/tile=<tile>/*.parquet` (contains id/url)

**Outputs:**
- `data/images/<tile>/originals/<id>.png` (if enabled)
- `data/images/<tile>/resized/<id>.png`
- `data/images/logs/missing_<parquet_basename>.csv`

**To re-run from scratch:**
- delete `data/images/<tile>/originals` and `data/images/<tile>/resized`
- delete `data/images/logs/missing_*.csv`

---

### Stage 8 — Geographic Layer Statistics (`statistics_geographic_layers.sh` + `statistics_geographic_layers.py`)

This stage computes metrics at z14/z8/country/continent/world and optional urban layers using DuckDB SQL fragments and process pools. The shell script forwards SLURM task id.

**Run:**
```bash
# local
python research_code/statistics_geographic_layers.py

# HPC
sbatch research_code/statistics_geographic_layers.sh
```

**Execution modes:**
- local direct run (unsharded) or optional CLI sharding args in Python
- HPC SLURM array task id pass-through

**Smart behaviors:**
- Resume logic: script exits early if `paths.final_filtered_dir` does not exist.
- Retry logic: none explicit around SQL blocks.
- Parallelism: process pool over directory shards.

**Inputs:**
- `paths.final_filtered_dir` parquet directory (must exist)
- `paths.osm_partitioned_dir` tile OSM parquet

**Outputs:**
- `data/processed/stats/geographic_layers/` with z14/z8/country/continent/world and urban-layer parquet shards

**To re-run from scratch:**
- delete `data/processed/stats/geographic_layers/*`

---

### Stage 9 — Aggregation Compile (`statistics_aggregation.sh` + `statistics_aggregation.py`)

This stage compiles stage-8 shard outputs into final all-level parquet summaries and optional non-temporal OSM rollups. The shell script forwards SLURM task id.

**Run:**
```bash
# local
python research_code/statistics_aggregation.py

# HPC
sbatch research_code/statistics_aggregation.sh
```

**Execution modes:**
- local direct run
- HPC array wrapper

**Smart behaviors:**
- Resume logic: writes compiled parquet targets deterministically in summary directory.
- Retry logic: none explicit; resource cleanup handled in `finally` blocks.
- Parallelism: process pools for optional country-based OSM processing.

**Inputs:**
- stage-8 geographic-layer parquet outputs
- configured country/continent/urban helper layers

**Outputs:**
- `data/processed/stats/summary/z14_tiles_with_stats_all.parquet`
- `data/processed/stats/summary/<zoom>_tiles_with_stats_all.parquet`
- `data/processed/stats/summary/countries_with_stats_all.parquet`
- `data/processed/stats/summary/continents_with_stats_all.parquet`
- `data/processed/stats/summary/world_with_stats_all.parquet`

**To re-run from scratch:**
- delete `data/processed/stats/summary/*.parquet`

---

Shell-only execution and mode graph:

```mermaid
graph TD
    start([Start]) --> s1([get_sequences_hpc.sh])
    s1 --> s2([get_metadata_hpc.sh])
    s2 --> s3([split_csvs_and_to_parquet_hpc.sh])
    s3 --> p4{Stage 4 and 5 order}
    p4 --> s4([spatial_intersections_and_filtering_hpc.sh])
    p4 --> s5([highways_sort_hpc.sh])
    s4 --> s6([find_and_get_nearest_osm_segments.sh])
    s5 --> s6

    s3 --> im([image_download.sh])
    im --> imMode{execution.mode}
    imMode --> imA[array]
    imMode --> imS[sequential]
    imMode --> imP[parallel]

    s6 --> sg([statistics_geographic_layers.sh])
    sg --> sa([statistics_aggregation.sh])

    s4 --> local4[local loop mode]
    s4 --> hpc4[SLURM array mode]
    s6 --> local6[local file loop]
    s6 --> hpc6[SLURM array mode]
```

## 6. Data Layout

Expected `data/` layout after a full successful run:

```text
data/
├─ starter_files/                                                Pre-run inputs
│  ├─ overture_divisions.parquet                                 Source polygon for tile clipping or auto-generated helper
│  ├─ GHS_UCDB_GLOBE_R2024A.gpkg                                 Stage 4 input (urban layer)
│  ├─ AFRICAPOLIS2020.shp (+ .dbf/.shx/.prj)                    Stage 4 optional input
│  └─ continents/*.geojson                                       Stage 4 helper input
├─ processed/
│  ├─ tiles/                                                     Stage 1 outputs (GPKG)
│  │  ├─ tiles_z<zoom>.gpkg
│  │  ├─ completed/finished_tiles_z<zoom>.gpkg
│  │  └─ failed/failed_tiles_z<zoom>.gpkg
│  ├─ mapillary_metadata/
│  │  ├─ raw_metadata/                                           Stage 2 outputs (CSV)
│  │  │  ├─ metadata_unfiltered_<tile>.csv
│  │  │  └─ missing_sequences_<tile>.csv
│  │  ├─ splitted_raw_metadata/                                  Stage 3 split outputs (CSV)
│  │  ├─ hive_partitioned_raw_metadata/                          Stage 3 parquet outputs
│  │  │  └─ tile=<tile>/*.parquet
│  │  └─ spatial_intersections/                                  Stage 4 and 6 outputs
│  │     ├─ intersected_unfiltered_metadata/tile=<tile>/*.parquet
│  │     ├─ intersected_filtered_metadata/tile=<tile>/*.parquet
│  │     ├─ found_osm_segments/tile=<tile>/*.parquet
│  │     └─ nearest_lines/tile=<tile>/*.parquet
│  ├─ stats/                                                     Stage 8 and 9 outputs
│  │  ├─ geographic_layers/*.parquet
│  │  └─ summary/*.parquet
│  └─ final_filtered_metadata/                                   Required by Stage 8; not produced by earlier shell stages directly
├─ osm_data/
│  ├─ ohsome_data/                                               Stage 5 filtered/intermediate OSM parquet
│  └─ hive_partitioned_osm_data/tile=<tile>/*.parquet           Stage 5 final OSM partitions
└─ images/
   ├─ <tile>/originals/*.png                                     Stage 7 optional original images
   ├─ <tile>/resized/*.png                                       Stage 7 resized outputs
   └─ logs/missing_*.csv                                         Stage 7 failed-download logs
```

## 7. Configuration Reference

The tables below list all leaf parameters in `research_code/config.yaml`.

Legend:
- ⚠️ = likely user-adjusted before production runs.
- `Used by` references the script section that resolves/consumes the key.

### `create_tiles`

| Parameter | Default | Used by | What it controls |
|---|---:|---|---|
| `create_tiles.params.zoom_level` | `8` | `create_tiles.py` | Tile zoom level. |
| `create_tiles.paths.data_dir` | `../data` | `create_tiles.py` | Base data directory. ⚠️ |
| `create_tiles.paths.processed_dir` | `{data_dir}/processed` | `create_tiles.py` and inherited | Derived processed root. |
| `create_tiles.paths.starter_dir` | `{data_dir}/starter_files` | stage 1/4/5/9 | Starter input root. |
| `create_tiles.paths.tiles_save_dir` | `{processed_dir}/tiles` | stage 1 | Tile gpkg output root. |
| `create_tiles.filenames.starter_polygon_fn` | `` | `create_tiles.py` | Optional fallback polygon file. |
| `create_tiles.filenames.country_filename` | `overture_divisions.parquet` | stage 1/4/5/9 | Country polygon parquet name. |

### `get_linestrings_from_tiles`

| Parameter | Default | Used by | What it controls |
|---|---:|---|---|
| `get_linestrings_from_tiles.params.zoom_level` | `null` | `get_linestrings_from_tiles.py` | Inherit zoom level from stage 1. |
| `get_linestrings_from_tiles.params.mly_key` | `MLY|...` | stage 1 and inherited | Mapillary access token. ⚠️ |
| `get_linestrings_from_tiles.paths.data_dir` | `null` | stage 1 | Inherited base data dir. |
| `get_linestrings_from_tiles.paths.processed_dir` | `null` | stage 1 | Inherited processed dir. |
| `get_linestrings_from_tiles.paths.tiles_save_dir` | `null` | stage 1 | Inherited tiles dir. |
| `get_linestrings_from_tiles.paths.completed_tiles_dir` | `{processed_dir}/tiles/completed` | stage 1/2 | Completed tiles gpkg dir. |
| `get_linestrings_from_tiles.paths.failed_tiles_dir` | `{processed_dir}/tiles/failed` | stage 1 | Failed tiles gpkg dir. |
| `get_linestrings_from_tiles.metadata_params.retries` | `5` | stage 1, inherited | Tile download retries. |

### `get_metadata`

| Parameter | Default | Used by | What it controls |
|---|---:|---|---|
| `get_metadata.params.zoom_level` | `null` | `get_metadata.py` | Inherited zoom level. |
| `get_metadata.params.mly_key` | `null` | `get_metadata.py` | Inherited Mapillary token. |
| `get_metadata.paths.data_dir` | `null` | `get_metadata.py` | Inherited data dir. |
| `get_metadata.paths.processed_dir` | `null` | `get_metadata.py` | Inherited processed dir. |
| `get_metadata.paths.raw_metadata_dir` | `{processed_dir}/mapillary_metadata/raw_metadata` | stage 2 | Metadata CSV output dir. |
| `get_metadata.paths.completed_tiles_dir` | `null` | stage 2 | Inherited completed tiles path. |
| `get_metadata.metadata_params.retries` | `null` | stage 2 | Inherited per-request retry base. |
| `get_metadata.metadata_params.batch_size` | `100` | stage 2 | Async batch size. |
| `get_metadata.metadata_params.windows` | `true` | stage 2 | Windows event-loop policy toggle. |
| `get_metadata.metadata_params.call_limit` | `5` | stage 2 | API call retry cap. |
| `get_metadata.metadata_params.empty_data_attempts` | `3` | stage 2 | Empty-response tolerance. |
| `get_metadata.metadata_params.max_connections` | `10000` | stage 2 | Connection budget upper bound. |
| `get_metadata.metadata_params.sleep_time` | `5` | stage 2 | Retry sleep/backoff base seconds. |
| `get_metadata.metadata_params.max_workers` | `16` | stage 2 | Thread worker count. |
| `get_metadata.metadata_params.missing_attempts` | `1` | stage 2 | Re-processing passes for missing sequences. |
| `get_metadata.metadata_params.monitor_interval` | `10` | stage 2 | Monitoring cycle seconds. |
| `get_metadata.metadata_params.monitor_check_timeout` | `10` | stage 2 | Monitor stop-check period. |
| `get_metadata.metadata_params.write_interval` | `300` | stage 2 | Buffered write interval seconds. |
| `get_metadata.metadata_params.write_check_timeout` | `10` | stage 2 | Writer stop-check period. |
| `get_metadata.metadata_params.file_age_threshold_seconds` | `450` | stage 2 | Recent file threshold in monitor logic. |
| `get_metadata.metadata_columns` | `[sequence,id,thumb_original_url,long,lat,computed_geometry,height,width,altitude,make,model,creator,is_pano,captured_at]` | stage 2 | Metadata output schema contract. |

### `metadata_download`

| Parameter | Default | Used by | What it controls |
|---|---:|---|---|
| `metadata_download.params.mly_key` | `null` | `metadata_download.py` | Inherited token. |
| `metadata_download.paths.data_dir` | `null` | `metadata_download.py` | Inherited data dir. |
| `metadata_download.paths.processed_dir` | `null` | `metadata_download.py` | Inherited processed dir. |
| `metadata_download.paths.raw_metadata_dir` | `null` | `metadata_download.py` | Inherited raw metadata dir. |
| `metadata_download.metadata_params.retries` | `null` | stage 2 | Inherited retries. |
| `metadata_download.metadata_params.batch_size` | `null` | stage 2 | Inherited batch size. |
| `metadata_download.metadata_params.windows` | `null` | stage 2 | Inherited windows toggle. |
| `metadata_download.metadata_params.call_limit` | `null` | stage 2 | Inherited call limit. |
| `metadata_download.metadata_params.empty_data_attempts` | `null` | stage 2 | Inherited empty-data attempts. |
| `metadata_download.metadata_params.max_connections` | `null` | stage 2 | Inherited max connections. |
| `metadata_download.metadata_params.sleep_time` | `null` | stage 2 | Inherited sleep time. |
| `metadata_download.metadata_params.max_workers` | `16` | stage 2 | Worker split size for async wrappers. |
| `metadata_download.metadata_params.query_bbox` | `[8.65757,49.392653,8.707523,49.420689]` | stage 2 | Discovery area bbox. ⚠️ |
| `metadata_download.metadata_params.metadata_basename` | `metadata_unfiltered` | stage 2 | Metadata output basename. |
| `metadata_download.metadata_params.missing_basename` | `missing_sequences` | stage 2 | Missing sequence basename. |
| `metadata_download.metadata_params.initial_subdivisions` | `100` | stage 2 | Initial bbox split grid size. |
| `metadata_download.metadata_params.subdivision_factor` | `4` | stage 2 | Recursive subdivision factor. |
| `metadata_download.metadata_params.enable_download` | `true` | stage 2 | Skip/enable metadata fetch after discovery. |
| `metadata_download.metadata_params.monitor_interval` | `null` | stage 2 | Inherited monitor interval. |
| `metadata_download.metadata_params.monitor_check_timeout` | `null` | stage 2 | Inherited monitor timeout. |
| `metadata_download.metadata_params.write_interval` | `null` | stage 2 | Inherited write interval. |
| `metadata_download.metadata_params.write_check_timeout` | `null` | stage 2 | Inherited write timeout. |
| `metadata_download.metadata_columns` | `null` | stage 2 | Inherited metadata columns. |

### `csv_to_parquet`

| Parameter | Default | Used by | What it controls |
|---|---:|---|---|
| `csv_to_parquet.paths.data_dir` | `null` | `csv_to_parquet.py` | Inherited data dir. |
| `csv_to_parquet.paths.processed_dir` | `null` | `csv_to_parquet.py` | Inherited processed dir. |
| `csv_to_parquet.paths.raw_metadata_dir` | `null` | stage 3 | Inherited raw metadata dir. |
| `csv_to_parquet.paths.splitted_raw_metadata_dir` | `{processed_dir}/mapillary_metadata/splitted_raw_metadata` | stage 3 | Split csv dir. |
| `csv_to_parquet.paths.tile_partitioned_parquet_raw_metadata_dir` | `{processed_dir}/mapillary_metadata/hive_partitioned_raw_metadata` | stage 3/4/7 | Tile parquet dir. |
| `csv_to_parquet.csv_split_params.n_rows` | `500000` | stage 3 shell | Split chunk row size. |
| `csv_to_parquet.csv_split_params.split_enabled` | `true` | stage 3 shell | Enable split pre-step. |
| `csv_to_parquet.csv_split_params.updated_after` | `2026-03-18T00:49:00` | stage 3 | Timestamp filter for processing. ⚠️ |

### `metadata_intersections_and_filtering`

| Parameter | Default | Used by | What it controls |
|---|---:|---|---|
| `metadata_intersections_and_filtering.params.zoom_level` | `null` | stage 4 | Inherited zoom. |
| `metadata_intersections_and_filtering.params.urban_threshold` | `100` | stage 4 | Urban simplification distance (m). |
| `metadata_intersections_and_filtering.params.rural_threshold` | `1000` | stage 4 | Rural simplification distance (m). |
| `metadata_intersections_and_filtering.params.ghsl_col_1` | `.ID_UC_G0` | stage 4 | GHSL joined column name 1. |
| `metadata_intersections_and_filtering.params.ghsl_col_2` | `.GC_UCN_MAI_2025` | stage 4 | GHSL joined column name 2. |
| `metadata_intersections_and_filtering.params.africapolis_col_1` | `.agglosID` | stage 4 | Africapolis joined column name 1. |
| `metadata_intersections_and_filtering.params.africapolis_col_2` | `.agglosName` | stage 4 | Africapolis joined column name 2. |
| `metadata_intersections_and_filtering.paths.data_dir` | `null` | stage 4 | Inherited data dir. |
| `metadata_intersections_and_filtering.paths.processed_dir` | `null` | stage 4 | Inherited processed dir. |
| `metadata_intersections_and_filtering.paths.starter_dir` | `null` | stage 4 | Inherited starter dir. |
| `metadata_intersections_and_filtering.paths.tile_partitioned_parquet_raw_metadata_dir` | `null` | stage 4 | Inherited stage 3 parquet path. |
| `metadata_intersections_and_filtering.paths.continents_dir` | `{starter_dir}/continents` | stage 4 | Continent geojson folder. |
| `metadata_intersections_and_filtering.paths.unfiltered_metadata_dir` | `{processed_dir}/mapillary_metadata/spatial_intersections/intersected_unfiltered_metadata` | stage 4/6 | Unfiltered intersect output path. |
| `metadata_intersections_and_filtering.paths.filtered_metadata_dir` | `{processed_dir}/mapillary_metadata/spatial_intersections/intersected_filtered_metadata` | stage 4 | Filtered intersect output path. |
| `metadata_intersections_and_filtering.metadata_params.updated_after` | `2026-03-18T00:49:00` | stage 4 | Timestamp skip threshold. ⚠️ |
| `metadata_intersections_and_filtering.filenames.continents_filename` | `{processed_dir}/continents.parquet` | stage 4/5/9 | Continents parquet path. |
| `metadata_intersections_and_filtering.filenames.overture_url` | `s3://overturemaps-us-west-2/release/2025-01-22.0` | stage 4/5 | Overture source root. |
| `metadata_intersections_and_filtering.filenames.country_filename` | `null` | stage 4/5/9 | Inherited country filename. |
| `metadata_intersections_and_filtering.filenames.ghsl_filename` | `GHS_UCDB_GLOBE_R2024A.gpkg` | stage 4/5/9 | GHSL input filename. |
| `metadata_intersections_and_filtering.filenames.africapolis_filename` | `AFRICAPOLIS2020.shp` | stage 4/5/9 | Africapolis input filename. |

### `highways_sort`

| Parameter | Default | Used by | What it controls |
|---|---:|---|---|
| `highways_sort.params.zoom_level` | `null` | stage 5 | Inherited zoom. |
| `highways_sort.params.n_max_rows_parquet` | `500000` | stage 5 | Tile chunk row cap. |
| `highways_sort.paths.data_dir` | `null` | stage 5 | Inherited data dir. |
| `highways_sort.paths.processed_dir` | `null` | stage 5 | Inherited processed dir. |
| `highways_sort.paths.starter_dir` | `null` | stage 5 | Inherited starter dir. |
| `highways_sort.paths.ohsome_osm_dir` | `` | stage 5 | Input OSM parquet dir. ⚠️ |
| `highways_sort.paths.osm_saving_dir` | `{data_dir}/osm_data/ohsome_data` | stage 5 | Intermediate filtered OSM output dir. |
| `highways_sort.paths.osm_partitioned_dir` | `{data_dir}/osm_data/hive_partitioned_osm_data` | stage 5/6/8 | Tile-partitioned OSM output dir. |
| `highways_sort.paths.continents_dir` | `null` | stage 5 | Inherited continents dir. |
| `highways_sort.metadata_params.retries` | `null` | stage 5 | Retry count for SQL operations. |
| `highways_sort.metadata_params.sleep_time` | `null` | stage 5 | Retry sleep seconds. |
| `highways_sort.metadata_params.max_workers` | `16` | stage 5 | Process pool worker count. |
| `highways_sort.filenames.continents_filename` | `null` | stage 5 | Inherited continents file path. |
| `highways_sort.filenames.overture_url` | `null` | stage 5 | Inherited Overture URL. |
| `highways_sort.filenames.country_filename` | `null` | stage 5 | Inherited country filename. |
| `highways_sort.filenames.ghsl_filename` | `null` | stage 5 | Inherited GHSL filename. |
| `highways_sort.filenames.africapolis_filename` | `null` | stage 5 | Inherited Africapolis filename. |

### `find_osm_segments`

| Parameter | Default | Used by | What it controls |
|---|---:|---|---|
| `find_osm_segments.params.earth_radius` | `6371008` | stage 6 | Haversine earth radius meters. |
| `find_osm_segments.params.zoom_level` | `null` | stage 6 | Inherited zoom. |
| `find_osm_segments.params.distance_threshold` | `30` | stage 6 | Max point-to-road distance meters. |
| `find_osm_segments.paths.data_dir` | `null` | stage 6 | Inherited data dir. |
| `find_osm_segments.paths.processed_dir` | `null` | stage 6 | Inherited processed dir. |
| `find_osm_segments.paths.unfiltered_metadata_dir` | `null` | stage 6 | Inherited intersected unfiltered root. |
| `find_osm_segments.paths.osm_partitioned_dir` | `null` | stage 6 | Inherited OSM tile root. |
| `find_osm_segments.paths.osm_intersections_dir` | `{processed_dir}/mapillary_metadata/spatial_intersections/found_osm_segments` | stage 6 | Candidate match output dir. |
| `find_osm_segments.metadata_params.updated_after` | `null` | stage 6 | Inherited timestamp skip threshold. |

### `get_nearest_osm_segments`

| Parameter | Default | Used by | What it controls |
|---|---:|---|---|
| `get_nearest_osm_segments.params.threshold_1` | `10` | stage 6 | Near band threshold. |
| `get_nearest_osm_segments.params.threshold_2` | `20` | stage 6 | Secondary band threshold. |
| `get_nearest_osm_segments.paths.data_dir` | `null` | stage 6 | Inherited data dir. |
| `get_nearest_osm_segments.paths.processed_dir` | `null` | stage 6 | Inherited processed dir. |
| `get_nearest_osm_segments.paths.osm_intersections_dir` | `null` | stage 6 | Inherited candidate match dir. |
| `get_nearest_osm_segments.paths.osm_nearest_line_dir` | `{processed_dir}/mapillary_metadata/spatial_intersections/nearest_lines` | stage 6/8 | Final nearest-line output dir. |
| `get_nearest_osm_segments.metadata_params.updated_after` | `null` | stage 6 | Inherited timestamp skip threshold. |

### `image_download`

| Parameter | Default | Used by | What it controls |
|---|---:|---|---|
| `image_download.paths.data_dir` | `null` | stage 7 | Inherited data dir. |
| `image_download.paths.processed_dir` | `null` | stage 7 | Inherited processed dir. |
| `image_download.paths.image_dir` | `{data_dir}/images` | stage 7 | Image output root. |
| `image_download.paths.tile_partitioned_parquet_raw_metadata_dir` | `null` | stage 7 | Inherited stage 3 parquet source path. |
| `image_download.image_params.image_size` | `[256,427]` | stage 7 | Resize target `(w,h)`. |
| `image_download.image_params.call_limit` | `5` | stage 7 | Download attempts per image. |
| `image_download.image_params.sleep_time` | `5` | stage 7 | Backoff base seconds. |
| `image_download.image_params.allowed_connections` | `10000` | stage 7 | Connection quota. |
| `image_download.image_params.max_workers` | `16` | stage 7 | Thread worker count. |
| `image_download.image_params.batch_size` | `1000` | stage 7 | Async batch size. |
| `image_download.image_params.windows` | `false` | stage 7 | Windows loop policy toggle. |
| `image_download.image_params.org_save_true` | `false` | stage 7 | Save originals in addition to resized. |
| `image_download.image_params.random_seed` | `42` | stage 7 | Input parquet shuffle seed. |
| `image_download.execution.mode` | `sequential` | `image_download.sh` | Launcher mode (`array|sequential|parallel`). ⚠️ |
| `image_download.execution.num_jobs` | `10` | `image_download.sh` | Chunking and job fanout value. |

### `statistics_geographic_layers`

| Parameter | Default | Used by | What it controls |
|---|---:|---|---|
| `statistics_geographic_layers.params.zoom_level` | `null` | stage 8 | Inherited zoom. |
| `statistics_geographic_layers.params.seed` | `42` | stage 8 | Random seed for sharding order. |
| `statistics_geographic_layers.paths.data_dir` | `null` | stage 8 | Inherited data dir. |
| `statistics_geographic_layers.paths.processed_dir` | `null` | stage 8 | Inherited processed dir. |
| `statistics_geographic_layers.paths.stats_dir` | `{processed_dir}/stats` | stage 8/9 | Stats root directory. |
| `statistics_geographic_layers.paths.osm_partitioned_dir` | `null` | stage 8 | Inherited OSM partition dir. |
| `statistics_geographic_layers.paths.final_filtered_dir` | `{processed_dir}/final_filtered_metadata` | stage 8 | Input metadata directory for stage 8. ⚠️ |
| `statistics_geographic_layers.statistics.shared.highways` | `[motorway,trunk,primary,secondary,tertiary,unclassified,residential]` | stage 8/9 | Highway groups for metric generation. |
| `statistics_geographic_layers.statistics.shared.areas` | `[urban,rural]` | stage 8/9 | Area classes. |
| `statistics_geographic_layers.statistics.shared.road_types` | `[paved,unpaved]` | stage 8/9 | Surface classes. |
| `statistics_geographic_layers.statistics.shared.road_classes.motorway` | `[motorway,motorway_link]` | stage 8/9 | Tag map for motorway class. |
| `statistics_geographic_layers.statistics.shared.road_classes.trunk` | `[trunk,trunk_link]` | stage 8/9 | Tag map for trunk class. |
| `statistics_geographic_layers.statistics.shared.road_classes.primary` | `[primary,primary_link]` | stage 8/9 | Tag map for primary class. |
| `statistics_geographic_layers.statistics.shared.road_classes.secondary` | `[secondary,secondary_link]` | stage 8/9 | Tag map for secondary class. |
| `statistics_geographic_layers.statistics.shared.road_classes.tertiary` | `[tertiary,tertiary_link]` | stage 8/9 | Tag map for tertiary class. |
| `statistics_geographic_layers.statistics.shared.road_classes.unclassified` | `[unclassified]` | stage 8/9 | Tag map for unclassified class. |
| `statistics_geographic_layers.statistics.shared.road_classes.residential` | `[residential]` | stage 8/9 | Tag map for residential class. |
| `statistics_geographic_layers.statistics.geographic_layers.osm_distance` | `15` | stage 8 | Max OSM distance for selecting matches. |
| `statistics_geographic_layers.statistics.geographic_layers.pred_distance` | `10` | stage 8 | Prediction distance threshold. |
| `statistics_geographic_layers.statistics.geographic_layers.sigma` | `1` | stage 8 | Urban scoring parameter. |
| `statistics_geographic_layers.statistics.geographic_layers.score` | `0.8` | stage 8 | Urban scoring parameter. |
| `statistics_geographic_layers.statistics.geographic_layers.threshold` | `0.3` | stage 8 | Urban scoring threshold. |
| `statistics_geographic_layers.statistics.geographic_layers.max_workers` | `8` | stage 8 | Process pool worker count. |
| `statistics_geographic_layers.statistics.geographic_layers.data_input_pattern` | `data_*.parquet` | stage 8 | Input file glob pattern. |
| `statistics_geographic_layers.statistics.geographic_layers.urban_area_layers` | `[GHS_STAT_UCDB2015MT_GLOBE_R2019A,AFRICAPOLIS2020]` | stage 8/9 | Urban area layer labels. |
| `statistics_geographic_layers.statistics.geographic_layers.urban_area_cols` | `[ID_HDC_G0,agglosID]` | stage 8 | Urban area key columns. |

### `statistics_aggregation`

| Parameter | Default | Used by | What it controls |
|---|---:|---|---|
| `statistics_aggregation.params.zoom_level` | `null` | stage 9 | Inherited zoom. |
| `statistics_aggregation.paths.data_dir` | `null` | stage 9 | Inherited data dir. |
| `statistics_aggregation.paths.processed_dir` | `null` | stage 9 | Inherited processed dir. |
| `statistics_aggregation.paths.stats_dir` | `null` | stage 9 | Inherited stats dir. |
| `statistics_aggregation.paths.osm_saving_dir` | `null` | stage 9 | Inherited OSM intermediate path. |
| `statistics_aggregation.filenames.country_filename` | `null` | stage 9 | Inherited country file name. |
| `statistics_aggregation.filenames.continents_filename` | `null` | stage 9 | Inherited continents file path. |
| `statistics_aggregation.filenames.ghsl_filename` | `null` | stage 9 | Inherited GHSL filename. |
| `statistics_aggregation.filenames.africapolis_filename` | `null` | stage 9 | Inherited Africapolis filename. |
| `statistics_aggregation.statistics.shared` | `null` | stage 9 | Inherited shared metric definitions. |
| `statistics_aggregation.statistics.geographic_layers.urban_area_layers` | `null` | stage 9 | Inherited urban layer labels. |
| `statistics_aggregation.statistics.aggregation.urban_layer_cols` | `[ID_HDC_G0,agglosID]` | stage 9 | Urban aggregation key columns. |
| `statistics_aggregation.statistics.aggregation.memory_limit_gb` | `2010` | stage 9 | DuckDB memory limit in GB. ⚠️ |
| `statistics_aggregation.statistics.aggregation.number_of_cpus` | `64` | stage 9 | CPU count for worker/sub-thread planning. |
| `statistics_aggregation.statistics.aggregation.max_workers` | `16` | stage 9 | Process worker count. |
| `statistics_aggregation.statistics.aggregation.process_non_temporal_osm` | `false` | stage 9 | Enables optional non-temporal OSM rollup branch. |

### `dlr`

| Parameter | Default | Used by | What it controls |
|---|---:|---|---|
| `dlr.params.mly_key` | `null` | `dlr.py` | Inherited token. |
| `dlr.metadata_params.retries` | `null` | `dlr.py` | Inherited retries. |

Notes on non-obvious config behavior:
- `start.py` resolves `null` keys by scanning earlier sections only, in YAML order; later sections are never used as providers.
- relative config file paths are resolved relative to `research_code/start.py`, not the current shell working directory.
- CLI overrides are strict: unknown keys raise immediately.
- `statistics_geographic_layers` and `statistics_aggregation` get a transformed runtime config when script name is inferred from caller context.

## 8. Known Issues

1. **Hardcoded Python path in stage 6 launcher**
- Where: `research_code/find_and_get_nearest_osm_segments.sh`, top-level `PYTHON_BIN` assignment.
- What happens: launcher fails on machines without `/mnt/d//micromamba/envs/eren/python.exe`.
- Why: executable path is hardcoded instead of using environment discovery.
- Workaround: set `PYTHON_BIN="python"` (or your env path) before running.

2. **Import-time config side effects in aggregation module**
- Where: `research_code/statistics_aggregation.py`, module-level `_BOOT_CFG = load_config()` and `_METRICS = build_metric_catalog(...)`.
- What happens: importing module triggers config parsing immediately.
- Why: config/metric initialization is at module scope instead of `main()` or lazy init.
- Workaround: run as script in expected project context; avoid importing in environments where config is unavailable.

3. **Stage 8 input directory is not produced by earlier shell stages**
- Where: `research_code/statistics_geographic_layers.py` (`paths.final_filtered_dir`) and `research_code/config.yaml` (`statistics_geographic_layers.paths.final_filtered_dir`).
- What happens: stage 8 logs skip and exits when `data/processed/final_filtered_metadata` does not exist.
- Why: pipeline shell stages produce `intersected_filtered_metadata`, but stage 8 expects `final_filtered_metadata` path.
- Workaround: either create/populate `final_filtered_metadata` or point `statistics_geographic_layers.paths.final_filtered_dir` to the produced filtered directory.

4. **Local mode in stage 6 launcher is effectively sequential**
- Where: `research_code/find_and_get_nearest_osm_segments.sh`, local branch.
- What happens: script appends `$!` without backgrounding Python commands, so local branch does not parallelize as intended.
- Why: missing `&` on worker invocations in local loop.
- Workaround: use SLURM array mode or run multiple files manually in parallel from shell.

## 9. Contributing & Tests

Run tests:

```bash
# preferred if pytest is available
python -m pytest tests

# baseline runner used by repo test style
python -m unittest discover -s tests
```

What is covered:
- all pipeline workers and launch-critical helpers have unit tests
- heavy use of mocks for API, DuckDB, filesystem, and thread behavior
- strong coverage for retry/flush/thread-shutdown edge cases in metadata and image download logic

When adding a new stage, keep this checklist:
1. Add a new section in `research_code/config.yaml` in the correct stage order.
2. Use `start.py` + strict accessors (`require_path`, typed parsers) instead of ad hoc defaults.
3. Provide a shell launcher if the stage needs operational orchestration (local/HPC).
4. Make resume behavior explicit (mtime checks, existing-output checks, or documented overwrite policy).
5. Add tests for happy path, skip/resume behavior, and failure/retry behavior.
6. Avoid module-level side effects that run on import.
