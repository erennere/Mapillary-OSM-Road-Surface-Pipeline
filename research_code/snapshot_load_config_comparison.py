"""Create side-by-side YAML snapshots for old and current load_config behavior.

This script reconstructs:
1) The old flat load_config output from a historical commit (3-4 days old), and
2) The current section-scoped output by resolving every section in config order.
"""

from __future__ import annotations

import argparse
import copy
import subprocess
from pathlib import Path
from typing import Any

import yaml

from start import resolve_config


def _git_show(repo_root: Path, spec: str) -> str:
    result = subprocess.run(
        ["git", "show", spec],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def _old_load_config_from_mapping(raw_cfg: dict[str, Any]) -> dict[str, Any]:
    """Recreate load_config behavior used in commit e047d8a."""
    cfg = copy.deepcopy(raw_cfg)
    data_dir = cfg["paths"]["data_dir"]

    def format_path_processed_dir(value: Any) -> Any:
        if isinstance(value, str):
            return value.format(data_dir=data_dir)
        return value

    processed_dir = format_path_processed_dir(cfg["paths"].get("processed_dir", data_dir))
    starter_dir = format_path_processed_dir(cfg["paths"].get("starter_dir", data_dir))

    def format_path(value: Any) -> Any:
        if isinstance(value, str):
            return value.format(
                data_dir=data_dir,
                processed_dir=processed_dir,
                starter_dir=starter_dir,
            )
        return value

    for key, value in cfg["paths"].items():
        cfg["paths"][key] = format_path(value)
    for key, value in cfg["filenames"].items():
        cfg["filenames"][key] = format_path(value)

    return cfg


def _resolve_all_current_sections(raw_cfg: dict[str, Any]) -> dict[str, Any]:
    resolved: dict[str, Any] = {}
    for section_name in raw_cfg:
        resolved[section_name] = resolve_config(section_name, raw_cfg)
    return resolved


def _sorted_mapping(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _sorted_mapping(value[key]) for key in sorted(value.keys())}
    if isinstance(value, list):
        return [_sorted_mapping(item) for item in value]
    return value


def _write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(payload, handle, sort_keys=False, allow_unicode=False)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Snapshot old and current load_config outputs into two YAML files.",
    )
    parser.add_argument(
        "--old-commit",
        default="e047d8a",
        help="Historical commit hash to reconstruct the old load_config output.",
    )
    parser.add_argument(
        "--old-output",
        default="research_code/old_load_config_snapshot.yaml",
        help="Path for old-load_config snapshot YAML.",
    )
    parser.add_argument(
        "--current-output",
        default="research_code/current_load_config_all_sections_snapshot.yaml",
        help="Path for current all-sections snapshot YAML.",
    )
    args = parser.parse_args()

    script_path = Path(__file__).resolve()
    repo_root = script_path.parent.parent

    old_config_text = _git_show(repo_root, f"{args.old_commit}:research_code/config.yaml")
    old_raw = yaml.safe_load(old_config_text)
    if not isinstance(old_raw, dict):
        raise TypeError("Historical config must be a mapping")

    current_config_path = repo_root / "research_code" / "config.yaml"
    with current_config_path.open("r", encoding="utf-8") as handle:
        current_raw = yaml.safe_load(handle)
    if not isinstance(current_raw, dict):
        raise TypeError("Current config must be a mapping")

    old_snapshot = _sorted_mapping(_old_load_config_from_mapping(old_raw))
    current_snapshot = _sorted_mapping(_resolve_all_current_sections(current_raw))

    old_output_path = repo_root / args.old_output
    current_output_path = repo_root / args.current_output

    _write_yaml(old_output_path, old_snapshot)
    _write_yaml(current_output_path, current_snapshot)

    print(f"Old snapshot written to: {old_output_path}")
    print(f"Current snapshot written to: {current_output_path}")


if __name__ == "__main__":
    main()
