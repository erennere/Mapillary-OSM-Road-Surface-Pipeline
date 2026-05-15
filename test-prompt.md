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
- `research_code/statistics_geographic_layers.py`
  - runtime config defaulting
  - selected SQL fragment builders
  - metric catalog assembly
  - z14 tile parsing

Ranked coverage backlog (high → low):

1. `research_code/find_osm_segments.py`
   - `haversine`
   - distance symmetry, zero-distance, random coordinate pairs
2. `research_code/metadata_intersections_and_filtering.py`
   - `filtering_simple`
   - `filtering_RDP`
   - `finding_tiles_for_points`
   - `finding_tiles_list_for_urban_areas`
3. `research_code/statistics_geographic_layers.py`
   - `haversine`
   - `calculate_length`
   - `create_tile`
   - remaining SQL builder helpers
4. `research_code/get_nearest_osm_segments.py`
   - randomized threshold edge cases for `create_mask`
5. Integration-heavy modules still mostly uncovered:
   - `csv_to_parquet.py`
   - `find_osm_segments.py::calculate_distance`
   - `highways_sort.py`
   - `dlr.py`
   - `get_linestrings_from_tiles.py`

Testing rule for this repo workstream:

- Prefer seeded-random test inputs for helper logic.
- Prefer dependency-isolated unit tests with lightweight stubs over brittle integration tests.
- Validate with `python -m unittest discover -s tests -v`.

Working prompt:

> Continue from the highest-ranked pure helpers first. Use seeded random data in every new test module, keep imports dependency-isolated with stubs, and expand outward only after the helper-level risk is covered.
