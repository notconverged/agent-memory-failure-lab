from __future__ import annotations

from pathlib import Path

from agent_memory import codex_hook
from agent_memory.core import MemoryCore
from agent_memory.evidence import classify_codex_event
from agent_memory.models import EvidenceAuthority


def capture(core: MemoryCore, event_name: str, session_id: str, **payload) -> None:
    core.capture_event(
        f"codex_{event_name}",
        {
            "hook_event_name": event_name,
            "session_id": session_id,
            **payload,
        },
    )
    core.ingest_spool()


def test_compiler_cursor_advances_only_after_success(tmp_path: Path):
    core = MemoryCore(tmp_path, "repo-1", "main")
    capture(core, "UserPromptSubmit", "session-1", prompt="Use Decimal")
    capture(
        core,
        "PostToolUse",
        "session-1",
        tool_name="exec_command",
        tool_input={"cmd": "pytest"},
        tool_response={"exit_code": 0},
    )
    first = codex_hook.build_compiler_job(core, "head-1", "session-1")
    assert first is not None
    assert len(first.evidence_bundle.evidence) == 2
    assert core.queue_compiler_job(first) is True
    assert core.queue_compiler_job(first) is False

    core.finish_compiler_job(first.job_id, "failed", error="temporary")
    retry = codex_hook.build_compiler_job(core, "head-1", "session-1")
    assert retry is not None
    assert retry.input_hash == first.input_hash
    assert core.queue_compiler_job(retry) is True

    core.finish_compiler_job(first.job_id, "completed")
    assert codex_hook.build_compiler_job(core, "head-1", "session-1") is None

    capture(core, "Stop", "session-1", reason="done")
    second = codex_hook.build_compiler_job(core, "head-1", "session-1")
    assert second is not None
    assert [item.source_type for item in second.evidence_bundle.evidence] == ["Stop"]


def test_evidence_authority_is_source_based():
    assert (
        classify_codex_event("UserPromptSubmit", {"prompt": "Use Decimal"})
        is EvidenceAuthority.EXPLICIT_USER
    )
    assert (
        classify_codex_event(
            "PostToolUse",
            {
                "tool_name": "exec_command",
                "tool_input": {"cmd": "python -m pytest"},
                "tool_response": {"exit_code": 0},
            },
        )
        is EvidenceAuthority.DIRECT_TEST
    )
    assert (
        classify_codex_event(
            "PostToolUse",
            {
                "tool_name": "read_file",
                "tool_input": {"path": "PROJECT_POLICY.md"},
                "tool_response": {"text": "Money uses Decimal"},
            },
        )
        is EvidenceAuthority.PROJECT_NORM
    )
