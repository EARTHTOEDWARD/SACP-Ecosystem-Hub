from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

from sacp_hub.config import default_workspace_source


def _repo_index(repos: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {str(repo.get("key", "")): repo for repo in repos}


def enrich_workspace_registry(raw: Dict[str, Any]) -> Dict[str, Any]:
    out = json.loads(json.dumps(raw))
    repos: List[Dict[str, Any]] = list(out.get("repos", []))
    idx = _repo_index(repos)

    def ensure_repo(repo: Dict[str, Any]) -> None:
        key = str(repo.get("key", ""))
        if key in idx:
            idx[key].update(repo)
        else:
            repos.append(repo)
            idx[key] = repo

    for repo in repos:
        key = str(repo.get("key", ""))
        if "adapter_type" not in repo:
            repo["adapter_type"] = "api" if key == "sacp_suite" else "cli"
        repo.setdefault("entrypoints", {})
        repo.setdefault("artifact_contracts", {"produces": [], "requires": []})

    if "sacp_suite" in idx:
        idx["sacp_suite"]["adapter_type"] = "api"
        idx["sacp_suite"]["entrypoints"].update(
            {
                "chemistry_simulate": "/api/v1/chemistry/simulate",
                "task_parse": "/api/parse-task",
            }
        )
        idx["sacp_suite"]["artifact_contracts"]["produces"] = sorted(
            set(idx["sacp_suite"]["artifact_contracts"].get("produces", []) + [
                "sacp.run.v0.1",
                "sacp.artifact.v0.1",
                "sacp.chemistry.adr.habitat_atlas.v1",
                "sacp.chemistry.adr.ratchet_witness.v1",
            ])
        )

    if "osm" in idx:
        idx["osm"]["adapter_type"] = "cli"
        idx["osm"]["entrypoints"].update(
            {
                "validate_runstore": "scripts/validate_runstore.py",
            }
        )
        idx["osm"]["artifact_contracts"]["requires"] = sorted(
            set(idx["osm"]["artifact_contracts"].get("requires", []) + ["sacp.run.v0.1", "sacp.artifact.v0.1"])
        )

    ensure_repo(
        {
            "key": "auic",
            "name": "Autodidactic Universe Intelligence Creator (AUIC)",
            "role": "autodidactic planning/episode runner and artifact-first benchmark loops",
            "env": "AUIC_ROOT",
            "default_path": "/Users/edward/Autodidactic Universe Intelligence Creator",
            "git_remote": None,
            "adapter_type": "python",
            "entrypoints": {
                "cli": "python -m auic.cli",
                "runs_show": "python -m auic.cli runs show --run-id <run_id>",
            },
            "artifact_contracts": {
                "produces": ["sacp.run.v0.1", "sacp.artifact.v0.1"],
                "requires": ["sacp.run.v0.1"],
            },
        }
    )

    ensure_repo(
        {
            "key": "maxwell_dynamics",
            "name": "Maxwell Dynamics",
            "role": "maxwell-native domain pack and certificate-producing dynamics",
            "env": "MAXWELL_DYNAMICS_ROOT",
            "default_path": "/Users/edward/Maxwell Dynamics",
            "git_remote": None,
            "adapter_type": "cli",
            "entrypoints": {
                "example6": "python scripts/run_example6_transport_pump_cycle.py",
                "validate_osm_contract": "python scripts/validate_osm_contract.py",
            },
            "artifact_contracts": {
                "produces": ["run_manifest.json", "atlas.json", "boundaries.json", "port_report.json"],
                "requires": ["sacp.run.v0.1"],
            },
        }
    )

    out["repos"] = repos
    return out


def sync_workspace_registry(source: Path, target: Path, *, update_source: bool = False) -> Dict[str, Any]:
    raw = json.loads(source.read_text(encoding="utf-8"))
    enriched = enrich_workspace_registry(raw)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(enriched, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if update_source:
        source.write_text(json.dumps(enriched, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return enriched


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync and enrich SACP ecosystem workspace registry")
    parser.add_argument("--source", default=str(default_workspace_source()))
    parser.add_argument("--target", default="config/workspace.registry.json")
    parser.add_argument("--update-source", action="store_true")
    args = parser.parse_args()

    enriched = sync_workspace_registry(
        source=Path(args.source),
        target=Path(args.target),
        update_source=bool(args.update_source),
    )
    print(json.dumps({"repos": len(enriched.get("repos", [])), "target": args.target}, indent=2))


if __name__ == "__main__":
    main()
