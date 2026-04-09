from __future__ import annotations

import json
from pathlib import Path


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _make_maxwell_run(run_dir: Path) -> Path:
    manifest = {
        "run_id": "mx_import_001",
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
            "mu_grid": [0.2, 0.4, 0.6],
            "series": [
                {"em_dynamics_v0": {}, "transport_v0": {}, "operator_shadow_v1": {}},
                {"em_dynamics_v0": {}, "triad_law4_v1": {}},
            ],
        },
    )
    _write_json(
        run_dir / "boundaries.json",
        {
            "boundaries": [
                {"temporal_gauge_certificate_ref": "certificates/temporal_gauge_certificate.boundary_000.v0.json"},
                {"temporal_gauge_certificate_ref": "certificates/temporal_gauge_certificate.boundary_001.v0.json"},
            ]
        },
    )
    _write_json(run_dir / "gate_rollout.json", {"policy": {"gate_mode": "olsta_min"}, "rollout": [{"t_index": 0}, {"t_index": 1}]})
    _write_json(run_dir / "olsta_panel.json", {"summary": {"n_feasible_mu": 2}})
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
