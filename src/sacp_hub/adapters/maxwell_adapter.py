from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from sacp_hub.adapters.base import (
    Adapter,
    AdapterCapability,
    AdapterResult,
    PreparedCall,
    ValidationReport,
)


def _safe_load_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)


def _artifact_path_set(manifest: Dict[str, Any]) -> set[str]:
    paths: set[str] = set()
    for item in list(manifest.get("artifacts", [])):
        if isinstance(item, dict):
            raw = str(item.get("path", "")).strip()
            if raw:
                paths.add(raw)
    return paths


def _optional_run_payloads(run_dir: Path, manifest: Dict[str, Any]) -> tuple[Dict[str, Dict[str, Any]], List[str]]:
    rel_paths = [
        "atlas.json",
        "boundaries.json",
        "gate.json",
        "gate_rollout.json",
        "olsta_panel.json",
        "em_panel.json",
        "temporal_gauge_calibration_summary.json",
        "metrics.json",
    ]
    known_artifacts = _artifact_path_set(manifest)
    loaded: Dict[str, Dict[str, Any]] = {}
    invalid: List[str] = []
    for rel in rel_paths:
        path = run_dir / rel
        if not path.exists():
            continue
        payload, error = _safe_load_json(path)
        if payload is None:
            invalid.append(f"{rel}: {error}")
            continue
        loaded[rel] = payload
    if "run_manifest.json" in known_artifacts:
        known_artifacts.remove("run_manifest.json")
    return loaded, invalid


def _build_run_summary(manifest: Dict[str, Any], optional_payloads: Dict[str, Dict[str, Any]], invalid_files: List[str]) -> Dict[str, Any]:
    artifact_paths = sorted(_artifact_path_set(manifest))
    boundaries = optional_payloads.get("boundaries.json", {})
    boundary_rows = list(boundaries.get("boundaries", [])) if isinstance(boundaries, dict) else []
    atlas = optional_payloads.get("atlas.json", {})
    series = list(atlas.get("series", [])) if isinstance(atlas, dict) else []
    gate_rollout = optional_payloads.get("gate_rollout.json", {})
    rollout_rows = list(gate_rollout.get("rollout", [])) if isinstance(gate_rollout, dict) else []
    tg_summary = optional_payloads.get("temporal_gauge_calibration_summary.json", {})
    gate = optional_payloads.get("gate.json", {})

    extension_paths = {
        "potential_tensor_signature": any("potential_tensor_signature." in path for path in artifact_paths),
        "holonomy_ledger": any("holonomy_ledger." in path for path in artifact_paths),
        "toroidization_stock": any("toroidization_stock." in path for path in artifact_paths),
        "open_circuit_reciprocity_certificate": any("open_circuit_reciprocity_certificate." in path for path in artifact_paths),
        "gauge_quotient_gluing_gap": any("gauge_quotient_gluing_gap." in path for path in artifact_paths),
    }

    return {
        "source": "maxwell",
        "run_id": manifest.get("run_id", "unknown"),
        "system": manifest.get("system", {}),
        "artifact_count": len(list(manifest.get("artifacts", []))),
        "available_files": sorted(optional_payloads.keys()),
        "invalid_optional_files": invalid_files,
        "osm_bundle_present": any(path.startswith("osm_bundle/") for path in artifact_paths),
        "atlas": {
            "mu_grid_count": len(list(atlas.get("mu_grid", []))) if isinstance(atlas, dict) else 0,
            "series_count": len(series),
            "has_em_dynamics": any(isinstance(row, dict) and "em_dynamics_v0" in row for row in series),
            "has_transport": any(
                isinstance(row, dict) and ("transport_v0" in row or "open_system_v0" in row) for row in series
            ),
            "has_operator_shadow": any(isinstance(row, dict) and "operator_shadow_v1" in row for row in series),
            "has_triad_law4": any(isinstance(row, dict) and "triad_law4_v1" in row for row in series),
        },
        "boundaries": {
            "count": len(boundary_rows),
            "temporal_gauge_certificate_count": sum(
                1
                for row in boundary_rows
                if isinstance(row, dict) and isinstance(row.get("temporal_gauge_certificate_ref"), str) and row.get("temporal_gauge_certificate_ref")
            ),
        },
        "gate": {
            "gate_mode": (
                str(gate_rollout.get("policy", {}).get("gate_mode", "")).strip()
                if isinstance(gate_rollout, dict)
                else ""
            )
            or (str(gate.get("policy_id", "")).strip() if isinstance(gate, dict) else ""),
            "rollout_count": len(rollout_rows),
        },
        "temporal_gauge": {
            "artifact_version": str(tg_summary.get("artifact_version", "")).strip() if isinstance(tg_summary, dict) else "",
            "within_inconclusive_budget": bool(
                tg_summary.get("summary", {}).get("within_inconclusive_budget", False)
            )
            if isinstance(tg_summary, dict)
            else False,
        },
        "panels": {
            "olsta_panel_present": "olsta_panel.json" in optional_payloads,
            "em_panel_present": "em_panel.json" in optional_payloads,
            "olsta_feasible_mu": int(optional_payloads.get("olsta_panel.json", {}).get("summary", {}).get("n_feasible_mu", 0))
            if isinstance(optional_payloads.get("olsta_panel.json", {}), dict)
            else 0,
        },
        "extension_artifacts": extension_paths,
    }


@dataclass
class MaxwellNormalizationAdapter(Adapter):
    def capabilities(self) -> AdapterCapability:
        return AdapterCapability(
            name="maxwell_normalizer",
            adapter_type="cli",
            entrypoints={"run_manifest": "var/runs/<run_id>/run_manifest.json"},
            produced_artifact_types=["hub.route_plan.v1"],
            required_artifact_types=[],
        )

    def prepare(self, stage_input_refs: Dict[str, Any]) -> PreparedCall:
        return PreparedCall(adapter_name="maxwell_normalizer", action="normalize_run", payload=dict(stage_input_refs))

    def execute(self, prepared_call: PreparedCall) -> AdapterResult:
        manifest_path = Path(str(prepared_call.payload["manifest_path"]))
        if not manifest_path.exists():
            return AdapterResult(ok=False, error_kind="infra", error_message=f"Missing Maxwell manifest: {manifest_path}")
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            optional_payloads, invalid_files = _optional_run_payloads(manifest_path.parent, data)
            return AdapterResult(
                ok=True,
                payload={
                    "source": "maxwell",
                    "manifest": data,
                    "optional_payloads": optional_payloads,
                    "invalid_optional_files": invalid_files,
                },
            )
        except Exception as exc:  # noqa: BLE001
            return AdapterResult(ok=False, error_kind="contract", error_message=f"Invalid Maxwell manifest: {exc}")

    def normalize(self, adapter_result: AdapterResult) -> List[Dict[str, Any]]:
        if not adapter_result.ok:
            return []
        manifest = dict(adapter_result.payload["manifest"])
        optional_payloads = dict(adapter_result.payload.get("optional_payloads", {}))
        invalid_optional_files = list(adapter_result.payload.get("invalid_optional_files", []))
        summary = _build_run_summary(manifest, optional_payloads, invalid_optional_files)
        return [
            {
                "artifact_type": "hub.route_plan.v1",
                "data": {
                    "session_type": "bioelectric_intervention_loop",
                    "steps": [],
                    "version": "external",
                    "summary": summary,
                },
            }
        ]

    def validate(self, normalized_artifacts: List[Dict[str, Any]]) -> ValidationReport:
        return ValidationReport(ok=True, errors=[])
