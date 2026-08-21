# Coding Agent Memory

一个面向 Coding Agent 的 local-first 持久记忆层。它不保存全部聊天历史，
而是在重新进入 repository 时恢复少量会改变后续工作的项目状态：
Decision、Constraint、ProjectFact 和带条件的 Failure。

> Coding Agent should remember the project state that changes future work.

TODO、当前进度和执行计划属于独立 Execution State，不是 durable memory。
Procedure 在 v0 中不激活。

## 唯一产品主线

Coding Agent Memory v0 只对应以下产品闭环：

```text
Hooks → atomic spool → Event Log → isolated Compiler
      → immutable revisions/refs → Reconciler → Router
      → context capsule / warning → Agent → new evidence
```

Codex plugin 是首个 adapter，不是产品边界。Python Core 保持宿主无关，
Event Log 是可重放权威，SQLite 和 Markdown 都是可重建投影。

## v0 边界

第一版支持：

- 单用户、单 Git repository 和多分支；
- 四类 durable memory 与独立 Execution State；
- 显式 proposed、active、conflicted、needs_revalidation 等状态；
- strict/hybrid promotion、证据驱动 reconciliation；
- anchor/FTS5 Router、bounded context capsule 和动作前 warning；
- 人工 CLI、只读＋反馈 MCP、薄 Codex plugin；
- Windows dogfood 与 Linux CI。

第一版不做 Procedure、云同步、多仓库共享、向量检索、完整代码依赖图、
自动代码回滚和完整 transcript 存储。

## 产品与评测的关系

仓库只有一个活跃产品 benchmark：

```text
Product
└── Coding Agent Memory v0

Evaluation
└── Repo Evolution
    └── C0–C5 experimental conditions
```

Repo Evolution 当前版本是 `0.1.0-draft.1`，状态为 specification 和 Git
snapshot materializer。它能够校验 scenario、gold、状态变化和可复现 Git
快照，但尚未执行真实 Coding Agent，也不能单独证明产品收益。

只有 execution adapter、评分闭环和冻结后的 confirmation runs 完成后，
Repo Evolution 才能产生产品效果证据。详见
[benchmark catalog](benchmarks/README.md) 和
[evaluation protocol](docs/evaluation-plan.md)。

## 当前状态

已完成：

- Event Log、atomic spool、SQLite/FTS5 projection；
- immutable revision/ref 状态机；
- strict/hybrid policy、Reconciler 和 Router；
- CLI、MCP、Markdown Inspector 和 Codex plugin；
- 隔离 Compiler、one-shot worker 和确定性测试；
- Repo Evolution specification、gold 和 Git materializer。

尚未完成：

- Repo Evolution Agent execution adapter 与自动评分闭环；
- C0–C5 pilot、protocol freeze 和 confirmation runs；
- 真实长期 dogfood、竞品统一体验和失败样例积累；
- payload retention compaction。

## 项目结构

```text
agent-memory-failure-lab/
├── src/agent_memory/             # 宿主无关的产品 Core
├── plugins/coding-agent-memory/  # 薄 Codex adapter
├── benchmarks/
│   ├── README.md                 # benchmark catalog
│   └── repo_evolution/           # 唯一活跃的 v0 benchmark
├── scripts/run_repo_evolution.py # specification/materializer 入口
├── docs/                         # PRD、架构、评测和决策
├── tests/
└── results/                      # 本地运行结果，不提交
```

## 本地运行

```powershell
python -m pip install -e ".[dev]"
agent-memory init
agent-memory doctor
agent-memory status
codex plugin install --dev ./plugins/coding-agent-memory
```

Repo Evolution dry run：

```powershell
python scripts/run_repo_evolution.py --dry-run --condition C3
```

生成隔离的 Git 演化 workspace：

```powershell
python scripts/run_repo_evolution.py `
  --workspace results/repo-evolution/C3 `
  --condition C3
```

该命令只生成 snapshots 和 manifest，不调用模型。

## 验证

```powershell
python -m ruff check src scripts tests
python -m pytest -q
python -m pytest -q -m evaluation
```

## 文档入口

- [Product Brief](docs/product-brief.md)
- [PRD](docs/prd.md)
- [Architecture](docs/architecture.md)
- [Evaluation Protocol](docs/evaluation-plan.md)
- [Decision Log](docs/decisions.md)
- [Project Plan](PROJECT_PLAN.md)
- [Competitive Analysis](docs/competitive-analysis.md)
- [Competitor Trial Protocol](docs/competitor-trial-protocol.md)
