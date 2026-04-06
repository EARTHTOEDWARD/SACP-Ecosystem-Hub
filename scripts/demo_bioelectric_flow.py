#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
import sys
import webbrowser
from typing import Any, Dict, List

import requests


def _build_points(n: int, *, offset: float, slope: float) -> List[Dict[str, Any]]:
    points: List[Dict[str, Any]] = []
    for i in range(n):
        t = float(i)
        values = [
            offset + slope * i + 0.08 * math.sin(i / 8.0),
            offset + 0.5 * slope * i + 0.05 * math.cos(i / 9.0),
            offset + 0.75 * slope * i + 0.06 * math.sin(i / 11.0 + 0.4),
        ]
        points.append({"t": t, "values": values})
    return points


def _call(
    session: requests.Session,
    *,
    method: str,
    url: str,
    payload: Dict[str, Any] | None,
    timeout: float,
) -> Dict[str, Any]:
    if method == "GET":
        response = session.get(url, timeout=timeout)
    else:
        response = session.post(url, json=payload, timeout=timeout)
    response.raise_for_status()
    return response.json()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a full live demo against SACP Ecosystem Hub API.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8060", help="Hub API base URL.")
    parser.add_argument("--prompt", default="Simulate bioelectric intervention loop and compare follow-up attractor dynamics.")
    parser.add_argument("--baseline-points", type=int, default=120)
    parser.add_argument("--followup-points", type=int, default=120)
    parser.add_argument("--baseline-offset", type=float, default=0.0)
    parser.add_argument("--followup-offset", type=float, default=-0.12)
    parser.add_argument("--baseline-slope", type=float, default=0.02)
    parser.add_argument("--followup-slope", type=float, default=0.014)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--open-browser", action="store_true", help="Open HTML report view in browser.")
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    baseline_points = _build_points(args.baseline_points, offset=args.baseline_offset, slope=args.baseline_slope)
    followup_points = _build_points(args.followup_points, offset=args.followup_offset, slope=args.followup_slope)

    print(f"Using Hub API: {base}")
    print("Step 1/7: compile intent")

    http = requests.Session()
    try:
        compiled = _call(
            http,
            method="POST",
            url=f"{base}/v1/intents/compile",
            payload={"prompt": args.prompt, "context": {"demo": True}},
            timeout=args.timeout,
        )
    except requests.RequestException as exc:
        print(f"Failed to reach hub API at {base}: {exc}", file=sys.stderr)
        print("Start the API first: uvicorn sacp_hub.api:app --reload --host 127.0.0.1 --port 8060", file=sys.stderr)
        return 2

    print(f"  intent.domain={compiled['intent']['domain']} mode={compiled['intent']['mode']}")
    print("Step 2/7: create session")

    created = _call(
        http,
        method="POST",
        url=f"{base}/v1/sessions",
        payload={"prompt": args.prompt, "context": {"demo": True}},
        timeout=args.timeout,
    )
    session_id = created["session_id"]
    run_id = created["run_id"]
    print(f"  session_id={session_id}")
    print(f"  run_id={run_id}")

    print("Step 3/7: ingest baseline window")
    ingested = _call(
        http,
        method="POST",
        url=f"{base}/v1/sessions/{session_id}/ingest",
        payload={"stream_kind": "baseline", "points": baseline_points, "metadata": {"source": "demo_baseline"}},
        timeout=args.timeout,
    )
    print(f"  baseline artifact={ingested['artifact_id']}")

    print("Step 4/7: advance baseline -> candidate -> execution")
    advanced = _call(
        http,
        method="POST",
        url=f"{base}/v1/sessions/{session_id}/advance",
        payload={},
        timeout=args.timeout,
    )
    print(f"  state after advance={advanced['state']}")
    if advanced["state"] not in {"awaiting_followup", "completed"}:
        print("Advance step did not reach follow-up waiting/completed state", file=sys.stderr)
        return 3

    print("Step 5/7: ingest follow-up and finalize")
    follow = _call(
        http,
        method="POST",
        url=f"{base}/v1/sessions/{session_id}/followup",
        payload={"points": followup_points, "metadata": {"source": "demo_followup_72h"}},
        timeout=args.timeout,
    )
    print(f"  state after followup={follow['state']}")
    if follow["state"] != "completed":
        print("Follow-up step did not complete the session", file=sys.stderr)
        return 4

    print("Step 6/7: fetch artifact lineage")
    artifacts = _call(
        http,
        method="GET",
        url=f"{base}/v1/sessions/{session_id}/artifacts",
        payload=None,
        timeout=args.timeout,
    )
    print(f"  total artifacts={len(artifacts['artifact_ids'])}")

    print("Step 7/7: fetch final report")
    report = _call(
        http,
        method="GET",
        url=f"{base}/v1/runs/{run_id}/report",
        payload=None,
        timeout=args.timeout,
    )
    conformance = report.get("conformance", {})
    intervention = report.get("intervention", {})
    delta_report = report.get("delta_report", {})
    print("Demo completed successfully:")
    print(f"  conformance.status={conformance.get('status')}")
    print(f"  selected_candidate_id={intervention.get('selected_candidate_id')}")
    print(f"  knocked_out_of_saddle={delta_report.get('knocked_out_of_saddle')}")
    print(f"  report summary={report.get('summary')}")
    report_url = f"{base}/v1/runs/{run_id}/report"
    report_view_url = f"{base}/v1/runs/{run_id}/report/view"
    print(f"  stable_report_url={report_url}")
    print(f"  stable_report_view_url={report_view_url}")

    if args.open_browser:
        webbrowser.open(report_view_url)
        print("  browser_opened=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
