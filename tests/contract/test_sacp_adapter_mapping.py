from __future__ import annotations

from sacp_hub.adapters.sacp_api import SACPAPIAdapter


def test_sacp_adapter_maps_baseline_to_hub_artifact_type():
    adapter = SACPAPIAdapter()
    windows = [{"artifact_id": "w1", "points": [{"t": 0.0, "values": [0.1, 0.2, 0.3]}]}]
    result = adapter.execute(adapter.prepare({"action": "baseline_analyze", "session_id": "s1", "windows": windows}))
    assert result.ok is True

    normalized = adapter.normalize(result)
    report = adapter.validate(normalized)

    assert normalized[0]["artifact_type"] == "hub.bioelectric.baseline_analysis.v1"
    assert report.ok is True
