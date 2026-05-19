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

