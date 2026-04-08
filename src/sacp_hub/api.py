from __future__ import annotations

import json
import os
from html import escape
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from sacp_hub.models import (
    AdvanceResponse,
    ArtifactListResponse,
    FollowupRequest,
    IngestRequest,
    IngestResponse,
    IntentCompileRequest,
    IntentCompileResponse,
    SessionCreateRequest,
    SessionCreateResponse,
    SessionView,
)
from sacp_hub.service import HubService, make_default_service


app = FastAPI(title="SACP Ecosystem Hub API", version="0.1.0")
_service: HubService = make_default_service()


def _format_metric(value: Any) -> str:
    try:
        return f"{float(value):.6f}"
    except (TypeError, ValueError):
        return "n/a"


def _render_metric_table(title: str, metrics: dict[str, Any]) -> str:
    rows = [
        ("mean_signal", "Mean Signal"),
        ("variance", "Variance"),
        ("instability", "Instability"),
        ("energy_gradient_proxy", "Energy Gradient Proxy"),
    ]
    row_html = "".join(
        f"<tr><td>{label}</td><td>{_format_metric(metrics.get(key))}</td></tr>"
        for key, label in rows
    )
    return f"""
    <section class="card">
      <h3>{escape(title)}</h3>
      <table>
        <tbody>
          {row_html}
        </tbody>
      </table>
    </section>
    """


def _render_report_html(report: dict[str, Any], heading: str) -> str:
    intervention = report.get("intervention", {})
    delta_report = report.get("delta_report", {})
    baseline_metrics = delta_report.get("baseline_metrics", {})
    followup_metrics = delta_report.get("followup_metrics", {})
    delta_metrics = delta_report.get("delta", {})
    lineage = report.get("lineage", {})
    suite_lineage = report.get("suite_lineage", {})
    artifacts = lineage.get("artifact_ids", [])
    summary = report.get("summary", "No summary available")
    conformance = report.get("conformance", {})
    suite_execution_request = intervention.get("suite_execution_request", {}) or {}
    suite_execution_run = intervention.get("suite_execution_run", {}) or {}
    observed_effect = intervention.get("observed_effect", {}) or {}
    raw_json = escape(json.dumps(report, indent=2, sort_keys=True))

    artifact_lines = "".join(f"<li><code>{escape(str(artifact_id))}</code></li>" for artifact_id in artifacts)
    suite_lineage_html = ""
    if suite_lineage:
        suite_json = escape(json.dumps(suite_lineage, indent=2, sort_keys=True))
        suite_lineage_html = f"""
    <section class="card">
      <h2>Suite Lineage</h2>
      <pre>{suite_json}</pre>
    </section>
    """

    return f"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>SACP Hub Report</title>
  <style>
    :root {{
      --bg: #f7f5ef;
      --ink: #12263a;
      --panel: #ffffff;
      --accent: #0c7c59;
      --muted: #4b5d6d;
      --line: #dce3e8;
    }}
    body {{
      margin: 0;
      padding: 32px;
      background:
        radial-gradient(circle at 10% 5%, #fef7d8 0%, transparent 38%),
        radial-gradient(circle at 95% 10%, #d7efe6 0%, transparent 40%),
        var(--bg);
      color: var(--ink);
      font-family: "IBM Plex Sans", "Avenir Next", sans-serif;
    }}
    .wrap {{
      max-width: 1100px;
      margin: 0 auto;
      display: grid;
      gap: 18px;
    }}
    .card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 18px;
      box-shadow: 0 10px 32px rgba(18, 38, 58, 0.08);
    }}
    h1, h2, h3 {{
      margin: 0 0 12px;
      line-height: 1.2;
    }}
    h1 {{
      font-size: 30px;
      letter-spacing: -0.01em;
    }}
    h2 {{
      font-size: 22px;
      color: var(--accent);
    }}
    h3 {{
      font-size: 16px;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }}
    .grid-3 {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 14px;
    }}
    .grid-2 {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 14px;
    }}
    td {{
      border-bottom: 1px dashed var(--line);
      padding: 8px 0;
    }}
    td:first-child {{
      color: var(--muted);
    }}
    code, pre {{
      font-family: "IBM Plex Mono", "SF Mono", Menlo, monospace;
      font-size: 12px;
    }}
    pre {{
      margin: 0;
      white-space: pre-wrap;
      word-break: break-word;
    }}
    ul {{
      margin: 0;
      padding-left: 18px;
      max-height: 260px;
      overflow: auto;
    }}
    .status {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 6px 10px;
      border-radius: 999px;
      background: #e6f4ee;
      color: #0b5f43;
      font-weight: 700;
      font-size: 13px;
    }}
    .meta {{
      display: grid;
      gap: 8px;
      font-size: 14px;
      color: var(--muted);
    }}
    @media (max-width: 880px) {{
      body {{
        padding: 16px;
      }}
      .grid-3, .grid-2 {{
        grid-template-columns: 1fr;
      }}
    }}
  </style>
</head>
<body>
  <main class="wrap">
    <section class="card">
      <h1>{escape(heading)}</h1>
      <p>{escape(str(summary))}</p>
      <div class="meta">
        <div><span class="status">Conformance: {escape(str(conformance.get("status", "unknown")))}</span></div>
        <div>Session: <code>{escape(str(report.get("session_id", "")))}</code></div>
        <div>Run: <code>{escape(str(lineage.get("run_id", "")))}</code></div>
      </div>
    </section>

    <section class="grid-2">
      <div class="card">
        <h2>Intervention</h2>
        <div class="meta">
          <div>Selected candidate: <code>{escape(str(intervention.get("selected_candidate_id", "")))}</code></div>
          <div>Reason: {escape(str(intervention.get("selection_reason", "")))}</div>
          <div>Predicted energy gradient reduction: {_format_metric(intervention.get("predicted_effect", {}).get("energy_gradient_reduction"))}</div>
          <div>Predicted instability reduction: {_format_metric(intervention.get("predicted_effect", {}).get("instability_reduction"))}</div>
          <div>Suite execution request run: <code>{escape(str(suite_execution_request.get("request_run_id", "")))}</code></div>
          <div>Suite execution request artifact: <code>{escape(str((suite_execution_request.get("request_ref") or {}).get("artifact_id", "")))}</code></div>
          <div>Suite execution run: <code>{escape(str(suite_execution_run.get("execution_run_id", "")))}</code></div>
          <div>Suite execution artifact: <code>{escape(str((suite_execution_run.get("execution_ref") or {}).get("artifact_id", "")))}</code></div>
          <div>Executed panel run: <code>{escape(str((suite_execution_run.get("executed_panel_run") or {}).get("run_id", "")))}</code></div>
          <div>Observed executed regime: <code>{escape(str(observed_effect.get("executed_regime", "")))}</code></div>
          <div>Knocked out of saddle: <strong>{escape(str(delta_report.get("knocked_out_of_saddle", "")))}</strong></div>
        </div>
      </div>
      <div class="card">
        <h2>Lineage</h2>
        <div class="meta">
          <div>Total artifacts: <strong>{len(artifacts)}</strong></div>
        </div>
        <ul>{artifact_lines}</ul>
      </div>
    </section>

    <section class="grid-3">
      {_render_metric_table("Baseline Metrics", baseline_metrics)}
      {_render_metric_table("Follow-up Metrics", followup_metrics)}
      {_render_metric_table("Delta", delta_metrics)}
    </section>

    <section class="card">
      <h2>Raw Report JSON</h2>
      <pre>{raw_json}</pre>
    </section>

    {suite_lineage_html}
  </main>
</body>
</html>
"""


def _render_demo_html() -> str:
    return """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>SACP Hub Demo</title>
  <style>
    :root {
      --bg: #f3f8f5;
      --ink: #0f2233;
      --panel: #ffffff;
      --line: #d4dde5;
      --accent: #00796b;
      --warn: #b54a00;
    }
    body {
      margin: 0;
      color: var(--ink);
      background:
        linear-gradient(125deg, rgba(0, 121, 107, 0.12), transparent 35%),
        linear-gradient(300deg, rgba(255, 214, 102, 0.18), transparent 40%),
        var(--bg);
      font-family: "Space Grotesk", "Trebuchet MS", sans-serif;
    }
    .wrap {
      max-width: 1060px;
      margin: 0 auto;
      padding: 28px 18px 34px;
      display: grid;
      gap: 16px;
    }
    .card {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 16px;
      box-shadow: 0 16px 32px rgba(6, 27, 41, 0.08);
    }
    h1, h2 {
      margin: 0 0 10px;
      line-height: 1.2;
    }
    h1 {
      font-size: 30px;
      letter-spacing: -0.015em;
    }
    h2 {
      color: var(--accent);
      font-size: 18px;
    }
    p {
      margin: 0 0 12px;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 12px;
    }
    label {
      display: grid;
      gap: 6px;
      font-size: 13px;
      color: #334f67;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.03em;
    }
    input, textarea, button {
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 10px 12px;
      font-family: "IBM Plex Mono", Menlo, monospace;
      font-size: 13px;
      color: var(--ink);
      background: #fff;
    }
    textarea {
      min-height: 72px;
      resize: vertical;
    }
    button {
      cursor: pointer;
      border: 0;
      font-family: "Space Grotesk", sans-serif;
      font-weight: 700;
      font-size: 15px;
      background: var(--accent);
      color: #fff;
      padding: 12px 18px;
    }
    button:disabled {
      opacity: 0.65;
      cursor: not-allowed;
    }
    .actions {
      display: flex;
      gap: 10px;
      align-items: center;
      flex-wrap: wrap;
    }
    .links {
      display: grid;
      gap: 6px;
      font-size: 14px;
    }
    a {
      color: #0055aa;
      text-decoration: none;
    }
    a:hover {
      text-decoration: underline;
    }
    .log {
      background: #0d1622;
      color: #d2f0e8;
      border-radius: 10px;
      padding: 12px;
      min-height: 220px;
      overflow: auto;
      white-space: pre-wrap;
      font-family: "IBM Plex Mono", Menlo, monospace;
      font-size: 12px;
      line-height: 1.45;
    }
    .error {
      color: var(--warn);
      font-weight: 700;
    }
    @media (max-width: 920px) {
      .grid {
        grid-template-columns: 1fr;
      }
    }
  </style>
</head>
<body>
  <main class="wrap">
    <section class="card">
      <h1>SACP Ecosystem Hub Demo Runner</h1>
      <p>Runs full bioelectric flow: baseline ingest -> advance -> follow-up -> report.</p>
      <div class="grid">
        <label>Prompt
          <textarea id="prompt">Simulate bioelectric intervention loop and compare follow-up attractor dynamics.</textarea>
        </label>
        <label>Baseline Points
          <input id="baselinePoints" type="number" value="120" min="10" step="1">
        </label>
        <label>Follow-up Points
          <input id="followupPoints" type="number" value="120" min="10" step="1">
        </label>
        <label>Baseline Offset
          <input id="baselineOffset" type="number" value="0.0" step="0.01">
        </label>
        <label>Follow-up Offset
          <input id="followupOffset" type="number" value="-0.12" step="0.01">
        </label>
        <label>Baseline Slope
          <input id="baselineSlope" type="number" value="0.02" step="0.001">
        </label>
        <label>Follow-up Slope
          <input id="followupSlope" type="number" value="0.014" step="0.001">
        </label>
      </div>
      <div class="actions">
        <button id="runBtn">Run Full Demo</button>
        <span id="status"></span>
      </div>
    </section>

    <section class="card">
      <h2>Result Links</h2>
      <div class="links">
        <div>Session: <code id="sessionId">-</code></div>
        <div>Run: <code id="runId">-</code></div>
        <div>JSON report: <a id="jsonReport" href="#" target="_blank" rel="noopener noreferrer">-</a></div>
        <div>HTML report: <a id="htmlReport" href="#" target="_blank" rel="noopener noreferrer">-</a></div>
      </div>
    </section>

    <section class="card">
      <h2>Execution Log</h2>
      <div id="log" class="log"></div>
      <div id="error" class="error"></div>
    </section>
  </main>
  <script>
    function buildPoints(n, offset, slope) {
      const points = [];
      for (let i = 0; i < n; i += 1) {
        points.push({
          t: Number(i),
          values: [
            offset + slope * i + 0.08 * Math.sin(i / 8.0),
            offset + 0.5 * slope * i + 0.05 * Math.cos(i / 9.0),
            offset + 0.75 * slope * i + 0.06 * Math.sin(i / 11.0 + 0.4),
          ],
        });
      }
      return points;
    }

    async function call(method, url, payload) {
      const options = { method, headers: { "Content-Type": "application/json" } };
      if (method !== "GET") {
        options.body = JSON.stringify(payload || {});
      }
      const response = await fetch(url, options);
      const body = await response.text();
      if (!response.ok) {
        throw new Error(method + " " + url + " failed (" + response.status + "): " + body);
      }
      return body ? JSON.parse(body) : {};
    }

    const logEl = document.getElementById("log");
    const errorEl = document.getElementById("error");
    const statusEl = document.getElementById("status");
    const runBtn = document.getElementById("runBtn");
    const sessionIdEl = document.getElementById("sessionId");
    const runIdEl = document.getElementById("runId");
    const jsonReportEl = document.getElementById("jsonReport");
    const htmlReportEl = document.getElementById("htmlReport");

    function log(message) {
      const stamp = new Date().toISOString().slice(11, 19);
      logEl.textContent += "[" + stamp + "] " + message + "\\n";
      logEl.scrollTop = logEl.scrollHeight;
    }

    function resetView() {
      logEl.textContent = "";
      errorEl.textContent = "";
      statusEl.textContent = "";
      sessionIdEl.textContent = "-";
      runIdEl.textContent = "-";
      jsonReportEl.textContent = "-";
      jsonReportEl.removeAttribute("href");
      htmlReportEl.textContent = "-";
      htmlReportEl.removeAttribute("href");
    }

    async function runDemo() {
      const base = window.location.origin;
      resetView();
      runBtn.disabled = true;
      statusEl.textContent = "Running...";

      const prompt = document.getElementById("prompt").value;
      const baselinePoints = Number(document.getElementById("baselinePoints").value);
      const followupPoints = Number(document.getElementById("followupPoints").value);
      const baselineOffset = Number(document.getElementById("baselineOffset").value);
      const followupOffset = Number(document.getElementById("followupOffset").value);
      const baselineSlope = Number(document.getElementById("baselineSlope").value);
      const followupSlope = Number(document.getElementById("followupSlope").value);

      try {
        log("1/7 compile intent");
        await call("POST", base + "/v1/intents/compile", { prompt, context: { demo_ui: true } });

        log("2/7 create session");
        const created = await call("POST", base + "/v1/sessions", { prompt, context: { demo_ui: true } });
        const sessionId = created.session_id;
        const runId = created.run_id;
        sessionIdEl.textContent = sessionId;
        runIdEl.textContent = runId;
        log("session_id=" + sessionId);
        log("run_id=" + runId);

        log("3/7 ingest baseline");
        await call("POST", base + "/v1/sessions/" + sessionId + "/ingest", {
          stream_kind: "baseline",
          points: buildPoints(baselinePoints, baselineOffset, baselineSlope),
          metadata: { source: "demo_ui_baseline" },
        });

        log("4/7 advance");
        const advanced = await call("POST", base + "/v1/sessions/" + sessionId + "/advance", {});
        log("state after advance=" + advanced.state);

        log("5/7 follow-up ingest and finalize");
        const follow = await call("POST", base + "/v1/sessions/" + sessionId + "/followup", {
          points: buildPoints(followupPoints, followupOffset, followupSlope),
          metadata: { source: "demo_ui_followup_72h" },
        });
        log("state after followup=" + follow.state);

        log("6/7 get lineage");
        const artifacts = await call("GET", base + "/v1/sessions/" + sessionId + "/artifacts");
        log("artifact_count=" + artifacts.artifact_ids.length);

        log("7/7 fetch report");
        const reportUrl = base + "/v1/runs/" + runId + "/report";
        const reportViewUrl = base + "/v1/runs/" + runId + "/report/view";
        const report = await call("GET", reportUrl);
        log("conformance=" + (report.conformance || {}).status);
        log("selected_candidate_id=" + ((report.intervention || {}).selected_candidate_id || ""));
        log("knocked_out_of_saddle=" + ((report.delta_report || {}).knocked_out_of_saddle || ""));

        jsonReportEl.href = reportUrl;
        jsonReportEl.textContent = reportUrl;
        htmlReportEl.href = reportViewUrl;
        htmlReportEl.textContent = reportViewUrl;

        statusEl.textContent = "Completed";
      } catch (error) {
        errorEl.textContent = String(error);
        statusEl.textContent = "Failed";
      } finally {
        runBtn.disabled = false;
      }
    }

    runBtn.addEventListener("click", runDemo);
  </script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def home() -> HTMLResponse:
    return HTMLResponse(
        """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>SACP Ecosystem Hub</title>
  <style>
    body {
      font-family: "IBM Plex Sans", "Avenir Next", sans-serif;
      margin: 0;
      padding: 28px;
      background: #eef4f8;
      color: #12263a;
    }
    .card {
      max-width: 760px;
      margin: 0 auto;
      background: #fff;
      border: 1px solid #d5dee7;
      border-radius: 14px;
      padding: 22px;
    }
    a { color: #005fa3; text-decoration: none; }
    a:hover { text-decoration: underline; }
    ul { margin: 10px 0 0; }
    li { margin: 8px 0; }
    code {
      font-family: "IBM Plex Mono", Menlo, monospace;
      font-size: 12px;
      background: #f4f7fa;
      padding: 2px 6px;
      border-radius: 5px;
    }
  </style>
</head>
<body>
  <main class="card">
    <h1>SACP Ecosystem Hub API</h1>
    <p>API is healthy. Use one of the links below:</p>
    <ul>
      <li><a href="/demo">Run the browser demo flow</a></li>
      <li><a href="/docs">Open OpenAPI docs</a></li>
      <li><a href="/health"><code>/health</code></a></li>
    </ul>
  </main>
</body>
</html>
        """
    )


@app.get("/demo", response_class=HTMLResponse)
def demo_page() -> HTMLResponse:
    return HTMLResponse(_render_demo_html())


@app.post("/v1/intents/compile", response_model=IntentCompileResponse)
def compile_intent(req: IntentCompileRequest) -> IntentCompileResponse:
    return _service.compile_intent(prompt=req.prompt, context=req.context)


@app.post("/v1/sessions", response_model=SessionCreateResponse)
def create_session(req: SessionCreateRequest) -> SessionCreateResponse:
    return _service.create_session(prompt=req.prompt, context=req.context)


@app.post("/v1/sessions/{session_id}/ingest", response_model=IngestResponse)
def ingest(session_id: str, req: IngestRequest) -> IngestResponse:
    try:
        return _service.ingest(session_id, req)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/v1/sessions/{session_id}/advance", response_model=AdvanceResponse)
def advance(session_id: str) -> AdvanceResponse:
    try:
        return _service.advance(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/v1/sessions/{session_id}/followup", response_model=AdvanceResponse)
def followup(session_id: str, req: FollowupRequest) -> AdvanceResponse:
    try:
        return _service.followup(session_id, req)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/v1/sessions/{session_id}", response_model=SessionView)
def get_session(session_id: str) -> SessionView:
    try:
        return _service.view_session(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/v1/sessions/{session_id}/artifacts", response_model=ArtifactListResponse)
def get_artifacts(session_id: str) -> ArtifactListResponse:
    try:
        return _service.list_artifacts(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/v1/sessions/{session_id}/report")
def get_report(session_id: str):
    try:
        return _service.report(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/v1/sessions/{session_id}/report/view", response_class=HTMLResponse)
def get_report_view(session_id: str) -> HTMLResponse:
    try:
        report = _service.report(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return HTMLResponse(_render_report_html(report, heading=f"Session Report: {session_id}"))


@app.get("/v1/runs/{run_id}/report")
def get_report_by_run(run_id: str):
    try:
        return _service.report_by_run(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/v1/runs/{run_id}/report/view", response_class=HTMLResponse)
def get_report_by_run_view(run_id: str) -> HTMLResponse:
    try:
        report = _service.report_by_run(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return HTMLResponse(_render_report_html(report, heading=f"Run Report: {run_id}"))


@app.get("/health")
def health():
    return {"ok": True, "service": "sacp_ecosystem_hub"}


def run() -> None:
    import uvicorn

    host = os.getenv("HUB_BIND", "127.0.0.1")
    port = int(os.getenv("HUB_PORT", "8060"))
    uvicorn.run("sacp_hub.api:app", host=host, port=port, reload=bool(int(os.getenv("HUB_RELOAD", "1"))))


if __name__ == "__main__":
    run()
