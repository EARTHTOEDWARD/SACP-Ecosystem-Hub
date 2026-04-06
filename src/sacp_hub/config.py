from __future__ import annotations

import os
from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_runs_root() -> Path:
    env = os.getenv("HUB_RUNS_DIR")
    if env:
        return Path(env).expanduser().resolve()
    return repo_root() / "var" / "runs"


def default_workspace_source() -> Path:
    return Path(os.getenv("SACP_WORKSPACE_JSON", "/Users/edward/SACP SUITE/WORKSPACE.json"))


def default_osm_root() -> Path:
    return Path(os.getenv("OSM_ROOT", "/Users/edward/Operating System for Measurements OSM"))


def default_sacp_api_base() -> str:
    return os.getenv("SACP_API_BASE_URL", "http://127.0.0.1:8000")
