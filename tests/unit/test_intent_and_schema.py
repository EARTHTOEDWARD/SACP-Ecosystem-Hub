from __future__ import annotations

from sacp_hub.artifact_registry import validate_artifact_data


def test_intent_compile_is_deterministic(service):
    prompt = "Analyze streamed bioelectric membrane data and compare follow-up dynamics"
    a = service.compile_intent(prompt)
    b = service.compile_intent(prompt)

    assert a.intent["domain"] == b.intent["domain"] == "bioelectric"
    assert a.intent["objective"] == b.intent["objective"]
    assert a.route_plan["steps"] == b.route_plan["steps"]


def test_intent_schema_validation(service):
    compiled = service.compile_intent("find attractor dynamics in simulated bioelectric signals")
    validated = validate_artifact_data("hub.intent.v1", compiled.intent)
    assert validated["simulation_only"] is True
    assert "bioelectric_v1" in validated["tags"]
