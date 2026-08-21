from __future__ import annotations

import json
from pathlib import Path

from agent_memory.core import MemoryCore
from agent_memory.models import (
    EventEnvelope,
    EvidenceAuthority,
    EvidenceRef,
    ExecutionNode,
    ExecutionStatus,
    MemoryKind,
    MemoryStatus,
)


def evidence(authority: EvidenceAuthority = EvidenceAuthority.EXPLICIT_USER):
    return (
        EvidenceRef(
            evidence_id="ev-1",
            authority=authority,
            source_type="user_prompt",
            source_ref="session-1:prompt-1",
            excerpt="Use Decimal. token=super-secret-value",
        ),
    )


def test_event_log_rebuilds_sqlite_projection(tmp_path: Path):
    core = MemoryCore(tmp_path, "repo-1", "main")
    revision = core.create_memory(
        MemoryKind.CONSTRAINT,
        "Money must use Decimal",
        "Avoid binary floating-point drift",
        MemoryStatus.ACTIVE,
        EvidenceAuthority.EXPLICIT_USER,
        evidence(),
    )
    assert core.store.get_current("repo-1", "main", revision.memory_id)["status"] == (
        "active"
    )

    event_count = sum(1 for _ in core.event_log.iter_events())
    core.rebuild()
    current = core.store.get_current("repo-1", "main", revision.memory_id)
    assert current is not None
    assert current["claim"] == "Money must use Decimal"
    assert event_count == 2


def test_spool_is_atomic_redacted_and_idempotent(tmp_path: Path):
    core = MemoryCore(tmp_path, "repo-1", "main")
    path = core.capture_event(
        "host_event",
        {"output": "API_KEY=secret-value-123", "source": "PostToolUse"},
    )
    assert path.suffix == ".json"
    assert not list(path.parent.glob("*.tmp-*"))
    assert "secret-value-123" not in path.read_text(encoding="utf-8")

    assert core.ingest_spool() == 1
    assert core.ingest_spool() == 0
    assert not path.exists()


def test_branch_overlay_wins_over_baseline(tmp_path: Path):
    baseline = MemoryCore(tmp_path, "repo-1", "main", "main")
    revision = baseline.create_memory(
        MemoryKind.PROJECT_FACT,
        "API version is v1",
        "Read from config",
        MemoryStatus.ACTIVE,
        EvidenceAuthority.DIRECT_REPO,
        evidence(EvidenceAuthority.DIRECT_REPO),
    )
    baseline.close()

    overlay = MemoryCore(tmp_path, "repo-1", "feature", "main")
    overlay.create_memory(
        MemoryKind.PROJECT_FACT,
        "API version is v2",
        "Feature branch config",
        MemoryStatus.ACTIVE,
        EvidenceAuthority.DIRECT_REPO,
        evidence(EvidenceAuthority.DIRECT_REPO),
        memory_id=revision.memory_id,
    )
    visible = overlay.store.list_current("repo-1", "feature", base_branch="main")
    assert len(visible) == 1
    assert visible[0]["claim"] == "API version is v2"


def test_feature_branch_can_read_baseline_ref(tmp_path: Path):
    baseline = MemoryCore(tmp_path, "repo-1", "main")
    revision = baseline.create_memory(
        MemoryKind.CONSTRAINT,
        "Use Decimal",
        "Baseline policy",
        MemoryStatus.ACTIVE,
        EvidenceAuthority.PROJECT_NORM,
        evidence(EvidenceAuthority.PROJECT_NORM),
    )
    baseline.close()
    overlay = MemoryCore(tmp_path, "repo-1", "feature", "main")
    current = overlay.store.get_current(
        "repo-1", "feature", revision.memory_id, base_branch="main"
    )
    assert current["claim"] == "Use Decimal"


def test_unknown_events_remain_replayable(tmp_path: Path):
    core = MemoryCore(tmp_path, "repo-1", "main")
    event = EventEnvelope(
        event_id="evt-unknown",
        event_type="future_event",
        repository_id="repo-1",
        branch="main",
        payload={"new": True},
    )
    core.event_log.append(event)
    assert core.catch_up() == 1
    assert json.loads(core.event_log.log_path.read_text().splitlines()[0])[
        "payload"
    ] == {"new": True}


def test_execution_state_is_separate_from_durable_memory(tmp_path: Path):
    core = MemoryCore(tmp_path, "repo-1", "main")
    core.upsert_execution_node(
        ExecutionNode(
            "node-1",
            "repo-1",
            "main",
            "Run integration tests",
            ExecutionStatus.ACTIVE,
        )
    )
    assert core.store.list_current("repo-1", "main") == []
    row = core.store.connection.execute(
        "SELECT status FROM execution_nodes WHERE node_id='node-1'"
    ).fetchone()
    assert row[0] == "active"


def test_terminal_status_requires_explicit_restore_revision(tmp_path: Path):
    core = MemoryCore(tmp_path, "repo-1", "main")
    revision = core.create_memory(
        MemoryKind.PROJECT_FACT,
        "Runtime is Python",
        "pyproject",
        MemoryStatus.ACTIVE,
        EvidenceAuthority.DIRECT_REPO,
        evidence(EvidenceAuthority.DIRECT_REPO),
    )
    core.transition(revision.memory_id, MemoryStatus.INVALIDATED, "no longer true")
    try:
        core.transition(revision.memory_id, MemoryStatus.ACTIVE, "unsafe shortcut")
    except ValueError as error:
        assert "invalid memory transition" in str(error)
    else:
        raise AssertionError("terminal state transition should fail")


def test_explicit_purge_rebuilds_log_without_memory(tmp_path: Path):
    core = MemoryCore(tmp_path, "repo-1", "main")
    revision = core.create_memory(
        MemoryKind.FAILURE,
        "A bounded attempt failed",
        "Observed test failure",
        MemoryStatus.ACTIVE,
        EvidenceAuthority.DIRECT_TEST,
        evidence(EvidenceAuthority.DIRECT_TEST),
    )
    assert core.purge(revision.memory_id) == 2
    assert core.store.history(revision.memory_id) == []
    assert revision.memory_id not in core.event_log.log_path.read_text(encoding="utf-8")
