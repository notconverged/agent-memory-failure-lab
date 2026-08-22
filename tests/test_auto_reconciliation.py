from __future__ import annotations

import subprocess
from pathlib import Path

from agent_memory.core import MemoryCore
from agent_memory.models import (
    Anchor,
    EvidenceAuthority,
    EvidenceRef,
    MemoryKind,
    MemoryStatus,
)
from agent_memory.reconciler import Reconciler


def git(repository: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def test_repository_reconciliation_marks_an_uncommitted_anchor_dirty(tmp_path: Path):
    repository = tmp_path / "repository"
    repository.mkdir()
    git(repository, "init")
    git(repository, "config", "user.name", "Memory Test")
    git(repository, "config", "user.email", "memory@example.invalid")
    target = repository / "src" / "policy.py"
    target.parent.mkdir()
    target.write_text("ROUNDING = 'HALF_UP'\n", encoding="utf-8")
    git(repository, "add", "-A")
    git(repository, "commit", "-m", "baseline")
    head = git(repository, "rev-parse", "HEAD")

    core = MemoryCore(tmp_path / "state", "repo-1", "main")
    evidence = EvidenceRef(
        "evidence-1",
        EvidenceAuthority.EXPLICIT_USER,
        "UserPromptSubmit",
        "event-1",
        "Use ROUND_HALF_UP",
    )
    memory = core.create_memory(
        MemoryKind.DECISION,
        "Use ROUND_HALF_UP",
        "Explicit policy",
        MemoryStatus.ACTIVE,
        EvidenceAuthority.EXPLICIT_USER,
        (evidence,),
        (Anchor("file", "src/policy.py"),),
    )
    reconciler = Reconciler(core)
    assert reconciler.reconcile_repository(repository, head) == []

    target.write_text("ROUNDING = 'HALF_EVEN'\n", encoding="utf-8")
    results = reconciler.reconcile_repository(repository, head)

    assert [item.action for item in results] == ["mark_dirty"]
    current = core.store.get_current("repo-1", "main", memory.memory_id)
    assert current["status"] == "needs_revalidation"
    checkpoint = core.store.get_reconciliation_checkpoint("repo-1", "main")
    assert checkpoint["changed_targets"] == ["src/policy.py"]
