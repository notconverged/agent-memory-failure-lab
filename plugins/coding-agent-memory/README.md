# Coding Agent Memory Codex adapter

This plugin is intentionally thin. The Python package owns storage, reconciliation,
routing, and audit behavior; the plugin only wires Codex hooks and the MCP stdio
server to that host-independent Core.

Development install from the repository root:

```powershell
python -m pip install -e .
codex plugin install --dev ./plugins/coding-agent-memory
agent-memory init
agent-memory doctor
```

After changing an already installed plugin, use the plugin-creator cachebuster and
reinstall flow documented in the project implementation guide.
