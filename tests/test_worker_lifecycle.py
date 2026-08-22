from __future__ import annotations

from pathlib import Path

from agent_memory.core import MemoryCore
from agent_memory.models import (
    CandidateOperation,
    CaptureCoverage,
    CompilerJob,
    EvidenceAuthority,
    EvidenceBundle,
    EvidenceRef,
    MemoryCandidate,
    MemoryKind,
    MemoryStatus,
    SessionStateSnapshot,
)
from agent_memory.worker import OneShotWorker


class ReviseCompiler:
    def __init__(self, memory_id: str) -> None:
        self.memory_id = memory_id

    def compile(self, job: CompilerJob) -> list[MemoryCandidate]:
        return [
            MemoryCandidate(
                MemoryKind.DECISION,
                "Use ROUND_HALF_EVEN",
                "Revision of the same policy memory",
                job.evidence_bundle.evidence,
                candidate_id="revise-1",
                operation=CandidateOperation.REVISE,
                target_memory_id=self.memory_id,
            )
        ]


class PivotCompiler:
    def __init__(self, old_memory_id: str) -> None:
        self.old_memory_id = old_memory_id

    def compile(self, job: CompilerJob) -> list[MemoryCandidate]:
        return [
            MemoryCandidate(
                MemoryKind.DECISION,
                "Use ROUND_HALF_EVEN",
                "Explicit policy pivot",
                job.evidence_bundle.evidence,
                candidate_id="pivot-1",
                supersedes_memory_ids=(self.old_memory_id,),
            )
        ]


def test_worker_supersedes_old_memory_and_advances_cursor(tmp_path: Path):
    core = MemoryCore(tmp_path, "repo-1", "main")
    evidence = EvidenceRef(
        "evidence-1",
        EvidenceAuthority.EXPLICIT_USER,
        "UserPromptSubmit",
        "event-1",
        "Use ROUND_HALF_EVEN instead of ROUND_HALF_UP",
    )
    old = core.create_memory(
        MemoryKind.DECISION,
        "Use ROUND_HALF_UP",
        "Old policy",
        MemoryStatus.ACTIVE,
        EvidenceAuthority.EXPLICIT_USER,
        (evidence,),
    )
    bundle = EvidenceBundle(
        "bundle-1",
        "event-1",
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
        "event-1",
        "head-1",
        bundle,
        SessionStateSnapshot("session-1", "Policy pivot"),
        input_start_event_id="event-1",
        input_end_event_id="event-1",
        input_hash="hash-1",
    )
    assert core.queue_compiler_job(job) is True
    result = OneShotWorker(core, PivotCompiler(old.memory_id), lambda: "head-1").run()
    assert result["processed"] == 1

    current_old = core.store.get_current("repo-1", "main", old.memory_id)
    assert current_old["status"] == "superseded"
    active = core.store.list_current("repo-1", "main", ["active"])
    assert [item["claim"] for item in active] == ["Use ROUND_HALF_EVEN"]
    edges = core.store.all_dependency_edges()
    assert edges[0]["target_id"] == old.memory_id
    assert edges[0]["evidence"][0]["relation"] == "supersedes"
    assert core.store.get_processing_cursor("repo-1", "main", "session-1") == "event-1"


def test_worker_revises_the_target_memory_in_place(tmp_path: Path):
    core = MemoryCore(tmp_path, "repo-1", "main")
    evidence = EvidenceRef(
        "evidence-1",
        EvidenceAuthority.EXPLICIT_USER,
        "UserPromptSubmit",
        "event-1",
        "Use ROUND_HALF_EVEN instead",
    )
    original = core.create_memory(
        MemoryKind.DECISION,
        "Use ROUND_HALF_UP",
        "Old policy",
        MemoryStatus.ACTIVE,
        EvidenceAuthority.EXPLICIT_USER,
        (evidence,),
    )
    bundle = EvidenceBundle(
        "bundle-1",
        "event-1",
        "repo-1",
        "main",
        "head-1",
        CaptureCoverage(True, ("UserPromptSubmit",), ("UserPromptSubmit",), ()),
        (evidence,),
    )
    job = CompilerJob(
        "job-revise",
        "repo-1",
        "main",
        "event-1",
        "head-1",
        bundle,
        SessionStateSnapshot("session-1", "Policy revision"),
        input_start_event_id="event-1",
        input_end_event_id="event-1",
        input_hash="hash-revise",
    )
    core.queue_compiler_job(job)

    result = OneShotWorker(
        core, ReviseCompiler(original.memory_id), lambda: "head-1"
    ).run()

    assert result["processed"] == 1
    current = core.store.get_current("repo-1", "main", original.memory_id)
    assert current["revision"] == 2
    assert current["claim"] == "Use ROUND_HALF_EVEN"
    assert current["status"] == "active"
    assert len(core.store.history(original.memory_id)) == 2
