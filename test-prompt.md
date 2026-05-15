# Test Coverage Prompt

Current verified coverage:

- `research_code/start.py::load_config`
  - path interpolation across configured directories
  - preservation of non-string config values
- `research_code/create_tiles.py::get_tiles_from_polygon`
  - polygon/world-bounds behavior
  - generated tile/id/x/y/z columns
- `research_code/get_nearest_osm_segments.py`
  - `create_mask`
  - `extract_first`
  - `process_one_file` query assembly, DuckDB function registration, cleanup/error handling
- `research_code/statistics_geographic_layers.py`
  - runtime config defaulting
  - selected SQL fragment builders
  - metric catalog assembly
  - z14 tile parsing
- `research_code/find_osm_segments.py`
  - `haversine`
  - `calculate_distance` query assembly, DuckDB function registration, cleanup/error handling

Ranked coverage backlog (high → low):

1. `research_code/statistics_geographic_layers.py`
   - `urban_query`
   - `process_file`
   - broader query-assembly validation with seeded-random parameters
2. `research_code/find_osm_segments.py`
   - `main`
   - path selection, updated-after skipping, and dispatch behavior
3. `research_code/get_nearest_osm_segments.py`
   - `main`
   - path selection, updated-after skipping, and dispatch behavior
4. `research_code/metadata_intersections_and_filtering.py`
   - integration-style helpers:
     - `download_overture_maps`
     - `intersection`
     - `intersections_with_metadata`
5. Integration-heavy modules still mostly uncovered:
   - `csv_to_parquet.py`
   - `highways_sort.py`
   - `dlr.py`
   - `get_linestrings_from_tiles.py`

Testing rule for this repo workstream:

- Prefer seeded-random test inputs for helper logic.
- Prefer dependency-isolated unit tests with lightweight stubs over brittle integration tests.
- Validate with `python -m unittest discover -s tests -v`.

Working prompt:

> Continue from the highest-ranked pure helpers first. Use seeded random data in every new test module, keep imports dependency-isolated with stubs, and expand outward only after the helper-level risk is covered.
