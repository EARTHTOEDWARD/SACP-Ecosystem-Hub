from __future__ import annotations

import pytest

from sacp_hub.adapters.sacp_api import SACPAPIAdapter
from sacp_hub.suite_bridge_contract import SUITE_HUB_BRIDGE_CONTRACT_VERSION


class _DummyResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


def _panel_export() -> dict:
    return {
        "provider": "sacp_suite",
        "bridge_kind": "panel_run",
        "bridge_contract_version": SUITE_HUB_BRIDGE_CONTRACT_VERSION,
        "run_id": "suite_panel_01",
        "export_hash": "sha256:" + "1" * 64,
        "suite_lineage": {"panel_run_id": "suite_panel_01"},
        "baseline_windows": [
            {
                "window_key": "pre_probe",
                "label": "pre_probe",
                "stream_kind": "baseline",
                "time_range": [0.0, 1.0],
                "points": [{"t": 0.0, "values": [0.1, 0.2, 0.3]}],
                "stats": {"mean_signal": 0.2, "l1_mean": 0.2, "point_count": 1.0},
            }
        ],
        "baseline_metrics": {
            "mean_signal": 0.2,
            "variance": 0.04,
            "instability": 0.12,
            "energy_gradient_proxy": 3.5,
        },
        "simulation": {"source": "suite_bridge", "sample_count": 24, "signal_energy_proxy": 0.31},
        "regime_summary": {"regime_id": "recovering"},
        "persistence_summary": {"status": "retained"},
        "challenge_summary": {"status": "stable_under_challenge"},
        "candidates": [
            {
                "candidate_id": "cand_bridge_01",
                "label": "impulse:vmem_core",
                "mechanism": "toward_recovering",
                "predicted_shift_score": 0.82,
                "confidence": 0.91,
                "suite_candidate_ref": {"candidate_id": "cand_bridge_01", "panel_run_id": "suite_panel_01"},
            }
        ],
    }


def _verification_export() -> dict:
    return {
        "provider": "sacp_suite",
        "bridge_kind": "verification_run",
        "bridge_contract_version": SUITE_HUB_BRIDGE_CONTRACT_VERSION,
        "run_id": "suite_verification_01",
        "export_hash": "sha256:" + "2" * 64,
        "suite_lineage": {"verification_run_id": "suite_verification_01"},
        "baseline": _panel_export(),
        "followup_windows": [
            {
                "window_key": "post_release",
                "label": "post_release",
                "stream_kind": "followup",
                "time_range": [1.0, 2.0],
                "points": [{"t": 1.0, "values": [0.05, 0.1, 0.15]}],
                "stats": {"mean_signal": 0.1, "l1_mean": 0.1, "point_count": 1.0},
            }
        ],
        "followup_metrics": {
            "mean_signal": 0.1,
            "variance": 0.02,
            "instability": 0.08,
            "energy_gradient_proxy": 2.0,
        },
        "selected_candidate": {"candidate_id": "cand_bridge_01"},
        "delta_report": {
            "baseline_metrics": _panel_export()["baseline_metrics"],
            "followup_metrics": {
                "mean_signal": 0.1,
                "variance": 0.02,
                "instability": 0.08,
                "energy_gradient_proxy": 2.0,
            },
            "delta": {
                "mean_signal": -0.1,
                "variance": -0.02,
                "instability": -0.04,
                "energy_gradient_proxy": -1.5,
            },
            "knocked_out_of_saddle": True,
        },
    }


def test_fetch_suite_bridge_export_accepts_valid_panel_export(monkeypatch: pytest.MonkeyPatch):
    adapter = SACPAPIAdapter(base_url="http://suite.test")
    monkeypatch.setattr("sacp_hub.adapters.sacp_api.requests.get", lambda *args, **kwargs: _DummyResponse(_panel_export()))

    payload = adapter.fetch_suite_bridge_export(
        {"provider": "sacp_suite", "bridge_kind": "panel_run", "run_id": "suite_panel_01"}
    )

    assert payload["bridge_contract_version"] == SUITE_HUB_BRIDGE_CONTRACT_VERSION
    assert payload["bridge_kind"] == "panel_run"
    assert payload["candidates"][0]["candidate_id"] == "cand_bridge_01"


def test_fetch_suite_bridge_export_accepts_valid_verification_export(monkeypatch: pytest.MonkeyPatch):
    adapter = SACPAPIAdapter(base_url="http://suite.test")
    monkeypatch.setattr("sacp_hub.adapters.sacp_api.requests.get", lambda *args, **kwargs: _DummyResponse(_verification_export()))

    payload = adapter.fetch_suite_bridge_export(
        {"provider": "sacp_suite", "bridge_kind": "verification_run", "run_id": "suite_verification_01"}
    )

    assert payload["bridge_contract_version"] == SUITE_HUB_BRIDGE_CONTRACT_VERSION
    assert payload["baseline"]["bridge_contract_version"] == SUITE_HUB_BRIDGE_CONTRACT_VERSION
    assert payload["delta_report"]["knocked_out_of_saddle"] is True


def test_fetch_suite_bridge_export_rejects_wrong_contract_version(monkeypatch: pytest.MonkeyPatch):
    adapter = SACPAPIAdapter(base_url="http://suite.test")
    bad = _panel_export()
    bad["bridge_contract_version"] = "broken.v0"
    monkeypatch.setattr("sacp_hub.adapters.sacp_api.requests.get", lambda *args, **kwargs: _DummyResponse(bad))

    with pytest.raises(ValueError, match="Invalid Suite bridge export contract"):
        adapter.fetch_suite_bridge_export({"provider": "sacp_suite", "bridge_kind": "panel_run", "run_id": "suite_panel_01"})


def test_fetch_suite_bridge_export_rejects_wrong_bridge_kind(monkeypatch: pytest.MonkeyPatch):
    adapter = SACPAPIAdapter(base_url="http://suite.test")
    bad = _panel_export()
    bad["bridge_kind"] = "verification_run"
    monkeypatch.setattr("sacp_hub.adapters.sacp_api.requests.get", lambda *args, **kwargs: _DummyResponse(bad))

    with pytest.raises(ValueError, match="Invalid Suite bridge export contract"):
        adapter.fetch_suite_bridge_export({"provider": "sacp_suite", "bridge_kind": "panel_run", "run_id": "suite_panel_01"})


def test_fetch_suite_bridge_export_rejects_malformed_payload(monkeypatch: pytest.MonkeyPatch):
    adapter = SACPAPIAdapter(base_url="http://suite.test")
    bad = _verification_export()
    bad.pop("baseline")
    monkeypatch.setattr("sacp_hub.adapters.sacp_api.requests.get", lambda *args, **kwargs: _DummyResponse(bad))

    with pytest.raises(ValueError, match="Invalid Suite bridge export contract"):
        adapter.fetch_suite_bridge_export(
            {"provider": "sacp_suite", "bridge_kind": "verification_run", "run_id": "suite_verification_01"}
        )


def test_create_suite_verification_from_panel_run_posts_expected_payload(monkeypatch: pytest.MonkeyPatch):
    seen: dict = {}

    def _post(url: str, json: dict, timeout: float):
        seen["url"] = url
        seen["json"] = json
        seen["timeout"] = timeout
        return _DummyResponse({"run_id": "suite_verification_created_01"})

    adapter = SACPAPIAdapter(base_url="http://suite.test")
    monkeypatch.setattr("sacp_hub.adapters.sacp_api.requests.post", _post)

    body = adapter.create_suite_verification_from_panel_run(
        panel_run_id="suite_panel_01",
        followup_points=[{"t": 0.0, "values": [0.1, 0.2, 0.3]}, {"t": 1.0, "values": [0.0, 0.1, 0.2]}],
        selected_candidate_id="cand_bridge_01",
        followup_source_kind="hub_followup",
        followup_metadata={"source": "bridge"},
    )

    assert body["run_id"] == "suite_verification_created_01"
    assert seen["url"] == "http://suite.test/api/v1/bcp/verification-runs/from-panel-run"
    assert seen["json"]["panel_run_id"] == "suite_panel_01"
    assert seen["json"]["selected_candidate_id"] == "cand_bridge_01"
    assert seen["json"]["followup_source_kind"] == "hub_followup"


def test_create_suite_intervention_request_from_panel_run_posts_expected_payload(monkeypatch: pytest.MonkeyPatch):
    seen: dict = {}

    def _post(url: str, json: dict, timeout: float):
        seen["url"] = url
        seen["json"] = json
        seen["timeout"] = timeout
        return _DummyResponse(
            {
                "run_id": "suite_request_01",
                "request_ref": {"artifact_id": "sha256:" + "4" * 64, "artifact_type": "sacp.bcp.intervention_request.v1"},
            }
        )

    adapter = SACPAPIAdapter(base_url="http://suite.test")
    monkeypatch.setattr("sacp_hub.adapters.sacp_api.requests.post", _post)

    body = adapter.create_suite_intervention_request_from_panel_run(
        panel_run_id="suite_panel_01",
        selected_candidate_id="cand_bridge_01",
        request_metadata={"source": "hub_execute_sim"},
    )

    assert body["run_id"] == "suite_request_01"
    assert seen["url"] == "http://suite.test/api/v1/bcp/intervention-requests/from-panel-run"
    assert seen["json"]["panel_run_id"] == "suite_panel_01"
    assert seen["json"]["selected_candidate_id"] == "cand_bridge_01"
    assert seen["json"]["request_metadata"]["source"] == "hub_execute_sim"
