from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from benchmarks.execution_state.adapters.base import (
    apply_session_files,
    capability,
    trace_text,
    write_json,
)
from scripts.competitor_adapters.base import to_jsonable


def capabilities() -> dict[str, Any]:
    evidence = ["runtime:graphiti-kuzu-episode-graph"]
    limitation = "Graph relations are semantic/event relations, not assumed execution-state edges."  # noqa: E501
    return {
        "active_path_integrity": capability(
            "not_observable",
            evidence_paths=evidence,
            derivation="Episodes and graph edges are observable, but no current execution cursor is exposed.",  # noqa: E501
            limitations=limitation,
        ),
        "branch_isolation": capability(
            "unsupported",
            evidence_paths=evidence,
            derivation="The adapter observes no active/inactive sibling execution branch mechanism.",  # noqa: E501
            limitations=limitation,
        ),
        "compression_fidelity": capability(
            "not_observable",
            evidence_paths=evidence,
            derivation="Graphiti derives entities and relations but exposes no ordered raw coverage for a boundary summary.",  # noqa: E501
            limitations=limitation,
        ),
        "maintain_precision": capability(
            "unsupported",
            evidence_paths=evidence,
            derivation="Episode ingestion exposes no pre-trust boundary validation result.",  # noqa: E501
            limitations=limitation,
        ),
    }


async def execute_request_async(request: dict[str, Any]) -> dict[str, Any]:
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("Graphiti provider credentials are not available")
    from graphiti_core import Graphiti
    from graphiti_core.driver.kuzu_driver import KuzuDriver
    from graphiti_core.nodes import EpisodeType

    data_dir = Path(request["data_dir"]).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    database = data_dir / "graphiti.kuzu"
    scenario = request["scenario"]
    run_id = request["run_id"]
    graph = Graphiti(graph_driver=KuzuDriver(db=str(database)))
    checkpoints_by_session: dict[str, list[dict[str, Any]]] = {}
    for checkpoint in scenario["product_checkpoints"]:
        checkpoints_by_session.setdefault(checkpoint["after_session_id"], []).append(
            checkpoint
        )
    observations: dict[str, dict[str, Any]] = {}
    episodes: list[str] = []
    workspace = Path(request["workspace"])
    try:
        await graph.build_indices_and_constraints()
        for session in scenario["sessions"]:
            apply_session_files(workspace, session)
            body = "\n".join(
                [
                    f"TASK: {session['instruction']}",
                    trace_text(
                        scenario, session["timeline_start"], session["timeline_end"]
                    ),
                ]
            )
            episode_name = f"{run_id}-{session['session_id']}"
            await graph.add_episode(
                name=episode_name,
                episode_body=body,
                source=EpisodeType.text,
                source_description="Execution-state controlled coding trace",
                reference_time=datetime.now(timezone.utc),
                group_id=run_id,
            )
            episodes.append(episode_name)
            for checkpoint in checkpoints_by_session.get(session["session_id"], []):
                try:
                    result = await graph.search(checkpoint["query"], group_id=run_id)
                    serial = to_jsonable(result)
                    text = json.dumps(serial, ensure_ascii=False)
                    observations[str(checkpoint["step_index"])] = {
                        "query_status": "completed" if serial else "empty",
                        "retrieval_text": text if serial else "",
                        "query": checkpoint["query"],
                        "raw": serial,
                    }
                except Exception as error:
                    observations[str(checkpoint["step_index"])] = {
                        "query_status": "error",
                        "retrieval_text": "",
                        "query": checkpoint["query"],
                        "error": str(error),
                    }
    finally:
        await graph.close()
    return {
        "system": "graphiti",
        "scenario_id": scenario["scenario_id"],
        "group_id": run_id,
        "episodes": episodes,
        "storage_paths": [str(database.resolve())],
        "observations": observations,
        "capabilities": capabilities(),
    }


def execute_request(request: dict[str, Any]) -> dict[str, Any]:
    return asyncio.run(execute_request_async(request))


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 2:
        print("usage: graphiti_adapter.py REQUEST_JSON OUTPUT_JSON", file=sys.stderr)
        return 2
    request = json.loads(Path(args[0]).read_text(encoding="utf-8"))
    try:
        result = execute_request(request)
    except Exception as error:
        result = {"status": "error", "error": str(error)}
        write_json(Path(args[1]), result)
        return 2
    result["status"] = "completed"
    write_json(Path(args[1]), result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
