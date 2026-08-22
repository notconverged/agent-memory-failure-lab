from __future__ import annotations

import json
import os
import uuid
from dataclasses import replace
from pathlib import Path
from typing import Any

from agent_memory.event_log import EventLog
from agent_memory.models import (
    Anchor,
    CompilerJob,
    EventEnvelope,
    EvidenceAuthority,
    EvidenceRef,
    ExecutionNode,
    MemoryKind,
    MemoryRevision,
    MemoryStatus,
)
from agent_memory.paths import RepositoryContext, repository_data_dir
from agent_memory.redaction import redact_text
from agent_memory.store import MemoryStore


class MemoryCore:
    PAYLOAD_QUOTA_BYTES = 256 * 1024 * 1024
    ALLOWED_TRANSITIONS = {
        MemoryStatus.PROPOSED: {
            MemoryStatus.ACTIVE,
            MemoryStatus.REJECTED,
            MemoryStatus.SUPERSEDED,
            MemoryStatus.CONFLICTED,
            MemoryStatus.UNPROVABLE,
            MemoryStatus.TOMBSTONED,
        },
        MemoryStatus.ACTIVE: {
            MemoryStatus.NEEDS_REVALIDATION,
            MemoryStatus.CONFLICTED,
            MemoryStatus.SUPERSEDED,
            MemoryStatus.INVALIDATED,
            MemoryStatus.TOMBSTONED,
        },
        MemoryStatus.NEEDS_REVALIDATION: {
            MemoryStatus.ACTIVE,
            MemoryStatus.CONFLICTED,
            MemoryStatus.UNPROVABLE,
            MemoryStatus.SUPERSEDED,
            MemoryStatus.INVALIDATED,
            MemoryStatus.TOMBSTONED,
        },
        MemoryStatus.CONFLICTED: {
            MemoryStatus.ACTIVE,
            MemoryStatus.SUPERSEDED,
            MemoryStatus.INVALIDATED,
            MemoryStatus.TOMBSTONED,
        },
        MemoryStatus.UNPROVABLE: {
            MemoryStatus.ACTIVE,
            MemoryStatus.INVALIDATED,
            MemoryStatus.TOMBSTONED,
        },
        MemoryStatus.SUPERSEDED: set(),
        MemoryStatus.INVALIDATED: set(),
        MemoryStatus.REJECTED: set(),
        MemoryStatus.TOMBSTONED: set(),
    }

    def __init__(
        self,
        data_root: Path,
        repository_id: str,
        branch: str,
        base_branch: str | None = None,
    ) -> None:
        self.data_root = data_root
        self.repository_id = repository_id
        self.branch = branch
        self.base_branch = base_branch or branch
        self.repository_dir = repository_data_dir(data_root, repository_id)
        self.event_log = EventLog(self.repository_dir)
        self.store = MemoryStore(self.repository_dir / "projection.sqlite3")
        self.catch_up()

    def close(self) -> None:
        self.store.close()

    def catch_up(self) -> int:
        projected = 0
        for event in self.event_log.iter_events():
            projected += int(self.store.project(event))
        return projected

    def ingest_spool(self) -> int:
        self.catch_up()
        ingested = 0
        for path in self.event_log.pending_spool():
            event = self.event_log.read_spool(path)
            if not self.store.has_event(event.event_id):
                self._commit(event)
                ingested += 1
            self.event_log.acknowledge_spool(path)
        return ingested

    def capture_event(
        self, event_type: str, payload: dict[str, Any], branch: str | None = None
    ) -> Path:
        sanitized = self._sanitize_payload(payload)
        event = self._event(event_type, sanitized, branch)
        encoded_size = len(json.dumps(event.to_dict(), ensure_ascii=False).encode())
        current_size = (
            self.event_log.log_path.stat().st_size
            if self.event_log.log_path.exists()
            else 0
        )
        spool_size = sum(path.stat().st_size for path in self.event_log.pending_spool())
        if current_size + spool_size + encoded_size > self.PAYLOAD_QUOTA_BYTES:
            raise ValueError("repository payload quota exceeded")
        return self.event_log.write_spool(event)

    def register_repository(self, context: RepositoryContext) -> None:
        self._commit(
            self._event(
                "repository_registered",
                {
                    "root": str(context.root),
                    "git_common_dir": str(context.git_common_dir),
                    "base_branch": context.base_branch,
                    "head": context.head,
                },
                context.branch,
            )
        )

    def create_memory(
        self,
        kind: MemoryKind,
        claim: str,
        rationale: str,
        status: MemoryStatus,
        authority: EvidenceAuthority,
        evidence: tuple[EvidenceRef, ...],
        anchors: tuple[Any, ...] = (),
        memory_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> MemoryRevision:
        identifier = memory_id or f"mem-{uuid.uuid4().hex}"
        revision_number = self.store.next_revision(identifier)
        previous = revision_number - 1 or None
        revision = MemoryRevision(
            memory_id=identifier,
            revision=revision_number,
            repository_id=self.repository_id,
            branch=self.branch,
            kind=kind,
            claim=redact_text(claim, 8_000),
            rationale=redact_text(rationale, 8_000),
            status=status,
            authority=authority,
            evidence=tuple(self._sanitize_evidence(item) for item in evidence),
            anchors=anchors,
            supersedes_revision=previous,
            metadata=metadata or {},
        )
        self._commit(self._event("memory_revision_created", revision.to_dict()))
        self._commit(
            self._event(
                "memory_ref_moved",
                {
                    "memory_id": identifier,
                    "revision": revision_number,
                    "status": status.value,
                    "reason": "revision_created",
                },
            )
        )
        return revision

    def transition(
        self,
        memory_id: str,
        status: MemoryStatus,
        reason: str,
        authority: EvidenceAuthority = EvidenceAuthority.EXPLICIT_USER,
    ) -> MemoryRevision:
        current = self.store.get_current(
            self.repository_id, self.branch, memory_id, self.base_branch
        )
        if current is None:
            raise KeyError(f"Unknown memory: {memory_id}")
        previous_status = MemoryStatus(current["status"])
        if status not in self.ALLOWED_TRANSITIONS[previous_status]:
            raise ValueError(
                f"invalid memory transition: {previous_status.value} -> {status.value}"
            )
        evidence = tuple(
            EvidenceRef(
                evidence_id=item["evidence_id"],
                authority=EvidenceAuthority(item["authority"]),
                source_type=item["source_type"],
                source_ref=item["source_ref"],
                excerpt=item.get("excerpt", ""),
                content_hash=item.get("content_hash", ""),
                captured_at=item["captured_at"],
            )
            for item in current["evidence"]
        )
        anchors = tuple(
            Anchor(
                anchor_type=item["anchor_type"],
                target=item["target"],
                content_hash=item.get("content_hash", ""),
                symbol=item.get("symbol"),
            )
            for item in current["anchors"]
        )
        metadata = dict(current["metadata"])
        metadata["adjudication_reason"] = redact_text(reason, 2_000)
        metadata["adjudication_authority"] = authority.value
        revision = self.create_memory(
            kind=MemoryKind(current["kind"]),
            claim=current["claim"],
            rationale=current["rationale"],
            status=status,
            authority=EvidenceAuthority(current["authority"]),
            evidence=evidence,
            anchors=anchors,
            memory_id=memory_id,
            metadata=metadata,
        )
        self._commit(
            self._event(
                "adjudication_recorded",
                {
                    "memory_id": memory_id,
                    "from_status": previous_status.value,
                    "to_status": status.value,
                    "revision": revision.revision,
                    "authority": authority.value,
                    "reason": redact_text(reason, 2_000),
                },
            )
        )
        return revision

    def rebuild(self) -> int:
        self.store.clear_projection()
        return self.catch_up()

    def export_json(self, target: Path) -> Path:
        payload = {
            "repository_id": self.repository_id,
            "branch": self.branch,
            "memories": self.store.list_current(
                self.repository_id, self.branch, base_branch=self.base_branch
            ),
        }
        temporary = target.with_suffix(target.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        os.replace(temporary, target)
        return target

    def purge(self, memory_id: str) -> int:
        kept: list[EventEnvelope] = []
        removed = 0
        for event in self.event_log.iter_events():
            if self._event_mentions_memory(event, memory_id):
                removed += 1
            else:
                kept.append(event)
        if removed == 0:
            raise KeyError(f"Unknown memory: {memory_id}")
        temporary = self.event_log.log_path.with_suffix(".jsonl.tmp")
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            for event in kept:
                stream.write(
                    json.dumps(
                        event.to_dict(), ensure_ascii=False, separators=(",", ":")
                    )
                    + "\n"
                )
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, self.event_log.log_path)
        self.rebuild()
        return removed

    def record_delivery(self, payload: dict[str, Any]) -> None:
        self._commit(self._event("delivery_recorded", payload))

    def record_feedback(
        self, verdict: str, comment: str = "", memory_id: str | None = None
    ) -> None:
        self._commit(
            self._event(
                "feedback_recorded",
                {
                    "memory_id": memory_id,
                    "verdict": verdict,
                    "comment": redact_text(comment, 2_000),
                },
            )
        )

    def queue_compiler_job(self, job: CompilerJob) -> bool:
        if job.repository_id != self.repository_id or job.branch != self.branch:
            raise ValueError("Compiler job scope does not match this core")
        if job.input_hash:
            existing = self.store.compiler_input_status(job.input_hash)
            if existing:
                if existing["status"] == "failed":
                    self._commit(
                        self._event(
                            "compiler_job_retried",
                            {
                                "job_id": existing["job_id"],
                                "input_hash": job.input_hash,
                            },
                        )
                    )
                    return True
                return False
        self._commit(self._event("compiler_job_queued", job.to_dict()))
        return True

    def finish_compiler_job(
        self,
        job_id: str,
        status: str,
        candidates: list[dict[str, Any]] | None = None,
        error: str | None = None,
    ) -> None:
        self._commit(
            self._event(
                "compiler_job_finished",
                {
                    "job_id": job_id,
                    "status": status,
                    "candidates": candidates or [],
                    "error": redact_text(error or "", 2_000) or None,
                },
            )
        )

    def record_reconciliation_checkpoint(
        self,
        head: str,
        worktree_hash: str,
        changed_targets: list[str],
    ) -> None:
        self._commit(
            self._event(
                "reconciliation_checkpoint_saved",
                {
                    "head": head,
                    "worktree_hash": worktree_hash,
                    "changed_targets": sorted(set(changed_targets)),
                },
            )
        )

    def add_dependency(
        self,
        source_memory_id: str,
        target_type: str,
        target_id: str,
        evidence: list[dict[str, Any]],
        status: str = "active",
    ) -> str:
        if target_type not in {"memory", "file", "symbol", "config", "test"}:
            raise ValueError("unsupported dependency target type")
        if status not in {"active", "proposed"}:
            raise ValueError("dependency status must be active or proposed")
        if status == "active" and not evidence:
            raise ValueError("active dependency requires evidence")
        edge_id = f"edge-{uuid.uuid4().hex}"
        self._commit(
            self._event(
                "dependency_edge_added",
                {
                    "edge_id": edge_id,
                    "source_memory_id": source_memory_id,
                    "target_type": target_type,
                    "target_id": target_id,
                    "status": status,
                    "evidence": self._sanitize_payload(evidence),
                },
            )
        )
        return edge_id

    def upsert_execution_node(self, node: ExecutionNode) -> None:
        if node.repository_id != self.repository_id or node.branch != self.branch:
            raise ValueError("Execution node scope does not match this core")
        self._commit(self._event("execution_node_upserted", node.to_dict()))

    def _commit(self, event: EventEnvelope) -> None:
        self.event_log.append(event)
        self.store.project(event)

    def _event(
        self,
        event_type: str,
        payload: dict[str, Any],
        branch: str | None = None,
    ) -> EventEnvelope:
        return EventEnvelope(
            event_id=f"evt-{uuid.uuid4().hex}",
            event_type=event_type,
            repository_id=self.repository_id,
            branch=branch or self.branch,
            payload=payload,
        )

    @staticmethod
    def _sanitize_evidence(evidence: EvidenceRef) -> EvidenceRef:
        return replace(evidence, excerpt=redact_text(evidence.excerpt))

    @classmethod
    def _sanitize_payload(cls, value: Any, depth: int = 0) -> Any:
        if depth >= 6:
            return "[MAX_DEPTH]"
        if isinstance(value, str):
            return redact_text(value)
        if isinstance(value, dict):
            items = list(value.items())[:100]
            result = {
                str(key)[:200]: cls._sanitize_payload(item, depth + 1)
                for key, item in items
            }
            if len(value) > 100:
                result["_truncated_items"] = len(value) - 100
            return result
        if isinstance(value, list | tuple):
            result = [cls._sanitize_payload(item, depth + 1) for item in value[:100]]
            if len(value) > 100:
                result.append(f"[TRUNCATED {len(value) - 100} ITEMS]")
            return result
        return value

    @classmethod
    def _event_mentions_memory(cls, event: EventEnvelope, memory_id: str) -> bool:
        def contains(value: Any) -> bool:
            if value == memory_id:
                return True
            if isinstance(value, dict):
                return any(contains(item) for item in value.values())
            if isinstance(value, list | tuple):
                return any(contains(item) for item in value)
            return False

        return contains(event.payload)
