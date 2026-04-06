from __future__ import annotations


def _points(offset: float, n: int = 48):
    return [{"t": float(i), "values": [offset + 0.02 * i, offset + 0.01 * i, offset + 0.03 * i]} for i in range(n)]


def _complete_session(client) -> tuple[str, str]:
    created = client.post("/v1/sessions", json={"prompt": "bioelectric simulation intervention loop"}).json()
    session_id = created["session_id"]
    run_id = created["run_id"]

    client.post(
        f"/v1/sessions/{session_id}/ingest",
        json={"stream_kind": "baseline", "points": _points(0.0)},
    )
    client.post(f"/v1/sessions/{session_id}/advance")
    client.post(
        f"/v1/sessions/{session_id}/followup",
        json={"points": _points(-0.1), "metadata": {}},
    )
    return session_id, run_id


def test_run_report_view_is_html(client_and_service):
    client, _service = client_and_service
    _session_id, run_id = _complete_session(client)

    resp = client.get(f"/v1/runs/{run_id}/report/view")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "Run Report" in resp.text
    assert "Bioelectric simulation session completed" in resp.text


def test_demo_page_loads(client_and_service):
    client, _service = client_and_service
    resp = client.get("/demo")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "SACP Ecosystem Hub Demo Runner" in resp.text
