from __future__ import annotations

import json
from pathlib import Path


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _make_maxwell_run(
    run_dir: Path,
    *,
    run_id: str = "mx_import_001",
    mu_grid_count: int = 3,
    series_count: int = 2,
    boundary_count: int = 2,
    certificate_count: int = 2,
    rollout_count: int = 2,
    feasible_mu: int = 2,
) -> Path:
    manifest = {
        "run_id": run_id,
        "system": {"name": "example4_maxwell_torus", "version": "v0"},
        "artifacts": [
            {"path": "atlas.json"},
            {"path": "boundaries.json"},
            {"path": "gate_rollout.json"},
            {"path": "olsta_panel.json"},
            {"path": "artifacts/holonomy_ledger.example4_proxy_cycle_basis.v0.json"},
        ],
    }
    _write_json(run_dir / "run_manifest.json", manifest)
    _write_json(
        run_dir / "atlas.json",
        {
            "mu_grid": [round(0.2 + 0.2 * idx, 3) for idx in range(mu_grid_count)],
            "series": [
                (
                    {"em_dynamics_v0": {}, "transport_v0": {}, "operator_shadow_v1": {}}
                    if idx == 0
                    else {"em_dynamics_v0": {}, "triad_law4_v1": {}}
                )
                for idx in range(series_count)
            ],
        },
    )
    _write_json(
        run_dir / "boundaries.json",
        {
            "boundaries": [
                (
                    {"temporal_gauge_certificate_ref": f"certificates/temporal_gauge_certificate.boundary_{idx:03d}.v0.json"}
                    if idx < certificate_count
                    else {}
                )
                for idx in range(boundary_count)
            ]
        },
    )
    _write_json(
        run_dir / "gate_rollout.json",
        {"policy": {"gate_mode": "olsta_min"}, "rollout": [{"t_index": idx} for idx in range(rollout_count)]},
    )
    _write_json(run_dir / "olsta_panel.json", {"summary": {"n_feasible_mu": feasible_mu}})
    return run_dir / "run_manifest.json"


def test_import_maxwell_run_seeds_baseline_and_advances(client_and_service, tmp_path: Path):
    client, service = client_and_service
    manifest_path = _make_maxwell_run(tmp_path / "maxwell_run")

    imported = client.post(
        "/v1/external/maxwell/import",
        json={"manifest_path": str(manifest_path), "context": {"source": "pytest"}},
    )
    assert imported.status_code == 200
    body = imported.json()
    assert body["imported_run_id"] == "mx_import_001"
    assert body["state"] == "running"
    assert body["route_plan"]["summary"]["source"] == "maxwell"

    session = service.sessions[body["session_id"]]
    assert "INTAKE" in session.completed_stages
    assert "BASELINE_ANALYZE" in session.completed_stages

    baseline_artifact = service.runstore.load_artifact(body["run_id"], body["baseline_artifact_id"])
    assert baseline_artifact.artifact_type == "hub.bioelectric.baseline_analysis.v1"
    assert baseline_artifact.data["window_ids"] == []
    assert baseline_artifact.data["metrics"]["mean_signal"] == 2.0
    assert baseline_artifact.data["metrics"]["variance"] == 3.0
    assert baseline_artifact.data["metrics"]["instability"] == 4.0
    assert baseline_artifact.data["metrics"]["energy_gradient_proxy"] == 7.0
    assert baseline_artifact.data["simulation"]["source"] == "maxwell"
    assert baseline_artifact.data["suite_context"]["source"] == "maxwell"

    advanced = client.post(f"/v1/sessions/{body['session_id']}/advance")
    assert advanced.status_code == 200
    assert advanced.json()["state"] == "awaiting_followup"


def test_import_maxwell_run_rejects_missing_manifest(client_and_service):
    client, _service = client_and_service

    imported = client.post(
        "/v1/external/maxwell/import",
        json={"manifest_path": "/tmp/does-not-exist/run_manifest.json"},
    )
    assert imported.status_code == 400
    assert "Missing Maxwell manifest" in imported.json()["detail"]


def test_imported_maxwell_session_accepts_followup_manifest_and_completes(client_and_service, tmp_path: Path):
    client, service = client_and_service
    baseline_manifest = _make_maxwell_run(
        tmp_path / "maxwell_baseline",
        run_id="mx_baseline_001",
        mu_grid_count=4,
        series_count=3,
        boundary_count=3,
        certificate_count=2,
        rollout_count=3,
        feasible_mu=2,
    )
    followup_manifest = _make_maxwell_run(
        tmp_path / "maxwell_followup",
        run_id="mx_followup_001",
        mu_grid_count=2,
        series_count=1,
        boundary_count=1,
        certificate_count=1,
        rollout_count=1,
        feasible_mu=1,
    )

    imported = client.post("/v1/external/maxwell/import", json={"manifest_path": str(baseline_manifest)})
    assert imported.status_code == 200
    session_id = imported.json()["session_id"]
    run_id = imported.json()["run_id"]

    advanced = client.post(f"/v1/sessions/{session_id}/advance")
    assert advanced.status_code == 200
    assert advanced.json()["state"] == "awaiting_followup"

    followup = client.post(
        f"/v1/sessions/{session_id}/external/maxwell/followup",
        json={"manifest_path": str(followup_manifest), "metadata": {"source": "pytest_followup"}},
    )
    assert followup.status_code == 200
    assert followup.json()["state"] == "completed"

    view = client.get(f"/v1/sessions/{session_id}").json()
    followup_artifact_id = view["artifacts_by_stage"]["FOLLOWUP_INGEST"][0]
    followup_artifact = service.runstore.load_artifact(run_id, followup_artifact_id)
    assert followup_artifact.artifact_type == "hub.bioelectric.baseline_analysis.v1"
    assert followup_artifact.data["simulation"]["analysis_role"] == "followup"
    assert followup_artifact.data["simulation"]["metadata"]["source"] == "pytest_followup"

    report = client.get(f"/v1/sessions/{session_id}/report")
    assert report.status_code == 200
    body = report.json()
    assert body["conformance"]["status"] == "passed"
    assert body["delta_report"]["knocked_out_of_saddle"] is True
    assert body["delta_report"]["suite_context"]["source"] == "maxwell"
    assert body["delta_report"]["suite_context"]["baseline_imported_run_id"] == "mx_baseline_001"
    assert body["delta_report"]["suite_context"]["followup_imported_run_id"] == "mx_followup_001"
    assert body["suite_lineage"]["external_maxwell"]["baseline"]["imported_run_id"] == "mx_baseline_001"
    assert body["suite_lineage"]["external_maxwell"]["followup"]["imported_run_id"] == "mx_followup_001"
    assert body["suite_lineage"]["external_maxwell"]["baseline"]["manifest_path"] == str(baseline_manifest)
    assert body["suite_lineage"]["external_maxwell"]["followup"]["manifest_path"] == str(followup_manifest)

    report_view = client.get(f"/v1/sessions/{session_id}/report/view")
    assert report_view.status_code == 200
    assert "External Maxwell Lineage" in report_view.text
    assert "mx_baseline_001" in report_view.text
    assert "mx_followup_001" in report_view.text
    assert str(baseline_manifest) in report_view.text
    assert str(followup_manifest) in report_view.text


def test_followup_maxwell_run_requires_external_import_session(client_and_service, tmp_path: Path):
    client, _service = client_and_service
    manifest_path = _make_maxwell_run(tmp_path / "maxwell_run_non_external")

    created = client.post("/v1/sessions", json={"prompt": "bioelectric simulation intervention loop"})
    session_id = created.json()["session_id"]
    client.post(
        f"/v1/sessions/{session_id}/ingest",
        json={"stream_kind": "baseline", "points": [{"t": 0.0, "values": [0.0, 0.1, 0.2]}]},
    )
    client.post(f"/v1/sessions/{session_id}/advance")

    followup = client.post(
        f"/v1/sessions/{session_id}/external/maxwell/followup",
        json={"manifest_path": str(manifest_path)},
    )
    assert followup.status_code == 400
    assert "not a Maxwell external-import session" in followup.json()["detail"]
