from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ExecutionNode:
    node_id: str
    step_key: str
    layer: str
    parent_id: str | None
    created_step_index: int
    trace_index: int | None
    action: str | None = None
    observation: str | None = None
    summary: str | None = None
    cover_node_ids: list[str] = field(default_factory=list)
    validation_status: str = "not_applicable"
    diagnostic_note: str = ""
    revision_generation: int = 0
    content_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ExecutionCursor:
    bottom_node_id: str | None
    top_node_id: str | None
    last_step_index: int
    revision_generation: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ExecutionState:
    as_of_step_index: int
    nodes: list[dict[str, Any]]
    active_raw_path: list[str]
    active_summary_path: list[str]
    compressed_state: list[str]
    recent_raw: list[str]
    hints: list[str]
    effective_active_raw_sequence: list[str]
    cursor: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
