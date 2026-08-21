from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class StringEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


class MemoryKind(StringEnum):
    DECISION = "Decision"
    CONSTRAINT = "Constraint"
    PROJECT_FACT = "ProjectFact"
    FAILURE = "Failure"


class MemoryStatus(StringEnum):
    PROPOSED = "proposed"
    ACTIVE = "active"
    NEEDS_REVALIDATION = "needs_revalidation"
    CONFLICTED = "conflicted"
    UNPROVABLE = "unprovable"
    SUPERSEDED = "superseded"
    INVALIDATED = "invalidated"
    REJECTED = "rejected"
    TOMBSTONED = "tombstoned"


class EvidenceAuthority(StringEnum):
    EXPLICIT_USER = "explicit_user"
    PROJECT_NORM = "project_norm"
    DIRECT_REPO = "direct_repo"
    DIRECT_TEST = "direct_test"
    TOOL_RESULT = "tool_result"
    AGENT_INFERENCE = "agent_inference"


class ExecutionStatus(StringEnum):
    PENDING = "pending"
    ACTIVE = "active"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


@dataclass(frozen=True)
class EvidenceRef:
    evidence_id: str
    authority: EvidenceAuthority
    source_type: str
    source_ref: str
    excerpt: str = ""
    content_hash: str = ""
    captured_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["authority"] = self.authority.value
        return value


@dataclass(frozen=True)
class Anchor:
    anchor_type: str
    target: str
    content_hash: str = ""
    symbol: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CaptureCoverage:
    complete: bool
    expected_sources: tuple[str, ...] = ()
    observed_sources: tuple[str, ...] = ()
    gaps: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MemoryCandidate:
    kind: MemoryKind
    claim: str
    rationale: str
    evidence: tuple[EvidenceRef, ...]
    anchors: tuple[Anchor, ...] = ()
    confidence: float | None = None
    candidate_id: str = ""
    has_counterevidence: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "claim": self.claim,
            "rationale": self.rationale,
            "evidence": [item.to_dict() for item in self.evidence],
            "anchors": [item.to_dict() for item in self.anchors],
            "confidence": self.confidence,
            "candidate_id": self.candidate_id,
            "has_counterevidence": self.has_counterevidence,
        }


@dataclass(frozen=True)
class MemoryRevision:
    memory_id: str
    revision: int
    repository_id: str
    branch: str
    kind: MemoryKind
    claim: str
    rationale: str
    status: MemoryStatus
    authority: EvidenceAuthority
    evidence: tuple[EvidenceRef, ...]
    anchors: tuple[Anchor, ...] = ()
    supersedes_revision: int | None = None
    created_at: str = field(default_factory=utc_now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "memory_id": self.memory_id,
            "revision": self.revision,
            "repository_id": self.repository_id,
            "branch": self.branch,
            "kind": self.kind.value,
            "claim": self.claim,
            "rationale": self.rationale,
            "status": self.status.value,
            "authority": self.authority.value,
            "evidence": [item.to_dict() for item in self.evidence],
            "anchors": [item.to_dict() for item in self.anchors],
            "supersedes_revision": self.supersedes_revision,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class EventEnvelope:
    event_id: str
    event_type: str
    repository_id: str
    branch: str
    payload: dict[str, Any]
    occurred_at: str = field(default_factory=utc_now)
    schema_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExecutionNode:
    node_id: str
    repository_id: str
    branch: str
    title: str
    status: ExecutionStatus
    parent_id: str | None = None
    details: str = ""
    updated_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["status"] = self.status.value
        return value


@dataclass(frozen=True)
class EvidenceBundle:
    bundle_id: str
    cursor: str
    repository_id: str
    branch: str
    head: str
    coverage: CaptureCoverage
    evidence: tuple[EvidenceRef, ...]
    summaries: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "bundle_id": self.bundle_id,
            "cursor": self.cursor,
            "repository_id": self.repository_id,
            "branch": self.branch,
            "head": self.head,
            "coverage": self.coverage.to_dict(),
            "evidence": [item.to_dict() for item in self.evidence],
            "summaries": list(self.summaries),
        }


@dataclass(frozen=True)
class SessionStateSnapshot:
    session_id: str
    task_summary: str
    active_execution_nodes: tuple[str, ...] = ()
    observed_head: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CompilerJob:
    job_id: str
    repository_id: str
    branch: str
    cursor: str
    head: str
    evidence_bundle: EvidenceBundle
    session_state: SessionStateSnapshot
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "repository_id": self.repository_id,
            "branch": self.branch,
            "cursor": self.cursor,
            "head": self.head,
            "evidence_bundle": self.evidence_bundle.to_dict(),
            "session_state": self.session_state.to_dict(),
            "created_at": self.created_at,
        }
