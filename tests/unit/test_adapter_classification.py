from __future__ import annotations

import requests

from sacp_hub.adapters.sacp_api import SACPAPIAdapter


def test_adapter_classifies_contract_error():
    adapter = SACPAPIAdapter()
    result = adapter.execute(adapter.prepare({"action": "candidate_generate", "session_id": "s1"}))
    assert result.ok is False
    assert result.error_kind == "contract"


def test_adapter_classifies_transient_timeout(monkeypatch):
    adapter = SACPAPIAdapter()

    def _timeout(_payload):
        raise requests.Timeout("simulated timeout")

    monkeypatch.setattr(adapter, "_baseline_analyze", _timeout)
    result = adapter.execute(adapter.prepare({"action": "baseline_analyze", "session_id": "s1", "windows": []}))
    assert result.ok is False
    assert result.error_kind == "transient"
