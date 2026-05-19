"""Shared helpers for strict configuration access and value parsing."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable


class ConfigKeyError(KeyError):
    """Raised when a required configuration key is missing."""


def _path_to_str(path: Iterable[str]) -> str:
    return ".".join(path)


def require_key(mapping: dict, key: str, context: str) -> Any:
    if key not in mapping:
        raise ConfigKeyError(f"Missing required config key: {context}.{key}")
    return mapping[key]


def require_section(cfg: dict, section: str) -> dict:
    value = require_key(cfg, section, "config")
    if not isinstance(value, dict):
        raise ValueError(f"Config section must be a mapping: config.{section}")
    return value


def require_path(cfg: dict, *path: str) -> Any:
    if not path:
        raise ValueError("require_path requires at least one key")

    current: Any = cfg
    walked = []
    for key in path:
        walked.append(key)
        if not isinstance(current, dict):
            raise ValueError(f"Config path is not a mapping at: {_path_to_str(walked[:-1])}")
        if key not in current:
            raise ConfigKeyError(f"Missing required config key: {_path_to_str(walked)}")
        current = current[key]
    return current


def format_mapping_values(mapping: dict[str, Any], format_vars: dict[str, Any], context: str) -> dict[str, Any]:
    pending = dict(mapping)
    resolved = {}

    while pending:
        progressed = False
        for key in list(pending.keys()):
            value = pending[key]
            if not isinstance(value, str):
                resolved[key] = value
                format_vars[key] = value
                del pending[key]
                progressed = True
                continue

            try:
                formatted = value.format(**format_vars)
            except KeyError:
                continue

            resolved[key] = formatted
            format_vars[key] = formatted
            del pending[key]
            progressed = True

        if not progressed:
            unresolved_key = next(iter(pending))
            try:
                pending[unresolved_key].format(**format_vars)
            except KeyError as exc:
                raise KeyError(
                    f"Missing path format dependency '{exc.args[0]}' while formatting {context}.{unresolved_key}"
                ) from exc
            raise KeyError(f"Failed to format {context}.{unresolved_key}")

    return resolved


def parse_int(value: Any, field_name: str, min_value: int | None = None) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Config value must be an integer: {field_name}") from exc

    if min_value is not None and parsed < min_value:
        raise ValueError(f"Config value must be >= {min_value}: {field_name}")
    return parsed


def parse_bool(value: Any, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"1", "true", "t", "yes", "y", "on"}:
            return True
        if text in {"0", "false", "f", "no", "n", "off"}:
            return False
    raise ValueError(f"Config value must be a boolean-like value: {field_name}")


def parse_bool_with_default(value: Any, field_name: str, default: bool = False) -> bool:
    try:
        return parse_bool(value, field_name)
    except ValueError:
        return default


def parse_positive_int(value: Any, field_name: str, default: int) -> int:
    try:
        parsed = parse_int(value, field_name)
    except ValueError:
        parsed = default
    return max(1, parsed)


def parse_float(value: Any, field_name: str, min_value: float | None = None) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Config value must be a float: {field_name}") from exc

    if min_value is not None and parsed < min_value:
        raise ValueError(f"Config value must be >= {min_value}: {field_name}")
    return parsed


def parse_iso_datetime(value: Any, field_name: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"Config value must be an ISO datetime string: {field_name}")
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"Config value must be a valid ISO datetime string: {field_name}") from exc
