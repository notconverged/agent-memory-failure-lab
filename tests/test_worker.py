from __future__ import annotations

from pathlib import Path

from agent_memory.core import MemoryCore
from agent_memory.models import (
    CaptureCoverage,
    CompilerJob,
    EvidenceAuthority,
    EvidenceBundle,
    EvidenceRef,
    MemoryCandidate,
    MemoryKind,
    SessionStateSnapshot,
)
from agent_memory.worker import OneShotWorker


class FixtureCompiler:
    def compile(self, job: CompilerJob) -> list[MemoryCandidate]:
        return [
            MemoryCandidate(
                MemoryKind.CONSTRAINT,
                "Use Decimal",
                "Explicit user requirement",
                job.evidence_bundle.evidence,
                candidate_id="candidate-1",
            )
        ]


def make_job(head: str = "abc123") -> CompilerJob:
    evidence = EvidenceRef(
        "evidence-1",
        EvidenceAuthority.EXPLICIT_USER,
        "user_prompt",
        "session-1:prompt-1",
    )
    bundle = EvidenceBundle(
        "bundle-1",
        "cursor-1",
        "repo-1",
        "main",
        head,
        CaptureCoverage(True, ("prompt",), ("prompt",), ()),
        (evidence,),
    )
    return CompilerJob(
        "job-1",
        "repo-1",
        "main",
        "cursor-1",
        head,
        bundle,
        SessionStateSnapshot("session-1", "Task"),
    )


def test_worker_imports_validated_candidate(tmp_path: Path):
    core = MemoryCore(tmp_path, "repo-1", "main")
    core.queue_compiler_job(make_job())
    result = OneShotWorker(core, FixtureCompiler(), lambda: "abc123").run()
    assert result == {"lease_acquired": True, "processed": 1, "failed": 0}
    memories = core.store.list_current("repo-1", "main")
    assert memories[0]["status"] == "active"
    assert memories[0]["kind"] == "Constraint"


def test_worker_rejects_stale_head(tmp_path: Path):
    core = MemoryCore(tmp_path, "repo-1", "main")
    core.queue_compiler_job(make_job())
    result = OneShotWorker(core, FixtureCompiler(), lambda: "new-head").run()
    assert result["failed"] == 1
    assert core.store.list_current("repo-1", "main") == []
