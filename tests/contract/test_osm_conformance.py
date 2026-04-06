from __future__ import annotations


def _points(offset: float, n: int = 30):
    return [{"t": float(i), "values": [offset + 0.02 * i, offset + 0.03 * i, offset + 0.01 * i]} for i in range(n)]


def test_osm_validator_passes_on_happy_session_run(service):
    created = service.create_session("bioelectric simulation")
    service.ingest(created.session_id, request={"stream_kind": "baseline", "points": _points(0.0)})
    service.advance(created.session_id)
    service.followup(created.session_id, request={"points": _points(-0.2), "metadata": {}})

    result = service.osm_adapter.execute(
        service.osm_adapter.prepare({"run_id": created.run_id, "runs_root": str(service.runstore.runs_root)})
    )
    assert result.ok is True
