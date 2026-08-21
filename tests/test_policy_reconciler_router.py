from __future__ import annotations

from pathlib import Path

from agent_memory.core import MemoryCore
from agent_memory.models import (
    Anchor,
    CaptureCoverage,
    EvidenceAuthority,
    EvidenceRef,
    MemoryCandidate,
    MemoryKind,
    MemoryStatus,
)
from agent_memory.policy import PromotionPolicy, evaluate_promotion
from agent_memory.reconciler import Reconciler
from agent_memory.router import ContextRouter


def ev(authority: EvidenceAuthority, source: str = "prompt") -> EvidenceRef:
    return EvidenceRef(
        evidence_id=f"ev-{authority.value}-{source}",
        authority=authority,
        source_type=source,
        source_ref="session:1",
    )


COMPLETE = CaptureCoverage(True, ("prompt",), ("prompt",), ())


def test_capture_gap_blocks_activation_even_with_normative_evidence():
    candidate = MemoryCandidate(
        MemoryKind.CONSTRAINT,
        "Use Decimal",
        "User requirement",
        (ev(EvidenceAuthority.EXPLICIT_USER),),
    )
    gap = CaptureCoverage(False, ("prompt", "tool"), ("prompt",), ("tool",))
    result = evaluate_promotion(candidate, gap, PromotionPolicy.HYBRID)
    assert result.status is MemoryStatus.PROPOSED
    assert result.automatic is False


def test_inference_cannot_turn_code_into_normative_decision():
    candidate = MemoryCandidate(
        MemoryKind.DECISION,
        "Redis is forbidden",
        "Inferred from current implementation",
        (
            ev(EvidenceAuthority.DIRECT_REPO, "config"),
            ev(EvidenceAuthority.AGENT_INFERENCE, "compiler"),
        ),
    )
    result = evaluate_promotion(candidate, COMPLETE, PromotionPolicy.HYBRID)
    assert result.status is MemoryStatus.PROPOSED
    assert result.reason == "normative_memory_requires_normative_evidence"


def test_temporary_user_attempt_cannot_auto_activate_as_decision():
    temporary = EvidenceRef(
        "ev-temp",
        EvidenceAuthority.EXPLICIT_USER,
        "user_prompt",
        "session:2",
        "Try Redis temporarily and compare it with the current cache.",
    )
    candidate = MemoryCandidate(
        MemoryKind.DECISION,
        "Use Redis",
        "Compiler interpreted the attempt",
        (temporary,),
    )
    result = evaluate_promotion(candidate, COMPLETE, PromotionPolicy.STRICT)
    assert result.status is MemoryStatus.PROPOSED
    assert result.reason == "provisional_language_requires_adjudication"


def test_hybrid_requires_independent_corroboration():
    candidate = MemoryCandidate(
        MemoryKind.FAILURE,
        "Cache attempt timed out under Windows",
        "Observed twice",
        (
            ev(EvidenceAuthority.TOOL_RESULT, "tool"),
            ev(EvidenceAuthority.AGENT_INFERENCE, "compiler"),
        ),
    )
    assert evaluate_promotion(candidate, COMPLETE).status is MemoryStatus.PROPOSED
    assert (
        evaluate_promotion(candidate, COMPLETE, PromotionPolicy.HYBRID).status
        is MemoryStatus.ACTIVE
    )


def test_reconciler_never_lets_code_supersede_constraint(tmp_path: Path):
    core = MemoryCore(tmp_path, "repo-1", "main")
    revision = core.create_memory(
        MemoryKind.CONSTRAINT,
        "Money must use Decimal",
        "Project policy",
        MemoryStatus.ACTIVE,
        EvidenceAuthority.PROJECT_NORM,
        (ev(EvidenceAuthority.PROJECT_NORM),),
        (Anchor("file", "src/money.py"),),
    )
    result = Reconciler(core).reconcile_anchor_change(
        revision.memory_id,
        "src/money.py",
        committed=True,
        new_claim="Money uses float",
    )
    assert result.new_status == "conflicted"
    assert result.action == "implementation_conflict"
    history = core.store.history(revision.memory_id)
    assert history[-1]["claim"] == "Money must use Decimal"


def test_uncommitted_change_only_marks_fact_for_revalidation(tmp_path: Path):
    core = MemoryCore(tmp_path, "repo-1", "feature", "main")
    revision = core.create_memory(
        MemoryKind.PROJECT_FACT,
        "Database is SQLite",
        "Config value",
        MemoryStatus.ACTIVE,
        EvidenceAuthority.DIRECT_REPO,
        (ev(EvidenceAuthority.DIRECT_REPO),),
        (Anchor("config", "config.toml"),),
    )
    result = Reconciler(core).reconcile_anchor_change(
        revision.memory_id, "config.toml", committed=False, new_claim="PostgreSQL"
    )
    assert result.new_status == "needs_revalidation"
    current = core.store.get_current("repo-1", "feature", revision.memory_id)
    assert current["claim"] == "Database is SQLite"


def test_router_injects_delta_and_labels_uncertainty(tmp_path: Path):
    core = MemoryCore(tmp_path, "repo-1", "main")
    active = core.create_memory(
        MemoryKind.CONSTRAINT,
        "Use Decimal for money",
        "Precision",
        MemoryStatus.ACTIVE,
        EvidenceAuthority.EXPLICIT_USER,
        (ev(EvidenceAuthority.EXPLICIT_USER),),
    )
    uncertain = core.create_memory(
        MemoryKind.PROJECT_FACT,
        "Database may still be SQLite",
        "Config changed",
        MemoryStatus.NEEDS_REVALIDATION,
        EvidenceAuthority.DIRECT_REPO,
        (ev(EvidenceAuthority.DIRECT_REPO),),
    )
    router = ContextRouter(core)
    first = router.route("Decimal SQLite", "session-1")
    assert "Use Decimal" in first.text
    assert "WARNING [needs_revalidation]" in first.text
    assert (active.memory_id, 1) in first.revisions
    assert (uncertain.memory_id, 1) in first.revisions

    second = router.route("Decimal SQLite", "session-1")
    assert "No new authorized memory" in second.text


def test_gate_is_bounded(tmp_path: Path):
    core = MemoryCore(tmp_path, "repo-1", "main")
    for index in range(20):
        core.create_memory(
            MemoryKind.CONSTRAINT,
            f"Constraint {index}: do not violate the money module boundary",
            "Bounded warning test",
            MemoryStatus.ACTIVE,
            EvidenceAuthority.EXPLICIT_USER,
            (ev(EvidenceAuthority.EXPLICIT_USER, str(index)),),
        )
    result = ContextRouter(core).gate("apply_patch", "money module " * 500, "session-1")
    assert result.token_estimate <= 200


def test_only_evidence_backed_active_dependency_propagates(tmp_path: Path):
    core = MemoryCore(tmp_path, "repo-1", "main")
    upstream = core.create_memory(
        MemoryKind.PROJECT_FACT,
        "Runtime is Python 3.10",
        "pyproject",
        MemoryStatus.ACTIVE,
        EvidenceAuthority.DIRECT_REPO,
        (ev(EvidenceAuthority.DIRECT_REPO),),
    )
    derived = core.create_memory(
        MemoryKind.PROJECT_FACT,
        "tomllib is available",
        "Derived from runtime",
        MemoryStatus.ACTIVE,
        EvidenceAuthority.DIRECT_REPO,
        (ev(EvidenceAuthority.DIRECT_REPO, "pyproject"),),
    )
    core.add_dependency(
        upstream.memory_id,
        "memory",
        derived.memory_id,
        [{"evidence_id": "ev-direct"}],
    )
    changed = Reconciler(core).propagate_memory_change(upstream.memory_id)
    assert changed == [derived.memory_id]
    current = core.store.get_current("repo-1", "main", derived.memory_id)
    assert current["status"] == "needs_revalidation"
