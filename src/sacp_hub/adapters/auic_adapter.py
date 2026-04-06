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


@dataclass
class AUICNormalizationAdapter(Adapter):
    def capabilities(self) -> AdapterCapability:
        return AdapterCapability(
            name="auic_normalizer",
            adapter_type="python",
            entrypoints={"manifest": "var/runs/<run_id>/manifest.json"},
            produced_artifact_types=["hub.route_plan.v1"],
            required_artifact_types=[],
        )

    def prepare(self, stage_input_refs: Dict[str, Any]) -> PreparedCall:
        return PreparedCall(adapter_name="auic_normalizer", action="normalize_run", payload=dict(stage_input_refs))

    def execute(self, prepared_call: PreparedCall) -> AdapterResult:
        manifest_path = Path(str(prepared_call.payload["manifest_path"]))
        if not manifest_path.exists():
            return AdapterResult(ok=False, error_kind="infra", error_message=f"Missing AUIC manifest: {manifest_path}")
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            return AdapterResult(ok=True, payload={"source": "auic", "manifest": manifest})
        except Exception as exc:  # noqa: BLE001
            return AdapterResult(ok=False, error_kind="contract", error_message=f"Invalid AUIC manifest: {exc}")

    def normalize(self, adapter_result: AdapterResult) -> List[Dict[str, Any]]:
        if not adapter_result.ok:
            return []
        manifest = dict(adapter_result.payload["manifest"])
        summary = {
            "source": "auic",
            "run_id": manifest.get("run_id", "unknown"),
            "artifact_count": len(manifest.get("artifacts", [])),
        }
        return [{"artifact_type": "hub.route_plan.v1", "data": {"session_type": "bioelectric_intervention_loop", "steps": [], "version": "external", "summary": summary}}]

    def validate(self, normalized_artifacts: List[Dict[str, Any]]) -> ValidationReport:
        return ValidationReport(ok=True, errors=[])
