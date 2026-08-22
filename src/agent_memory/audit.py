from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any

from agent_memory.core import MemoryCore
from agent_memory.store import MemoryStore

PROJECTION_TABLES = (
    "projected_events",
    "repositories",
    "memories",
    "revisions",
    "memory_refs",
    "dependency_edges",
    "execution_nodes",
    "compiler_jobs",
    "compiler_inputs",
    "processing_cursors",
    "reconciliation_checkpoints",
    "deliveries",
    "feedback",
)


def projection_digest(store: MemoryStore) -> str:
    payload: dict[str, list[list[Any]]] = {}
    tables = list(PROJECTION_TABLES)
    if store.fts_enabled:
        tables.append("memory_fts")
    for table in tables:
        columns = [
            item[1]
            for item in store.connection.execute(f"PRAGMA table_info({table})")
        ]
        rows = [
            [row[column] for column in columns]
            for row in store.connection.execute(f"SELECT * FROM {table}")
        ]
        payload[table] = sorted(
            rows,
            key=lambda row: json.dumps(row, ensure_ascii=False, default=str),
        )
    canonical = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def rebuilt_projection_digest(core: MemoryCore, events: list[Any]) -> str:
    with tempfile.TemporaryDirectory(prefix="agent-memory-audit-") as directory:
        store = MemoryStore(Path(directory) / "projection.sqlite3")
        try:
            for event in events:
                store.project(event)
            return projection_digest(store)
        finally:
            store.close()

def build_audit(core: MemoryCore, session_id: str) -> dict[str, Any]:
    all_events = list(core.event_log.iter_events())
    events = [
        event
        for event in all_events
        if str(event.payload.get("session_id", "")) == session_id
    ]
    jobs = core.store.compiler_jobs_for_session(session_id)
    deliveries = core.store.deliveries_for_session(session_id)
    memories = core.store.list_current(
        core.repository_id, core.branch, base_branch=core.base_branch
    )
    histories = {
        memory["memory_id"]: core.store.history(memory["memory_id"])
        for memory in memories
    }
    dependencies = core.store.all_dependency_edges()

    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, str]] = []

    def add_node(node_id: str, node_type: str, **attributes: Any) -> None:
        nodes[node_id] = {"id": node_id, "type": node_type, **attributes}

    for event in events:
        add_node(
            f"event:{event.event_id}",
            "event",
            event_type=event.event_type,
            occurred_at=event.occurred_at,
        )
    for job in jobs:
        job_node = f"job:{job['job_id']}"
        add_node(job_node, "compiler_job", status=job["status"], head=job["head"])
        for evidence in job["input"]["evidence_bundle"]["evidence"]:
            event_node = f"event:{evidence['evidence_id']}"
            if event_node in nodes:
                edges.append(
                    {"source": event_node, "target": job_node, "type": "compiled_from"}
                )
        head_node = f"git:{job['head']}"
        add_node(head_node, "git_head", head=job["head"])
        edges.append({"source": head_node, "target": job_node, "type": "observed_at"})

    revision_keys: set[tuple[str, int]] = set()
    for memory_id, history in histories.items():
        memory_node = f"memory:{memory_id}"
        add_node(memory_node, "memory", memory_id=memory_id)
        previous: str | None = None
        for revision in history:
            key = (memory_id, revision["revision"])
            revision_keys.add(key)
            revision_node = f"revision:{memory_id}@{revision['revision']}"
            add_node(
                revision_node,
                "revision",
                status=revision["status"],
                kind=revision["kind"],
                claim=revision["claim"],
            )
            edges.append(
                {"source": memory_node, "target": revision_node, "type": "has_revision"}
            )
            if previous:
                edges.append(
                    {
                        "source": previous,
                        "target": revision_node,
                        "type": "next_revision",
                    }
                )
            previous = revision_node
            job_id = revision["metadata"].get("compiler_job_id")
            if job_id and f"job:{job_id}" in nodes:
                edges.append(
                    {
                        "source": f"job:{job_id}",
                        "target": revision_node,
                        "type": "materialized_as",
                    }
                )
            for anchor in revision["anchors"]:
                anchor_id = f"anchor:{anchor['anchor_type']}:{anchor['target']}"
                add_node(
                    anchor_id,
                    "git_anchor",
                    anchor_type=anchor["anchor_type"],
                    target=anchor["target"],
                    content_hash=anchor.get("content_hash", ""),
                )
                edges.append(
                    {
                        "source": revision_node,
                        "target": anchor_id,
                        "type": "anchored_at",
                    }
                )
        ref_node = f"ref:{core.branch}:{memory_id}"
        add_node(
            ref_node,
            "memory_ref",
            status=history[-1]["status"],
            revision=history[-1]["revision"],
        )
        edges.append(
            {
                "source": f"revision:{memory_id}@{history[-1]['revision']}",
                "target": ref_node,
                "type": "current_ref",
            }
        )

    for dependency in dependencies:
        source = f"memory:{dependency['source_memory_id']}"
        if dependency["target_type"] == "memory":
            target = f"memory:{dependency['target_id']}"
            relation = next(
                (
                    item.get("relation")
                    for item in dependency["evidence"]
                    if item.get("relation")
                ),
                "depends_on",
            )
            edges.append({"source": source, "target": target, "type": relation})

    dangling_deliveries = 0
    for delivery in deliveries:
        delivery_node = f"delivery:{delivery['delivery_id']}"
        add_node(
            delivery_node,
            "delivery",
            delivery_type=delivery["delivery_type"],
            delivered_at=delivery["delivered_at"],
        )
        for memory_id, revision in delivery["revisions"]:
            if (memory_id, revision) not in revision_keys:
                dangling_deliveries += 1
                continue
            edges.append(
                {
                    "source": f"revision:{memory_id}@{revision}",
                    "target": delivery_node,
                    "type": "delivered_in",
                }
            )

    current_projection_digest = projection_digest(core.store)
    replayed_projection_digest = rebuilt_projection_digest(core, all_events)
    projected = core.store.connection.execute(
        "SELECT COUNT(*) FROM projected_events"
    ).fetchone()[0]
    dangling_refs = core.store.connection.execute(
        """
        SELECT COUNT(*) FROM memory_refs ref
        LEFT JOIN revisions r ON r.memory_id=ref.memory_id
            AND r.revision=ref.current_revision
        WHERE r.memory_id IS NULL
        """
    ).fetchone()[0]
    checks = {
        "event_log_exists": core.event_log.log_path.exists(),
        "projection_matches_event_log": projected == len(all_events),
        "rebuild_projection_matches": (
            current_projection_digest == replayed_projection_digest
        ),
        "no_dangling_refs": dangling_refs == 0,
        "no_dangling_deliveries": dangling_deliveries == 0,
        "session_has_capture": bool(events),
        "session_has_compiler_job": bool(jobs),
        "session_has_delivery": bool(deliveries),
    }
    return {
        "repository_id": core.repository_id,
        "branch": core.branch,
        "session_id": session_id,
        "storage": {
            "event_log": str(core.event_log.log_path),
            "projection": str(core.store.database_path),
            "repository_dir": str(core.repository_dir),
            "projection_digest": current_projection_digest,
            "replayed_projection_digest": replayed_projection_digest,
        },
        "summary": {
            "events": len(events),
            "compiler_jobs": len(jobs),
            "memories": len(memories),
            "deliveries": len(deliveries),
            "nodes": len(nodes),
            "edges": len(edges),
        },
        "checks": {
            key: {"status": "PASS" if value else "FAIL"}
            for key, value in checks.items()
        },
        "ok": all(checks.values()),
        "nodes": list(nodes.values()),
        "edges": edges,
    }


def render_markdown(audit: dict[str, Any]) -> str:
    lines = [
        "# Agent Memory Trace",
        "",
        f"- Repository: {audit['repository_id']}",
        f"- Branch: {audit['branch']}",
        f"- Session: {audit['session_id']}",
        f"- Overall: {'PASS' if audit['ok'] else 'FAIL'}",
        "",
        "## Storage",
        "",
    ]
    lines.extend(f"- {key}: {value}" for key, value in audit["storage"].items())
    lines.extend(["", "## Checks", ""])
    lines.extend(
        f"- {name}: {result['status']}"
        for name, result in audit["checks"].items()
    )
    lines.extend(["", "## Summary", ""])
    lines.append(json.dumps(audit["summary"], indent=2, ensure_ascii=False))
    return "\n".join(lines) + "\n"


def render_dot(audit: dict[str, Any]) -> str:
    lines = ["digraph memory_trace {", "  rankdir=LR;"]
    for node in audit["nodes"]:
        label = _dot(f"{node['type']}\n{node['id']}")
        lines.append(f'  "{_dot(node["id"])}" [label="{label}"];')
    for edge in audit["edges"]:
        lines.append(
            f'  "{_dot(edge["source"])}" -> "{_dot(edge["target"])}" '
            f'[label="{_dot(edge["type"])}"];'
        )
    lines.append("}")
    return "\n".join(lines) + "\n"


def write_output(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)
    return path


def _dot(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
