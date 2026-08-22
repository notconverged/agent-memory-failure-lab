from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from benchmarks.execution_state.adapters.base import (
    apply_session_files,
    capability,
    trace_text,
    write_json,
)
from scripts.competitor_adapters.base import to_jsonable


def _replace_paths(config: dict[str, Any], data_dir: Path) -> dict[str, Any]:
    value = json.loads(json.dumps(config))
    vector = value.setdefault("vector_store", {})
    if vector.get("provider") != "qdrant":
        raise ValueError("mem0-vector requires vector_store.provider=qdrant")
    vector.setdefault("config", {})["path"] = str((data_dir / "qdrant").resolve())
    value["history_db_path"] = str((data_dir / "history.sqlite3").resolve())
    return value


def _contains_secret(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            name = str(key).casefold().replace("-", "_")
            if ("api_key" in name or "token" in name) and item:
                return True
            if _contains_secret(item):
                return True
    if isinstance(value, list):
        return any(_contains_secret(item) for item in value)
    return False


def capabilities() -> dict[str, Any]:
    evidence = ["runtime:mem0-vector-qdrant-only-config"]
    limitation = "Assessment is limited to the pinned Qdrant-only OSS configuration."
    return {
        "active_path_integrity": capability(
            "unsupported",
            evidence_paths=evidence,
            derivation="The configured store exposes retrieved memories, not an ordered execution cursor path.",  # noqa: E501
            limitations=limitation,
        ),
        "branch_isolation": capability(
            "unsupported",
            evidence_paths=evidence,
            derivation="The configured store has no active/inactive sibling execution branch abstraction.",  # noqa: E501
            limitations=limitation,
        ),
        "compression_fidelity": capability(
            "not_observable",
            evidence_paths=evidence,
            derivation="Mem0 may consolidate content, but this interface exposes no raw-to-summary coverage mapping.",  # noqa: E501
            limitations=limitation,
        ),
        "maintain_precision": capability(
            "unsupported",
            evidence_paths=evidence,
            derivation="The configured update path exposes no boundary validation result before trust.",  # noqa: E501
            limitations=limitation,
        ),
    }


def execute_request(request: dict[str, Any]) -> dict[str, Any]:
    config_path_value = os.environ.get("AMLAB_MEM0_CONFIG")
    if not config_path_value:
        raise RuntimeError("AMLAB_MEM0_CONFIG must point to a secret-free Mem0 config")
    config_path = Path(config_path_value).expanduser().resolve()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if _contains_secret(config):
        raise ValueError("Mem0 config must not contain inline API keys or tokens")
    data_dir = Path(request["data_dir"]).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    config = _replace_paths(config, data_dir)

    from mem0 import Memory

    memory = Memory.from_config(config)
    scenario = request["scenario"]
    run_id = request["run_id"]
    scope = {
        "user_id": f"amlab-user-{run_id}",
        "agent_id": f"amlab-agent-{run_id}",
        "run_id": run_id,
    }
    checkpoints_by_session: dict[str, list[dict[str, Any]]] = {}
    for checkpoint in scenario["product_checkpoints"]:
        checkpoints_by_session.setdefault(checkpoint["after_session_id"], []).append(
            checkpoint
        )
    writes: list[Any] = []
    observations: dict[str, dict[str, Any]] = {}
    workspace = Path(request["workspace"])
    for session in scenario["sessions"]:
        apply_session_files(workspace, session)
        content = "\n".join(
            [
                f"TASK: {session['instruction']}",
                trace_text(
                    scenario, session["timeline_start"], session["timeline_end"]
                ),
            ]
        )
        writes.append(
            to_jsonable(
                memory.add(
                    [{"role": "user", "content": content}],
                    **scope,
                    metadata={
                        "session_id": session["session_id"],
                        "phase_id": session["phase_id"],
                    },
                )
            )
        )
        for checkpoint in checkpoints_by_session.get(session["session_id"], []):
            try:
                result = memory.search(checkpoint["query"], filters=scope)
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
    stored = to_jsonable(memory.get_all(filters=scope))
    return {
        "system": "mem0-vector",
        "scenario_id": scenario["scenario_id"],
        "scope": scope,
        "config_path": str(config_path),
        "storage_paths": [
            str((data_dir / "qdrant").resolve()),
            str((data_dir / "history.sqlite3").resolve()),
        ],
        "writes": writes,
        "stored": stored,
        "observations": observations,
        "capabilities": capabilities(),
    }


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 2:
        print("usage: mem0_adapter.py REQUEST_JSON OUTPUT_JSON", file=sys.stderr)
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
