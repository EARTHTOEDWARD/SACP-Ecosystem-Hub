from __future__ import annotations


def _points(offset: float, n: int = 48):
    return [{"t": float(i), "values": [offset + 0.02 * i, offset + 0.01 * i, offset + 0.03 * i]} for i in range(n)]


def test_happy_path_end_to_end(client_and_service):
    client, _service = client_and_service

    created = client.post("/v1/sessions", json={"prompt": "bioelectric simulation intervention loop"}).json()
    session_id = created["session_id"]

    ingest_resp = client.post(
        f"/v1/sessions/{session_id}/ingest",
        json={"stream_kind": "baseline", "points": _points(0.0)},
    )
    assert ingest_resp.status_code == 200

    advance_resp = client.post(f"/v1/sessions/{session_id}/advance")
    assert advance_resp.status_code == 200
    assert advance_resp.json()["state"] == "awaiting_followup"

    follow_resp = client.post(
        f"/v1/sessions/{session_id}/followup",
        json={"points": _points(-0.1), "metadata": {}},
    )
    assert follow_resp.status_code == 200
    assert follow_resp.json()["state"] == "completed"

    report = client.get(f"/v1/sessions/{session_id}/report")
    assert report.status_code == 200
    body = report.json()
    assert body["conformance"]["status"] == "passed"
    assert len(body["lineage"]["artifact_ids"]) > 0
