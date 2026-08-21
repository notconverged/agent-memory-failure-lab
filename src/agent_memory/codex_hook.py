from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

from agent_memory.core import MemoryCore
from agent_memory.models import (
    CaptureCoverage,
    CompilerJob,
    EvidenceAuthority,
    EvidenceBundle,
    EvidenceRef,
    SessionStateSnapshot,
)
from agent_memory.paths import default_data_root, discover_repository
from agent_memory.redaction import content_hash, redact_text
from agent_memory.router import ContextRouter

SEMANTIC_BOUNDARIES = {"PostCompact", "Stop", "SessionEnd"}


def handle_hook(payload: dict[str, Any], data_root: Path | None = None) -> dict:
    if os.environ.get("AGENT_MEMORY_COMPILER_MODE") == "1":
        return {}
    event_name = payload.get("hook_event_name", "Unknown")
    cwd = Path(payload.get("cwd") or Path.cwd())
    context = discover_repository(cwd)
    core = MemoryCore(
        data_root or default_data_root(),
        context.repository_id,
        context.branch,
        context.base_branch,
    )
    session_id = str(payload.get("session_id") or "unknown-session")
    try:
        core.capture_event(
            f"codex_{event_name}",
            _capture_payload(payload),
            context.branch,
        )
        if event_name == "SessionStart":
            core.ingest_spool()
            routed = ContextRouter(core).route(
                "", session_id, "session_header", token_budget=180
            )
            return _context_output(event_name, routed.text)
        if event_name == "UserPromptSubmit":
            core.ingest_spool()
            routed = ContextRouter(core).route(
                str(payload.get("prompt", "")),
                session_id,
                "context_capsule",
                token_budget=800,
            )
            return _context_output(event_name, routed.text)
        if event_name == "PreToolUse":
            try:
                started = time.perf_counter()
                tool_input = json.dumps(
                    payload.get("tool_input", {}), ensure_ascii=False
                )
                routed = ContextRouter(core).gate(
                    str(payload.get("tool_name", "unknown")), tool_input, session_id
                )
                latency_ms = round((time.perf_counter() - started) * 1000, 3)
                core.capture_event(
                    "pre_tool_gate_observed",
                    {"latency_ms": latency_ms, "delivered": bool(routed.revisions)},
                )
                return _context_output(event_name, routed.text)
            except Exception as error:
                core.capture_event(
                    "GateUnavailable",
                    {"error": str(error), "tool_name": payload.get("tool_name")},
                )
                return {}
        if event_name in SEMANTIC_BOUNDARIES:
            core.ingest_spool()
            job = build_compiler_job(core, context.head, session_id)
            if job is not None:
                core.queue_compiler_job(job)
                launch_worker(data_root or default_data_root(), cwd)
        return {}
    finally:
        core.close()


def build_compiler_job(
    core: MemoryCore, head: str, session_id: str
) -> CompilerJob | None:
    events = [
        event
        for event in core.event_log.iter_events()
        if event.event_type.startswith("codex_")
    ][-100:]
    if not events:
        return None
    last_cursor = core.store.connection.execute(
        "SELECT cursor FROM compiler_jobs ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    if last_cursor and last_cursor[0] == events[-1].event_id:
        return None
    evidence: list[EvidenceRef] = []
    observed: set[str] = set()
    summaries: list[str] = []
    for event in events:
        source = event.event_type.removeprefix("codex_")
        observed.add(source)
        authority = (
            EvidenceAuthority.EXPLICIT_USER
            if source == "UserPromptSubmit"
            else EvidenceAuthority.TOOL_RESULT
        )
        summary = redact_text(json.dumps(event.payload, ensure_ascii=False), 2_000)
        evidence.append(
            EvidenceRef(
                event.event_id,
                authority,
                source,
                event.event_id,
                summary,
                content_hash(summary),
                event.occurred_at,
            )
        )
        summaries.append(summary)
    expected = {"UserPromptSubmit", "PostToolUse"}
    gaps = expected - observed
    coverage = CaptureCoverage(
        not gaps,
        tuple(sorted(expected)),
        tuple(sorted(observed)),
        tuple(sorted(gaps)),
    )
    cursor = events[-1].event_id
    bundle = EvidenceBundle(
        f"bundle-{uuid.uuid4().hex}",
        cursor,
        core.repository_id,
        core.branch,
        head,
        coverage,
        tuple(evidence),
        tuple(summaries),
    )
    state = SessionStateSnapshot(session_id, "Semantic boundary", observed_head=head)
    return CompilerJob(
        f"job-{uuid.uuid4().hex}",
        core.repository_id,
        core.branch,
        cursor,
        head,
        bundle,
        state,
    )


def launch_worker(data_root: Path, cwd: Path) -> None:
    command = [
        sys.executable,
        "-m",
        "agent_memory.cli",
        "--data-root",
        str(data_root),
        "--cwd",
        str(cwd),
        "worker",
    ]
    flags = 0
    if os.name == "nt":
        flags = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
    subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=flags,
        close_fds=True,
    )


def _capture_payload(payload: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "session_id",
        "turn_id",
        "hook_event_name",
        "source",
        "reason",
        "prompt",
        "tool_name",
        "tool_use_id",
        "tool_input",
        "tool_response",
        "trigger",
        "last_assistant_message",
    }
    return {key: value for key, value in payload.items() if key in allowed}


def _context_output(event_name: str, context: str) -> dict:
    return {
        "hookSpecificOutput": {
            "hookEventName": event_name,
            "additionalContext": context,
        }
    }


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        result = handle_hook(payload)
    except Exception as error:
        # All hooks are advisory in v0. PreToolUse must fail open.
        result = {"systemMessage": f"Agent Memory hook unavailable: {error}"}
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
