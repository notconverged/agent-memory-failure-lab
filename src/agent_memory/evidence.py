from __future__ import annotations

import json
import re
from pathlib import PurePosixPath
from typing import Any

from agent_memory.models import EvidenceAuthority

TEST_COMMAND = re.compile(
    r"\b(python\s+-m\s+pytest|cargo\s+test|npm\s+test|pytest|unittest|tox|nox)\b",
    re.IGNORECASE,
)
PROJECT_NORMS = {
    "agents.md",
    "project_policy.md",
    "contributing.md",
    "pyproject.toml",
}


def classify_codex_event(
    event_type: str, payload: dict[str, Any]
) -> EvidenceAuthority:
    """Conservatively classify captured hook evidence.

    Authority comes from the observed source, never from an LLM-generated claim.
    Unknown tool payloads remain TOOL_RESULT.
    """

    if event_type == "UserPromptSubmit":
        return EvidenceAuthority.EXPLICIT_USER
    if event_type != "PostToolUse":
        return EvidenceAuthority.TOOL_RESULT

    tool_name = str(payload.get("tool_name", "")).casefold()
    tool_input = payload.get("tool_input", {})
    tool_response = payload.get("tool_response", {})
    serialized = json.dumps(
        {"input": tool_input, "response": tool_response},
        ensure_ascii=False,
        default=str,
    )
    normalized = serialized.replace("\\", "/").casefold()
    paths = {
        PurePosixPath(token.strip("'\" ,:[]{}")).name
        for token in normalized.split()
        if "/" in token or "." in token
    }
    if paths & PROJECT_NORMS:
        return EvidenceAuthority.PROJECT_NORM
    if TEST_COMMAND.search(serialized):
        return EvidenceAuthority.DIRECT_TEST
    if any(
        marker in tool_name
        for marker in ("apply_patch", "read", "write", "edit", "git", "exec")
    ):
        return EvidenceAuthority.DIRECT_REPO
    return EvidenceAuthority.TOOL_RESULT
