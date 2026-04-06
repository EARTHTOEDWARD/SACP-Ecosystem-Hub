# SACP Ecosystem Hub

Simulation-first orchestration hub for routing researcher intents across the SACP ecosystem.

## What it provides

- Thin control-plane API (`/v1/*`) for session orchestration
- Adapter-based execution model (SACP API, OSM validator, Maxwell/AUIC normalizers)
- Typed RunStore artifact bus (`sacp.run.v0.1` + `sacp.artifact.v0.1`)
- Bioelectric intervention loop v1:
  - baseline ingest and analysis
  - intervention candidate generation and simulated execution
  - follow-up ingest and delta comparison
  - conformance validation via OSM validator

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn sacp_hub.api:app --reload --host 127.0.0.1 --port 8060
```

Open API docs at [http://127.0.0.1:8060/docs](http://127.0.0.1:8060/docs).
Open browser demo UI at [http://127.0.0.1:8060/demo](http://127.0.0.1:8060/demo).

## Workspace sync

```bash
sacp-hub-sync-workspace --source "/Users/edward/SACP SUITE/WORKSPACE.json" --target "./config/workspace.registry.json"
```

## Live demo flow

Run the API in one terminal:

```bash
uvicorn sacp_hub.api:app --reload --host 127.0.0.1 --port 8060
```

Run the end-to-end demo client in another terminal:

```bash
python scripts/demo_bioelectric_flow.py --base-url http://127.0.0.1:8060
```

Use the stable run-based report URL from script output:

```text
http://127.0.0.1:8060/v1/runs/<run_id>/report
```

Use the browser-friendly report view URL:

```text
http://127.0.0.1:8060/v1/runs/<run_id>/report/view
```

Optional: have the demo script open the HTML report automatically:

```bash
python scripts/demo_bioelectric_flow.py --base-url http://127.0.0.1:8060 --open-browser
```

## Tests

```bash
pytest
```
