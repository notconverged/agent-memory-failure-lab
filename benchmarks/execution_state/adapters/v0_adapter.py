from __future__ import annotations

import subprocess
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from benchmarks.execution_state.adapters.base import (
    AdapterContext,
    apply_session_files,
    capability,
    trace_text,
)


class V0Adapter:
    """Drive the unchanged product through its hook and router entrypoints."""

    POLL_INTERVAL_SECONDS = 0.25
    WORKER_TIMEOUT_SECONDS = 240.0

    def __init__(
        self,
        hook: Callable[..., dict[str, Any]] | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._hook = hook
        self._sleep = sleep

    @staticmethod
    def capabilities() -> dict[str, Any]:
        code_evidence = [
            "src/agent_memory/models.py:ExecutionNode",
            "src/agent_memory/codex_hook.py:handle_hook",
        ]
        return {
            "active_path_integrity": capability(
                "not_observable",
                evidence_paths=code_evidence,
                derivation=(
                    "ExecutionNode has parent_id, but the normal hook/compiler/worker "
                    "pipeline does not establish a current execution cursor."
                ),
                limitations="A class definition alone is not runtime path evidence.",
            ),
            "branch_isolation": capability(
                "unsupported",
                evidence_paths=code_evidence,
                derivation="The current product projection has no active/inactive sibling execution branch model.",  # noqa: E501
                limitations="Git branch overlays are durable-memory scope, not execution alternatives.",  # noqa: E501
            ),
            "compression_fidelity": capability(
                "unsupported",
                evidence_paths=code_evidence,
                derivation="The current ExecutionNode has no raw/summary layer or cover-node relation.",  # noqa: E501
                limitations="Compiler summaries are evidence inputs, not boundary summary nodes.",  # noqa: E501
            ),
            "maintain_precision": capability(
                "unsupported",
                evidence_paths=code_evidence,
                derivation="The current product has no summary-before-trust boundary validation operation.",  # noqa: E501
                limitations="Promotion and reconciliation do not expose MAGE Maintain semantics.",  # noqa: E501
            ),
        }

    def execute(self, context: AdapterContext) -> dict[str, Any]:
        from agent_memory.codex_hook import handle_hook
        from agent_memory.core import MemoryCore
        from agent_memory.paths import discover_repository
        from agent_memory.router import ContextRouter

        hook = self._hook or handle_hook
        observations: dict[str, dict[str, Any]] = {}
        checkpoints_by_session: dict[str, list[dict[str, Any]]] = {}
        for checkpoint in context.scenario["product_checkpoints"]:
            checkpoints_by_session.setdefault(
                checkpoint["after_session_id"], []
            ).append(checkpoint)

        for session in context.scenario["sessions"]:
            apply_session_files(context.workspace, session)
            payload_base = {
                "cwd": str(context.workspace.resolve()),
                "session_id": session["session_id"],
                "source": "execution-state-benchmark-synthetic-hook-replay",
            }
            hook({**payload_base, "hook_event_name": "SessionStart"}, context.data_dir)
            hook(
                {
                    **payload_base,
                    "hook_event_name": "UserPromptSubmit",
                    "prompt": session["instruction"],
                },
                context.data_dir,
            )
            for event in context.scenario["timeline"]:
                step = int(event["step_index"])
                if (
                    session["timeline_start"] <= step <= session["timeline_end"]
                    and event["operation"] == "grow"
                ):
                    hook(
                        {
                            **payload_base,
                            "hook_event_name": "PostToolUse",
                            "tool_name": "exec_command",
                            "tool_use_id": event["step_key"],
                            "tool_input": {"action": event["action"]},
                            "tool_response": event["observation"],
                        },
                        context.data_dir,
                    )
            hook({**payload_base, "hook_event_name": "SessionEnd"}, context.data_dir)
            self._wait_for_worker(
                context.data_dir,
                context.workspace,
                session["session_id"],
                MemoryCore,
                discover_repository,
            )
            for checkpoint in checkpoints_by_session.get(session["session_id"], []):
                repository = discover_repository(context.workspace)
                core = MemoryCore(
                    context.data_dir,
                    repository.repository_id,
                    repository.branch,
                    repository.base_branch,
                )
                try:
                    routed = ContextRouter(core).route(
                        checkpoint["query"],
                        f"probe-{context.run_id}-{checkpoint['step_index']}",
                        "benchmark_probe",
                        token_budget=800,
                    )
                    text = routed.text.strip()
                    observations[str(checkpoint["step_index"])] = {
                        "query_status": "completed" if text else "empty",
                        "retrieval_text": text,
                        "query": checkpoint["query"],
                        "revisions": list(routed.revisions),
                    }
                except Exception as error:
                    observations[str(checkpoint["step_index"])] = {
                        "query_status": "error",
                        "retrieval_text": "",
                        "query": checkpoint["query"],
                        "error": str(error),
                    }
                finally:
                    core.close()
        return {
            "system": "v0",
            "scenario_id": context.scenario["scenario_id"],
            "ingestion_mode": "synthetic_hook_replay",
            "production_entrypoint": "agent_memory.codex_hook.handle_hook",
            "equivalence": "payload_compatible_not_live_codex_session",
            "retrieval_entrypoint": "agent_memory.router.ContextRouter",
            "retrieval_probe_side_effect": "delivery_record_only",
            "codex_cli_version": self._codex_version(),
            "model_id": "not_observable",
            "storage_paths": [str(context.data_dir.resolve())],
            "observations": observations,
            "capabilities": self.capabilities(),
        }

    def _wait_for_worker(
        self,
        data_root: Path,
        workspace: Path,
        session_id: str,
        core_type: type,
        discover_repository: Callable[[Path], Any],
    ) -> None:
        deadline = time.monotonic() + self.WORKER_TIMEOUT_SECONDS
        saw_job = False
        while time.monotonic() < deadline:
            repository = discover_repository(workspace)
            core = core_type(
                data_root,
                repository.repository_id,
                repository.branch,
                repository.base_branch,
            )
            try:
                jobs = core.store.compiler_jobs_for_session(session_id)
            finally:
                core.close()
            if jobs:
                saw_job = True
                states = {job["status"] for job in jobs}
                if states <= {"completed"}:
                    return
                failed = states & {"failed", "stale"}
                if failed:
                    details = [
                        {"status": job["status"], "error": job.get("error")}
                        for job in jobs
                        if job["status"] in failed
                    ]
                    raise RuntimeError(
                        f"v0 compiler job failed for {session_id}: {details}"
                    )
            self._sleep(self.POLL_INTERVAL_SECONDS)
        detail = "job never appeared" if not saw_job else "job remained pending"
        raise RuntimeError(f"v0 worker timeout for {session_id}: {detail}")

    @staticmethod
    def _codex_version() -> str:
        try:
            result = subprocess.run(
                ["codex", "--version"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            return (result.stdout or result.stderr).strip() or "not_observable"
        except (OSError, subprocess.SubprocessError):
            return "not_observable"


def session_trace(scenario: dict[str, Any], session: dict[str, Any]) -> str:
    return trace_text(scenario, session["timeline_start"], session["timeline_end"])
