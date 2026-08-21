# Competitive Analysis Framework

这份文档先冻结调查框架，不把未经验证的产品功能写成事实。正式调研时，
每个方案都用同一张表记录，并保存来源、版本和体验日期。

## 1. Comparison Dimensions

| Dimension | Questions |
| --- | --- |
| Capture | 什么时候写？自动、手动还是用户确认？ |
| Substance | 记住什么？事实、偏好、决策、轨迹还是技能？ |
| Storage | repo-local、user-local、cloud 还是向量数据库？ |
| Retrieval | 什么时候检索？关键词、标签、semantic 还是 Agent 主动调用？ |
| Control | 用户能否查看、修改、删除、纠错和 supersede？ |
| Provenance | 是否能看到来源 session、时间和证据？ |
| Failure handling | 如何处理 stale、conflict、irrelevant memory？ |
| Integration | 依赖哪个 Agent、MCP、CLI 或文件约定？ |
| Cost | token、latency、网络和维护成本是什么？ |

## 2. Initial Alternatives to Investigate

- README / AGENTS.md / CLAUDE.md 等项目级文档；
- Claude Code、Codex、Cursor 等 Coding Agent 的 rules/memory 机制；
- Mem0；
- Letta / MemGPT；
- MemoraX 及其他 coding memory projects；
- 直接使用 DSH session、skills 或 plugin 的方案。
- Claude-Mem：hooks、worker、SQLite 和 progressive disclosure；
- Basic Memory：MCP/Skills、file-first 与人工可读性。

首轮必须使用 `competitor-trial-protocol.md` 和同一个 repo-evolution 场景，
并在独立仓库与隔离配置中运行。结论只作为 system-level 产品对照。

## 3. Research Log Template

| Product | Version/date | Capture | Store | Retrieve | Control | Failure handling | Evidence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| TBD | TBD | TBD | TBD | TBD | TBD | TBD | URL / screenshot / test |

## 4. Product Opportunity Hypothesis

本项目暂时不声称“市场上没有 memory”。待调查后重点验证：

> 现有 Coding Agent 能保存规则或文件，但用户仍缺少一个 repo-scoped、可解释、
> 可纠错、带 provenance 的 memory lifecycle。

如果调研证明这一假设不成立，应修改 PRD，而不是为了保留项目结论而选择性
忽略反例。
