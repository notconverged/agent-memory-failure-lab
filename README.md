# Coding Agent Memory

一个面向 Coding Agent 的本地优先持久记忆层（persistent memory layer）。

项目目标不是让 Agent 记住全部聊天历史，而是让它在重新进入 repository
时恢复少量真正有价值的项目上下文：架构决策、项目约束、可验证的项目事实
和带条件的失败经验。TODO 与当前进度属于独立 Execution State，不是长期记忆。

> Coding Agent should remember the project state that changes future work.

仓库同时包含一个可复现的 evaluation foundation，用于判断 memory 是否真的
减少跨 session 的重复探索和错误，而不是只展示一个能工作的 demo。

## 产品问题

跨 session 使用 Coding Agent 时，Agent 往往会重新扫描文件、重复尝试已经
失败的方法，或者忘记用户已经做出的架构决策。当前常见 workaround 是
README、AGENTS.md、CLAUDE.md、手动总结和聊天记录，但这些方式通常缺少：

- 明确的 memory 类型和来源；
- 什么时候应该恢复某条 memory 的判断；
- 过期、冲突和错误 memory 的处理；
- 用户查看、修改、删除和纠正 memory 的能力。

## 产品方向

当前项目从 research-first benchmark 转为 product-first Coding Agent Memory。
原有 Stage 0 不删除，而重新定位为产品的 baseline evaluation：

> 在固定 harness 下建立 no-memory / relevant-memory 对照，验证跨 session
> memory 是否能产生可观察的行为改善。

产品闭环计划为：

```text
Hooks → atomic spool → Event Log → isolated Compiler
      → immutable revisions/refs → Reconciler → Router
      → context capsule / warning → Agent → new evidence
```

## MVP 边界

第一版优先支持：

1. repo-level memory；
2. Decision、Constraint、ProjectFact、Failure 四类 durable memory；
3. Event Log、SQLite projection、strict promotion 与显式不确定性；
4. FTS5/anchor 检索、context capsule 与动作前 warning；
5. revision/history/edit/invalidate/restore/tombstone/purge；
6. 只读＋反馈 MCP 与薄 Codex plugin；
7. Stage 0、repo-evolution benchmark 和 dogfooding。

明确不做：

- 记住完整聊天历史；
- 通用个人助理 memory；
- 一开始就做多 Agent 共享；
- 一开始就引入复杂 embedding、vector database、latent memory 或 RL policy；
- 把某个 DSH memory plugin 当成产品本身。
- Procedure、云同步、多仓库共享和自动代码回滚。

## 当前状态

已完成：

- Stage 0 cross-session memory isolation harness；
- Benchmark Oracle Fact、host-managed injection 和 host-side verifier；
- Windows / WSL 环境迁移记录；
- 产品方向、MVP 边界和技术架构文档骨架。
- 可重放 Event Log、atomic spool、SQLite/FTS5 projection；
- revision/ref 状态机、strict/hybrid policy、Reconciler 与 Router；
- CLI、只读＋反馈 MCP、Markdown Inspector 和 Codex plugin；
- 隔离 Compiler executor、one-shot lease worker 与确定性测试。

尚未完成：

- Product discovery 和竞品调查；
- 真实长期 dogfood 与外部服务体验；
- C0–C5 真实模型 pilot/confirmation runs；
- payload retention compaction 与完整 benchmark 样本扩充；
- 连续 dogfooding 和产品级 evaluation。

## 项目结构

```text
agent-memory-failure-lab/
├── README.md
├── PROJECT_PLAN.md
├── agent.md
├── src/                         # 产品代码
├── plugins/coding-agent-memory/ # 薄 Codex adapter
├── configs/minimal.cordis.yml   # Stage 0 固定 harness
├── benchmarks/decimal_transfer/ # Stage 0 benchmark
├── benchmarks/repo_evolution/   # v0 executable benchmark
├── scripts/run_episode.py       # Stage 0 runner
├── docs/
│   ├── product-brief.md
│   ├── competitive-analysis.md
│   ├── prd.md
│   ├── architecture.md
│   ├── decisions.md
│   ├── isolation-spec.md
│   └── environment-setup.md
├── tests/
└── results/                     # 本地实验结果，不提交敏感信息
```

Stage 0 暂时保留在 `configs/`、`benchmarks/` 和 `scripts/`，以保持已有运行
入口稳定。产品代码成熟后，再将评测代码整理到 `eval/`。

## v0 本地运行

```powershell
python -m pip install -e .
agent-memory init
agent-memory doctor
agent-memory status
codex plugin install --dev ./plugins/coding-agent-memory
```

插件更新后使用 cachebuster/reinstall 流程。Core 数据默认保存在用户数据目录，
不会写入 repository 工作树。

## 推荐工作流

```text
Discovery
    → Product Brief
    → Lightweight PRD
    → Technical Spike
    → MVP
    → Evaluation
    → Dogfooding
    → Iteration
```

不要直接跳到复杂 retrieval。第一条技术探针只需要证明：本地 memory store
能否被 Coding Agent 读取，并在新的 session 中影响行动。

## Stage 0 运行

默认 Python 3.10+。真实 DSH 运行需要固定 DSH
`v0.1.0-rc.7` / commit `99f6f02`，并配置对应 provider 的 API key。

先运行本地检查：

```powershell
python scripts/run_episode.py --dry-run --condition no_memory
python scripts/run_episode.py --dry-run --condition relevant_memory
pytest
```

如果使用 Windows native DSH：

```powershell
dsh --profile headless --patch configs/minimal.cordis.yml --dump-config
python scripts/run_episode.py --smoke
python scripts/run_episode.py --confirm --replicates 10
```

如果使用 WSL Ubuntu，请先阅读[环境安装与迁移记录](docs/environment-setup.md)。
Windows native 和 WSL Linux 需要分别安装 DSH，不能混合使用 session 或实验结果。

Stage 0 的详细隔离规则、指标和接受标准见
[isolation-spec.md](docs/isolation-spec.md)。

## 文档入口

- [产品 Brief](docs/product-brief.md)
- [竞品与替代方案调查框架](docs/competitive-analysis.md)
- [轻量 PRD](docs/prd.md)
- [技术架构](docs/architecture.md)
- [产品方向决策记录](docs/decisions.md)
- [Stage 0 隔离规范](docs/isolation-spec.md)
- [Windows / WSL 环境记录](docs/environment-setup.md)
- [项目实施计划](PROJECT_PLAN.md)
- [项目协作与代码规范](agent.md)
