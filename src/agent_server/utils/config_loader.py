"""Shared helpers for loading aegra/langgraph configuration files."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Tuple


def _candidate_paths(default_path: str | Path | None = None) -> list[Path]:
    """Return config lookup order matching LangGraphService semantics."""

    candidates: list[Path] = []
    env_path = os.getenv("AEGRA_CONFIG")
    if env_path:
        candidates.append(Path(env_path))

    if default_path:
        candidates.append(Path(default_path))

    candidates.append(Path("aegra.json"))
    candidates.append(Path("langgraph.json"))
    return candidates


def resolve_config_path(default_path: str | Path | None = None) -> Path:
    """Resolve the first existing configuration file from known locations."""

    for candidate in _candidate_paths(default_path):
        if candidate and candidate.exists():
            return candidate.resolve()
    raise ValueError(
        "Configuration file not found. Expected one of AEGRA_CONFIG, ./aegra.json, or ./langgraph.json"
    )


@lru_cache(maxsize=1)
def load_project_config(
    default_path: str | Path | None = None,
) -> Tuple[dict[str, Any], Path]:
    """Load and cache the project config + resolved path."""

    config_path = resolve_config_path(default_path)
    with config_path.open() as fh:
        data = json.load(fh)
    return data, config_path


def get_http_config(default_path: str | Path | None = None) -> dict[str, Any] | None:
    """Return the optional HTTP config section from project config."""

    config, _ = load_project_config(default_path)
    return config.get("http")
