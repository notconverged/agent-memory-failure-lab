# Coding Agent Memory v0 项目实施计划

## 1. 产品目标

构建一个宿主无关、local-first 的 Coding Agent Memory Core，并通过薄 Codex
adapter 完成真实闭环：

```text
Hooks → Event Log → Compiler → Memory Revision
      → Reconciler → Router → Context/Warning
      → Agent behavior → new evidence
```

产品不假装自己永远知道正确答案。capture gap、证据不足、冲突、过期和无法
判断必须在数据模型、路由和审计中显式表达。

## 2. v0 范围

### In scope

- 单用户、单 repository、多分支；
- Decision、Constraint、ProjectFact、Failure；
- 独立 ExecutionNode，不将 TODO 编译为 durable memory；
- Event Log、SQLite projection、Markdown Inspector；
- strict/hybrid promotion、证据驱动 Reconciler；
- FTS5/anchor Router 与 bounded delivery；
- CLI、只读＋反馈 MCP 和 Codex plugin；
- Repo Evolution 产品评测与长期 dogfood。

### Out of scope

- Procedure activation；
- multi-user、cloud sync 和跨 repository 共享；
- vector retrieval、完整代码依赖图和自动代码回滚；
- 保存完整 transcript；
- 在 execution adapter 完成前声称 benchmark 已证明产品收益。

## 3. 关键风险

1. capture 不完整，系统不知道真实发生过什么；
2. Compiler 把临时尝试编译为长期决策；
3. Reconciler 错误 supersede 旧 memory；
4. Agent 收到 warning 但未采纳；
5. host-assisted Compiler 污染或争用主 Agent 上下文。

v0 通过 evidence、authority、immutable revision、uncertainty state 和 audit
降低这些风险，而不是承诺完全消除不确定性。

## 4. 当前工程状态

已完成：

- [x] atomic spool 与可重放 Event Log；
- [x] SQLite/FTS5 projection 与 Markdown Inspector；
- [x] immutable revision、branch ref 和状态机；
- [x] strict/hybrid promotion 与 capture-gap guardrail；
- [x] Reconciler、直接 anchor propagation 和 read-only impact report；
- [x] Router、delivery ledger 和 bounded injection；
- [x] CLI、MCP、Codex hooks 和 one-shot worker；
- [x] 隔离 Compiler executor 与 schema validation；
- [x] Windows 本地测试和 Linux CI。

待完成：

- [ ] 真实 Codex dogfood 闭环；
- [ ] retention compaction 与 payload quota 验证；
- [ ] Repo Evolution execution adapter；
- [ ] 自动评分与结构化 run result；
- [ ] C0–C5 pilot 和 confirmation；
- [ ] 竞品统一体验与长期失败样例库。

## 5. Evaluation 主线

唯一活跃 benchmark 是 Repo Evolution。C0–C5 是同一 benchmark 的实验条件：

| Condition | 作用 |
|---|---|
| C0 | No cross-session memory control |
| C1 | Length-matched placebo control |
| C2 | Append-only without reconciliation |
| C3 | Strict promotion and reconciliation |
| C4 | Hybrid promotion and reconciliation |
| C5 | Oracle current-state upper bound |

当前 runner 只校验 specification 并生成 Git snapshots/manifest，
`agent_executed=false`。它不是完成的产品 benchmark runner。

所有正式实验必须遵守：fresh session、clean workspace、固定 model/tools/prompt/
budget、禁止隐式持久状态、pilot 后冻结 protocol，以及 manifest 记录 benchmark
version、product version 和 Git commit。

## 6. 实施顺序

### Phase A — Specification hardening

- [x] 定义 scenario、gold、C0–C5 和版本契约；
- [x] 生成可复现的多阶段 Git snapshots；
- [ ] 补充 capture gap、反证和 branch overlay 场景；
- [ ] 冻结 execution adapter 所需 I/O schema。

### Phase B — Agent execution adapter

- [ ] 每个 phase 创建 fresh session 和 clean workspace；
- [ ] 运行固定 Codex adapter、tools、prompt 和 budget；
- [ ] 接入产品 capture/compile/reconcile/route/delivery 链路；
- [ ] 保存结构化 events、memory revisions、delivery 和 behavior trace；
- [ ] 对执行失败、超时和 gate unavailable 给出明确状态。

### Phase C — Pilot and freeze

- [ ] 每个 condition 运行 3 次 pilot；
- [ ] 检查任务难度、floor/ceiling effect 和 trace completeness；
- [ ] 冻结 benchmark version、任务、模型、工具、prompt、budget 和指标；
- [ ] 冻结后将 protocol status 从 `draft` 改为 `frozen`。

### Phase D — Confirmation

- [ ] C0–C4 各运行 10 次，C5 可运行 3 次；
- [ ] 报告 capture、activation、supersession、routing 和行为指标；
- [ ] false activation、false supersession、stale/invalid injection 必须为 0；
- [ ] C3/C4 未优于 control 时报告 inconclusive/negative，不改主指标。

### Phase E — Dogfooding

- [ ] 长期用于真实项目；
- [ ] 记录重复探索、错误 memory、warning compliance 和用户纠错；
- [ ] 将真实失败转成 regression tests 和后续 benchmark 场景；
- [ ] 只有证据显示必要时才考虑 vector retrieval 或其他 host adapter。

## 7. Definition of Done

### Engineering acceptance

1. Event Log 可重放，SQLite 可完全重建；
2. capture gap 禁止自动 activation/supersession；
3. normative memory 不会被代码偏离自动替代；
4. Router 不把 conflicted、unprovable、stale 或 invalid 内容注入为事实；
5. MCP feedback 不能直接修改 active ref；
6. PreToolUse p95 ≤ 300 ms，并在失败时 fail-open；
7. Windows dogfood 和 Linux CI 均通过。

### Product evidence

1. Repo Evolution execution/scoring 闭环完成；
2. confirmation protocol 在观察结果前冻结；
3. 指标同时覆盖正确性、行为、成本和失败恢复；
4. engineering completion 与 product benefit 分开报告；
5. 有可复盘的真实 dogfood 记录和失败样例。

## 8. 下一步

```text
Repo Evolution specification hardening
→ Agent execution adapter
→ C0–C5 pilot
→ freeze protocol
→ confirmation runs
→ long-term dogfooding
```
