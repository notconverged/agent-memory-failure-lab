from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from agent_memory.models import (
    CaptureCoverage,
    EvidenceAuthority,
    MemoryCandidate,
    MemoryKind,
    MemoryStatus,
)


class PromotionPolicy(str, Enum):
    STRICT = "strict"
    HYBRID = "hybrid"


NORMATIVE_AUTHORITIES = {
    EvidenceAuthority.EXPLICIT_USER,
    EvidenceAuthority.PROJECT_NORM,
}
DIRECT_AUTHORITIES = {
    EvidenceAuthority.DIRECT_REPO,
    EvidenceAuthority.DIRECT_TEST,
}
PROVISIONAL_PATTERN = re.compile(
    r"(?i)\b(try|temporary|experiment|prototype|maybe|explore)\b|"
    r"(尝试|临时|试试|实验|探索)"
)


@dataclass(frozen=True)
class PromotionResult:
    status: MemoryStatus
    reason: str
    automatic: bool


def evaluate_promotion(
    candidate: MemoryCandidate,
    coverage: CaptureCoverage,
    policy: PromotionPolicy = PromotionPolicy.STRICT,
) -> PromotionResult:
    if not coverage.complete or coverage.gaps:
        return PromotionResult(
            MemoryStatus.PROPOSED,
            "capture_gap_prevents_automatic_activation",
            False,
        )
    if candidate.has_counterevidence:
        return PromotionResult(
            MemoryStatus.PROPOSED, "counterevidence_requires_adjudication", False
        )

    authorities = {item.authority for item in candidate.evidence}
    if candidate.kind in {MemoryKind.DECISION, MemoryKind.CONSTRAINT}:
        evidence_text = " ".join(item.excerpt for item in candidate.evidence)
        if PROVISIONAL_PATTERN.search(evidence_text):
            return PromotionResult(
                MemoryStatus.PROPOSED,
                "provisional_language_requires_adjudication",
                False,
            )
        if not authorities & NORMATIVE_AUTHORITIES:
            return PromotionResult(
                MemoryStatus.PROPOSED,
                "normative_memory_requires_normative_evidence",
                False,
            )
        return PromotionResult(MemoryStatus.ACTIVE, "normative_evidence", True)

    if candidate.kind is MemoryKind.PROJECT_FACT:
        if authorities & DIRECT_AUTHORITIES:
            return PromotionResult(MemoryStatus.ACTIVE, "direct_repo_evidence", True)

    if candidate.kind is MemoryKind.FAILURE:
        if EvidenceAuthority.DIRECT_TEST in authorities:
            return PromotionResult(MemoryStatus.ACTIVE, "direct_failure_outcome", True)

    if policy is PromotionPolicy.HYBRID:
        independent_sources = {
            (item.authority, item.source_type) for item in candidate.evidence
        }
        if len(independent_sources) >= 2:
            return PromotionResult(
                MemoryStatus.ACTIVE, "independently_corroborated", True
            )

    return PromotionResult(
        MemoryStatus.PROPOSED, "insufficient_authority_for_automatic_activation", False
    )
