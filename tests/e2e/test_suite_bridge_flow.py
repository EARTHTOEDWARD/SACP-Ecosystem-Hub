from __future__ import annotations

from sacp_hub.suite_bridge_contract import SUITE_HUB_BRIDGE_CONTRACT_VERSION


def _points(offset: float, n: int = 24):
    return [{"t": float(i), "values": [offset + 0.02 * i, offset + 0.01 * i, offset + 0.03 * i]} for i in range(n)]


def _window(window_key: str, label: str, stream_kind: str, offset: float):
    points = _points(offset)
    mean_signal = sum(sum(row["values"]) / len(row["values"]) for row in points) / len(points)
    l1_mean = sum(sum(abs(v) for v in row["values"]) for row in points) / (len(points) * len(points[0]["values"]))
    return {
        "window_key": window_key,
        "label": label,
        "stream_kind": stream_kind,
        "time_range": [points[0]["t"], points[-1]["t"]],
        "points": points,
        "stats": {
            "mean_signal": float(mean_signal),
            "l1_mean": float(l1_mean),
            "point_count": float(len(points)),
        },
    }


def _panel_export(run_id: str) -> dict:
    return {
        "provider": "sacp_suite",
        "bridge_kind": "panel_run",
        "bridge_contract_version": SUITE_HUB_BRIDGE_CONTRACT_VERSION,
        "run_id": run_id,
        "export_hash": "sha256:" + "1" * 64,
        "suite_lineage": {
            "panel_run_id": run_id,
            "summary_ref": {"artifact_id": "sha256:" + "2" * 64, "artifact_type": "sacp.bcp.panel_run.v1"},
        },
        "baseline_windows": [
            _window("pre_probe", "pre_probe", "baseline", 0.0),
            _window("post_release", "post_release", "baseline", -0.05),
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
                "suite_candidate_ref": {"candidate_id": "cand_bridge_01", "panel_run_id": run_id},
            },
            {
                "candidate_id": "cand_bridge_02",
                "label": "dc_step:edge_pair",
                "mechanism": "preserve_steady",
                "predicted_shift_score": 0.41,
                "confidence": 0.67,
                "suite_candidate_ref": {"candidate_id": "cand_bridge_02", "panel_run_id": run_id},
            },
        ],
    }


def _verification_export(run_id: str, baseline_run_id: str) -> dict:
    return {
        "provider": "sacp_suite",
        "bridge_kind": "verification_run",
        "bridge_contract_version": SUITE_HUB_BRIDGE_CONTRACT_VERSION,
        "run_id": run_id,
        "export_hash": "sha256:" + "3" * 64,
        "suite_lineage": {
            "verification_run_id": run_id,
            "baseline_panel_run_id": baseline_run_id,
            "followup_panel_run_id": "follow_panel_01",
        },
        "baseline": _panel_export(baseline_run_id),
        "followup_windows": [
            _window("post_release", "post_release", "followup", -0.1),
            _window("post_challenge", "post_challenge", "followup", -0.12),
        ],
        "followup_metrics": {
            "mean_signal": 0.1,
            "variance": 0.02,
            "instability": 0.08,
            "energy_gradient_proxy": 2.0,
        },
        "selected_candidate": {
            "candidate_id": "cand_bridge_01",
            "predicted_regime_direction": "toward_recovering",
        },
        "delta_report": {
            "baseline_metrics": {
                "mean_signal": 0.2,
                "variance": 0.04,
                "instability": 0.12,
                "energy_gradient_proxy": 3.5,
            },
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
            "suite_context": {"status": "aligned"},
        },
    }


def test_bridge_baseline_advance_uses_suite_candidates(client_and_service, monkeypatch):
    client, service = client_and_service

    def _fetch_bridge_export(suite_bridge: dict) -> dict:
        assert suite_bridge["bridge_kind"] == "panel_run"
        return _panel_export(str(suite_bridge["run_id"]))

    def _create_request(**kwargs) -> dict:
        assert kwargs["panel_run_id"] == "suite_panel_01"
        assert kwargs["selected_candidate_id"] == "cand_bridge_01"
        return {
            "run_id": "suite_request_01",
            "request_ref": {"artifact_id": "sha256:" + "5" * 64, "artifact_type": "sacp.bcp.intervention_request.v1"},
        }

    def _execute_request(**kwargs) -> dict:
        assert kwargs["request_run_id"] == "suite_request_01"
        return {
            "run_id": "suite_execution_01",
            "execution_ref": {
                "artifact_id": "sha256:" + "8" * 64,
                "artifact_type": "sacp.bcp.intervention_execution.v1",
            },
            "executed_panel_run": {
                "run_id": "suite_panel_exec_01",
                "summary_ref": {"artifact_id": "sha256:" + "9" * 64, "artifact_type": "sacp.bcp.panel_run.v1"},
            },
            "execution": {"observed_effect": {"executed_regime": "recovering"}},
        }

    monkeypatch.setattr(service.sacp_adapter, "fetch_suite_bridge_export", _fetch_bridge_export)
    monkeypatch.setattr(service.sacp_adapter, "create_suite_intervention_request_from_panel_run", _create_request)
    monkeypatch.setattr(service.sacp_adapter, "create_suite_execution_from_intervention_request", _execute_request)

    created = client.post("/v1/sessions", json={"prompt": "bioelectric simulation intervention loop"}).json()
    session_id = created["session_id"]
    run_id = created["run_id"]

    ingest_resp = client.post(
        f"/v1/sessions/{session_id}/ingest",
        json={
            "stream_kind": "baseline",
            "suite_bridge": {"provider": "sacp_suite", "bridge_kind": "panel_run", "run_id": "suite_panel_01"},
            "metadata": {"source": "bridge"},
        },
    )
    assert ingest_resp.status_code == 200

    advance_resp = client.post(f"/v1/sessions/{session_id}/advance")
    assert advance_resp.status_code == 200
    assert advance_resp.json()["state"] == "awaiting_followup"

    candidate_artifact_id = service.sessions[session_id].stage_outputs["CANDIDATE_GENERATE"]
    candidate_artifact = service.runstore.load_artifact(run_id, candidate_artifact_id)
    assert candidate_artifact.data["suite_context"]["bridge_kind"] == "panel_run"
    assert candidate_artifact.data["candidates"][0]["candidate_id"] == "cand_bridge_01"
    assert candidate_artifact.data["candidates"][0]["suite_candidate_ref"]["panel_run_id"] == "suite_panel_01"
    execution_artifact_id = service.sessions[session_id].stage_outputs["EXECUTE_SIM"]
    execution_artifact = service.runstore.load_artifact(run_id, execution_artifact_id)
    assert execution_artifact.data["suite_execution_request"]["request_run_id"] == "suite_request_01"
    assert execution_artifact.data["suite_execution_request"]["request_ref"]["artifact_id"].startswith("sha256:")
    assert execution_artifact.data["suite_execution_run"]["execution_run_id"] == "suite_execution_01"
    assert execution_artifact.data["observed_effect"]["executed_regime"] == "recovering"


def test_bridge_verification_followup_completes_with_suite_lineage(client_and_service, monkeypatch):
    client, _service = client_and_service

    def _fetch_bridge_export(suite_bridge: dict) -> dict:
        if suite_bridge["bridge_kind"] == "panel_run":
            return _panel_export(str(suite_bridge["run_id"]))
        return _verification_export(str(suite_bridge["run_id"]), baseline_run_id="suite_panel_01")

    def _create_request(**kwargs) -> dict:
        return {
            "run_id": "suite_request_02",
            "request_ref": {"artifact_id": "sha256:" + "6" * 64, "artifact_type": "sacp.bcp.intervention_request.v1"},
        }

    def _execute_request(**kwargs) -> dict:
        return {
            "run_id": "suite_execution_02",
            "execution_ref": {
                "artifact_id": "sha256:" + "a" * 64,
                "artifact_type": "sacp.bcp.intervention_execution.v1",
            },
            "executed_panel_run": {
                "run_id": "suite_panel_exec_02",
                "summary_ref": {"artifact_id": "sha256:" + "b" * 64, "artifact_type": "sacp.bcp.panel_run.v1"},
            },
            "execution": {"observed_effect": {"executed_regime": "recovering"}},
        }

    monkeypatch.setattr(_service.sacp_adapter, "fetch_suite_bridge_export", _fetch_bridge_export)
    monkeypatch.setattr(_service.sacp_adapter, "create_suite_intervention_request_from_panel_run", _create_request)
    monkeypatch.setattr(_service.sacp_adapter, "create_suite_execution_from_intervention_request", _execute_request)

    created = client.post("/v1/sessions", json={"prompt": "bioelectric simulation intervention loop"}).json()
    session_id = created["session_id"]

    client.post(
        f"/v1/sessions/{session_id}/ingest",
        json={
            "stream_kind": "baseline",
            "suite_bridge": {"provider": "sacp_suite", "bridge_kind": "panel_run", "run_id": "suite_panel_01"},
            "metadata": {"source": "bridge"},
        },
    )
    advance_resp = client.post(f"/v1/sessions/{session_id}/advance")
    assert advance_resp.status_code == 200
    assert advance_resp.json()["state"] == "awaiting_followup"

    follow_resp = client.post(
        f"/v1/sessions/{session_id}/followup",
        json={
            "suite_bridge": {"provider": "sacp_suite", "bridge_kind": "verification_run", "run_id": "suite_verification_01"},
            "metadata": {"source": "bridge"},
        },
    )
    assert follow_resp.status_code == 200
    assert follow_resp.json()["state"] == "completed"

    report = client.get(f"/v1/sessions/{session_id}/report")
    assert report.status_code == 200
    body = report.json()
    assert body["conformance"]["status"] == "passed"
    assert body["intervention"]["selected_candidate_id"] == "cand_bridge_01"
    assert body["delta_report"]["knocked_out_of_saddle"] is True
    assert body["suite_lineage"]["baseline"]["bridge_contract_version"] == SUITE_HUB_BRIDGE_CONTRACT_VERSION
    assert body["suite_lineage"]["baseline"]["suite_run_id"] == "suite_panel_01"
    assert body["suite_lineage"]["execution"]["request_run_id"] == "suite_request_02"
    assert body["suite_lineage"]["execution"]["execution_run_id"] == "suite_execution_02"
    assert body["suite_lineage"]["followup"]["suite_run_id"] == "suite_verification_01"

    report_view = client.get(f"/v1/sessions/{session_id}/report/view")
    assert report_view.status_code == 200
    assert "Suite Lineage" in report_view.text
    assert "suite_request_02" in report_view.text
    assert "suite_execution_02" in report_view.text


def test_bridge_panel_followup_points_auto_create_suite_verification_run(client_and_service, monkeypatch):
    client, service = client_and_service

    def _fetch_bridge_export(suite_bridge: dict) -> dict:
        if suite_bridge["bridge_kind"] == "panel_run":
            return _panel_export(str(suite_bridge["run_id"]))
        return _verification_export(str(suite_bridge["run_id"]), baseline_run_id="suite_panel_01")

    def _create_suite_verification_from_panel_run(**kwargs) -> dict:
        assert kwargs["panel_run_id"] == "suite_panel_01"
        assert kwargs["selected_candidate_id"] == "cand_bridge_01"
        assert len(kwargs["followup_points"]) == 24
        assert kwargs["followup_metadata"]["request_run_id"] == "suite_request_03"
        return {"run_id": "suite_verification_auto_01"}

    def _create_request(**kwargs) -> dict:
        return {
            "run_id": "suite_request_03",
            "request_ref": {"artifact_id": "sha256:" + "7" * 64, "artifact_type": "sacp.bcp.intervention_request.v1"},
        }

    def _execute_request(**kwargs) -> dict:
        return {
            "run_id": "suite_execution_03",
            "execution_ref": {
                "artifact_id": "sha256:" + "c" * 64,
                "artifact_type": "sacp.bcp.intervention_execution.v1",
            },
            "executed_panel_run": {
                "run_id": "suite_panel_exec_03",
                "summary_ref": {"artifact_id": "sha256:" + "d" * 64, "artifact_type": "sacp.bcp.panel_run.v1"},
            },
            "execution": {"observed_effect": {"executed_regime": "recovering"}},
        }

    monkeypatch.setattr(service.sacp_adapter, "fetch_suite_bridge_export", _fetch_bridge_export)
    monkeypatch.setattr(service.sacp_adapter, "create_suite_intervention_request_from_panel_run", _create_request)
    monkeypatch.setattr(service.sacp_adapter, "create_suite_execution_from_intervention_request", _execute_request)
    monkeypatch.setattr(
        service.sacp_adapter,
        "create_suite_verification_from_panel_run",
        _create_suite_verification_from_panel_run,
    )

    created = client.post("/v1/sessions", json={"prompt": "bioelectric simulation intervention loop"}).json()
    session_id = created["session_id"]

    client.post(
        f"/v1/sessions/{session_id}/ingest",
        json={
            "stream_kind": "baseline",
            "suite_bridge": {"provider": "sacp_suite", "bridge_kind": "panel_run", "run_id": "suite_panel_01"},
            "metadata": {"source": "bridge"},
        },
    )
    advance_resp = client.post(f"/v1/sessions/{session_id}/advance")
    assert advance_resp.status_code == 200
    assert advance_resp.json()["state"] == "awaiting_followup"

    follow_resp = client.post(
        f"/v1/sessions/{session_id}/followup",
        json={"points": _points(-0.1), "metadata": {"source": "synthetic_followup"}},
    )
    assert follow_resp.status_code == 200
    assert follow_resp.json()["state"] == "completed"

    report = client.get(f"/v1/sessions/{session_id}/report")
    assert report.status_code == 200
    body = report.json()
    assert body["suite_lineage"]["baseline"]["suite_run_id"] == "suite_panel_01"
    assert body["suite_lineage"]["execution"]["request_run_id"] == "suite_request_03"
    assert body["suite_lineage"]["execution"]["execution_run_id"] == "suite_execution_03"
    assert body["suite_lineage"]["followup"]["suite_run_id"] == "suite_verification_auto_01"
    assert body["intervention"]["selected_candidate_id"] == "cand_bridge_01"
    assert body["delta_report"]["knocked_out_of_saddle"] is True
