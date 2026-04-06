from __future__ import annotations

from sacp_hub.adapters.base import AdapterResult


def _points(n: int = 26):
    return [{"t": float(i), "values": [0.02 * i, 0.01 * i, 0.03 * i]} for i in range(n)]


def test_retry_after_transient_failure_does_not_duplicate_completed_stages(client_and_service, monkeypatch):
    client, service = client_and_service
    created = client.post("/v1/sessions", json={"prompt": "bioelectric"}).json()
    session_id = created["session_id"]

    client.post(f"/v1/sessions/{session_id}/ingest", json={"stream_kind": "baseline", "points": _points()})

    original_execute = service.sacp_adapter.execute
    calls = {"count": 0}

    def flaky_execute(prepared_call):
        if prepared_call.action == "baseline_analyze" and calls["count"] == 0:
            calls["count"] += 1
            return AdapterResult(ok=False, error_kind="transient", error_message="temporary timeout")
        return original_execute(prepared_call)

    monkeypatch.setattr(service.sacp_adapter, "execute", flaky_execute)

    first = client.post(f"/v1/sessions/{session_id}/advance")
    assert first.status_code == 200
    assert first.json()["state"] == "failed"

    second = client.post(f"/v1/sessions/{session_id}/advance")
    assert second.status_code == 200
    assert second.json()["state"] == "awaiting_followup"

    view = client.get(f"/v1/sessions/{session_id}").json()
    assert view["completed_stages"].count("BASELINE_ANALYZE") == 1
    assert len(view["artifacts_by_stage"]["BASELINE_ANALYZE"]) == 1
