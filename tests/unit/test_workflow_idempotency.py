from __future__ import annotations


def _baseline_points(n: int = 24):
    return [{"t": float(i), "values": [0.1 * i, 0.2 * i, 0.05 * i]} for i in range(n)]


def test_advance_is_stage_idempotent(service):
    session = service.create_session("bioelectric intervention simulation")
    service.ingest(session.session_id, request={"stream_kind": "baseline", "points": _baseline_points()})
    first = service.advance(session.session_id)
    second = service.advance(session.session_id)

    assert first.state in {"awaiting_followup", "failed"}
    assert second.produced_artifact_ids == []

    view = service.view_session(session.session_id)
    assert view.completed_stages.count("BASELINE_ANALYZE") == 1
    assert view.completed_stages.count("CANDIDATE_GENERATE") == 1
    assert view.completed_stages.count("EXECUTE_SIM") == 1
