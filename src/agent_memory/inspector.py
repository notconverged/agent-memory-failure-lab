from __future__ import annotations

import os
from pathlib import Path

from agent_memory.core import MemoryCore


def render_markdown(core: MemoryCore) -> str:
    memories = core.store.list_current(
        core.repository_id, core.branch, base_branch=core.base_branch
    )
    lines = [
        "# Coding Agent Memory Inspector",
        "",
        f"Repository: `{core.repository_id}`  ",
        f"Branch: `{core.branch}`",
        "",
        (
            "> Read-only projection. Use `agent-memory edit/invalidate/restore` "
            "to change data."
        ),
        "",
    ]
    for memory in memories:
        lines.extend(
            [
                f"## {memory['kind']}: {memory['claim']}",
                "",
                f"- Ref: `{memory['memory_id']}@{memory['revision']}`",
                f"- Status: `{memory['status']}`",
                f"- Authority: `{memory['authority']}`",
                f"- Created: `{memory['created_at']}`",
                f"- Rationale: {memory['rationale']}",
                "- Evidence:",
            ]
        )
        for item in memory["evidence"]:
            lines.append(
                f"  - `{item['evidence_id']}` {item['source_type']}: "
                f"`{item['source_ref']}`"
            )
        lines.append("")
    if not memories:
        lines.append("No memory objects yet.\n")
    return "\n".join(lines)


def write_markdown(core: MemoryCore, target: Path) -> Path:
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(render_markdown(core), encoding="utf-8")
    os.replace(temporary, target)
    return target
