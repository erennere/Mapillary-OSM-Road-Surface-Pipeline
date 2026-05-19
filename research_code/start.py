"""Public config API for script runtime resolution and strict config access."""

import copy
import inspect
import os
from pathlib import Path
from typing import Any

import yaml

from config_utils import (
    format_mapping_values,
    parse_bool,
    parse_bool_with_default,
    parse_float,
    parse_int,
    parse_iso_datetime,
    parse_positive_int,
    require_path,
    require_section,
)


__all__ = [
    "ConfigResolutionError",
    "load_config",
    "resolve_mapillary_token",
    "load_statistics_aggregation_runtime_config",
    "load_statistics_runtime_config",
    "parse_bool",
    "parse_bool_with_default",
    "parse_float",
    "parse_int",
    "parse_iso_datetime",
    "parse_positive_int",
    "require_path",
    "require_section",
    "resolve_config",
]


_MISSING = object()


def resolve_mapillary_token(config_token: str, env_var_name: str = "MAPILLARY_ACCESS_TOKEN") -> str:
    token = (config_token or "").strip()
    if token and token != "__ENV_MAPILLARY_ACCESS_TOKEN__":
        return token

    env_token = os.environ.get(env_var_name, "").strip()
    if env_token:
        return env_token

    raise ValueError(
        "Mapillary token is missing. Set get_linestrings_from_tiles.params.mly_key "
        f"or define {env_var_name}."
    )


class ConfigResolutionError(KeyError):
    def __init__(self, script_name: str, key: str | None, message: str):
        self.script_name = script_name
        self.key = key
        super().__init__(message)


def _lookup_path(mapping: dict[str, Any], path: tuple[str, ...]) -> Any:
    current: Any = mapping
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return _MISSING
        current = current[key]
    return current


def _ordered_script_names(raw_config: dict[str, Any]) -> list[str]:
    return list(raw_config.keys())


def _find_owner_value(script_name: str, path: tuple[str, ...], raw_config: dict[str, Any]) -> Any:
    for candidate_name in _ordered_script_names(raw_config):
        if candidate_name == script_name:
            break
        candidate_value = _lookup_path(raw_config[candidate_name], path)
        if candidate_value is not _MISSING and candidate_value is not None:
            return copy.deepcopy(candidate_value)
    return _MISSING


def _merge_cli_overrides(base: dict[str, Any], overrides: dict[str, Any], path: tuple[str, ...]) -> None:
    for key, value in overrides.items():
        current_path = path + (key,)
        dotted_path = ".".join(current_path)
        if key not in base:
            raise KeyError(f"Unknown CLI override key '{dotted_path}'")

        current_value = base[key]
        if isinstance(value, dict) and isinstance(current_value, dict):
            _merge_cli_overrides(current_value, value, current_path)
            continue

        base[key] = copy.deepcopy(value)


def _resolve_node(script_name: str, node: Any, path: tuple[str, ...], raw_config: dict[str, Any]) -> Any:
    if node is None:
        owner_value = _find_owner_value(script_name, path, raw_config)
        if owner_value is _MISSING:
            dotted_path = ".".join(path)
            raise ConfigResolutionError(
                script_name,
                dotted_path,
                f"Config key '{dotted_path}' in section '{script_name}' could not be resolved from any section.",
            )
        return owner_value

    if isinstance(node, dict):
        resolved = {}
        for key, value in node.items():
            resolved[key] = _resolve_node(script_name, value, path + (key,), raw_config)
        return resolved

    return copy.deepcopy(node)


def _format_path_values(cfg: dict[str, Any]) -> None:
    if "paths" not in cfg:
        return

    paths = cfg["paths"]
    if not isinstance(paths, dict):
        raise TypeError("Config section 'paths' must be a mapping")

    formatted_paths = format_mapping_values(paths, {}, "config.paths")
    cfg["paths"] = formatted_paths

    if "filenames" not in cfg:
        return

    filenames = cfg["filenames"]
    if not isinstance(filenames, dict):
        raise TypeError("Config section 'filenames' must be a mapping")

    cfg["filenames"] = format_mapping_values(filenames, dict(formatted_paths), "config.filenames")


def _validate_no_none(script_name: str, node: Any, path: tuple[str, ...]) -> None:
    if node is None:
        dotted_path = ".".join(path)
        raise ConfigResolutionError(
            script_name,
            dotted_path,
            f"Config key '{dotted_path}' in section '{script_name}' resolved to null.",
        )

    if isinstance(node, dict):
        for key, value in node.items():
            _validate_no_none(script_name, value, path + (key,))


def _infer_script_name() -> str:
    caller_frame = inspect.stack()[2]
    return Path(caller_frame.filename).stem


def _resolve_config_path(filepath: str) -> Path:
    config_path = Path(filepath)
    if config_path.is_absolute():
        return config_path
    return Path(__file__).resolve().parent / config_path


def _build_inferred_runtime_config(script_name: str, cfg: dict[str, Any]) -> dict[str, Any]:
    if script_name == "statistics_geographic_layers":
        runtime_cfg = load_statistics_runtime_config(cfg)
        runtime_cfg["statistics"] = copy.deepcopy(require_section(cfg, "statistics"))
        return runtime_cfg

    if script_name == "statistics_aggregation":
        runtime_cfg = load_statistics_aggregation_runtime_config(cfg)
        runtime_cfg["statistics"] = copy.deepcopy(require_section(cfg, "statistics"))
        return runtime_cfg

    return cfg


def resolve_config(
    script_name: str,
    raw_config: dict[str, Any],
    cli_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if script_name not in raw_config:
        available = ", ".join(_ordered_script_names(raw_config))
        raise ConfigResolutionError(
            script_name,
            None,
            f"Config section '{script_name}' is missing. Available sections: {available}",
        )

    script_cfg = raw_config[script_name]
    if not isinstance(script_cfg, dict):
        raise TypeError(f"Config section '{script_name}' must be a mapping")

    resolved_script_cfg = copy.deepcopy(script_cfg)
    if cli_overrides is not None:
        if not isinstance(cli_overrides, dict):
            raise TypeError("CLI overrides must be a mapping")
        _merge_cli_overrides(resolved_script_cfg, cli_overrides, ())

    resolved = _resolve_node(script_name, resolved_script_cfg, (), raw_config)
    _format_path_values(resolved)
    _validate_no_none(script_name, resolved, ())
    return resolved


def load_config(
    filepath: str = "./config.yaml",
    script_name: str | None = None,
    cli_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config_path = _resolve_config_path(filepath)
    with open(config_path, "r", encoding="utf-8") as f:
        raw_config = yaml.safe_load(f)

    if not isinstance(raw_config, dict):
        raise TypeError("Config root must be a mapping of script sections")

    inferred_script_name = script_name is None
    resolved_script_name = script_name or _infer_script_name()
    resolved_cfg = resolve_config(resolved_script_name, raw_config, cli_overrides=cli_overrides)

    if inferred_script_name:
        return _build_inferred_runtime_config(resolved_script_name, resolved_cfg)

    return resolved_cfg


def load_statistics_runtime_config(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return strict runtime settings for the statistics_geographic_layers stage."""
    if cfg is None:
        cfg = load_config(script_name="statistics_geographic_layers")

    selected_results_dir = os.path.join(
        os.path.abspath(require_path(cfg, "paths", "stats_dir")),
        "geographic_layers",
    )

    max_workers = parse_int(
        require_path(cfg, "statistics", "geographic_layers", "max_workers"),
        "statistics.geographic_layers.max_workers",
        min_value=1,
    )

    return {
        "seed": parse_int(require_path(cfg, "params", "seed"), "params.seed"),
        "osm_distance": parse_int(
            require_path(cfg, "statistics", "geographic_layers", "osm_distance"),
            "statistics.geographic_layers.osm_distance",
            min_value=0,
        ),
        "pred_distance": parse_int(
            require_path(cfg, "statistics", "geographic_layers", "pred_distance"),
            "statistics.geographic_layers.pred_distance",
            min_value=0,
        ),
        "sigma": parse_float(
            require_path(cfg, "statistics", "geographic_layers", "sigma"),
            "statistics.geographic_layers.sigma",
            min_value=0.0,
        ),
        "score": parse_float(
            require_path(cfg, "statistics", "geographic_layers", "score"),
            "statistics.geographic_layers.score",
            min_value=0.0,
        ),
        "threshold": parse_float(
            require_path(cfg, "statistics", "geographic_layers", "threshold"),
            "statistics.geographic_layers.threshold",
            min_value=0.0,
        ),
        "max_workers": max_workers,
        "data_input_pattern": require_path(cfg, "statistics", "geographic_layers", "data_input_pattern"),
        "osm_partitioned_dir": os.path.abspath(require_path(cfg, "paths", "osm_partitioned_dir")),
        "final_filtered_dir": os.path.abspath(require_path(cfg, "paths", "final_filtered_dir")),
        "results_dir": selected_results_dir,
        "urban_area_layers": require_path(cfg, "statistics", "geographic_layers", "urban_area_layers"),
        "urban_area_cols": require_path(cfg, "statistics", "geographic_layers", "urban_area_cols"),
        "zoom_level": parse_int(require_path(cfg, "params", "zoom_level"), "params.zoom_level", min_value=1),
    }


def load_statistics_aggregation_runtime_config(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return strict runtime settings for the statistics_aggregation stage."""
    if cfg is None:
        cfg = load_config(script_name="statistics_aggregation")

    max_workers = parse_int(
        require_path(cfg, "statistics", "aggregation", "max_workers"),
        "statistics.aggregation.max_workers",
        min_value=1,
    )
    stats_dir = os.path.abspath(require_path(cfg, "paths", "stats_dir"))
    processed_dir = require_path(cfg, "paths", "processed_dir")
    country_filename = require_path(cfg, "filenames", "country_filename")
    continents_filename = require_path(cfg, "filenames", "continents_filename")
    ghsl_filename = require_path(cfg, "filenames", "ghsl_filename")
    africapolis_filename = require_path(cfg, "filenames", "africapolis_filename")

    runtime_cfg = {
        "osm_file_pattern": require_path(cfg, "paths", "osm_saving_dir"),
        "results_dir": os.path.join(stats_dir, "geographic_layers"),
        "results_dir_compiled": os.path.join(stats_dir, "summary"),
        "urban_areas_dir": processed_dir,
        "country_layer": os.path.abspath(os.path.join(processed_dir, f"intersected_{country_filename}")),
        "continent_layer": os.path.abspath(continents_filename),
        "urban_layers": [
            f"country_intersected_intersected_{ghsl_filename.replace('.gpkg', '.parquet')}",
            f"country_intersected_intersected_{africapolis_filename.replace('.shp', '.parquet')}",
        ],
        "urban_layer_cols": require_path(cfg, "statistics", "aggregation", "urban_layer_cols"),
        "urban_areas": require_path(cfg, "statistics", "geographic_layers", "urban_area_layers"),
        "zoom_level": parse_int(require_path(cfg, "params", "zoom_level"), "params.zoom_level", min_value=1),
        "memory_limit_gb": parse_int(
            require_path(cfg, "statistics", "aggregation", "memory_limit_gb"),
            "statistics.aggregation.memory_limit_gb",
            min_value=1,
        ),
        "number_of_cpus": parse_int(
            require_path(cfg, "statistics", "aggregation", "number_of_cpus"),
            "statistics.aggregation.number_of_cpus",
            min_value=1,
        ),
        "max_workers": max_workers,
        "process_non_temporal_osm": parse_bool(
            require_path(cfg, "statistics", "aggregation", "process_non_temporal_osm"),
            "statistics.aggregation.process_non_temporal_osm",
        ),
    }
    runtime_cfg["sub_threads"] = max(1, runtime_cfg["number_of_cpus"] // max_workers)
    return runtime_cfg
