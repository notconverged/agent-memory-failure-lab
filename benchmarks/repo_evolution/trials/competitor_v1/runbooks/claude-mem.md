# Claude-Mem

1. 记录 Node/npm/Bun/uv、Codex CLI 和 Claude-Mem 版本。
2. 设置 `CLAUDE_MEM_DATA_DIR=.local-lab/competitors/claude-mem/data/<run-id>`。
3. 用官方安装器选择 Codex CLI；启动 worker 并验证 health。
4. 逐阶段检查 SQLite、viewer、transcript watch 和注入内容。
5. 安装修复优先使用 `npx claude-mem repair`，不要手工删除用户目录。
