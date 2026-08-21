from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from agent_memory.core import MemoryCore
from agent_memory.models import MemoryStatus

AUTHORIZED_STATUSES = {MemoryStatus.ACTIVE.value}
WARNING_STATUSES = {
    MemoryStatus.CONFLICTED.value,
    MemoryStatus.UNPROVABLE.value,
    MemoryStatus.NEEDS_REVALIDATION.value,
}


@dataclass(frozen=True)
class RoutedContext:
    text: str
    revisions: tuple[tuple[str, int], ...]
    token_estimate: int
    truncated: bool


class ContextRouter:
    def __init__(self, core: MemoryCore) -> None:
        self.core = core

    def route(
        self,
        query: str,
        session_id: str,
        delivery_type: str = "context_capsule",
        token_budget: int = 800,
        anchors: tuple[str, ...] = (),
        delta_only: bool = True,
    ) -> RoutedContext:
        statuses = AUTHORIZED_STATUSES | WARNING_STATUSES
        current = self.core.store.list_current(
            self.core.repository_id,
            self.core.branch,
            statuses=statuses,
            base_branch=self.core.base_branch,
        )
        by_id = {item["memory_id"]: item for item in current}

        selected: list[dict] = []
        anchor_set = set(anchors)
        for memory in current:
            if any(item["target"] in anchor_set for item in memory["anchors"]):
                selected.append(memory)

        for branch in {self.core.branch, self.core.base_branch}:
            for memory in self.core.store.search_current(
                self.core.repository_id, branch, query, statuses, limit=30
            ):
                canonical = by_id.get(memory["memory_id"], memory)
                if canonical not in selected:
                    selected.append(canonical)

        if not query.strip() and not selected:
            selected = current
        selected.sort(
            key=lambda item: self._score(item, query, anchor_set), reverse=True
        )

        if delta_only:
            delivered = self.core.store.delivered_revisions(
                self.core.repository_id, self.core.branch, session_id
            )
            selected = [
                item
                for item in selected
                if (item["memory_id"], item["revision"]) not in delivered
            ]

        lines = ["[Coding Agent Memory — scoped, evidence-backed]"]
        included: list[tuple[str, int]] = []
        truncated = False
        for item in selected:
            line = self._format(item)
            if self._tokens("\n".join([*lines, line])) > token_budget:
                truncated = True
                continue
            lines.append(line)
            included.append((item["memory_id"], item["revision"]))

        if len(lines) == 1:
            lines.append("No new authorized memory matched this context.")
        text = "\n".join(lines)
        tokens = self._tokens(text)
        self.core.record_delivery(
            {
                "session_id": session_id,
                "delivery_type": delivery_type,
                "query": query[:2_000],
                "revisions": included,
                "payload_hash": hashlib.sha256(text.encode()).hexdigest(),
                "token_estimate": tokens,
            }
        )
        return RoutedContext(text, tuple(included), tokens, truncated)

    def gate(
        self,
        tool_name: str,
        tool_input: str,
        session_id: str,
        token_budget: int = 200,
    ) -> RoutedContext:
        # This path deliberately performs no LLM call, Git operation, or repo scan.
        return self.route(
            f"{tool_name} {tool_input[:1_000]}",
            session_id,
            delivery_type="pre_tool_warning",
            token_budget=token_budget,
            delta_only=False,
        )

    @staticmethod
    def _format(memory: dict) -> str:
        pointer = f"{memory['memory_id']}@{memory['revision']}"
        if memory["status"] in WARNING_STATUSES:
            return (
                f"- WARNING [{memory['status']}] {memory['claim']} "
                f"(inspect evidence: {pointer})"
            )
        return f"- [{memory['kind']}] {memory['claim']} ({pointer})"

    @staticmethod
    def _score(memory: dict, query: str, anchors: set[str]) -> tuple[int, str]:
        anchor_score = sum(
            10 for item in memory["anchors"] if item["target"] in anchors
        )
        terms = set(re.findall(r"[\w./-]+", query.casefold()))
        text = f"{memory['claim']} {memory['rationale']}".casefold()
        lexical = sum(1 for term in terms if term in text)
        status = 2 if memory["status"] == MemoryStatus.ACTIVE.value else 1
        return anchor_score + lexical + status, memory["created_at"]

    @staticmethod
    def _tokens(value: str) -> int:
        return max(1, (len(value) + 3) // 4)
