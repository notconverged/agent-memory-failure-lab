from __future__ import annotations

import json
import sys
from collections.abc import Callable
from typing import Any

from agent_memory.core import MemoryCore
from agent_memory.paths import default_data_root, discover_repository
from agent_memory.router import ContextRouter

TOOLS = [
    {
        "name": "memory_status",
        "description": "Return local memory status counts for this repository branch.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "memory_context",
        "description": "Route bounded, authorized memory for a task context.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "session_id": {"type": "string"},
                "token_budget": {"type": "integer", "minimum": 1, "maximum": 800},
            },
            "required": ["query", "session_id"],
        },
    },
    {
        "name": "memory_search",
        "description": "Search current memory refs using SQLite FTS5.",
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
    {
        "name": "memory_get",
        "description": "Get one current memory revision by ID.",
        "inputSchema": {
            "type": "object",
            "properties": {"memory_id": {"type": "string"}},
            "required": ["memory_id"],
        },
    },
    {
        "name": "memory_history",
        "description": "Get immutable revision history for one memory ID.",
        "inputSchema": {
            "type": "object",
            "properties": {"memory_id": {"type": "string"}},
            "required": ["memory_id"],
        },
    },
    {
        "name": "memory_feedback",
        "description": "Record feedback evidence without changing active refs.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "verdict": {"type": "string"},
                "comment": {"type": "string"},
                "memory_id": {"type": "string"},
            },
            "required": ["verdict"],
        },
    },
]


class MCPServer:
    def __init__(self, core_factory: Callable[[], MemoryCore]) -> None:
        self.core_factory = core_factory

    def handle(self, request: dict[str, Any]) -> dict[str, Any] | None:
        if "id" not in request:
            return None
        request_id = request["id"]
        method = request.get("method")
        try:
            if method == "initialize":
                requested = request.get("params", {}).get("protocolVersion")
                result = {
                    "protocolVersion": requested or "2025-06-18",
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "coding-agent-memory", "version": "0.1.0"},
                }
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": TOOLS}
            elif method == "tools/call":
                result = self._call_tool(request.get("params", {}))
            else:
                return self._error(request_id, -32601, f"Unknown method: {method}")
            return {"jsonrpc": "2.0", "id": request_id, "result": result}
        except (KeyError, TypeError, ValueError) as error:
            return self._error(request_id, -32602, str(error))
        except Exception as error:
            return self._error(request_id, -32603, str(error))

    def _call_tool(self, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name")
        arguments = params.get("arguments") or {}
        core = self.core_factory()
        try:
            if name == "memory_status":
                value = core.store.statistics(core.repository_id, core.branch)
            elif name == "memory_context":
                value = (
                    ContextRouter(core)
                    .route(
                        arguments["query"],
                        arguments["session_id"],
                        token_budget=min(int(arguments.get("token_budget", 800)), 800),
                    )
                    .text
                )
            elif name == "memory_search":
                value = core.store.search_current(
                    core.repository_id,
                    core.branch,
                    arguments["query"],
                    ["active", "conflicted", "unprovable", "needs_revalidation"],
                )
            elif name == "memory_get":
                value = core.store.get_current(
                    core.repository_id,
                    core.branch,
                    arguments["memory_id"],
                    core.base_branch,
                )
            elif name == "memory_history":
                value = core.store.history(arguments["memory_id"])
            elif name == "memory_feedback":
                core.record_feedback(
                    arguments["verdict"],
                    arguments.get("comment", ""),
                    arguments.get("memory_id"),
                )
                value = {"recorded": True, "active_ref_changed": False}
            else:
                raise ValueError(f"Unknown tool: {name}")
            return {
                "content": [
                    {
                        "type": "text",
                        "text": value
                        if isinstance(value, str)
                        else json.dumps(value, ensure_ascii=False, default=str),
                    }
                ]
            }
        finally:
            core.close()

    @staticmethod
    def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": code, "message": message[:2_000]},
        }


def default_core() -> MemoryCore:
    context = discover_repository()
    return MemoryCore(
        default_data_root(),
        context.repository_id,
        context.branch,
        context.base_branch,
    )


def main() -> int:
    server = MCPServer(default_core)
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            request = json.loads(line)
            response = server.handle(request)
        except json.JSONDecodeError as error:
            response = MCPServer._error(None, -32700, str(error))
        if response is not None:
            print(json.dumps(response, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
