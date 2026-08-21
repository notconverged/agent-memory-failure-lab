from __future__ import annotations

import time
from pathlib import Path
from statistics import quantiles

from agent_memory import codex_hook
from agent_memory.core import MemoryCore
from agent_memory.mcp_server import MCPServer
from agent_memory.models import (
    EvidenceAuthority,
    EvidenceRef,
    MemoryKind,
    MemoryStatus,
)
from agent_memory.paths import RepositoryContext


def seeded_core(tmp_path: Path) -> MemoryCore:
    core = MemoryCore(tmp_path, "repo-1", "main")
    core.create_memory(
        MemoryKind.CONSTRAINT,
        "Use Decimal for money",
        "Explicit requirement",
        MemoryStatus.ACTIVE,
        EvidenceAuthority.EXPLICIT_USER,
        (
            EvidenceRef(
                "ev-1",
                EvidenceAuthority.EXPLICIT_USER,
                "prompt",
                "session:1",
            ),
        ),
    )
    return core


def test_mcp_exposes_only_read_and_feedback_tools(tmp_path: Path):
    core = seeded_core(tmp_path)
    core.close()
    server = MCPServer(lambda: MemoryCore(tmp_path, "repo-1", "main"))
    response = server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    names = {item["name"] for item in response["result"]["tools"]}
    assert names == {
        "memory_status",
        "memory_context",
        "memory_search",
        "memory_get",
        "memory_history",
        "memory_feedback",
    }
    assert not names & {"memory_edit", "memory_invalidate", "memory_activate"}


def test_mcp_feedback_does_not_move_active_ref(tmp_path: Path):
    core = seeded_core(tmp_path)
    memory_id = core.store.list_current("repo-1", "main")[0]["memory_id"]
    core.close()
    server = MCPServer(lambda: MemoryCore(tmp_path, "repo-1", "main"))
    response = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "memory_feedback",
                "arguments": {
                    "verdict": "ignored",
                    "memory_id": memory_id,
                    "comment": "not relevant",
                },
            },
        }
    )
    assert "active_ref_changed" in response["result"]["content"][0]["text"]
    reopened = MemoryCore(tmp_path, "repo-1", "main")
    assert reopened.store.history(memory_id)[-1]["revision"] == 1


def test_codex_hook_uses_official_context_shape_and_bounded_gate(
    tmp_path: Path, monkeypatch
):
    context = RepositoryContext(
        "repo-1", tmp_path, tmp_path / ".git", "main", "main", "abc123"
    )
    monkeypatch.setattr(codex_hook, "discover_repository", lambda cwd: context)
    seeded_core(tmp_path).close()
    started = time.perf_counter()
    result = codex_hook.handle_hook(
        {
            "hook_event_name": "PreToolUse",
            "session_id": "session-1",
            "cwd": str(tmp_path),
            "tool_name": "apply_patch",
            "tool_input": {"command": "edit the money module"},
        },
        tmp_path,
    )
    elapsed_ms = (time.perf_counter() - started) * 1000
    specific = result["hookSpecificOutput"]
    assert specific["hookEventName"] == "PreToolUse"
    assert "Use Decimal" in specific["additionalContext"]
    assert elapsed_ms < 300


def test_compiler_mode_prevents_recursive_hook_capture(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AGENT_MEMORY_COMPILER_MODE", "1")
    result = codex_hook.handle_hook(
        {"hook_event_name": "SessionStart", "cwd": str(tmp_path)}, tmp_path
    )
    assert result == {}


def test_pre_tool_gate_p95_is_below_300ms(tmp_path: Path, monkeypatch):
    context = RepositoryContext(
        "repo-1", tmp_path, tmp_path / ".git", "main", "main", "abc123"
    )
    monkeypatch.setattr(codex_hook, "discover_repository", lambda cwd: context)
    seeded_core(tmp_path).close()
    timings: list[float] = []
    for index in range(30):
        started = time.perf_counter()
        codex_hook.handle_hook(
            {
                "hook_event_name": "PreToolUse",
                "session_id": f"session-{index}",
                "cwd": str(tmp_path),
                "tool_name": "apply_patch",
                "tool_input": {"command": "edit money"},
            },
            tmp_path,
        )
        timings.append((time.perf_counter() - started) * 1000)
    assert quantiles(timings, n=100)[94] < 300
