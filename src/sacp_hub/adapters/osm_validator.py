from __future__ import annotations

import subprocess
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
from sacp_hub.config import default_osm_root


@dataclass
class OSMValidatorAdapter(Adapter):
    osm_root: Path = default_osm_root()

    def capabilities(self) -> AdapterCapability:
        return AdapterCapability(
            name="osm_validator",
            adapter_type="cli",
            entrypoints={
                "validate_runstore": str(self.osm_root / "scripts" / "validate_runstore.py"),
            },
            produced_artifact_types=[],
            required_artifact_types=["hub.final_brief.v1"],
        )

    def prepare(self, stage_input_refs: Dict[str, Any]) -> PreparedCall:
        return PreparedCall(adapter_name="osm_validator", action="validate", payload=dict(stage_input_refs))

    def execute(self, prepared_call: PreparedCall) -> AdapterResult:
        runs_root = Path(str(prepared_call.payload["runs_root"]))
        run_id = str(prepared_call.payload["run_id"])
        script = self.osm_root / "scripts" / "validate_runstore.py"
        if not script.exists():
            return AdapterResult(ok=False, error_kind="infra", error_message=f"Missing validator script: {script}")

        cmd = ["python3", str(script), "--runs-root", str(runs_root), "--run-id", run_id]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode == 0:
            return AdapterResult(ok=True, payload={"status": "passed", "run_id": run_id}, raw_stdout=proc.stdout)

        stderr = proc.stderr.strip()
        stdout = proc.stdout.strip()
        combined = "\n".join(part for part in [stdout, stderr] if part)
        kind = "contract" if "schema" in combined.lower() or "mismatch" in combined.lower() else "infra"
        return AdapterResult(
            ok=False,
            error_kind=kind,
            error_message=f"OSM validator failed for run_id={run_id}",
            raw_stdout=stdout,
            raw_stderr=stderr,
        )

    def normalize(self, adapter_result: AdapterResult) -> List[Dict[str, Any]]:
        return []

    def validate(self, normalized_artifacts: List[Dict[str, Any]]) -> ValidationReport:
        return ValidationReport(ok=True, errors=[])
