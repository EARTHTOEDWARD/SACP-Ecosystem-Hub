from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

import requests

from sacp_hub.adapters.base import (
    Adapter,
    AdapterCapability,
    AdapterResult,
    PreparedCall,
    ValidationReport,
)
from sacp_hub.config import default_sacp_api_base


@dataclass
class SACPAPIAdapter(Adapter):
    base_url: str = default_sacp_api_base()
    timeout_seconds: float = 20.0

    def capabilities(self) -> AdapterCapability:
        return AdapterCapability(
            name="sacp_api",
            adapter_type="api",
            entrypoints={
                "chemistry_simulate": f"{self.base_url}/api/v1/chemistry/simulate",
                "bcp_panel_export": f"{self.base_url}/api/v1/bcp/hub-exports/panel-runs/{{run_id}}",
                "bcp_verification_export": f"{self.base_url}/api/v1/bcp/hub-exports/verification-runs/{{run_id}}",
            },
            produced_artifact_types=[
                "hub.bioelectric.baseline_analysis.v1",
                "hub.intervention_candidate_set.v1",
                "hub.intervention_execution.v1",
                "hub.followup_delta_report.v1",
            ],
            required_artifact_types=["hub.stream_window.v1"],
        )

    def prepare(self, stage_input_refs: Dict[str, Any]) -> PreparedCall:
        action = str(stage_input_refs.get("action", "")).strip()
        if action not in {
            "baseline_analyze",
            "candidate_generate",
            "execute_intervention",
            "delta_compare",
        }:
            raise ValueError(f"Unsupported SACP action: {action}")
        return PreparedCall(adapter_name="sacp_api", action=action, payload=dict(stage_input_refs))

    def execute(self, prepared_call: PreparedCall) -> AdapterResult:
        action = prepared_call.action
        payload = prepared_call.payload
        try:
            if action == "baseline_analyze":
                return AdapterResult(ok=True, payload=self._baseline_analyze(payload))
            if action == "candidate_generate":
                return AdapterResult(ok=True, payload=self._candidate_generate(payload))
            if action == "execute_intervention":
                return AdapterResult(ok=True, payload=self._execute_intervention(payload))
            if action == "delta_compare":
                return AdapterResult(ok=True, payload=self._delta_compare(payload))
            return AdapterResult(ok=False, error_kind="contract", error_message=f"Unknown action: {action}")
        except requests.Timeout as exc:
            return AdapterResult(ok=False, error_kind="transient", error_message=f"SACP timeout: {exc}")
        except requests.ConnectionError as exc:
            return AdapterResult(ok=False, error_kind="transient", error_message=f"SACP connection error: {exc}")
        except requests.RequestException as exc:
            return AdapterResult(ok=False, error_kind="infra", error_message=f"SACP request error: {exc}")
        except (KeyError, ValueError, TypeError) as exc:
            return AdapterResult(ok=False, error_kind="contract", error_message=f"Invalid stage payload: {exc}")
        except Exception as exc:  # noqa: BLE001
            return AdapterResult(ok=False, error_kind="infra", error_message=f"Unexpected adapter error: {exc}")

    def normalize(self, adapter_result: AdapterResult) -> List[Dict[str, Any]]:
        if not adapter_result.ok:
            return []
        payload = adapter_result.payload
        action = str(payload.get("action", ""))
        if action == "baseline_analyze":
            return [{"artifact_type": "hub.bioelectric.baseline_analysis.v1", "data": payload}]
        if action == "candidate_generate":
            return [{"artifact_type": "hub.intervention_candidate_set.v1", "data": payload}]
        if action == "execute_intervention":
            return [{"artifact_type": "hub.intervention_execution.v1", "data": payload}]
        if action == "delta_compare":
            return [{"artifact_type": "hub.followup_delta_report.v1", "data": payload}]
        return []

    def validate(self, normalized_artifacts: List[Dict[str, Any]]) -> ValidationReport:
        errors: List[str] = []
        for artifact in normalized_artifacts:
            if "artifact_type" not in artifact:
                errors.append("artifact_type missing")
            if "data" not in artifact:
                errors.append("data missing")
        return ValidationReport(ok=not errors, errors=errors)

    def _baseline_analyze(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        windows = list(payload["windows"])
        flattened = [point for window in windows for point in window.get("points", [])]
        if not flattened:
            raise ValueError("No baseline points available")

        vector_len = len(flattened[0]["values"])
        means = [0.0 for _ in range(vector_len)]
        for point in flattened:
            values = point["values"]
            for idx, value in enumerate(values):
                means[idx] += float(value)
        n = float(len(flattened))
        means = [value / n for value in means]

        variance = 0.0
        gradient_sum = 0.0
        for idx, point in enumerate(flattened):
            values = [float(v) for v in point["values"]]
            variance += sum((values[i] - means[i]) ** 2 for i in range(vector_len))
            if idx > 0:
                prev = [float(v) for v in flattened[idx - 1]["values"]]
                gradient_sum += sum(abs(values[i] - prev[i]) for i in range(vector_len))

        instability = gradient_sum / max(1.0, n - 1.0)
        variance = variance / max(1.0, n)
        sim = self._try_sacp_chemistry_sim(payload.get("t_max", 120.0))

        return {
            "action": "baseline_analyze",
            "session_id": payload["session_id"],
            "window_ids": [str(window["artifact_id"]) for window in windows],
            "metrics": {
                "variance": float(variance),
                "instability": float(instability),
                "mean_signal": float(sum(means) / len(means)),
                "energy_gradient_proxy": float(gradient_sum),
            },
            "simulation": sim,
        }

    def _candidate_generate(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        baseline = dict(payload["baseline"])
        metrics = dict(baseline["metrics"])
        instability = float(metrics["instability"])
        base = max(0.01, min(1.0, instability / 5.0))
        candidates = [
            {
                "candidate_id": "cand_ion_na_block_v1",
                "label": "Na channel block candidate",
                "mechanism": "reduce excitability",
                "predicted_shift_score": round(base + 0.08, 6),
                "confidence": 0.72,
            },
            {
                "candidate_id": "cand_ca_mod_v1",
                "label": "Ca modulation candidate",
                "mechanism": "stabilize oscillatory gain",
                "predicted_shift_score": round(base + 0.05, 6),
                "confidence": 0.68,
            },
            {
                "candidate_id": "cand_k_support_v1",
                "label": "K support candidate",
                "mechanism": "promote repolarization",
                "predicted_shift_score": round(base + 0.03, 6),
                "confidence": 0.64,
            },
        ]
        candidates.sort(key=lambda row: row["predicted_shift_score"], reverse=True)
        return {
            "action": "candidate_generate",
            "session_id": payload["session_id"],
            "baseline_artifact_id": payload["baseline_artifact_id"],
            "candidates": candidates,
        }

    def _execute_intervention(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        candidates = list(payload["candidates"])
        if not candidates:
            raise ValueError("No candidates to execute")
        selected = candidates[0]
        effect_scale = float(selected["predicted_shift_score"])
        return {
            "action": "execute_intervention",
            "session_id": payload["session_id"],
            "selected_candidate_id": selected["candidate_id"],
            "selection_reason": "Highest predicted_shift_score",
            "predicted_effect": {
                "instability_reduction": round(effect_scale * 0.4, 6),
                "energy_gradient_reduction": round(effect_scale * 0.3, 6),
            },
        }

    def _delta_compare(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        baseline_metrics = dict(payload["baseline_metrics"])
        followup_metrics = dict(payload["followup_metrics"])
        delta = {
            key: float(followup_metrics.get(key, 0.0) - baseline_metrics.get(key, 0.0))
            for key in sorted(set(baseline_metrics) | set(followup_metrics))
        }
        knocked_out = delta.get("instability", 0.0) < 0 and delta.get("energy_gradient_proxy", 0.0) < 0
        return {
            "action": "delta_compare",
            "session_id": payload["session_id"],
            "baseline_metrics": baseline_metrics,
            "followup_metrics": followup_metrics,
            "delta": delta,
            "knocked_out_of_saddle": bool(knocked_out),
        }

    def _try_sacp_chemistry_sim(self, t_max: float) -> Dict[str, Any]:
        req = {"t_max": float(max(20.0, min(400.0, t_max))), "dt": 0.02}
        url = f"{self.base_url}/api/v1/chemistry/simulate"
        try:
            resp = requests.post(url, json=req, timeout=self.timeout_seconds)
            resp.raise_for_status()
            body = resp.json()
            x = body.get("x", [])
            signal_energy = 0.0
            samples = 0
            for row in x[:200]:
                signal_energy += sum(abs(float(v)) for v in row)
                samples += 1
            return {
                "source": "sacp_api",
                "sample_count": int(samples),
                "signal_energy_proxy": float(signal_energy / max(1, samples)),
            }
        except Exception:
            return {
                "source": "fallback",
                "sample_count": 0,
                "signal_energy_proxy": 0.0,
            }

    def fetch_suite_bridge_export(self, suite_bridge: Dict[str, Any]) -> Dict[str, Any]:
        provider = str(suite_bridge.get("provider", "")).strip()
        if provider != "sacp_suite":
            raise ValueError(f"Unsupported suite bridge provider: {provider}")
        bridge_kind = str(suite_bridge.get("bridge_kind", "")).strip()
        run_id = str(suite_bridge.get("run_id", "")).strip()
        if not run_id:
            raise ValueError("suite bridge run_id is required")
        raw_base = str(suite_bridge.get("suite_base_url") or self.base_url).strip().rstrip("/")
        base_url = raw_base or self.base_url.rstrip("/")
        if bridge_kind == "panel_run":
            url = f"{base_url}/api/v1/bcp/hub-exports/panel-runs/{run_id}"
        elif bridge_kind == "verification_run":
            url = f"{base_url}/api/v1/bcp/hub-exports/verification-runs/{run_id}"
        else:
            raise ValueError(f"Unsupported suite bridge kind: {bridge_kind}")
        resp = requests.get(url, timeout=self.timeout_seconds)
        resp.raise_for_status()
        return resp.json()
