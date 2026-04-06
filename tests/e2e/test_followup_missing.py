from __future__ import annotations


def _points(n: int = 20):
    return [{"t": float(i), "values": [0.01 * i, 0.02 * i, 0.03 * i]} for i in range(n)]


def test_missing_followup_keeps_session_awaiting_followup(client_and_service):
    client, _service = client_and_service
    created = client.post("/v1/sessions", json={"prompt": "bioelectric"}).json()
    session_id = created["session_id"]

    client.post(f"/v1/sessions/{session_id}/ingest", json={"stream_kind": "baseline", "points": _points()})
    client.post(f"/v1/sessions/{session_id}/advance")

    follow = client.post(f"/v1/sessions/{session_id}/followup", json={"points": [], "metadata": {}})
    assert follow.status_code == 200
    assert follow.json()["state"] == "awaiting_followup"
