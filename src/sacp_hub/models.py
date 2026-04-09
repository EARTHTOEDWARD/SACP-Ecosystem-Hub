from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


SessionStateLiteral = Literal["created", "running", "awaiting_followup", "completed", "failed"]
StageLiteral = Literal[
    "INTAKE",
    "WINDOW",
    "BASELINE_ANALYZE",
    "CANDIDATE_GENERATE",
    "EXECUTE_SIM",
    "FOLLOWUP_INGEST",
    "DELTA_COMPARE",
    "BRIEF",
    "CONFORMANCE",
]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class StreamPoint(BaseModel):
    t: float
    values: List[float] = Field(min_length=1)


class IntentCompileRequest(BaseModel):
    prompt: str = Field(min_length=3)
    context: Dict[str, Any] = Field(default_factory=dict)


class IntentCompileResponse(BaseModel):
    intent: Dict[str, Any]
    route_plan: Dict[str, Any]


class SessionCreateRequest(BaseModel):
    prompt: str = Field(min_length=3)
    context: Dict[str, Any] = Field(default_factory=dict)


class SessionCreateResponse(BaseModel):
    session_id: str
    run_id: str
    state: SessionStateLiteral
    intent: Dict[str, Any]
    route_plan: Dict[str, Any]


class MaxwellImportRequest(BaseModel):
    manifest_path: str = Field(min_length=1)
    prompt: Optional[str] = None
    context: Dict[str, Any] = Field(default_factory=dict)


class MaxwellImportResponse(BaseModel):
    session_id: str
    run_id: str
    imported_run_id: str
    state: SessionStateLiteral
    intent: Dict[str, Any]
    route_plan: Dict[str, Any]
    baseline_artifact_id: str


class SuiteBridgeRefV1(BaseModel):
    provider: Literal["sacp_suite"] = "sacp_suite"
    bridge_kind: Literal["panel_run", "verification_run"]
    run_id: str = Field(min_length=1)
    suite_base_url: Optional[str] = None


class IngestRequest(BaseModel):
    stream_kind: Literal["baseline", "followup"] = "baseline"
    points: List[StreamPoint] = Field(default_factory=list)
    suite_bridge: Optional[SuiteBridgeRefV1] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_source(self) -> "IngestRequest":
        has_points = bool(self.points)
        has_bridge = self.suite_bridge is not None
        if has_points == has_bridge:
            raise ValueError("Provide exactly one of points or suite_bridge")
        return self


class IngestResponse(BaseModel):
    session_id: str
    stream_kind: Literal["baseline", "followup"]
    artifact_id: str
    state: SessionStateLiteral


class AdvanceResponse(BaseModel):
    session_id: str
    state: SessionStateLiteral
    produced_artifact_ids: List[str] = Field(default_factory=list)
    stage_history: List[StageLiteral] = Field(default_factory=list)


class FollowupRequest(BaseModel):
    points: List[StreamPoint] = Field(default_factory=list)
    suite_bridge: Optional[SuiteBridgeRefV1] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_source(self) -> "FollowupRequest":
        has_points = bool(self.points)
        has_bridge = self.suite_bridge is not None
        if has_points and has_bridge:
            raise ValueError("Provide at most one of points or suite_bridge")
        return self


class ArtifactListResponse(BaseModel):
    session_id: str
    artifact_ids: List[str]
    artifacts_by_stage: Dict[str, List[str]]


class SessionView(BaseModel):
    session_id: str
    run_id: str
    state: SessionStateLiteral
    prompt: str
    stage_history: List[StageLiteral]
    completed_stages: List[StageLiteral]
    artifacts_by_stage: Dict[str, List[str]]
    created_at: datetime
    updated_at: datetime
    errors: List[Dict[str, Any]] = Field(default_factory=list)


class SessionRecord(BaseModel):
    session_id: str = Field(default_factory=lambda: uuid4().hex)
    run_id: str
    prompt: str
    state: SessionStateLiteral = "created"
    stage_history: List[StageLiteral] = Field(default_factory=list)
    completed_stages: List[StageLiteral] = Field(default_factory=list)
    artifacts_by_stage: Dict[str, List[str]] = Field(default_factory=dict)
    artifact_ids: List[str] = Field(default_factory=list)
    artifact_refs: List[Dict[str, Any]] = Field(default_factory=list)
    stage_outputs: Dict[str, str] = Field(default_factory=dict)
    baseline_window_ids: List[str] = Field(default_factory=list)
    followup_window_ids: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    errors: List[Dict[str, Any]] = Field(default_factory=list)
    context: Dict[str, Any] = Field(default_factory=dict)

    def touch(self) -> None:
        self.updated_at = utcnow()


class ErrorEnvelope(BaseModel):
    stage: StageLiteral
    kind: Literal["transient", "contract", "infra"]
    message: str
