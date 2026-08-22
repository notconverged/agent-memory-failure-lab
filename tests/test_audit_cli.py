from __future__ import annotations

from pathlib import Path

from agent_memory.audit import build_audit, render_dot, render_markdown
from agent_memory.core import MemoryCore
from agent_memory.models import (
    CaptureCoverage,
    CompilerJob,
    EvidenceAuthority,
    EvidenceBundle,
    EvidenceRef,
    MemoryKind,
    MemoryStatus,
    SessionStateSnapshot,
)


def test_audit_traces_capture_job_revision_ref_anchor_and_delivery(tmp_path: Path):
    core = MemoryCore(tmp_path, "repo-1", "main")
    core.capture_event(
        "codex_UserPromptSubmit",
        {"session_id": "session-1", "prompt": "Use Decimal"},
    )
    core.ingest_spool()
    event = next(core.event_log.iter_events())
    evidence = EvidenceRef(
        event.event_id,
        EvidenceAuthority.EXPLICIT_USER,
        "UserPromptSubmit",
        event.event_id,
        "Use Decimal",
    )
    bundle = EvidenceBundle(
        "bundle-1",
        event.event_id,
        "repo-1",
        "main",
        "head-1",
        CaptureCoverage(True, ("UserPromptSubmit",), ("UserPromptSubmit",), ()),
        (evidence,),
    )
    job = CompilerJob(
        "job-1",
        "repo-1",
        "main",
        event.event_id,
        "head-1",
        bundle,
        SessionStateSnapshot("session-1", "Task"),
        input_start_event_id=event.event_id,
        input_end_event_id=event.event_id,
        input_hash="input-1",
    )
    core.queue_compiler_job(job)
    revision = core.create_memory(
        MemoryKind.CONSTRAINT,
        "Use Decimal",
        "Policy",
        MemoryStatus.ACTIVE,
        EvidenceAuthority.EXPLICIT_USER,
        (evidence,),
        metadata={"compiler_job_id": "job-1", "candidate_id": "candidate-1"},
    )
    core.finish_compiler_job("job-1", "completed", [revision.to_dict()])
    core.record_delivery(
        {
            "session_id": "session-1",
            "delivery_type": "context_capsule",
            "query": "money",
            "revisions": [(revision.memory_id, revision.revision)],
            "payload_hash": "hash",
            "token_estimate": 10,
        }
    )

    audit = build_audit(core, "session-1")
    assert audit["ok"] is True
    assert audit["summary"]["compiler_jobs"] == 1
    edge_types = {edge["type"] for edge in audit["edges"]}
    assert {"compiled_from", "materialized_as", "current_ref", "delivered_in"} <= (
        edge_types
    )
    assert "digraph memory_trace" in render_dot(audit)
    assert "Overall: PASS" in render_markdown(audit)

    core.store.connection.execute(
        "UPDATE revisions SET claim = 'corrupted projection'"
    )
    core.store.connection.commit()
    corrupted = build_audit(core, "session-1")
    assert corrupted["checks"]["rebuild_projection_matches"]["status"] == "FAIL"
    assert corrupted["ok"] is False
