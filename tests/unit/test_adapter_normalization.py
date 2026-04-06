from __future__ import annotations

from sacp_hub.adapters.sacp_api import SACPAPIAdapter


def test_normalize_and_validate_candidate_payload():
    adapter = SACPAPIAdapter()
    payload = {
        "action": "candidate_generate",
        "session_id": "s1",
        "baseline_artifact_id": "a1",
        "candidates": [{"candidate_id": "c1", "label": "x", "mechanism": "m", "predicted_shift_score": 0.2, "confidence": 0.6}],
    }
    normalized = adapter.normalize(type("R", (), {"ok": True, "payload": payload})())
    report = adapter.validate(normalized)

    assert normalized[0]["artifact_type"] == "hub.intervention_candidate_set.v1"
    assert report.ok is True
