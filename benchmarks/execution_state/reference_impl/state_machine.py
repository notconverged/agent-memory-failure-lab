from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from typing import Any

from benchmarks.execution_state.reference_impl.models import (
    ExecutionCursor,
    ExecutionNode,
    ExecutionState,
)
from benchmarks.execution_state.reference_impl.validator import validate_boundary


def _normalize(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n")


def raw_content_hash(action: str, observation: str) -> str:
    payload = json.dumps(
        {"action": _normalize(action), "observation": _normalize(observation)},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def summary_content_hash(summary: str) -> str:
    return hashlib.sha256(_normalize(summary).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Variant:
    name: str
    compress: bool
    maintain: bool
    revise: bool
    flat: bool


class ReferenceStateMachine:
    RAW_ROOT = "raw-root"
    SUMMARY_ROOT = "summary-root"

    def __init__(self, variant: Variant) -> None:
        self.variant = variant
        self.nodes: dict[str, ExecutionNode] = {
            self.RAW_ROOT: ExecutionNode(
                self.RAW_ROOT,
                "_raw_root",
                "raw",
                None,
                0,
                None,
                content_hash="0" * 64,
            ),
            self.SUMMARY_ROOT: ExecutionNode(
                self.SUMMARY_ROOT,
                "_summary_root",
                "summary",
                None,
                0,
                None,
                content_hash="0" * 64,
            ),
        }
        self.children: dict[str, list[str]] = {
            self.RAW_ROOT: [],
            self.SUMMARY_ROOT: [],
        }
        self.step_key_to_node: dict[str, str] = {}
        self.raw_current = self.RAW_ROOT
        self.summary_current = self.SUMMARY_ROOT
        self.revision_generation = 0
        self.trace_index = 0
        self.raw_buffer: list[str] = []
        self.flat_history: list[str] = []
        self.last_summary_id: str | None = None
        self.last_maintain_failed = False
        self.operations: list[dict[str, Any]] = []
        self.maintain_decisions: dict[str, str] = {}
        self.snapshots: dict[int, ExecutionState] = {0: self._state(0)}

    def apply(self, event: dict[str, Any]) -> None:
        step_index = int(event["step_index"])
        if step_index in self.snapshots or step_index != max(self.snapshots) + 1:
            raise ValueError(
                "reference timeline step_index must be contiguous and unique"
            )
        operation = event["operation"]
        handler = getattr(self, f"_{operation}", None)
        if handler is None:
            raise ValueError(f"unsupported reference operation: {operation}")
        handler(event)
        self.snapshots[step_index] = copy.deepcopy(self._state(step_index))

    def materialize_state(self) -> ExecutionState:
        return copy.deepcopy(self.snapshots[max(self.snapshots)])

    def materialize_state_at(self, step_index: int) -> ExecutionState:
        if step_index not in self.snapshots:
            raise ValueError(f"unknown execution-state step_index: {step_index}")
        return copy.deepcopy(self.snapshots[step_index])

    def _record(self, event: dict[str, Any], status: str, **extra: Any) -> None:
        self.operations.append(
            {
                "step_index": event["step_index"],
                "operation": event["operation"],
                "status": status,
                "revision_generation": self.revision_generation,
                **extra,
            }
        )

    def _grow(self, event: dict[str, Any]) -> None:
        action = _normalize(str(event["action"]))
        observation = _normalize(str(event["observation"]))
        digest = raw_content_hash(action, observation)
        self.trace_index += 1
        reused: str | None = None
        if not self.variant.flat:
            matches = [
                child
                for child in self.children.get(self.raw_current, [])
                if self.nodes[child].layer == "raw"
                and self.nodes[child].content_hash == digest
            ]
            if len(matches) > 1:
                raise ValueError("duplicate equal raw children violate tree invariants")
            reused = matches[0] if matches else None
        if reused:
            node_id = reused
            self.raw_current = reused
            self.step_key_to_node[event["step_key"]] = reused
            self._record(
                event,
                "reused",
                node_id=reused,
                existing_step_key=self.nodes[reused].step_key,
            )
        else:
            node_id = f"raw-{len([n for n in self.nodes.values() if n.layer == 'raw'])}"
            parent = self.raw_current
            node = ExecutionNode(
                node_id=node_id,
                step_key=str(event["step_key"]),
                layer="raw",
                parent_id=parent,
                created_step_index=int(event["step_index"]),
                trace_index=self.trace_index,
                action=action,
                observation=observation,
                revision_generation=self.revision_generation,
                content_hash=digest,
            )
            self.nodes[node_id] = node
            self.children.setdefault(parent, []).append(node_id)
            self.children[node_id] = []
            self.raw_current = node_id
            self.step_key_to_node[node.step_key] = node_id
            self._record(event, "created", node_id=node_id)
        self.raw_buffer.append(node_id)
        self.flat_history.append(node_id)

    def _boundary(self, event: dict[str, Any]) -> None:
        self._record(event, "observed", boundary_id=event["boundary_id"])

    def _compress(self, event: dict[str, Any]) -> None:
        if not self.variant.compress or self.variant.flat:
            self._record(event, "skipped", reason="compress_disabled")
            return
        summary = _normalize(str(event["summary"]))
        node_id = (
            f"summary-{len([n for n in self.nodes.values() if n.layer == 'summary'])}"
        )
        node = ExecutionNode(
            node_id=node_id,
            step_key=str(event["step_key"]),
            layer="summary",
            parent_id=self.summary_current,
            created_step_index=int(event["step_index"]),
            trace_index=None,
            summary=summary,
            cover_node_ids=list(self.raw_buffer),
            validation_status="pending",
            revision_generation=self.revision_generation,
            content_hash=summary_content_hash(summary),
        )
        self.nodes[node_id] = node
        self.children.setdefault(self.summary_current, []).append(node_id)
        self.children[node_id] = []
        self.summary_current = node_id
        self.last_summary_id = node_id
        self.step_key_to_node[node.step_key] = node_id
        self.raw_buffer.clear()
        self._record(event, "created", node_id=node_id)

    def _maintain(self, event: dict[str, Any]) -> None:
        if not self.variant.maintain or self.variant.flat:
            self.last_maintain_failed = False
            self._record(event, "skipped", reason="maintain_disabled")
            return
        if self.variant.compress:
            if self.last_summary_id is None:
                raise ValueError("Maintain requires a preceding summary")
            content = self.nodes[self.last_summary_id].summary or ""
        else:
            content = "\n".join(
                f"{self.nodes[node_id].action}\n{self.nodes[node_id].observation}"
                for node_id in self.raw_buffer
            )
        result = validate_boundary(content, event["validation"])
        decision = "pass" if result.passed else "fail"
        self.maintain_decisions[str(event["step_index"])] = decision
        self.last_maintain_failed = not result.passed
        if self.variant.compress and self.last_summary_id:
            node = self.nodes[self.last_summary_id]
            node.validation_status = "passed" if result.passed else "failed"
            node.diagnostic_note = result.feedback
        if result.passed and not self.variant.compress:
            self.raw_buffer.clear()
        self._record(event, decision, feedback=result.feedback)

    def _revise(self, event: dict[str, Any]) -> None:
        if (
            not self.variant.revise
            or self.variant.flat
            or not self.last_maintain_failed
        ):
            reason = (
                "revise_disabled" if not self.variant.revise else "no_failure_signal"
            )
            self._record(event, "skipped", reason=reason)
            return
        raw_id = self.step_key_to_node[str(event["target_raw_step_key"])]
        self.raw_current = raw_id
        if self.variant.compress:
            summary_key = event.get("target_summary_step_key")
            self.summary_current = (
                self.step_key_to_node[str(summary_key)]
                if summary_key
                else self.SUMMARY_ROOT
            )
            self.last_summary_id = (
                None
                if self.summary_current == self.SUMMARY_ROOT
                else self.summary_current
            )
        else:
            self.summary_current = self.SUMMARY_ROOT
            self.last_summary_id = None
        self.revision_generation += 1
        self.raw_buffer.clear()
        self.last_maintain_failed = False
        self._record(event, "revised", target_raw_node_id=raw_id)

    def _path(self, current: str, root: str) -> list[str]:
        values: list[str] = []
        cursor = current
        while cursor != root:
            values.append(cursor)
            parent = self.nodes[cursor].parent_id
            if parent is None:
                raise ValueError("execution tree is disconnected")
            cursor = parent
        values.reverse()
        return values

    def _state(self, step_index: int) -> ExecutionState:
        raw_path_ids = self._path(self.raw_current, self.RAW_ROOT)
        summary_path_ids = self._path(self.summary_current, self.SUMMARY_ROOT)
        raw_keys = [self.nodes[node_id].step_key for node_id in raw_path_ids]
        summary_keys = [self.nodes[node_id].step_key for node_id in summary_path_ids]
        active = set(raw_path_ids + summary_path_ids)
        hints: list[str] = []
        for parent in [
            self.RAW_ROOT,
            *raw_path_ids,
            self.SUMMARY_ROOT,
            *summary_path_ids,
        ]:
            for child in self.children.get(parent, []):
                if child not in active:
                    note = self.nodes[child].diagnostic_note
                    hints.append(note or self.nodes[child].step_key)
        visible_nodes = [
            node.to_dict()
            for node_id, node in self.nodes.items()
            if node_id not in {self.RAW_ROOT, self.SUMMARY_ROOT}
        ]
        recent = (
            raw_keys
            if not self.variant.compress and not self.variant.flat
            else [self.nodes[node_id].step_key for node_id in self.raw_buffer]
        )
        effective = (
            [self.nodes[node_id].step_key for node_id in self.flat_history]
            if self.variant.flat
            else raw_keys
        )
        return ExecutionState(
            as_of_step_index=step_index,
            nodes=visible_nodes,
            active_raw_path=raw_keys,
            active_summary_path=summary_keys,
            compressed_state=[
                self.nodes[node_id].summary or "" for node_id in summary_path_ids
            ],
            recent_raw=recent,
            hints=hints,
            effective_active_raw_sequence=effective,
            cursor=ExecutionCursor(
                None if self.raw_current == self.RAW_ROOT else self.raw_current,
                None
                if self.summary_current == self.SUMMARY_ROOT
                else self.summary_current,
                step_index,
                self.revision_generation,
            ).to_dict(),
        )
