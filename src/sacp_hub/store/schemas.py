from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


SHA256_PATTERN = r"^sha256:[0-9a-f]{64}$"


class BlobRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    blob_id: str = Field(pattern=SHA256_PATTERN)
    mime_type: Optional[str] = None
    compression: Optional[str] = None
    size_bytes: Optional[int] = Field(default=None, ge=0)
    logical_name: Optional[str] = None


class StorageRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    uri: Optional[str] = None
    backend: Optional[str] = None
    mime_type: Optional[str] = None
    compression: Optional[str] = None
    size_bytes: Optional[int] = Field(default=None, ge=0)


class Hashes(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sha256: str = Field(pattern=SHA256_PATTERN)


class ArtifactRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_id: str = Field(pattern=SHA256_PATTERN)
    artifact_type: str
    hashes: Hashes
    uri: Optional[str] = None


class DatasetRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_id: str
    version: Optional[str] = None
    uri: str
    hashes: Hashes
    schema_id: Optional[str] = None
    slice: Optional[Dict[str, Any]] = None


class CreatedBy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    stage: Optional[str] = None
    tool: Optional[str] = None


class ArtifactManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_id: Literal["sacp.artifact.v0.1"] = "sacp.artifact.v0.1"
    artifact_id: Optional[str] = Field(default=None, pattern=SHA256_PATTERN)
    artifact_type: str
    schema_version: str = "0.1.0"
    created_by: CreatedBy
    created_at: datetime
    storage: Optional[StorageRef] = None
    blobs: List[BlobRef] = Field(default_factory=list)
    inputs: List[ArtifactRef | DatasetRef] = Field(default_factory=list)
    data: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    hashes: Optional[Hashes] = None


class RunModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plugin_key: str
    plugin_version: Optional[str] = None
    entrypoint: Optional[str] = None


class RunParameters(BaseModel):
    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    model_params: Dict[str, Any] = Field(default_factory=dict)
    integrator: Dict[str, Any] = Field(default_factory=dict)
    measurement: Dict[str, Any] = Field(default_factory=dict)
    noise: Dict[str, Any] = Field(default_factory=dict)
    notes: Optional[str] = None


class RunTimestamps(BaseModel):
    model_config = ConfigDict(extra="forbid")

    created_at: datetime
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    timezone: Optional[str] = None


class TelemetryRefs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    raw_series_ref: Optional[ArtifactRef] = None
    parameter_traces_ref: Optional[ArtifactRef] = None
    window_features_ref: Optional[ArtifactRef] = None
    event_log_ref: Optional[ArtifactRef] = None
    run_metadata_ref: Optional[ArtifactRef] = None
    trace_ledger_ref: Optional[ArtifactRef] = None


class RunHashes(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_manifest_sha256: Optional[str] = Field(default=None, pattern=SHA256_PATTERN)
    inputs_merkle_root: Optional[str] = Field(default=None, pattern=SHA256_PATTERN)
    telemetry_bundle_hash: Optional[str] = Field(default=None, pattern=SHA256_PATTERN)
    artifacts_merkle_root: Optional[str] = Field(default=None, pattern=SHA256_PATTERN)


class RunManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_id: Literal["sacp.run.v0.1"] = "sacp.run.v0.1"
    run_id: str
    model: RunModel
    parameters: RunParameters
    seeds: Dict[str, int] = Field(default_factory=dict)
    timestamps: RunTimestamps
    input_datasets: List[DatasetRef] = Field(default_factory=list)
    telemetry_refs: TelemetryRefs = Field(default_factory=TelemetryRefs)
    artifact_refs: List[ArtifactRef] = Field(default_factory=list)
    hashes: RunHashes = Field(default_factory=RunHashes)
    status: Optional[str] = None
    error: Optional[Dict[str, Any]] = None
