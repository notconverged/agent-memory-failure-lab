from __future__ import annotations

import hashlib
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent_memory.core import MemoryCore
from agent_memory.models import (
    EvidenceAuthority,
    EvidenceRef,
    MemoryKind,
    MemoryStatus,
)


@dataclass(frozen=True)
class ReconciliationResult:
    memory_id: str
    previous_status: str
    new_status: str
    action: str
    reason: str


class Reconciler:
    def __init__(self, core: MemoryCore) -> None:
        self.core = core

    def reconcile_anchor_change(
        self,
        memory_id: str,
        target: str,
        *,
        committed: bool,
        new_claim: str | None = None,
        evidence_excerpt: str = "",
    ) -> ReconciliationResult:
        current = self.core.store.get_current(
            self.core.repository_id,
            self.core.branch,
            memory_id,
            self.core.base_branch,
        )
        if current is None:
            raise KeyError(f"Unknown memory: {memory_id}")
        previous = current["status"]
        kind = MemoryKind(current["kind"])

        if not committed:
            revision = self.core.transition(
                memory_id,
                MemoryStatus.NEEDS_REVALIDATION,
                f"Uncommitted change touched anchor {target}",
            )
            return ReconciliationResult(
                memory_id,
                previous,
                revision.status.value,
                "mark_dirty",
                "uncommitted_changes_cannot_authorize_truth",
            )

        if kind in {MemoryKind.DECISION, MemoryKind.CONSTRAINT}:
            revision = self.core.transition(
                memory_id,
                MemoryStatus.CONFLICTED,
                f"Implementation changed at {target}; normative claim not superseded",
            )
            return ReconciliationResult(
                memory_id,
                previous,
                revision.status.value,
                "implementation_conflict",
                "code_cannot_supersede_normative_memory",
            )

        if kind is MemoryKind.PROJECT_FACT and new_claim:
            evidence = EvidenceRef(
                evidence_id=f"ev-{uuid.uuid4().hex}",
                authority=EvidenceAuthority.DIRECT_REPO,
                source_type="git_snapshot",
                source_ref=target,
                excerpt=evidence_excerpt,
            )
            revision = self.core.create_memory(
                MemoryKind.PROJECT_FACT,
                new_claim,
                f"Direct repository evidence changed at {target}",
                MemoryStatus.ACTIVE,
                EvidenceAuthority.DIRECT_REPO,
                (evidence,),
                memory_id=memory_id,
                metadata={"reconciled_from_status": previous},
            )
            return ReconciliationResult(
                memory_id,
                previous,
                revision.status.value,
                "new_revision",
                "project_fact_updated_by_direct_evidence",
            )

        revision = self.core.transition(
            memory_id,
            MemoryStatus.NEEDS_REVALIDATION,
            f"Anchor changed at {target}",
        )
        return ReconciliationResult(
            memory_id,
            previous,
            revision.status.value,
            "mark_dirty",
            "environment_change_requires_revalidation",
        )

    def reconcile_repository(
        self, repository_root: Path, head: str
    ) -> list[ReconciliationResult]:
        checkpoint = self.core.store.get_reconciliation_checkpoint(
            self.core.repository_id, self.core.branch
        )
        status = self._git(repository_root, "status", "--porcelain=v1")
        worktree_hash = hashlib.sha256(status.encode()).hexdigest()
        if (
            checkpoint
            and checkpoint["head"] == head
            and checkpoint["worktree_hash"] == worktree_hash
        ):
            return []

        changed_targets = self._status_targets(status)
        previous_head = checkpoint["head"] if checkpoint else ""
        if previous_head and previous_head != head:
            changed_targets.update(
                self._git(
                    repository_root,
                    "diff",
                    "--name-only",
                    previous_head,
                    head,
                ).splitlines()
            )

        results: list[ReconciliationResult] = []
        committed = not bool(status.strip())
        for item in self.impact_report(changed_targets):
            if item["status"] != MemoryStatus.ACTIVE.value:
                continue
            target = item["anchors"][0]["target"]
            results.append(
                self.reconcile_anchor_change(
                    item["memory_id"],
                    target,
                    committed=committed,
                    evidence_excerpt=f"Git change observed at {target}",
                )
            )
        self.core.record_reconciliation_checkpoint(
            head, worktree_hash, sorted(changed_targets)
        )
        return results

    @staticmethod
    def _git(repository_root: Path, *args: str) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=repository_root,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.stdout.rstrip()

    @staticmethod
    def _status_targets(status: str) -> set[str]:
        targets: set[str] = set()
        for line in status.splitlines():
            value = line[3:].strip()
            if " -> " in value:
                value = value.split(" -> ", maxsplit=1)[1]
            if value:
                targets.add(value.replace("\\", "/"))
        return targets

    def impact_report(self, changed_targets: set[str]) -> list[dict[str, Any]]:
        memories = self.core.store.list_current(
            self.core.repository_id,
            self.core.branch,
            base_branch=self.core.base_branch,
        )
        report: list[dict[str, Any]] = []
        for memory in memories:
            matching = [
                anchor
                for anchor in memory["anchors"]
                if anchor["target"] in changed_targets
            ]
            if matching:
                report.append(
                    {
                        "memory_id": memory["memory_id"],
                        "kind": memory["kind"],
                        "status": memory["status"],
                        "anchors": matching,
                        "recommended_action": "review_only",
                    }
                )
        return report

    def propagate_memory_change(self, source_memory_id: str) -> list[str]:
        dependents = self.core.store.active_memory_dependents(
            self.core.repository_id, self.core.branch, source_memory_id
        )
        transitioned: list[str] = []
        for memory_id in dependents:
            current = self.core.store.get_current(
                self.core.repository_id,
                self.core.branch,
                memory_id,
                self.core.base_branch,
            )
            if current and current["status"] == MemoryStatus.ACTIVE.value:
                self.core.transition(
                    memory_id,
                    MemoryStatus.NEEDS_REVALIDATION,
                    f"Upstream memory changed: {source_memory_id}",
                )
                transitioned.append(memory_id)
        return transitioned
