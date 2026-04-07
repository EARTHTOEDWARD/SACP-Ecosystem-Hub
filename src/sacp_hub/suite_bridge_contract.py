from __future__ import annotations

from typing import Any, Dict, List, Literal

from pydantic import BaseModel, ConfigDict, Field


SHA256_PATTERN = r"^sha256:[0-9a-f]{64}$"
SUITE_HUB_BRIDGE_CONTRACT_VERSION = "sacp_suite.hub_bridge.v1"


class SuiteBridgePointV1(BaseModel):
    model_config = ConfigDict(extra="ignore")

    t: float
    values: List[float] = Field(default_factory=list)


class SuiteBridgeWindowV1(BaseModel):
    model_config = ConfigDict(extra="ignore")

    window_key: str
    label: str
    stream_kind: Literal["baseline", "followup"]
    time_range: List[float] = Field(default_factory=list, min_length=2, max_length=2)
    points: List[SuiteBridgePointV1] = Field(default_factory=list)
    stats: Dict[str, float] = Field(default_factory=dict)


class SuiteBridgeCandidateV1(BaseModel):
    model_config = ConfigDict(extra="ignore")

    candidate_id: str
    label: str
    mechanism: str
    predicted_shift_score: float
    confidence: float
    suite_candidate_ref: Dict[str, Any] = Field(default_factory=dict)


class SuitePanelRunExportV1(BaseModel):
    model_config = ConfigDict(extra="ignore")

    provider: Literal["sacp_suite"] = "sacp_suite"
    bridge_kind: Literal["panel_run"] = "panel_run"
    bridge_contract_version: Literal[SUITE_HUB_BRIDGE_CONTRACT_VERSION] = SUITE_HUB_BRIDGE_CONTRACT_VERSION
    run_id: str
    export_hash: str = Field(pattern=SHA256_PATTERN)
    suite_lineage: Dict[str, Any] = Field(default_factory=dict)
    baseline_windows: List[SuiteBridgeWindowV1] = Field(default_factory=list)
    baseline_metrics: Dict[str, float] = Field(default_factory=dict)
    simulation: Dict[str, Any] = Field(default_factory=dict)
    regime_summary: Dict[str, Any] = Field(default_factory=dict)
    persistence_summary: Dict[str, Any] = Field(default_factory=dict)
    challenge_summary: Dict[str, Any] = Field(default_factory=dict)
    candidates: List[SuiteBridgeCandidateV1] = Field(default_factory=list)


class SuiteVerificationRunExportV1(BaseModel):
    model_config = ConfigDict(extra="ignore")

    provider: Literal["sacp_suite"] = "sacp_suite"
    bridge_kind: Literal["verification_run"] = "verification_run"
    bridge_contract_version: Literal[SUITE_HUB_BRIDGE_CONTRACT_VERSION] = SUITE_HUB_BRIDGE_CONTRACT_VERSION
    run_id: str
    export_hash: str = Field(pattern=SHA256_PATTERN)
    suite_lineage: Dict[str, Any] = Field(default_factory=dict)
    baseline: SuitePanelRunExportV1
    followup_windows: List[SuiteBridgeWindowV1] = Field(default_factory=list)
    followup_metrics: Dict[str, float] = Field(default_factory=dict)
    selected_candidate: Dict[str, Any] = Field(default_factory=dict)
    delta_report: Dict[str, Any] = Field(default_factory=dict)
