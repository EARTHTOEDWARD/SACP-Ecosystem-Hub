from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List

from sacp_hub.adapters.auic_adapter import AUICNormalizationAdapter
from sacp_hub.adapters.base import AdapterResult
from sacp_hub.adapters.maxwell_adapter import MaxwellNormalizationAdapter
from sacp_hub.adapters.osm_validator import OSMValidatorAdapter
from sacp_hub.adapters.sacp_api import SACPAPIAdapter
from sacp_hub.artifact_registry import validate_artifact_data
from sacp_hub.config import default_runs_root
from sacp_hub.models import (
    AdvanceResponse,
    ArtifactListResponse,
    ErrorEnvelope,
    FollowupRequest,
    IngestRequest,
    IngestResponse,
    IntentCompileResponse,
    SessionCreateResponse,
    SessionRecord,
    SessionView,
)
from sacp_hub.store.runstore import RunStore
from sacp_hub.store.schemas import ArtifactRef


@dataclass(frozen=True)
class StageFailure(Exception):
    stage: str
    kind: str
    message: str

    def __str__(self) -> str:
        return f"[{self.stage}] ({self.kind}) {self.message}"


_STAGE_SEQUENCE = [
    "INTAKE",
    "WINDOW",
    "BASELINE_ANALYZE",
    "CANDIDATE_GENERATE",
    "EXECUTE_SIM",
    "FOLLOWUP_INGEST",
    "DELTA_COMPARE",
    "BRIEF",
    "CONFORMANCE",
]


class HubService:
    def __init__(self, runs_root: Path | None = None) -> None:
        self.runstore = RunStore(runs_root=runs_root or default_runs_root())
        self.sessions: Dict[str, SessionRecord] = {}
        self.sacp_adapter = SACPAPIAdapter()
        self.osm_adapter = OSMValidatorAdapter()
        self.maxwell_adapter = MaxwellNormalizationAdapter()
        self.auic_adapter = AUICNormalizationAdapter()

    def compile_intent(self, prompt: str, context: Dict[str, Any] | None = None) -> IntentCompileResponse:
        text = prompt.lower()
        domain = "bioelectric" if any(k in text for k in ["bioelectric", "ion", "membrane", "cancer", "clinical"]) else "research"
        objective = "strange attractor intervention loop"
        mode = "realtime" if any(k in text for k in ["stream", "real time", "realtime", "live"]) else "batch"
        tags = ["simulation_only", "bioelectric_v1", "artifact_bus"]
        if mode == "realtime":
            tags.append("micro_batch_streaming")

        intent = {
            "prompt": prompt,
            "domain": domain,
            "objective": objective,
            "mode": mode,
            "simulation_only": True,
            "tags": tags,
        }

        steps = [
            {"stage": "INTAKE", "owner": "hub", "description": "Compile intent and initialize session artifacts"},
            {"stage": "WINDOW", "owner": "hub", "description": "Ingest baseline stream windows"},
            {"stage": "BASELINE_ANALYZE", "owner": "sacp_api", "description": "Compute baseline attractor metrics"},
            {"stage": "CANDIDATE_GENERATE", "owner": "sacp_api", "description": "Generate simulated intervention candidates"},
            {"stage": "EXECUTE_SIM", "owner": "sacp_api", "description": "Apply best intervention in simulation"},
            {"stage": "FOLLOWUP_INGEST", "owner": "hub", "description": "Ingest follow-up stream windows"},
            {"stage": "DELTA_COMPARE", "owner": "sacp_api", "description": "Compare baseline versus follow-up dynamics"},
            {"stage": "BRIEF", "owner": "hub", "description": "Build researcher-facing brief with lineage"},
            {"stage": "CONFORMANCE", "owner": "osm_validator", "description": "Run OSM RunStore conformance check"},
        ]

        route_plan = {
            "session_type": "bioelectric_intervention_loop",
            "steps": steps,
            "version": "v1",
        }
        return IntentCompileResponse(intent=intent, route_plan=route_plan)

    def create_session(self, prompt: str, context: Dict[str, Any] | None = None) -> SessionCreateResponse:
        compile_out = self.compile_intent(prompt=prompt, context=context or {})
        run_id = self.runstore.create_run()
        session = SessionRecord(run_id=run_id, prompt=prompt, context=context or {})

        self._mark_stage(session, "INTAKE")
        self._write_artifact(session, "INTAKE", "hub.intent.v1", compile_out.intent)
        self._write_artifact(session, "INTAKE", "hub.route_plan.v1", compile_out.route_plan)
        self._complete_stage(session, "INTAKE")
        self._write_session_state(session, last_stage="INTAKE")

        self.sessions[session.session_id] = session
        self._commit_manifest(session)

        return SessionCreateResponse(
            session_id=session.session_id,
            run_id=session.run_id,
            state=session.state,
            intent=compile_out.intent,
            route_plan=compile_out.route_plan,
        )

    def ingest(self, session_id: str, request: IngestRequest) -> IngestResponse:
        if isinstance(request, dict):
            request = IngestRequest.model_validate(request)
        session = self._get_session_or_raise(session_id)
        stage = "WINDOW" if request.stream_kind == "baseline" else "FOLLOWUP_INGEST"
        self._mark_stage(session, stage)

        window_ids = session.baseline_window_ids if request.stream_kind == "baseline" else session.followup_window_ids
        if request.suite_bridge is not None:
            snapshot = self._write_suite_bridge_snapshot(
                session=session,
                stage=stage,
                stream_kind=request.stream_kind,
                suite_bridge=request.suite_bridge.model_dump(mode="python"),
            )
            exported_windows = list(snapshot["baseline_windows"] if request.stream_kind == "baseline" else snapshot["followup_windows"])
            if not exported_windows:
                raise StageFailure(stage=stage, kind="contract", message=f"No {request.stream_kind} windows in Suite bridge export")
            for raw_window in exported_windows:
                manifest = self._write_bridge_window(
                    session=session,
                    stage=stage,
                    stream_kind=request.stream_kind,
                    window_ids=window_ids,
                    raw_window=raw_window,
                )
            artifact_id = str(session.context[f"{request.stream_kind}_suite_bridge_artifact_id"])
        else:
            window_index = len(window_ids)
            points = [point.model_dump(mode="python") for point in request.points]
            stats = self._window_stats(points)

            data = {
                "session_id": session.session_id,
                "stream_kind": request.stream_kind,
                "window_index": window_index,
                "points": points,
                "stats": stats,
                "metadata": dict(request.metadata),
            }
            manifest = self._write_artifact(session, stage, "hub.stream_window.v1", data)
            window_ids.append(str(manifest.artifact_id))
            artifact_id = str(manifest.artifact_id)
        self._complete_stage(session, stage)

        if request.stream_kind == "baseline" and session.state == "created":
            session.state = "running"
        session.touch()
        self._write_session_state(session, last_stage=stage)
        self._commit_manifest(session)

        return IngestResponse(
            session_id=session.session_id,
            stream_kind=request.stream_kind,
            artifact_id=artifact_id,
            state=session.state,
        )

    def advance(self, session_id: str) -> AdvanceResponse:
        session = self._get_session_or_raise(session_id)
        produced: List[str] = []

        try:
            if "BASELINE_ANALYZE" not in session.completed_stages:
                if not session.baseline_window_ids:
                    raise StageFailure(stage="BASELINE_ANALYZE", kind="contract", message="No baseline windows ingested")
                self._mark_stage(session, "BASELINE_ANALYZE")
                baseline_payload = self._run_baseline_analyze(session)
                manifest = self._write_artifact(
                    session,
                    "BASELINE_ANALYZE",
                    "hub.bioelectric.baseline_analysis.v1",
                    baseline_payload,
                )
                session.stage_outputs["BASELINE_ANALYZE"] = str(manifest.artifact_id)
                self._complete_stage(session, "BASELINE_ANALYZE")
                produced.append(str(manifest.artifact_id))

            if "CANDIDATE_GENERATE" not in session.completed_stages:
                self._mark_stage(session, "CANDIDATE_GENERATE")
                candidate_payload = self._run_candidate_generate(session)
                manifest = self._write_artifact(
                    session,
                    "CANDIDATE_GENERATE",
                    "hub.intervention_candidate_set.v1",
                    candidate_payload,
                )
                session.stage_outputs["CANDIDATE_GENERATE"] = str(manifest.artifact_id)
                self._complete_stage(session, "CANDIDATE_GENERATE")
                produced.append(str(manifest.artifact_id))

            if "EXECUTE_SIM" not in session.completed_stages:
                self._mark_stage(session, "EXECUTE_SIM")
                execution_payload = self._run_execute_intervention(session)
                manifest = self._write_artifact(
                    session,
                    "EXECUTE_SIM",
                    "hub.intervention_execution.v1",
                    execution_payload,
                )
                session.stage_outputs["EXECUTE_SIM"] = str(manifest.artifact_id)
                self._complete_stage(session, "EXECUTE_SIM")
                produced.append(str(manifest.artifact_id))

            session.state = "awaiting_followup"
            session.touch()
            self._write_session_state(session, last_stage="EXECUTE_SIM")
            self._commit_manifest(session)
        except StageFailure as exc:
            self._record_error(session, exc.stage, exc.kind, exc.message)
            session.state = "failed"
            self._write_session_state(session, last_stage=exc.stage)
            self._commit_manifest(session)

        return AdvanceResponse(
            session_id=session.session_id,
            state=session.state,
            produced_artifact_ids=produced,
            stage_history=list(session.stage_history),
        )

    def followup(self, session_id: str, request: FollowupRequest) -> AdvanceResponse:
        if isinstance(request, dict):
            request = FollowupRequest.model_validate(request)
        session = self._get_session_or_raise(session_id)

        if request.points or request.suite_bridge is not None:
            self.ingest(
                session_id,
                IngestRequest(
                    stream_kind="followup",
                    points=request.points,
                    suite_bridge=request.suite_bridge,
                    metadata=request.metadata,
                ),
            )
            if request.suite_bridge is None and request.points:
                try:
                    self._maybe_create_suite_followup_bridge(
                        session=session,
                        followup_points=[point.model_dump(mode="python") for point in request.points],
                        followup_metadata=dict(request.metadata),
                    )
                except StageFailure as exc:
                    self._record_error(session, exc.stage, exc.kind, exc.message)
                    session.state = "failed"
                    self._write_session_state(session, last_stage=exc.stage)
                    self._commit_manifest(session)
                    return AdvanceResponse(
                        session_id=session.session_id,
                        state=session.state,
                        produced_artifact_ids=[],
                        stage_history=list(session.stage_history),
                    )

        if not session.followup_window_ids:
            return AdvanceResponse(
                session_id=session.session_id,
                state=session.state,
                produced_artifact_ids=[],
                stage_history=list(session.stage_history),
            )

        produced: List[str] = []
        try:
            if "DELTA_COMPARE" not in session.completed_stages:
                self._mark_stage(session, "DELTA_COMPARE")
                delta_payload = self._run_delta_compare(session)
                manifest = self._write_artifact(
                    session,
                    "DELTA_COMPARE",
                    "hub.followup_delta_report.v1",
                    delta_payload,
                )
                session.stage_outputs["DELTA_COMPARE"] = str(manifest.artifact_id)
                self._complete_stage(session, "DELTA_COMPARE")
                produced.append(str(manifest.artifact_id))

            self._mark_stage(session, "BRIEF")
            brief_payload = self._build_brief(session, conformance={"status": "pending"})
            brief_manifest = self._write_artifact(session, "BRIEF", "hub.final_brief.v1", brief_payload)
            session.stage_outputs["BRIEF"] = str(brief_manifest.artifact_id)
            self._complete_stage(session, "BRIEF")
            produced.append(str(brief_manifest.artifact_id))

            self._mark_stage(session, "CONFORMANCE")
            conformance = self._run_conformance(session)
            self._complete_stage(session, "CONFORMANCE")

            brief_payload = self._build_brief(session, conformance=conformance)
            final_brief_manifest = self._write_artifact(session, "BRIEF", "hub.final_brief.v1", brief_payload)
            session.stage_outputs["BRIEF"] = str(final_brief_manifest.artifact_id)
            produced.append(str(final_brief_manifest.artifact_id))

            session.state = "completed"
            session.touch()
            self._write_session_state(session, last_stage="CONFORMANCE")
            self._commit_manifest(session)
        except StageFailure as exc:
            self._record_error(session, exc.stage, exc.kind, exc.message)
            session.state = "failed"
            self._write_session_state(session, last_stage=exc.stage)
            self._commit_manifest(session)

        return AdvanceResponse(
            session_id=session.session_id,
            state=session.state,
            produced_artifact_ids=produced,
            stage_history=list(session.stage_history),
        )

    def view_session(self, session_id: str) -> SessionView:
        session = self._get_session_or_raise(session_id)
        return SessionView(
            session_id=session.session_id,
            run_id=session.run_id,
            state=session.state,
            prompt=session.prompt,
            stage_history=list(session.stage_history),
            completed_stages=list(session.completed_stages),
            artifacts_by_stage={k: list(v) for k, v in session.artifacts_by_stage.items()},
            created_at=session.created_at,
            updated_at=session.updated_at,
            errors=list(session.errors),
        )

    def list_artifacts(self, session_id: str) -> ArtifactListResponse:
        session = self._get_session_or_raise(session_id)
        return ArtifactListResponse(
            session_id=session.session_id,
            artifact_ids=list(session.artifact_ids),
            artifacts_by_stage={k: list(v) for k, v in session.artifacts_by_stage.items()},
        )

    def report(self, session_id: str) -> Dict[str, Any]:
        if session_id in self.sessions:
            session = self.sessions[session_id]
            report_artifact_id = session.stage_outputs.get("BRIEF")
            if report_artifact_id:
                manifest = self.runstore.load_artifact(session.run_id, report_artifact_id)
                return manifest.data

        recovered = self._report_from_runs_by_session_id(session_id)
        if recovered is not None:
            return recovered

        raise KeyError(f"Unknown session_id: {session_id}")

    def report_by_run(self, run_id: str) -> Dict[str, Any]:
        return self._report_for_run_id(run_id)

    # ----------------------------- Internal ---------------------------------

    def _run_baseline_analyze(self, session: SessionRecord) -> Dict[str, Any]:
        snapshot = self._load_suite_bridge_snapshot(session, "baseline")
        if snapshot is not None:
            return {
                "action": "baseline_analyze",
                "session_id": session.session_id,
                "window_ids": list(session.baseline_window_ids),
                "metrics": dict(snapshot.get("baseline_metrics", {})),
                "simulation": dict(snapshot.get("simulation", {})),
                "suite_context": {
                    "provider": snapshot.get("provider"),
                    "bridge_kind": snapshot.get("bridge_kind"),
                    "bridge_contract_version": snapshot.get("bridge_contract_version"),
                    "suite_run_id": snapshot.get("suite_run_id"),
                    "suite_base_url": snapshot.get("suite_base_url"),
                    "export_hash": snapshot.get("export_hash"),
                    "suite_lineage": dict(snapshot.get("suite_lineage", {})),
                    "regime_summary": dict(snapshot.get("regime_summary", {})),
                    "persistence_summary": dict(snapshot.get("persistence_summary", {})),
                    "challenge_summary": dict(snapshot.get("challenge_summary", {})),
                },
            }
        windows = []
        for artifact_id in session.baseline_window_ids:
            payload = self._load_stream_window(session, artifact_id)
            payload["artifact_id"] = artifact_id
            windows.append(payload)
        prepared = self.sacp_adapter.prepare(
            {
                "action": "baseline_analyze",
                "session_id": session.session_id,
                "windows": windows,
                "t_max": 120.0,
            }
        )
        result = self.sacp_adapter.execute(prepared)
        return self._require_ok("BASELINE_ANALYZE", result)

    def _run_candidate_generate(self, session: SessionRecord) -> Dict[str, Any]:
        baseline_artifact_id = session.stage_outputs.get("BASELINE_ANALYZE")
        if not baseline_artifact_id:
            raise StageFailure(stage="CANDIDATE_GENERATE", kind="contract", message="Missing baseline analysis artifact")
        baseline_payload = self._load_hub_payload(
            session,
            baseline_artifact_id,
            expected_type="hub.bioelectric.baseline_analysis.v1",
            stage="CANDIDATE_GENERATE",
        )
        snapshot = self._load_suite_bridge_snapshot(session, "baseline")
        if snapshot is not None and snapshot.get("candidates"):
            return {
                "action": "candidate_generate",
                "session_id": session.session_id,
                "baseline_artifact_id": baseline_artifact_id,
                "candidates": list(snapshot.get("candidates", [])),
                "suite_context": {
                    "provider": snapshot.get("provider"),
                    "bridge_kind": snapshot.get("bridge_kind"),
                    "bridge_contract_version": snapshot.get("bridge_contract_version"),
                    "suite_run_id": snapshot.get("suite_run_id"),
                    "suite_base_url": snapshot.get("suite_base_url"),
                    "export_hash": snapshot.get("export_hash"),
                    "suite_lineage": dict(snapshot.get("suite_lineage", {})),
                },
            }
        prepared = self.sacp_adapter.prepare(
            {
                "action": "candidate_generate",
                "session_id": session.session_id,
                "baseline_artifact_id": baseline_artifact_id,
                "baseline": baseline_payload,
            }
        )
        result = self.sacp_adapter.execute(prepared)
        return self._require_ok("CANDIDATE_GENERATE", result)

    def _run_execute_intervention(self, session: SessionRecord) -> Dict[str, Any]:
        candidate_artifact_id = session.stage_outputs.get("CANDIDATE_GENERATE")
        if not candidate_artifact_id:
            raise StageFailure(stage="EXECUTE_SIM", kind="contract", message="Missing candidate artifact")
        candidates_payload = self._load_hub_payload(
            session,
            candidate_artifact_id,
            expected_type="hub.intervention_candidate_set.v1",
            stage="EXECUTE_SIM",
        )
        suite_context = dict(candidates_payload.get("suite_context", {}))
        candidates = list(candidates_payload.get("candidates", []))
        if suite_context and candidates:
            selected = max(candidates, key=lambda row: float(row.get("predicted_shift_score", 0.0)))
            effect_scale = float(selected.get("predicted_shift_score", 0.0))
            suite_execution_request: Dict[str, Any] = {}
            suite_execution_run: Dict[str, Any] = {}
            observed_effect: Dict[str, Any] = {}
            panel_run_id = str(selected.get("suite_candidate_ref", {}).get("panel_run_id") or suite_context.get("suite_run_id") or "").strip()
            if panel_run_id:
                try:
                    created = self.sacp_adapter.create_suite_intervention_request_from_panel_run(
                        panel_run_id=panel_run_id,
                        selected_candidate_id=str(selected.get("candidate_id") or "").strip() or None,
                        request_metadata={
                            "source": "sacp_hub_execute_sim",
                            "session_id": session.session_id,
                            "hub_run_id": session.run_id,
                        },
                        suite_base_url=str(suite_context.get("suite_base_url") or "").strip() or None,
                    )
                    suite_execution_request = {
                        "request_run_id": str(created.get("run_id")),
                        "request_ref": dict(created.get("request_ref") or {}),
                        "selected_candidate_id": str(selected.get("candidate_id")),
                    }
                    executed = self.sacp_adapter.create_suite_execution_from_intervention_request(
                        request_run_id=str(created.get("run_id")),
                        suite_base_url=str(suite_context.get("suite_base_url") or "").strip() or None,
                    )
                    suite_execution_run = {
                        "execution_run_id": str(executed.get("run_id")),
                        "execution_ref": dict(executed.get("execution_ref") or {}),
                        "executed_panel_run": dict(executed.get("executed_panel_run") or {}),
                    }
                    observed_effect = dict((executed.get("execution") or {}).get("observed_effect") or {})
                except ValueError as exc:
                    raise StageFailure(stage="EXECUTE_SIM", kind="contract", message=str(exc)) from exc
                except Exception as exc:  # noqa: BLE001
                    raise StageFailure(stage="EXECUTE_SIM", kind="infra", message=f"Suite intervention execution failed: {exc}") from exc
            return {
                "action": "execute_intervention",
                "session_id": session.session_id,
                "selected_candidate_id": selected["candidate_id"],
                "selection_reason": "Highest bridge predicted_shift_score",
                "predicted_effect": {
                    "instability_reduction": round(effect_scale * 0.4, 6),
                    "energy_gradient_reduction": round(effect_scale * 0.3, 6),
                },
                "suite_candidate_ref": dict(selected.get("suite_candidate_ref", {})),
                "suite_execution_request": suite_execution_request,
                "suite_execution_run": suite_execution_run,
                "observed_effect": observed_effect,
                "suite_context": suite_context,
            }
        prepared = self.sacp_adapter.prepare(
            {
                "action": "execute_intervention",
                "session_id": session.session_id,
                "candidates": candidates_payload["candidates"],
            }
        )
        result = self.sacp_adapter.execute(prepared)
        return self._require_ok("EXECUTE_SIM", result)

    def _run_delta_compare(self, session: SessionRecord) -> Dict[str, Any]:
        baseline_artifact_id = session.stage_outputs.get("BASELINE_ANALYZE")
        execution_artifact_id = session.stage_outputs.get("EXECUTE_SIM")
        if not baseline_artifact_id or not execution_artifact_id:
            raise StageFailure(stage="DELTA_COMPARE", kind="contract", message="Missing baseline/execution artifacts")

        baseline_payload = self._load_hub_payload(
            session,
            baseline_artifact_id,
            expected_type="hub.bioelectric.baseline_analysis.v1",
            stage="DELTA_COMPARE",
        )
        _execution_payload = self._load_hub_payload(
            session,
            execution_artifact_id,
            expected_type="hub.intervention_execution.v1",
            stage="DELTA_COMPARE",
        )
        snapshot = self._load_suite_bridge_snapshot(session, "followup")
        if snapshot is not None and snapshot.get("delta_report"):
            delta_payload = dict(snapshot.get("delta_report", {}))
            delta_payload.setdefault("session_id", session.session_id)
            delta_payload.setdefault(
                "suite_context",
                {
                    "provider": snapshot.get("provider"),
                    "bridge_kind": snapshot.get("bridge_kind"),
                    "bridge_contract_version": snapshot.get("bridge_contract_version"),
                    "suite_run_id": snapshot.get("suite_run_id"),
                    "export_hash": snapshot.get("export_hash"),
                    "suite_lineage": dict(snapshot.get("suite_lineage", {})),
                },
            )
            return delta_payload

        followup_windows = [self._load_stream_window(session, artifact_id) for artifact_id in session.followup_window_ids]
        followup_metrics = self._aggregate_window_metrics(followup_windows)

        prepared = self.sacp_adapter.prepare(
            {
                "action": "delta_compare",
                "session_id": session.session_id,
                "baseline_metrics": baseline_payload["metrics"],
                "followup_metrics": followup_metrics,
            }
        )
        result = self.sacp_adapter.execute(prepared)
        return self._require_ok("DELTA_COMPARE", result)

    def _run_conformance(self, session: SessionRecord) -> Dict[str, Any]:
        prepared = self.osm_adapter.prepare({"run_id": session.run_id, "runs_root": str(self.runstore.runs_root)})
        result = self.osm_adapter.execute(prepared)
        if not result.ok:
            raise StageFailure(
                stage="CONFORMANCE",
                kind=str(result.error_kind or "infra"),
                message=(result.error_message or "Unknown conformance error"),
            )
        return {
            "status": "passed",
            "stdout": result.raw_stdout,
            "validator": self.osm_adapter.capabilities().entrypoints["validate_runstore"],
        }

    @staticmethod
    def _require_ok(stage: str, result: AdapterResult) -> Dict[str, Any]:
        if result.ok:
            return dict(result.payload)
        raise StageFailure(stage=stage, kind=str(result.error_kind or "infra"), message=str(result.error_message or "Adapter failed"))

    def _build_brief(self, session: SessionRecord, conformance: Dict[str, Any]) -> Dict[str, Any]:
        execution_payload = {}
        delta_payload = {}
        suite_lineage: Dict[str, Any] = {}
        if "EXECUTE_SIM" in session.stage_outputs:
            execution_payload = self._load_hub_payload(
                session,
                session.stage_outputs["EXECUTE_SIM"],
                expected_type="hub.intervention_execution.v1",
                stage="BRIEF",
            )
        if "DELTA_COMPARE" in session.stage_outputs:
            delta_payload = self._load_hub_payload(
                session,
                session.stage_outputs["DELTA_COMPARE"],
                expected_type="hub.followup_delta_report.v1",
                stage="BRIEF",
            )
        baseline_snapshot = self._load_suite_bridge_snapshot(session, "baseline")
        followup_snapshot = self._load_suite_bridge_snapshot(session, "followup")
        if baseline_snapshot is not None:
            suite_lineage["baseline"] = {
                "suite_run_id": baseline_snapshot.get("suite_run_id"),
                "bridge_kind": baseline_snapshot.get("bridge_kind"),
                "bridge_contract_version": baseline_snapshot.get("bridge_contract_version"),
                "suite_lineage": dict(baseline_snapshot.get("suite_lineage", {})),
                "export_hash": baseline_snapshot.get("export_hash"),
            }
        if execution_payload.get("suite_execution_request"):
            suite_lineage["execution"] = dict(execution_payload.get("suite_execution_request", {}))
        if execution_payload.get("suite_execution_run"):
            suite_lineage.setdefault("execution", {}).update(dict(execution_payload.get("suite_execution_run", {})))
        if followup_snapshot is not None:
            suite_lineage["followup"] = {
                "suite_run_id": followup_snapshot.get("suite_run_id"),
                "bridge_kind": followup_snapshot.get("bridge_kind"),
                "bridge_contract_version": followup_snapshot.get("bridge_contract_version"),
                "suite_lineage": dict(followup_snapshot.get("suite_lineage", {})),
                "export_hash": followup_snapshot.get("export_hash"),
            }

        summary = "Bioelectric simulation session completed" if conformance.get("status") == "passed" else "Bioelectric session in progress"
        return {
            "session_id": session.session_id,
            "summary": summary,
            "intervention": execution_payload,
            "delta_report": delta_payload,
            "conformance": conformance,
            "lineage": {
                "run_id": session.run_id,
                "artifact_ids": list(session.artifact_ids),
                "artifacts_by_stage": {key: list(values) for key, values in session.artifacts_by_stage.items()},
            },
            "suite_lineage": suite_lineage,
        }

    def _load_stream_window(self, session: SessionRecord, artifact_id: str) -> Dict[str, Any]:
        return self._load_hub_payload(
            session,
            artifact_id,
            expected_type="hub.stream_window.v1",
            stage="WINDOW",
        )

    def _load_hub_payload(
        self,
        session: SessionRecord,
        artifact_id: str,
        *,
        expected_type: str,
        stage: str,
    ) -> Dict[str, Any]:
        try:
            artifact = self.runstore.load_artifact(session.run_id, artifact_id)
        except Exception as exc:  # noqa: BLE001
            raise StageFailure(stage=stage, kind="contract", message=f"Failed to load artifact {artifact_id}: {exc}") from exc
        if artifact.artifact_type != expected_type:
            raise StageFailure(
                stage=stage,
                kind="contract",
                message=f"Artifact type mismatch for {artifact_id}: {artifact.artifact_type} != {expected_type}",
            )
        try:
            return validate_artifact_data(artifact.artifact_type, dict(artifact.data))
        except Exception as exc:  # noqa: BLE001
            raise StageFailure(stage=stage, kind="contract", message=f"Artifact data validation failed: {exc}") from exc

    @staticmethod
    def _window_stats(points: List[Dict[str, Any]]) -> Dict[str, float]:
        vector_len = len(points[0]["values"])
        sums = [0.0 for _ in range(vector_len)]
        abs_sum = 0.0
        for point in points:
            values = [float(v) for v in point["values"]]
            for idx, value in enumerate(values):
                sums[idx] += value
                abs_sum += abs(value)
        n = float(len(points))
        mean_vector = [value / n for value in sums]
        return {
            "mean_signal": float(sum(mean_vector) / len(mean_vector)),
            "l1_mean": float(abs_sum / max(1.0, n * vector_len)),
            "point_count": float(len(points)),
        }

    def _aggregate_window_metrics(self, windows: Iterable[Dict[str, Any]]) -> Dict[str, float]:
        all_points: List[Dict[str, Any]] = []
        for window in windows:
            all_points.extend(list(window.get("points", [])))
        if not all_points:
            raise StageFailure(stage="DELTA_COMPARE", kind="contract", message="No follow-up points available")

        vector_len = len(all_points[0]["values"])
        means = [0.0 for _ in range(vector_len)]
        for point in all_points:
            values = [float(v) for v in point["values"]]
            for idx, value in enumerate(values):
                means[idx] += value
        n = float(len(all_points))
        means = [value / n for value in means]

        variance = 0.0
        gradient_sum = 0.0
        for idx, point in enumerate(all_points):
            values = [float(v) for v in point["values"]]
            variance += sum((values[i] - means[i]) ** 2 for i in range(vector_len))
            if idx > 0:
                prev = [float(v) for v in all_points[idx - 1]["values"]]
                gradient_sum += sum(abs(values[i] - prev[i]) for i in range(vector_len))

        return {
            "variance": float(variance / max(1.0, n)),
            "instability": float(gradient_sum / max(1.0, n - 1.0)),
            "mean_signal": float(sum(means) / len(means)),
            "energy_gradient_proxy": float(gradient_sum),
        }

    def _maybe_create_suite_followup_bridge(
        self,
        *,
        session: SessionRecord,
        followup_points: List[Dict[str, Any]],
        followup_metadata: Dict[str, Any],
    ) -> None:
        baseline_snapshot = self._load_suite_bridge_snapshot(session, "baseline")
        if baseline_snapshot is None:
            return
        if str(baseline_snapshot.get("bridge_kind", "")) != "panel_run":
            return
        if self._load_suite_bridge_snapshot(session, "followup") is not None:
            return

        execution_artifact_id = session.stage_outputs.get("EXECUTE_SIM")
        selected_candidate_id = None
        execution_request_metadata: Dict[str, Any] = {}
        if execution_artifact_id:
            execution_payload = self._load_hub_payload(
                session,
                execution_artifact_id,
                expected_type="hub.intervention_execution.v1",
                stage="FOLLOWUP_INGEST",
            )
            selected_candidate_id = str(execution_payload.get("selected_candidate_id") or "").strip() or None
            execution_request_metadata = dict(execution_payload.get("suite_execution_request", {}))
            execution_request_metadata.update(dict(execution_payload.get("suite_execution_run", {})))

        try:
            created = self.sacp_adapter.create_suite_verification_from_panel_run(
                panel_run_id=str(baseline_snapshot.get("suite_run_id", "")).strip(),
                followup_points=followup_points,
                selected_candidate_id=selected_candidate_id,
                followup_source_kind="hub_followup",
                followup_metadata={**dict(followup_metadata), **execution_request_metadata},
                suite_base_url=str(baseline_snapshot.get("suite_base_url", "")).strip() or None,
            )
        except ValueError as exc:
            raise StageFailure(stage="FOLLOWUP_INGEST", kind="contract", message=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise StageFailure(stage="FOLLOWUP_INGEST", kind="infra", message=f"Suite verification creation failed: {exc}") from exc
        self._write_suite_bridge_snapshot(
            session=session,
            stage="FOLLOWUP_INGEST",
            stream_kind="followup",
            suite_bridge={
                "provider": "sacp_suite",
                "bridge_kind": "verification_run",
                "run_id": str(created["run_id"]),
                "suite_base_url": str(baseline_snapshot.get("suite_base_url", "")).strip() or None,
            },
        )

    def _write_suite_bridge_snapshot(
        self,
        *,
        session: SessionRecord,
        stage: str,
        stream_kind: str,
        suite_bridge: Dict[str, Any],
    ) -> Dict[str, Any]:
        bridge_kind = str(suite_bridge["bridge_kind"])
        suite_run_id = str(suite_bridge["run_id"])
        suite_base_url = str(suite_bridge.get("suite_base_url") or self.sacp_adapter.base_url).rstrip("/")
        export = self.sacp_adapter.fetch_suite_bridge_export(suite_bridge)
        source_url = (
            f"{suite_base_url}/api/v1/bcp/hub-exports/panel-runs/{suite_run_id}"
            if bridge_kind == "panel_run"
            else f"{suite_base_url}/api/v1/bcp/hub-exports/verification-runs/{suite_run_id}"
        )

        if bridge_kind == "verification_run":
            baseline = dict(export.get("baseline", {}))
            data = {
                "session_id": session.session_id,
                "stream_kind": stream_kind,
                "provider": "sacp_suite",
                "bridge_kind": bridge_kind,
                "bridge_contract_version": str(export.get("bridge_contract_version", "")),
                "suite_run_id": suite_run_id,
                "suite_base_url": suite_base_url,
                "source_url": source_url,
                "export_hash": str(export.get("export_hash", "")),
                "suite_lineage": dict(export.get("suite_lineage", {})),
                "baseline_windows": list(baseline.get("baseline_windows", [])),
                "followup_windows": list(export.get("followup_windows", [])),
                "baseline_metrics": dict(baseline.get("baseline_metrics", {})),
                "followup_metrics": dict(export.get("followup_metrics", {})),
                "simulation": dict(baseline.get("simulation", {})),
                "regime_summary": dict(baseline.get("regime_summary", {})),
                "persistence_summary": dict(baseline.get("persistence_summary", {})),
                "challenge_summary": dict(baseline.get("challenge_summary", {})),
                "candidates": list(baseline.get("candidates", [])),
                "selected_candidate": dict(export.get("selected_candidate", {})),
                "delta_report": dict(export.get("delta_report", {})),
            }
        else:
            data = {
                "session_id": session.session_id,
                "stream_kind": stream_kind,
                "provider": "sacp_suite",
                "bridge_kind": bridge_kind,
                "bridge_contract_version": str(export.get("bridge_contract_version", "")),
                "suite_run_id": suite_run_id,
                "suite_base_url": suite_base_url,
                "source_url": source_url,
                "export_hash": str(export.get("export_hash", "")),
                "suite_lineage": dict(export.get("suite_lineage", {})),
                "baseline_windows": list(export.get("baseline_windows", [])),
                "followup_windows": [],
                "baseline_metrics": dict(export.get("baseline_metrics", {})),
                "followup_metrics": {},
                "simulation": dict(export.get("simulation", {})),
                "regime_summary": dict(export.get("regime_summary", {})),
                "persistence_summary": dict(export.get("persistence_summary", {})),
                "challenge_summary": dict(export.get("challenge_summary", {})),
                "candidates": list(export.get("candidates", [])),
                "selected_candidate": {},
                "delta_report": {},
            }
        manifest = self._write_artifact(session, stage, "hub.sacp_bridge_snapshot.v1", data, set_stage_output=False)
        session.context[f"{stream_kind}_suite_bridge_artifact_id"] = str(manifest.artifact_id)
        session.context[f"{stream_kind}_suite_bridge_run_id"] = suite_run_id
        return data

    def _write_bridge_window(
        self,
        *,
        session: SessionRecord,
        stage: str,
        stream_kind: str,
        window_ids: List[str],
        raw_window: Dict[str, Any],
    ):
        data = {
            "session_id": session.session_id,
            "stream_kind": stream_kind,
            "window_index": len(window_ids),
            "points": list(raw_window.get("points", [])),
            "stats": dict(raw_window.get("stats", {})),
            "metadata": {
                "source": "suite_bridge",
                "window_key": raw_window.get("window_key"),
                "label": raw_window.get("label"),
                "time_range": list(raw_window.get("time_range", [])),
            },
        }
        manifest = self._write_artifact(session, stage, "hub.stream_window.v1", data, set_stage_output=False)
        window_ids.append(str(manifest.artifact_id))
        return manifest

    def _load_suite_bridge_snapshot(self, session: SessionRecord, stream_kind: str) -> Dict[str, Any] | None:
        artifact_id = str(session.context.get(f"{stream_kind}_suite_bridge_artifact_id", "")).strip()
        if not artifact_id:
            return None
        return self._load_hub_payload(
            session,
            artifact_id,
            expected_type="hub.sacp_bridge_snapshot.v1",
            stage="WINDOW" if stream_kind == "baseline" else "FOLLOWUP_INGEST",
        )

    def _write_artifact(
        self,
        session: SessionRecord,
        stage: str,
        artifact_type: str,
        data: Dict[str, Any],
        *,
        set_stage_output: bool = True,
    ):
        valid_data = validate_artifact_data(artifact_type, data)
        inputs = self._current_artifact_refs(session)
        manifest = self.runstore.put_artifact(
            run_id=session.run_id,
            artifact_type=artifact_type,
            data=valid_data,
            inputs=inputs,
            stage=stage,
            tool=f"hub:{stage.lower()}",
        )
        artifact_id = str(manifest.artifact_id)
        session.artifact_ids.append(artifact_id)
        ref = self.runstore.to_artifact_ref(manifest)
        session.artifact_refs.append(ref.model_dump(mode="python"))
        session.artifacts_by_stage.setdefault(stage, []).append(artifact_id)
        if set_stage_output:
            session.stage_outputs[stage] = artifact_id
        return manifest

    def _write_session_state(self, session: SessionRecord, *, last_stage: str) -> None:
        data = {
            "session_id": session.session_id,
            "state": session.state,
            "last_stage": last_stage,
            "stage_history": list(session.stage_history),
            "artifact_ids": list(session.artifact_ids),
        }
        self._write_artifact(
            session,
            "SESSION_STATE",
            "hub.session_state.v1",
            data,
            set_stage_output=False,
        )

    def _current_artifact_refs(self, session: SessionRecord):
        refs = []
        for raw_ref in session.artifact_refs:
            refs.append(ArtifactRef.model_validate(raw_ref))
        return refs

    def _mark_stage(self, session: SessionRecord, stage: str) -> None:
        session.stage_history.append(stage)
        session.touch()

    def _complete_stage(self, session: SessionRecord, stage: str) -> None:
        if stage not in session.completed_stages:
            session.completed_stages.append(stage)
        session.touch()

    def _record_error(self, session: SessionRecord, stage: str, kind: str, message: str) -> None:
        envelope = ErrorEnvelope(stage=stage, kind=kind, message=message)
        session.errors.append(envelope.model_dump(mode="python"))
        session.touch()

    def _commit_manifest(self, session: SessionRecord) -> None:
        status = "running"
        error = None
        if session.state == "completed":
            status = "completed"
        elif session.state == "failed":
            status = "failed"
            error = session.errors[-1] if session.errors else {"message": "Unknown failure"}

        refs = self._current_artifact_refs(session)
        self.runstore.commit_run_manifest(
            session.run_id,
            plugin_key="sacp_ecosystem_hub",
            entrypoint="api:/v1/sessions",
            artifact_refs=refs,
            status=status,
            error=error,
        )

    def _get_session_or_raise(self, session_id: str) -> SessionRecord:
        if session_id not in self.sessions:
            raise KeyError(f"Unknown session_id: {session_id}")
        return self.sessions[session_id]

    def _report_from_runs_by_session_id(self, session_id: str) -> Dict[str, Any] | None:
        for run_id in self._iter_run_ids():
            try:
                report = self._report_for_run_id(run_id)
            except Exception:
                continue
            if str(report.get("session_id", "")) == session_id:
                return report
        return None

    def _report_for_run_id(self, run_id: str) -> Dict[str, Any]:
        try:
            run_manifest = self.runstore.load_run_manifest(run_id)
        except Exception as exc:  # noqa: BLE001
            raise KeyError(f"Unknown run_id: {run_id}") from exc

        brief_refs = [ref for ref in run_manifest.artifact_refs if ref.artifact_type == "hub.final_brief.v1"]
        if not brief_refs:
            raise KeyError(f"No final brief artifact for run_id: {run_id}")

        brief_ref = brief_refs[-1]
        artifact = self.runstore.load_artifact(run_id, brief_ref.artifact_id)
        if artifact.artifact_type != "hub.final_brief.v1":
            raise KeyError(f"Final brief artifact type mismatch for run_id: {run_id}")
        return dict(artifact.data)

    def _iter_run_ids(self) -> List[str]:
        runs_root = self.runstore.runs_root
        if not runs_root.exists():
            return []

        candidates: List[tuple[float, str]] = []
        for entry in runs_root.iterdir():
            if not entry.is_dir():
                continue
            manifest_path = entry / "manifest.json"
            if not manifest_path.exists():
                continue
            try:
                stamp = manifest_path.stat().st_mtime
            except Exception:
                stamp = 0.0
            candidates.append((stamp, entry.name))
        candidates.sort(key=lambda row: (-row[0], row[1]))
        return [run_id for _, run_id in candidates]


def make_default_service() -> HubService:
    return HubService()
