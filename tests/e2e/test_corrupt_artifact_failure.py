from __future__ import annotations


def _points(offset: float, n: int = 22):
    return [{"t": float(i), "values": [offset + 0.01 * i, offset + 0.03 * i, offset + 0.02 * i]} for i in range(n)]


def test_corrupt_intermediate_artifact_fails_with_stage_context(client_and_service):
    client, service = client_and_service

    created = client.post("/v1/sessions", json={"prompt": "bioelectric"}).json()
    session_id = created["session_id"]
    run_id = created["run_id"]

    client.post(f"/v1/sessions/{session_id}/ingest", json={"stream_kind": "baseline", "points": _points(0.0)})
    client.post(f"/v1/sessions/{session_id}/advance")

    view = client.get(f"/v1/sessions/{session_id}").json()
    baseline_artifact_id = view["artifacts_by_stage"]["BASELINE_ANALYZE"][0]
    artifact_path = service.runstore.run_dir(run_id) / "artifacts" / baseline_artifact_id / "artifact.json"
    artifact_path.write_text("{invalid json", encoding="utf-8")

    follow = client.post(
        f"/v1/sessions/{session_id}/followup",
        json={"points": _points(-0.1), "metadata": {}},
    )
    assert follow.status_code == 200
    assert follow.json()["state"] == "failed"

    view_after = client.get(f"/v1/sessions/{session_id}").json()
    assert any(err["stage"] == "DELTA_COMPARE" for err in view_after["errors"])
