from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "coding-agent-memory"


def test_plugin_manifest_and_default_hook_discovery_are_valid():
    manifest = json.loads(
        (PLUGIN / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    assert manifest["name"] == "coding-agent-memory"
    assert manifest["version"] == "0.1.0"
    assert manifest["mcpServers"] == "./.mcp.json"
    assert "hooks" not in manifest
    hooks = json.loads((PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    assert {"SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse"} <= set(
        hooks["hooks"]
    )


def test_plugin_mcp_surface_points_to_host_independent_core():
    config = json.loads((PLUGIN / ".mcp.json").read_text(encoding="utf-8"))
    server = config["mcpServers"]["coding-agent-memory"]
    assert server["command"] == "python"
    assert server["args"] == ["-m", "agent_memory.mcp_server"]
