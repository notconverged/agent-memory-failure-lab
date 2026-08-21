from __future__ import annotations

import json
from importlib.metadata import version
from pathlib import Path

from agent_memory import __version__
from agent_memory.mcp_server import MCPServer

ROOT = Path(__file__).resolve().parents[1]


def test_product_components_share_one_version_contract():
    plugin = json.loads(
        (
            ROOT
            / "plugins"
            / "coding-agent-memory"
            / ".codex-plugin"
            / "plugin.json"
        ).read_text(encoding="utf-8")
    )
    response = MCPServer(lambda: None).handle(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-06-18"},
        }
    )

    assert response is not None
    assert version("agent-memory-failure-lab") == __version__
    assert plugin["version"] == __version__
    assert response["result"]["serverInfo"]["version"] == __version__
