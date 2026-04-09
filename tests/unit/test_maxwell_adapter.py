from __future__ import annotations

import json
from pathlib import Path

from sacp_hub.adapters.maxwell_adapter import MaxwellNormalizationAdapter
from sacp_hub.artifact_registry import validate_artifact_data


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def test_maxwell_adapter_normalizes_rich_run_summary(tmp_path: Path) -> None:
    run_dir = tmp_path / "run_001"
    manifest = {
        "run_id": "mx_001",
        "system": {"name": "example6_maxwell_transport", "version": "v0"},
        "artifacts": [
            {"path": "atlas.json"},
            {"path": "boundaries.json"},
            {"path": "gate_rollout.json"},
            {"path": "olsta_panel.json"},
            {"path": "artifacts/potential_tensor_signature.full_run.v0.json"},
        ],
    }
    _write_json(run_dir / "run_manifest.json", manifest)
    _write_json(
        run_dir / "atlas.json",
        {
            "mu_grid": [0.2, 0.4],
            "series": [
                {"em_dynamics_v0": {}, "transport_v0": {}, "operator_shadow_v1": {}, "triad_law4_v1": {}},
                {"em_dynamics_v0": {}, "open_system_v0": {}},
            ],
        },
    )
    _write_json(
        run_dir / "boundaries.json",
        {
            "boundaries": [
                {"temporal_gauge_certificate_ref": "certificates/temporal_gauge_certificate.boundary_000.v0.json"},
                {},
            ]
        },
    )
    _write_json(run_dir / "gate_rollout.json", {"policy": {"gate_mode": "olsta_min"}, "rollout": [{"t_index": 0}]})
    _write_json(run_dir / "olsta_panel.json", {"summary": {"n_feasible_mu": 1}})
    _write_json(
        run_dir / "temporal_gauge_calibration_summary.json",
        {"artifact_version": "temporal_gauge_calibration_summary_v0", "summary": {"within_inconclusive_budget": True}},
    )

    adapter = MaxwellNormalizationAdapter()
    prepared = adapter.prepare({"manifest_path": str(run_dir / "run_manifest.json")})
    result = adapter.execute(prepared)
    assert result.ok is True

    normalized = adapter.normalize(result)
    summary = normalized[0]["data"]["summary"]
    assert summary["source"] == "maxwell"
    assert summary["run_id"] == "mx_001"
    assert summary["artifact_count"] == 5
    assert summary["atlas"]["series_count"] == 2
    assert summary["atlas"]["has_em_dynamics"] is True
    assert summary["boundaries"]["count"] == 2
    assert summary["boundaries"]["temporal_gauge_certificate_count"] == 1
    assert summary["gate"]["gate_mode"] == "olsta_min"
    assert summary["temporal_gauge"]["within_inconclusive_budget"] is True
    assert summary["panels"]["olsta_panel_present"] is True
    assert summary["panels"]["olsta_feasible_mu"] == 1
    assert summary["extension_artifacts"]["potential_tensor_signature"] is True


def test_route_plan_contract_preserves_external_summary() -> None:
    data = {
        "session_type": "bioelectric_intervention_loop",
        "steps": [],
        "version": "external",
        "summary": {
            "source": "maxwell",
            "run_id": "mx_002",
            "artifact_count": 3,
        },
    }
    validated = validate_artifact_data("hub.route_plan.v1", data)
    assert validated["summary"]["source"] == "maxwell"
    assert validated["summary"]["run_id"] == "mx_002"
