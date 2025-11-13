"""Utilities for propagating request headers into LangGraph config."""

from __future__ import annotations

from fnmatch import fnmatch
from typing import Mapping

from .config_loader import get_http_config


def _get_patterns() -> tuple[list[str], list[str]]:
    http_cfg = get_http_config() or {}
    cfg = http_cfg.get("configurable_headers") or {}
    includes = cfg.get("includes") or cfg.get("include") or []
    excludes = cfg.get("excludes") or cfg.get("exclude") or []
    includes = [pat.lower() for pat in includes]
    excludes = [pat.lower() for pat in excludes]
    return includes, excludes


def _matches(patterns: list[str], value: str) -> bool:
    return any(fnmatch(value, pattern) for pattern in patterns)


def extract_configurable_headers(headers: Mapping[str, str]) -> dict[str, str]:
    includes, excludes = _get_patterns()
    if not includes and not excludes:
        return {}

    extracted: dict[str, str] = {}
    for key, value in headers.items():
        key_lower = key.lower()
        if excludes and _matches(excludes, key_lower):
            continue
        if includes and not _matches(includes, key_lower):
            continue
        extracted[key_lower] = value
    return extracted
