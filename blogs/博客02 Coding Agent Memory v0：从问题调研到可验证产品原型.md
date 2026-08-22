# Coding Agent Memory v0：从问题调研到可验证产品原型

> 这是一份项目阶段性 checkpoint，不是最终成果报告。它记录当前已经做出的产品和技术决定、已经实现的代码、尚未验证的假设，以及下一阶段的测试入口。

## 1. 我在解决什么问题

Coding Agent 能够读取当前仓库，但跨 session 之后，它通常无法可靠恢复上一次工作的状态：

- 哪些架构决策已经确定；
- 哪些方案只是临时尝试；
- 哪些方法已经失败；
- 当前任务进行到哪里；
- 哪些旧信息已经失效；
- 下一次 Agent 只应该看到哪些上下文。

因此，问题不是简单的“让 Agent 记住更多聊天记录”，而是：

> 如何维护一个不断变化、可验证、带证据、不会被旧状态污染的 Coding Agent 项目状态层。

研究和竞品观察显示，`CLAUDE.md`、`AGENTS.md`、handoff、ExecPlan、Memory Bank 等工作流已经能够缓解稳定规则和 session 交接问题，但动态 task state 的维护仍然脆弱。尤其是 stale memory：旧记忆可能比没有记忆更危险，因为 Agent 会把它当作当前事实继续行动。

## 2. 从研究项目转为产品项目

项目最初包含一个类似论文实验的 Decimal Transfer / Stage 0 harness，用来隔离跨 session memory 是否改善 Agent 行为。这个实验基础设施对于方法学有价值，但它不是产品本身。

现在项目采用两个明确层级：

```text
Coding Agent Memory v0       = 产品原型
Repo-evolution benchmark     = v0 产品的主要评估场景
旧 Stage 0 / Decimal 测试    = 已退役的早期实验路径
```

因此，后续不会再用 Decimal benchmark 代表产品进展。当前产品主线是：

```text
Hooks
→ Event Log
→ isolated Compiler
→ Memory Revision / Ref
→ Reconciler
→ Context Router
→ Context Capsule / Warning
→ Agent action
→ new evidence
```

## 3. v0 的产品边界

v0 是一个单用户、单仓库、local-first 的 Coding Agent Memory Core，并通过一个薄 Codex plugin 验证真实闭环。

### v0 支持

- repo-level memory；
- `Decision`、`Constraint`、`ProjectFact`、`Failure` 四类 durable memory；
- Event Log 和 SQLite projection；
- immutable revision、branch ref 和状态迁移；
- evidence、anchor、freshness 和 conflict；
- strict / hybrid promotion policy；
- FTS5 和直接 anchor 检索；
- Context Capsule 和动作前 warning；
- CLI、只读＋反馈 MCP 和 Codex hooks；
- repo-evolution benchmark。

### v0 不支持

- `Procedure` durable memory；
- 多用户、多仓库共享和云同步；
- 向量检索和语义重排；
- 完整代码依赖图；
- 自动代码回滚；
- 完整 transcript 保存；
- 把当前 TODO、progress 和 next action 混入 durable memory。

当前 progress 属于独立的 `Execution State` 平面，状态为：

```text
pending / active / blocked / completed / abandoned
```

## 4. 当前代码结构

### Core

```text
src/agent_memory/
├── models.py       数据结构、枚举和序列化
├── paths.py        repository identity 和本地数据目录
├── redaction.py    证据脱敏和长度限制
├── event_log.py    spool 与追加式 events.jsonl
├── store.py        SQLite projection、FTS5、refs、jobs、delivery
├── core.py         创建 revision、移动 ref、状态转换
├── policy.py       candidate promotion 判断
├── reconciler.py   代码/证据变化后的状态协调
├── router.py       作用域、状态、anchor、FTS5 和预算路由
├── compiler.py     隔离 Codex compiler 和输出校验
├── worker.py       lease 保护的 one-shot compiler worker
├── mcp_server.py   Agent-facing read-only + feedback MCP
├── cli.py          人工查看、编辑、失效、恢复和导出
└── inspector.py    SQLite 的只读 Markdown 投影
```

### Adapter 与评估

```text
plugins/coding-agent-memory/  Codex hooks、MCP 配置和安装脚本
benchmarks/repo_evolution/   v0 的 repo-evolution 场景、gold 和条件
tests/                        deterministic unit/integration tests
docs/                         PRD、架构、决策、竞品和评估协议
```

## 5. 记忆的具体文件形式

记忆不是提交到代码仓库里的 Markdown 文件。Windows 默认保存在：

```text
%LOCALAPPDATA%\CodingAgentMemory\
└── repositories\
    └── repo-<repository-id>\
        ├── events.jsonl
        ├── projection.sqlite3
        └── spool\
```

`events.jsonl` 是可重放的权威日志。SQLite 是可从 Event Log 重建的查询投影，Markdown Inspector 也只是只读视图。

一个 Memory Revision 的核心内容是：

```json
{
  "memory_id": "mem-...",
  "revision": 2,
  "repository_id": "repo-...",
  "branch": "main",
  "kind": "Decision",
  "claim": "Use FastAPI for the async service",
  "rationale": "The service requires async request handling",
  "status": "active",
  "authority": "explicit_user",
  "evidence": [
    {
      "evidence_id": "ev-...",
      "authority": "explicit_user",
      "source_type": "session",
      "source_ref": "session-123",
      "excerpt": "Use FastAPI for the async service",
      "content_hash": "..."
    }
  ],
  "anchors": [
    {
      "anchor_type": "file",
      "target": "src/api.py",
      "content_hash": "..."
    }
  ],
  "supersedes_revision": 1,
  "metadata": {}
}
```

系统区分：

```text
MemoryRevision = 不可变的历史版本
MemoryRef      = 某个 branch 当前指向的版本
MemoryStatus   = 该版本当前是否可以被使用
```

编辑并不是覆盖旧 JSON，而是创建同一个 `memory_id` 的新 revision。

## 6. 一条记忆如何流转

```text
Hook event
    ↓
atomic spool
    ↓
events.jsonl
    ↓
CompilerJob
    ↓
MemoryCandidate
    ↓
promotion policy
    ↓
MemoryRevision + MemoryRef
    ↓
Reconciler
    ↓
Router
    ↓
Context Capsule / PreToolUse warning
    ↓
Agent action
    ↓
new evidence
```

Compiler 只能产生候选记忆，不能直接决定它是 active。隔离的 Codex compiler 只能读取有界的 `EvidenceBundle + SessionStateSnapshot`，并且输出必须通过 job cursor、HEAD、evidence ID、capture coverage 和 schema 校验。

## 7. 代码如何决定一条记忆是否激活

默认策略是 `strict`。

- `Decision` / `Constraint`：需要用户明确证据或项目规范证据；
- `ProjectFact`：可以由直接仓库或配置证据激活；
- `Failure`：需要直接测试结果，并保留环境、attempt 和 outcome；
- capture 有 gap：只能是 `proposed`；
- 有 counterevidence：不能自动激活；
- 临时、尝试、实验、maybe 等措辞不能自动变成规范性记忆。

因此当前决策链是：

```text
LLM extraction
→ deterministic validation
→ authority rules
→ promotion status
→ immutable revision
```

`hybrid` 允许独立 corroborating evidence 支持的候选自动 active，但在安全 guardrail 和 benchmark 证明之前不会替代 strict 默认策略。

## 8. 代码变化后如何处理旧记忆

Reconciler 不会简单地把所有旧记忆删除：

- 未提交变化触及 anchor：标记 `needs_revalidation`；
- Decision / Constraint 对应代码变化：标记 `conflicted`，因为代码不能自动替代规范性决策；
- ProjectFact 有新的直接仓库证据：创建新 revision；
- 证据不足：保持不确定状态；
- 有证据的 memory-to-memory 边可以传播 dirty；
- 没有证据的推断边不会参与 dirty propagation。

当前 v0 的 rollback 只生成影响报告，不修改代码。

## 9. Agent 什么时候能看到记忆

Router 的顺序是：

```text
repository / branch scope
→ status / validity
→ supersession
→ freshness
→ anchor / trigger
→ SQLite FTS5
→ bounded delivery
```

正常的 active memory 可以作为事实注入。`conflicted`、`unprovable` 和 `needs_revalidation` 只能以 warning 和 evidence pointer 形式出现，不能被包装成确定事实。

交付预算目前是：

```text
SessionStart       约 180 tokens
UserPromptSubmit   最多约 800 tokens
PreToolUse         最多约 200 tokens
```

PreToolUse 热路径不调用 LLM、不执行 Git diff、不扫描仓库。失败时 fail-open，并记录 `GateUnavailable`。

## 10. 竞品调研得出的项目定位

当前调研对象分三层：

1. 直接产品：Claude-Mem、Basic Memory、Cline Memory Bank；
2. 宿主能力和工作流：Claude Code Memory、Cursor Rules、`AGENTS.md`、ExecPlan；
3. 机制和研究参照：Graphiti、Mem0、Letta、MAGE、MemoRepair、STALE、remem 等。

已有系统已经较好覆盖 capture、普通 retrieval、稳定规则和 handoff。当前项目的主要技术假设逐渐收窄为：

> Repository changes should induce explicit validity transitions over project memory, and propagate dirtiness only through evidence-backed dependencies.

中文就是：代码库变化不应该只让记忆变旧，而应该触发可解释的有效性状态迁移；存在依赖溯源时，只沿真实依赖传播 dirty 状态。

竞品的系统级体验仍需要在统一测试仓库上验证，不能仅凭功能列表声称某个机制优于另一个机制。

## 11. 当前已经完成与尚未证明的内容

### 已经实现

- Event Log、atomic spool 和 SQLite projection；
- Memory Revision / Ref 和状态机；
- strict / hybrid policy；
- Reconciler、直接 dependency propagation 和 Router；
- Codex isolated compiler、one-shot worker 和 lease；
- CLI、MCP、Markdown Inspector 和 Codex plugin；
- repo-evolution benchmark 的 scenario、gold、conditions 和 runner；
- Linux CI 与确定性测试。

### 尚未证明

- capture coverage 在真实 Codex workflow 中是否足够；
- strict 或 hybrid 是否能改善真实任务结果；
- false activation、false supersession 和 stale injection 是否为零；
- Agent 是否会采纳 warning；
- memory 是否减少重复探索；
- Event Log、SQLite、FTS5 和 compiler 的实际空间成本；
- Claude-Mem、Basic Memory 等竞品在同一场景下的恢复和冲突处理表现。

“已经实现”不等于“已经验证有效”。这是开始 benchmark 前必须保持的边界。

## 12. 下一步执行顺序

```text
完成本 checkpoint
    ↓
工程回归测试与资源 profiling
    ↓
repo-evolution C0–C5 pilot
    ↓
冻结任务、模型、工具、prompt 和指标
    ↓
confirmation runs
    ↓
Codex 长期 dogfooding
    ↓
Claude-Mem / Basic Memory 统一体验
    ↓
根据失败样例决定 v0.1 方向
```

这篇文章的作用是保持项目认知同步。后续 benchmark 结果应该追加到新的实验记录中，不要回写成预先知道的结论；如果结果不支持产品假设，应报告为 inconclusive 或 negative，而不是事后修改主要指标。

## 13. 当前阅读入口

- 产品问题和调研：[docs/Coding Agent Memory — Problem Discovery & Validation.md](../docs/Coding%20Agent%20Memory%20%E2%80%94%20Problem%20Discovery%20%26%20Validation.md)
- 产品范围：[docs/prd.md](../docs/prd.md)
- 技术架构：[docs/architecture.md](../docs/architecture.md)
- 决策记录：[docs/decisions.md](../docs/decisions.md)
- 竞品体验协议：[docs/competitor-trial-protocol.md](../docs/competitor-trial-protocol.md)
- v0 评估注册：[docs/evaluation-plan.md](../docs/evaluation-plan.md)
- 主要 benchmark：[benchmarks/repo_evolution/README.md](../benchmarks/repo_evolution/README.md)
