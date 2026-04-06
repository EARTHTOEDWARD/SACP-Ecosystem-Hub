from __future__ import annotations

from sacp_hub.artifact_registry import validate_artifact_data


def _points(offset: float, n: int = 40):
    return [{"t": float(i), "values": [offset + 0.03 * i, offset + 0.01 * i, offset + 0.02 * i]} for i in range(n)]


def test_all_emitted_hub_artifacts_validate(service):
    session = service.create_session("bioelectric attractor diagnosis and intervention")
    service.ingest(session.session_id, request={"stream_kind": "baseline", "points": _points(0.0)})
    service.advance(session.session_id)
    service.followup(session.session_id, request={"points": _points(-0.1), "metadata": {}})

    artifacts = service.list_artifacts(session.session_id).artifact_ids
    for artifact_id in artifacts:
        manifest = service.runstore.load_artifact(session.run_id, artifact_id)
        if manifest.artifact_type.startswith("hub."):
            validate_artifact_data(manifest.artifact_type, dict(manifest.data))
