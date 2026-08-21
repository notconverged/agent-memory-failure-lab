from __future__ import annotations

import os
import uuid
from collections.abc import Callable

from agent_memory.compiler import CompilerExecutor, highest_authority
from agent_memory.core import MemoryCore
from agent_memory.models import (
    CaptureCoverage,
    CompilerJob,
    EvidenceAuthority,
    EvidenceBundle,
    EvidenceRef,
    SessionStateSnapshot,
)
from agent_memory.policy import PromotionPolicy, evaluate_promotion


class OneShotWorker:
    def __init__(
        self,
        core: MemoryCore,
        compiler: CompilerExecutor,
        current_head: Callable[[], str],
        promotion_policy: PromotionPolicy = PromotionPolicy.STRICT,
    ) -> None:
        self.core = core
        self.compiler = compiler
        self.current_head = current_head
        self.promotion_policy = promotion_policy

    def run(self) -> dict[str, int | bool]:
        owner = f"{os.getpid()}-{uuid.uuid4().hex}"
        lease_name = f"compiler:{self.core.repository_id}"
        if not self.core.store.acquire_lease(lease_name, owner):
            return {"lease_acquired": False, "processed": 0, "failed": 0}
        processed = 0
        failed = 0
        try:
            self.core.ingest_spool()
            for raw in self.core.store.pending_compiler_jobs():
                job = compiler_job_from_dict(raw)
                if self.current_head() != job.head:
                    self.core.finish_compiler_job(
                        job.job_id, "stale", error="HEAD changed before import"
                    )
                    failed += 1
                    continue
                try:
                    candidates = self.compiler.compile(job)
                    imported: list[dict] = []
                    for candidate in candidates:
                        result = evaluate_promotion(
                            candidate,
                            job.evidence_bundle.coverage,
                            self.promotion_policy,
                        )
                        revision = self.core.create_memory(
                            candidate.kind,
                            candidate.claim,
                            candidate.rationale,
                            result.status,
                            highest_authority(candidate),
                            candidate.evidence,
                            candidate.anchors,
                            metadata={
                                "compiler_job_id": job.job_id,
                                "promotion_reason": result.reason,
                                "promotion_policy": self.promotion_policy.value,
                            },
                        )
                        imported.append(revision.to_dict())
                    self.core.finish_compiler_job(
                        job.job_id, "completed", candidates=imported
                    )
                    processed += 1
                except Exception as error:  # worker must preserve failure evidence
                    self.core.finish_compiler_job(
                        job.job_id, "failed", error=str(error)
                    )
                    failed += 1
        finally:
            self.core.store.release_lease(lease_name, owner)
        return {"lease_acquired": True, "processed": processed, "failed": failed}


def compiler_job_from_dict(value: dict) -> CompilerJob:
    bundle_value = value["evidence_bundle"]
    coverage_value = bundle_value["coverage"]
    coverage = CaptureCoverage(
        bool(coverage_value["complete"]),
        tuple(coverage_value.get("expected_sources", ())),
        tuple(coverage_value.get("observed_sources", ())),
        tuple(coverage_value.get("gaps", ())),
    )
    evidence = tuple(
        EvidenceRef(
            item["evidence_id"],
            EvidenceAuthority(item["authority"]),
            item["source_type"],
            item["source_ref"],
            item.get("excerpt", ""),
            item.get("content_hash", ""),
            item["captured_at"],
        )
        for item in bundle_value["evidence"]
    )
    bundle = EvidenceBundle(
        bundle_value["bundle_id"],
        bundle_value["cursor"],
        bundle_value["repository_id"],
        bundle_value["branch"],
        bundle_value["head"],
        coverage,
        evidence,
        tuple(bundle_value.get("summaries", ())),
    )
    state_value = value["session_state"]
    state = SessionStateSnapshot(
        state_value["session_id"],
        state_value["task_summary"],
        tuple(state_value.get("active_execution_nodes", ())),
        state_value.get("observed_head", ""),
    )
    return CompilerJob(
        value["job_id"],
        value["repository_id"],
        value["branch"],
        value["cursor"],
        value["head"],
        bundle,
        state,
        value["created_at"],
    )
