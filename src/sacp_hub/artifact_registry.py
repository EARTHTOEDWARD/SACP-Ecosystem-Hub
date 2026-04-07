from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal

from pydantic import BaseModel, Field


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class RouteStep(BaseModel):
    stage: str
    owner: str
    description: str


class IntentArtifact(BaseModel):
    prompt: str
    domain: str
    objective: str
    mode: Literal["batch", "realtime"]
    simulation_only: bool = True
    compiled_at: str = Field(default_factory=_utcnow_iso)
    tags: List[str] = Field(default_factory=list)


class RoutePlanArtifact(BaseModel):
    session_type: Literal["bioelectric_intervention_loop"] = "bioelectric_intervention_loop"
    steps: List[RouteStep]
    version: str = "v1"


class SessionStateArtifact(BaseModel):
    session_id: str
    state: str
    last_stage: str
    stage_history: List[str]
    artifact_ids: List[str]


class WindowPoint(BaseModel):
    t: float
    values: List[float]


class StreamWindowArtifact(BaseModel):
    session_id: str
    stream_kind: Literal["baseline", "followup"]
    window_index: int
    points: List[WindowPoint]
    stats: Dict[str, float]
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SACPBridgeSnapshotArtifact(BaseModel):
    session_id: str
    stream_kind: Literal["baseline", "followup"]
    provider: Literal["sacp_suite"] = "sacp_suite"
    bridge_kind: Literal["panel_run", "verification_run"]
    bridge_contract_version: str
    suite_run_id: str
    suite_base_url: str
    source_url: str
    export_hash: str
    suite_lineage: Dict[str, Any] = Field(default_factory=dict)
    baseline_windows: List[Dict[str, Any]] = Field(default_factory=list)
    followup_windows: List[Dict[str, Any]] = Field(default_factory=list)
    baseline_metrics: Dict[str, float] = Field(default_factory=dict)
    followup_metrics: Dict[str, float] = Field(default_factory=dict)
    simulation: Dict[str, Any] = Field(default_factory=dict)
    regime_summary: Dict[str, Any] = Field(default_factory=dict)
    persistence_summary: Dict[str, Any] = Field(default_factory=dict)
    challenge_summary: Dict[str, Any] = Field(default_factory=dict)
    candidates: List[Dict[str, Any]] = Field(default_factory=list)
    selected_candidate: Dict[str, Any] = Field(default_factory=dict)
    delta_report: Dict[str, Any] = Field(default_factory=dict)


class BaselineAnalysisArtifact(BaseModel):
    session_id: str
    window_ids: List[str]
    metrics: Dict[str, float]
    simulation: Dict[str, Any]
    suite_context: Dict[str, Any] = Field(default_factory=dict)


class InterventionCandidate(BaseModel):
    candidate_id: str
    label: str
    mechanism: str
    predicted_shift_score: float
    confidence: float
    suite_candidate_ref: Dict[str, Any] = Field(default_factory=dict)


class InterventionCandidateSetArtifact(BaseModel):
    session_id: str
    baseline_artifact_id: str
    candidates: List[InterventionCandidate]
    suite_context: Dict[str, Any] = Field(default_factory=dict)


class InterventionExecutionArtifact(BaseModel):
    session_id: str
    selected_candidate_id: str
    selection_reason: str
    predicted_effect: Dict[str, float]
    suite_candidate_ref: Dict[str, Any] = Field(default_factory=dict)
    suite_execution_request: Dict[str, Any] = Field(default_factory=dict)
    suite_context: Dict[str, Any] = Field(default_factory=dict)


class FollowupDeltaReportArtifact(BaseModel):
    session_id: str
    baseline_metrics: Dict[str, float]
    followup_metrics: Dict[str, float]
    delta: Dict[str, float]
    knocked_out_of_saddle: bool
    suite_context: Dict[str, Any] = Field(default_factory=dict)


class FinalBriefArtifact(BaseModel):
    session_id: str
    summary: str
    intervention: Dict[str, Any]
    delta_report: Dict[str, Any]
    conformance: Dict[str, Any]
    lineage: Dict[str, Any]
    suite_lineage: Dict[str, Any] = Field(default_factory=dict)


ARTIFACT_MODELS: Dict[str, type[BaseModel]] = {
    "hub.intent.v1": IntentArtifact,
    "hub.route_plan.v1": RoutePlanArtifact,
    "hub.session_state.v1": SessionStateArtifact,
    "hub.stream_window.v1": StreamWindowArtifact,
    "hub.sacp_bridge_snapshot.v1": SACPBridgeSnapshotArtifact,
    "hub.bioelectric.baseline_analysis.v1": BaselineAnalysisArtifact,
    "hub.intervention_candidate_set.v1": InterventionCandidateSetArtifact,
    "hub.intervention_execution.v1": InterventionExecutionArtifact,
    "hub.followup_delta_report.v1": FollowupDeltaReportArtifact,
    "hub.final_brief.v1": FinalBriefArtifact,
}


def validate_artifact_data(artifact_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
    model = ARTIFACT_MODELS.get(artifact_type)
    if model is None:
        raise ValueError(f"Unknown artifact type: {artifact_type}")
    return model.model_validate(data).model_dump(mode="python")
