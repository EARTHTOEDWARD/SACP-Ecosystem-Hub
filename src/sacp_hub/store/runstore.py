from __future__ import annotations

import json
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

from sacp_hub.store.hashing import canonical_json_bytes, hash_json
from sacp_hub.store.schemas import (
    ArtifactManifest,
    ArtifactRef,
    BlobRef,
    CreatedBy,
    Hashes,
    RunManifest,
    RunModel,
    RunParameters,
    RunTimestamps,
    StorageRef,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=str(path.parent), delete=False) as tmp:
        tmp.write(data)
        tmp.flush()
        Path(tmp.name).replace(path)


class RunStore:
    def __init__(self, runs_root: Path):
        self.runs_root = runs_root

    def run_dir(self, run_id: str) -> Path:
        return self.runs_root / run_id

    def create_run(self, run_id: Optional[str] = None) -> str:
        rid = run_id or uuid.uuid4().hex
        base = self.run_dir(rid)
        (base / "cas" / "sha256").mkdir(parents=True, exist_ok=True)
        (base / "artifacts").mkdir(parents=True, exist_ok=True)
        return rid

    def _blob_path(self, run_id: str, blob_id: str) -> Path:
        algo, hex_digest = blob_id.split(":", 1)
        if algo != "sha256":
            raise ValueError(f"Unsupported blob algorithm: {algo}")
        return self.run_dir(run_id) / "cas" / algo / hex_digest[:2] / hex_digest

    def put_blob(
        self,
        run_id: str,
        data: bytes,
        *,
        mime_type: str | None = None,
        compression: str | None = None,
        logical_name: str | None = None,
    ) -> BlobRef:
        blob_id = hash_json({"data": data.decode("utf-8", errors="ignore")})
        # For arbitrary bytes, use raw sha256 of bytes instead of JSON-hashing wrapper.
        # The wrapper hash is replaced below with canonical byte hash for conformance.
        from sacp_hub.store.hashing import sha256_bytes

        blob_id = sha256_bytes(data)
        path = self._blob_path(run_id, blob_id)
        if not path.exists():
            _atomic_write_bytes(path, data)
        return BlobRef(
            blob_id=blob_id,
            mime_type=mime_type,
            compression=compression,
            size_bytes=path.stat().st_size,
            logical_name=logical_name,
        )

    def _artifact_manifest_path(self, run_id: str, artifact_id: str) -> Path:
        return self.run_dir(run_id) / "artifacts" / artifact_id / "artifact.json"

    @staticmethod
    def _artifact_fingerprint_payload(manifest: ArtifactManifest) -> dict[str, Any]:
        return {
            "artifact_type": manifest.artifact_type,
            "schema_version": manifest.schema_version,
            "data": manifest.data,
            "blobs": [blob.model_dump(mode="python") for blob in manifest.blobs],
            "inputs": [
                ref.model_dump(mode="python") if hasattr(ref, "model_dump") else ref
                for ref in manifest.inputs
            ],
        }

    def put_artifact(
        self,
        run_id: str,
        *,
        artifact_type: str,
        data: dict[str, Any],
        blobs: Sequence[BlobRef] = (),
        inputs: Sequence[ArtifactRef] = (),
        metadata: Optional[dict[str, Any]] = None,
        stage: Optional[str] = None,
        tool: Optional[str] = None,
    ) -> ArtifactManifest:
        manifest = ArtifactManifest(
            artifact_type=artifact_type,
            created_by=CreatedBy(run_id=run_id, stage=stage, tool=tool),
            created_at=_utcnow(),
            blobs=list(blobs),
            inputs=list(inputs),
            data=data,
            metadata=metadata or {},
        )

        artifact_id = hash_json(self._artifact_fingerprint_payload(manifest))
        manifest.artifact_id = artifact_id
        manifest.hashes = Hashes(sha256=artifact_id)

        path = self._artifact_manifest_path(run_id, artifact_id)
        rel_uri = str(path.relative_to(self.run_dir(run_id)))
        manifest.storage = StorageRef(uri=rel_uri, mime_type="application/json")

        _atomic_write_bytes(
            path,
            json.dumps(manifest.model_dump(mode="json"), indent=2, ensure_ascii=False, sort_keys=True).encode("utf-8"),
        )
        return manifest

    def load_artifact(self, run_id: str, artifact_id: str) -> ArtifactManifest:
        path = self._artifact_manifest_path(run_id, artifact_id)
        raw = json.loads(path.read_text(encoding="utf-8"))
        return ArtifactManifest.model_validate(raw)

    def commit_run_manifest(
        self,
        run_id: str,
        *,
        plugin_key: str,
        entrypoint: str,
        artifact_refs: Iterable[ArtifactRef],
        status: str,
        error: dict[str, Any] | None = None,
    ) -> RunManifest:
        now = _utcnow()
        manifest = RunManifest(
            run_id=run_id,
            model=RunModel(plugin_key=plugin_key, entrypoint=entrypoint),
            parameters=RunParameters(model_params={}, integrator={}, measurement={}, noise={}, notes=None),
            seeds={},
            timestamps=RunTimestamps(created_at=now, started_at=now, ended_at=now),
            artifact_refs=list(artifact_refs),
            status=status,
            error=error,
        )

        payload = manifest.model_dump(mode="json")
        payload_for_hash = dict(payload)
        payload_for_hash["hashes"] = dict(payload_for_hash.get("hashes") or {})
        payload_for_hash["hashes"].pop("run_manifest_sha256", None)
        manifest_hash = hash_json(payload_for_hash)
        manifest.hashes.run_manifest_sha256 = manifest_hash

        run_dir = self.run_dir(run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = run_dir / "manifest.json"
        _atomic_write_bytes(
            manifest_path,
            json.dumps(manifest.model_dump(mode="json"), indent=2, ensure_ascii=False, sort_keys=True).encode("utf-8"),
        )
        _atomic_write_bytes(run_dir / "manifest.sha256", f"{manifest_hash}\n".encode("utf-8"))
        return manifest

    def load_run_manifest(self, run_id: str) -> RunManifest:
        path = self.run_dir(run_id) / "manifest.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        return RunManifest.model_validate(raw)

    @staticmethod
    def to_artifact_ref(manifest: ArtifactManifest) -> ArtifactRef:
        return ArtifactRef(
            artifact_id=str(manifest.artifact_id),
            artifact_type=manifest.artifact_type,
            hashes=manifest.hashes if manifest.hashes else Hashes(sha256=str(manifest.artifact_id)),
            uri=(manifest.storage.uri if manifest.storage else None),
        )
