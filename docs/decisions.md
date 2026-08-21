# Decision Log

## 2026-08-19 — Shift from research-first to product-first

### Decision

项目主线从“研究 Agent memory 机制”调整为“构建 Coding Agent Memory 产品”。

### What stays

- Stage 0 isolation harness；
- Benchmark Oracle Fact；
- fixed DSH baseline；
- host-managed memory injection；
- verifier、trace、summary 和五层隔离边界。

### What changes

- README 采用 product-first framing；
- Stage 0 改称 baseline evaluation foundation；
- 新增 Product Brief、PRD、Technical Architecture 和竞争调查框架；
- 后续优先做 Technical Spike、MVP 和 dogfooding，而不是直接推进 E2–E5；
- research questions 改写为 product risks、technical uncertainties 和 evaluation hypotheses。

### Rationale

已有 Stage 0 是产品价值证明所需要的 evidence layer，不应删除；但如果继续把
它作为项目首页的主要身份，项目会过度 research-oriented，无法体现真实用户、
产品边界、可用性和迭代闭环。

### Consequence

当前仓库保留旧的 Stage 0 路径以保证运行入口稳定。产品代码逐步进入 `src/`，
评测代码未来再整理到 `eval/`；目录迁移必须在有测试和兼容入口后进行。

## 2026-08-21 — Freeze v0 memory boundary and uncertainty model

### Decision

Durable memory contains only Decision, Constraint, ProjectFact, and Failure.
Procedure is inactive in v0. TODO, plan, and current progress move to a separate
Execution State plane.

The Event Log is authoritative; SQLite and Markdown are rebuildable projections.
Codex is a thin first adapter. Promotion defaults to strict, and all capture gaps,
freshness uncertainty, conflicts, and unprovable claims must remain explicit.

### Rationale

The main product risk is false certainty: incomplete capture, temporary attempts
compiled as decisions, incorrect supersession, ignored warnings, and compiler
context pollution. Evidence, authority, immutable revisions, isolation, and
audit make these risks observable and testable.

### Consequence

- no Procedure activation, vector search, cloud sync, or automatic rollback in v0;
- uncommitted code cannot authorize durable truth;
- code cannot supersede normative memory;
- MCP is read-only plus feedback; human CLI owns adjudication;
- engineering acceptance is reported separately from benchmark benefit.
