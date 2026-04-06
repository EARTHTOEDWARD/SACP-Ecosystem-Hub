from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sacp_hub.api import app
from sacp_hub.service import HubService


@pytest.fixture()
def runs_root(tmp_path: Path) -> Path:
    return tmp_path / "runs"


@pytest.fixture()
def service(runs_root: Path) -> HubService:
    return HubService(runs_root=runs_root)


@pytest.fixture()
def client_and_service(monkeypatch: pytest.MonkeyPatch, runs_root: Path):
    svc = HubService(runs_root=runs_root)
    monkeypatch.setattr("sacp_hub.api._service", svc)
    with TestClient(app) as client:
        yield client, svc
