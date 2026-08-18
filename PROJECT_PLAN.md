# Agent Memory Failure Lab 项目实施计划

## 1. 项目定位

本项目研究 Agent memory 的正向迁移（positive transfer）与负向迁移（negative transfer）。核心问题是：

> When does memory help an agent, and when does memory hurt it?

项目将 memory 当作被测变量，而不是把某个 Agent framework 当作项目本身。第一阶段使用 framework-independent experimental harness，后续再接入 Letta 或其他系统进行扩展验证。

第一阶段的更准确名称是 **Cross-Session Memory Isolation Lab**，研究：

> How does explicit cross-session experience memory alter agent behavior when within-session working memory and harness state are held constant?

这里的 `Session`、当前工具结果和任务内 working memory 不是要删除的 memory，而是所有实验条件共同拥有的 measurement infrastructure。真正的 treatment variable 是跨 episode 的显式 experience memory。

## 2. 研究假设

### H1：有用经验可以提升后续任务表现

在后续任务需要复用前序反馈时，`Append-only Memory` 的 Task Success Rate 应高于 `No Memory`。

### H2：追加式 memory 会产生过期和冲突干扰

当项目规则发生更新时，`Append-only Memory` 仍可能召回旧规则，从而引入 stale memory error 或 memory-induced error。

### H3：冲突感知 memory 可以保留收益并降低错误

`Conflict-aware Memory` 应识别新旧规则之间的 contradiction，并将旧信息标记为 `superseded` 或 `invalidated`，在保留有用经验的同时降低冲突错误。

这些是假设，不是预先承诺的结论。实验结果可能支持、部分支持或否定它们。

## 3. 实验单元与隔离规范

### 3.1 两层状态定义

```text
Agent State
├── Within-Episode Working Memory
│   ├── current session history
│   ├── current tool observations
│   └── current task reasoning context
└── Cross-Episode Experience Memory
    ├── retrieved experience
    ├── stored feedback
    ├── freshness / version state
    └── update / invalidate / supersede policy
```

第一阶段只操纵第二层。`No Memory` 的严谨名称是 **No Cross-Session Memory**，并不意味着 Agent 在当前任务中没有工作状态。

### 3.2 Hermetic Harness Profile

如果使用 DSH，所有 condition 必须共享同一个 hermetic harness profile：

保留：

- Agent loop；
- Session 与 event log；
- 固定的 model、tools、system prompt、max steps；
- bash / editor 等完成任务所需工具；
- trajectory logging，用于 failure attribution。

每个 episode 必须：

- 创建新 Session；
- 完成后关闭 Session；
- 禁止 resume、fork 或引用 previous session；
- 将 Session trajectory 作为日志保存，但不自动注入下一个 episode。

第一阶段关闭或固定：

- compaction；
- Skills；
- Goals；
- MCP memory 与其他 persistent memory plugin；
- session fork 与 previous session reference；
- AGENTS.md / workspace instructions（关闭，或保证所有 condition 完全一致）。

### 3.3 文件系统与环境隔离

每个 episode 从同一个固定的 clean repository snapshot 开始。不得让前一个 episode 的：

- 修改后的代码或文档；
- git history；
- logs、test outputs、generated files；
- cache、模型文件或环境状态

成为下一个 episode 的隐式 memory。建议使用固定 base commit 加独立 workspace/worktree 运行，并把实验 trace 保存到 Agent 不可见的结果目录。

### 3.4 固定变量与实验变量

固定变量包括：DSH harness、model、tools、system prompt、current-session history、task、clean environment 和 max steps。唯一改变的是 `Cross-Session Memory Policy` 及其可见内容。

### 3.5 五层实验控制边界

为了避免把模型能力、DSH 配置、Session 状态、文件系统状态和 memory 效应混在一起，正式实验使用以下五层控制边界（five experimental boundaries）：

```text
1. Model Boundary
   provider / model / reasoning configuration 固定

2. Harness Boundary
   DSH / tools / system prompt / tool schema 固定

3. Session Boundary
   每个 episode 使用 fresh session，不 resume、不 fork

4. Environment Boundary
   每个 episode 从同一 clean benchmark workspace 开始

5. Memory Boundary
   跨 episode 的唯一信息通道，只允许实验 memory 变化
```

具体执行规则如下：

- `Model Boundary`：主实验固定一个确切的 `(provider, model)` pair，同时固定 reasoning effort、temperature、max tokens、context budget 和模型版本；不能把“模型差异”误认为“memory 差异”。
- `Harness Boundary`：所有 condition 使用相同的 DSH commit、Agent loop、system prompt、工具集合、tool schema、max steps 和 memory injection 位置。第一阶段采用 host-managed retrieval，memory 不暴露为 `memory_search`、`memory_write` 或 `memory_forget` 工具。
- `Session Boundary`：1 个 episode = 1 个 fresh DSH session + 1 个 fresh workspace + 1 个 task。Session event log 可以保留用于事后分析，但不能自动注入下一个 episode。
- `Environment Boundary`：每次从 benchmark-defined clean snapshot 创建 workspace；前一 episode 的代码、文档、日志、缓存、git history 和 generated files 都不能成为隐式 memory。
- `Memory Boundary`：除实验控制器管理的 cross-episode memory 外，不允许其他持久化信息通道。memory payload、maintenance policy、retrieval policy 必须在实验记录中明确区分。

每次 run 至少保存以下 metadata：

```json
{
  "provider": "fixed-provider",
  "model": "fixed-model",
  "reasoning_effort": "fixed",
  "temperature": 0,
  "max_tokens": 4096,
  "context_budget": 8192,
  "tool_schema_version": "v1",
  "dsh_commit": "...",
  "model_snapshot": "...",
  "run_date": "YYYY-MM-DD",
  "memory_condition": "B2_relevant_append"
}
```

API provider、protocol adapter 和 model 是三个需要分别记录的变量。同一个模型通过不同 provider 或 protocol 使用时，也应视为不同的实验配置。

### 3.6 模型选择 Pilot

主实验不先比较“哪个 API 最适合 memory”，而先做一个小型 model selection pilot：选择 2 个实际可负担且 tool-use 稳定的模型，各运行约 8–12 个 prototype tasks，只比较 `B0 No Cross-Session Memory` 与 `Oracle Memory`。

主模型需要同时满足：

- 能稳定完成 read → edit → test → inspect failure → fix 的 tool loop；
- `B0` 不接近 0%，避免 floor effect；
- `B0` 不接近 100%，避免 ceiling effect；
- Oracle Memory 相对 B0 有清晰的 `Oracle Gap`；
- 成本和速率适合重复实验。

选定后冻结主实验的 provider、model 和 protocol。等 E1–E5 主线完成，再用其他模型做 cross-model robustness，而不是在主实验中同时更换模型。

## 4. 第一阶段实验边界

### 纳入范围

- sequential coding / interactive tasks；
- 有明确 expected behavior 的任务；
- 可自动执行的 verifier；
- 以文本 memory 为起点；
- 先控制 retrieval 变量，再研究 retrieval quality；
- 记录每个 episode 的 task、answer、verification、feedback、memory state 和结果。

### 暂不纳入

- embedding、vector database 和复杂 semantic retrieval；
- latent memory、learned gate、skill adapter；
- 一开始就依赖 Letta、Hermes、A-MEM 或其他框架；
- 开放式聊天偏好类任务；
- 未固定版本或无法追踪输入输出的外部 API 实验。

## 5. 实验条件

| 条件 | 跨 episode 状态 | 第一阶段作用 |
|---|---:|---|
| `B0 NoCrossSessionMemory` | 无 | 基础 control / lower bound |
| `B1 IrrelevantPlaceboMemory` | 注入长度近似相同但与任务无关的经验 | 控制额外 context 的 placebo / distractor effect |
| `B2 RelevantAppendMemory` | 追加相关、有效的 experience | 测试 positive transfer |
| `B3 StaleAppendMemory` | 同时暴露旧规则与新规则 | 测试 stale memory / conflict-induced error |
| `B4 FreshnessAwareMemory` | 只暴露 active rule，旧规则标记 superseded / invalidated | 测试 freshness-aware maintenance 是否降低负迁移 |

`AppendOnlyMemory` 和 `ConflictAwareMemory` 仍然是实现层名称；实验报告优先使用 B0–B4，因为它们更明确地表达 treatment 与 control 的关系。第一版允许 B4 只提供最小规则式实现，不要求一次完成复杂 semantic retrieval。

### 5.1 Memory content 的第一阶段选择

第一阶段使用 **Benchmark Oracle Fact** 作为标准化 memory payload。例如 benchmark 设计者预先知道：

```json
{
  "id": "R1",
  "content": "Financial calculations must use Decimal.",
  "source_episode": "Ep1",
  "valid_from": 1,
  "valid_until": null
}
```

`Verifier Feedback` 不直接替代 Oracle Fact，而是作为 observed evidence，证明 Agent 在前一 episode 中确实遇到过这条经验。这样可以先假定 experience extraction 是正确的，只研究 memory 的 maintenance、retrieval、injection 和 utilization。

第一阶段暂不把 Full Trajectory 或 Agent Summary 直接写入 memory：前者会引入噪声过滤与 extraction 问题，后者会引入 LLM reflection quality 的混杂因素。它们在 E2 再作为 memory acquisition 的对照。

### 5.2 E1–E5 渐进实验路线

这里的 `E1–E5` 指 **Experiment Stage（实验阶段）**，不是单个任务的 Episode 编号。为避免混淆，具体任务统一使用 `Ep1`、`Ep2` 等写法。

```text
E1  Oracle content + host-managed retrieval
 ↓
E2  放开 memory acquisition / construction
 ↓
E3  放开 retrieval quality
 ↓
E4  放开 agent memory control
 ↓
E5  learned / RL memory policy
```

#### E1：Oracle Content / Maintenance Baseline

目标是先回答：在 memory 内容正确、retrieval 和 injection 固定时，append-only 与 freshness-aware maintenance 是否导致不同的行为？

- memory payload 使用 canonical Benchmark Oracle Fact；
- verifier 只负责证明 Agent 观察到了相关反馈；
- host controller 负责写入、retrieve 和在固定位置 inject；
- Agent 只看到普通的 bash/editor 等任务工具；
- 依次运行 B0、B1、B2、B3、B4，先测 positive transfer、placebo effect、stale error 和 freshness effect。

E1 的核心因果链是：

```text
正确的 memory fact
    → 不同 maintenance policy
    → 相同 retrieval / injection
    → Agent behavior
```

#### E2：Memory Acquisition / Construction

固定 E1 已验证的 maintenance、retrieval 和 injection，只改变 memory 是如何从 experience 产生的：

- Benchmark Oracle Fact；
- Verifier Feedback；
- Full Trajectory + deterministic extraction；
- Agent Summary / reflection。

这一阶段研究的是“什么值得写进 memory”，而不是“写进去之后如何处理过期冲突”。因此需要继续使用相同的 task sequence、verifier 和 memory backend，并记录 extraction error。

#### E3：Retrieval Quality

固定 memory content 和 maintenance，只逐步放开 retrieval：

- Oracle retrieval：benchmark 直接给出当前 active fact，作为上限；
- deterministic retrieval：基于 task / module key 的可解释规则；
- 实际 lexical 或 semantic retrieval：测量召回是否正确、是否遗漏、是否带入无关或 stale fact。

E3 仍然优先由 host controller 发起 retrieval，不立即开放 `memory_search` 工具。这样可以把 retrieval quality 与 Agent 是否主动搜索区分开，并单独报告 `Recall Accuracy`、irrelevant retrieval 和 retrieval latency/token cost。

#### E4：Agent Memory Control

在 memory backend 和 retrieval 机制已稳定后，才把控制权逐步交给 Agent，研究它能否正确决定：

```text
是否 retrieve？检索什么？什么时候 write / update / forget？
```

这一阶段允许加入 `memory_search`、`memory_write`、`memory_forget` 等工具，但必须把 tool-surface change 明确标记为新的实验变量，不能再与 E1 的纯 memory-content effect 直接混为一谈。重点指标包括 search-before-action、write precision、forget/update accuracy 和 control-induced failure。

#### E5：Learned / RL Memory Policy

最后才比较 rule-based controller、LLM reflection controller、bandit 或 RL policy。此时 store、retrieve、update、forget 的决策都可能被学习，研究 reward design、长期 credit assignment、exploration cost 和 policy generalization。

E5 必须建立在 E1–E4 已经有稳定 verifier、trace 和 failure taxonomy 的基础上；否则 learned policy 失败时无法判断是 reward、retrieval、memory content 还是 Agent tool-use 出错。

### 5.3 Episode 示例：E1 之后如何测试 transfer 与 stale memory

下面的 `Ep1`–`Ep6` 是 E1 阶段中的任务序列示例，不是上面的 E1–E5 实验阶段：

1. `Ep1`：实现 `calculate_return()`。Agent 可能先使用 `float`，verifier 返回 `Expected Decimal, got float`，修正后通过测试；控制器据此确认 Agent 遇到过 R1，并写入 canonical R1。
2. `Ep2`：在新 Session 和新 workspace 中实现 `calculate_drawdown()`，任务在第一次 action 前不重复说明 Decimal 规则；观察 memory 是否带来 first-attempt positive transfer。
3. `Ep3`–`Ep4`：重复稳定规则任务，测量 transfer 是否可复现，而不是只依赖单个 episode。
4. `Ep5`：benchmark 明确定义环境更新：`analytics/` 改用 `numpy.float64`，新规则 R2 在该模块范围内 supersede R1。
5. `Ep6`：实现 `analytics/rolling_volatility.py`；比较 append-only 同时暴露 R1/R2 与 freshness-aware 只暴露 active R2 时的行为差异。

这个序列必须由 benchmark fixture 明确定义。`Ep5` 的规则更新不是前一个 Agent 偶然改文件造成的，否则无法区分环境变化和 filesystem leakage。

## 6. 最小任务与数据结构

第一批任务围绕项目内部规则学习设计，例如：

1. Episode 1：任务反馈指出金融计算必须使用 `Decimal`，而不是 Python `float`；
2. Episode 2：不重复说明规则，检查 Agent 是否复用经验；
3. Episode 3：项目规则更新为在指定模块使用 `numpy.float64`；
4. Episode 4：检查 Agent 是否继续错误使用旧规则，或正确应用新规则。

建议的 episode schema：

```json
{
  "episode_id": 1,
  "instruction": "Implement calculate_return.",
  "expected_behavior": "Use Decimal for financial calculations.",
  "verifier": "decimal_required",
  "feedback": "Financial calculations must use Decimal.",
  "memory_target": "Use Decimal for financial calculations.",
  "memory_condition": "stable",
  "environment_snapshot": "base-v1",
  "session_id": "episode-1-session",
  "error_type": null
}
```

后续可增加 `update`、`contradiction`、`irrelevant` 等 memory condition，并将 verifier 从字符串扩展为可调用的显式实现。每条 trace 还应记录 retrieved memory、memory visibility、workspace snapshot 和 session boundary。

## 7. 实施阶段

### Phase 0：项目初始化

- [x] 明确研究问题、首轮 baseline 和参考项目边界；
- [x] 创建项目实施计划；
- [x] 建立项目级 agent 与代码规范；
- [x] 初始化 Git repository 与 GitHub remote；
- [ ] 写出 `Experimental Isolation Spec`，冻结 Session、DSH persistent channels 和 workspace reset 规则；
- [ ] 完成五层控制边界清单，并为每次 run 记录 provider、model、protocol、DSH commit 和 memory condition；
- [ ] 完成 model selection pilot，冻结正式实验的 `(provider, model)` pair；
- [ ] 记录 Python environment 与实际依赖版本。

### Phase 1：最小实验 harness

- [ ] 定义 `Memory`、`Agent`、`Task`、`Verifier` 的最小 interface；
- [ ] 实现 `NoMemory`；
- [ ] 实现 `AppendOnlyMemory`；
- [ ] 实现 mock agent，先不接 LLM；
- [ ] 实现顺序执行 episode 的 `runner`；
- [ ] 确保上一轮 verifier feedback 能进入下一轮 memory；
- [ ] 先用 Benchmark Oracle Fact 作为标准化 payload，并用 verifier evidence 证明 experience 已被观察；
- [ ] 将 within-episode session history 与 cross-episode memory interface 分离；
- [ ] 输出结构化的 `results.json`。

### Phase 2：可验证 benchmark

- [ ] 编写 3–5 个 sequential tasks；
- [ ] 为每个 task 编写确定性的 verifier；
- [ ] 添加 stable、update、contradiction、irrelevant 条件，并覆盖 B0–B4；
- [ ] 为任务 schema 和 verifier 写测试；
- [ ] 测试每个 episode 是否从同一 clean snapshot 开始；
- [ ] 测试 compaction、skills、goals、MCP memory、session resume 等 persistent channels 已关闭或固定；
- [ ] 固定随机种子（如确实存在随机过程）。

### Phase 3：baseline 实验

- [ ] 在相同 task order、相同 agent policy、相同 clean snapshot 下运行 B0–B4；
- [ ] 完成 E1：host-managed retrieval 下的 Oracle content / maintenance baseline；
- [ ] 记录 task success、retrieved memory、verifier feedback、session trace 和错误归因；
- [ ] 生成最小结果表与 matplotlib 图表；
- [ ] 检查是否存在时间顺序破坏、未来信息泄露、filesystem leakage 或不公平的 context 差异。

### Phase 4：failure analysis

- [ ] 区分 no-transfer failure、placebo/context effect、stale memory error、memory conflict error 和 irrelevant retrieval；
- [ ] 定义 `Memory-induced Error Rate`；
- [ ] 分析 memory token overhead；
- [ ] 对失败 episode 保存可复盘的 trace；
- [ ] 在 README 中解释结果、反例与局限性。

### Phase 5：Conflict-aware Memory

- [ ] 定义 memory item 的状态：`active`、`superseded`、`invalidated`；
- [ ] 实现最小 contradiction detection 规则；
- [ ] 比较 append-only 与 conflict-aware 的错误率；
- [ ] 设计边界案例，避免把“新规则”误判为无关信息；
- [ ] 评估规则复杂度、可解释性和额外开销。

### Phase 6：外部框架与扩展

- [ ] E2：固定 maintenance 与 retrieval，比较 Oracle Fact、Verifier Feedback、deterministic trajectory extraction 和 Agent Summary；
- [ ] E3：固定 memory content，逐步比较 Oracle、deterministic 和实际 lexical/semantic retrieval；
- [ ] E4：开放 memory tools，研究 Agent 的 retrieve/write/update/forget control policy；
- [ ] E5：在前四阶段稳定后，再研究 LLM controller、bandit 或 RL memory policy；
- [ ] 先锁定 benchmark 与 baseline，再评估 Letta integration；
- [ ] 记录外部框架版本、配置和 commit hash；
- [ ] 将框架 adapter 与核心 benchmark 解耦；
- [ ] 再考虑 A-MEM、Hermes 或 OpenClaw 作为参考/对照；
- [ ] 不让框架 API 行为替代对 memory failure mode 的定义。

## 8. 指标

首版至少报告：

### Task Success Rate

```text
passed_tasks / total_tasks
```

### Memory-induced Error Rate

```text
errors caused by retrieved memory / memory-dependent tasks
```

后续可加入：

- `Placebo Effect`：B1 相对 B0 的变化，用于估计无关 context 本身的影响；
- `Recall Accuracy`：召回的 memory 是否与当前 task 相关；
- `Stale Memory Error Rate`：因过期 memory 导致的错误比例；
- `Conflict Resolution Accuracy`：冲突时是否选择当前有效规则；
- `Token Overhead`：memory context 带来的额外 token 或字符开销；
- `Trace Completeness`：失败是否能从日志中复盘。

所有指标都需要结合任务定义和错误样例解释，不能只给单一 aggregate number。

## 9. 运行与可复现性约束

- 实验按 episode 的时间顺序执行，不随机打乱 sequential tasks；
- train / validation / test（若后续引入）按时间或任务版本划分；
- 不能把后续 episode 的 feedback 提前写入当前 episode；
- DSH Session 可以保留用于 trajectory logging，但不得跨 episode resume 或自动注入；
- compaction、skills、goals、MCP memory、session fork 和 previous session reference 必须关闭或固定；
- 每个 episode 必须从同一个 clean repository snapshot 开始，防止 filesystem 成为隐式 memory；
- 每次实验记录 config、task version、memory condition、seed 和依赖版本；
- 原始数据、密钥、`.env`、大型模型文件和临时 cache 不提交；
- 结果文件应能追溯到代码版本和运行参数；
- 不把 `D:\Vault\Reference\MemoryAgentBench` 这样的本地绝对路径写成项目硬依赖。

## 10. Definition of Done

第一版项目完成的最低标准：

1. clone 后能看到清晰的问题定义和运行说明；
2. 有一份明确的 Experimental Isolation Spec；
3. 有 3–5 个可自动验证的 sequential tasks；
4. B0–B2 可运行，B3–B4 至少有最小规则式实现；
5. runner 能完整跑通 `task → answer → verifier → feedback → memory → next task`；
6. E1 能使用 Oracle Fact、host-managed retrieval 和固定 injection 跑通，并生成结构化 `results.json`；
7. `results.json` 包含 provider、model、DSH commit、session、workspace snapshot、memory condition 和 memory trace；
8. 至少报告 Task Success Rate、Placebo Effect 和 Memory-induced Error Rate，并给出失败样例；
9. 结果能够解释 memory 带来的收益和风险，而不是只展示 demo；
10. E2–E5 的后续变量释放顺序已经写入实验记录，且每一步都不会回头混入前一阶段未控制的变量。

## 11. 下一步执行顺序

1. 新建 `Experimental Isolation Spec`，明确五层控制边界、B0–B4、DSH profile、Session 边界和 workspace reset；
2. 完成 2 个模型、8–12 个 prototype tasks 的 model selection pilot，冻结正式实验的 provider/model/protocol；
3. 在 `src/memory.py` 中定义 cross-session memory 的最小 interface 和 Oracle Fact schema；
4. 在 `tasks/tasks.json` 中建立第一批 3–5 个 sequential episodes，并明确 `Ep1`–`Ep6` 的规则更新 fixture；
5. 编写确定性 mock agent、verifier、host-managed retrieval 和 clean-snapshot runner；
6. 为 memory lifecycle、session isolation、filesystem reset、metadata 和 trace 写单元测试；
7. 先完成 E1：运行 B0、B1、B2，再加入 B3、B4，分析 positive transfer、placebo、stale memory 与 freshness-aware maintenance；
8. E1 稳定后依次推进 E2 acquisition、E3 retrieval、E4 agent control、E5 learned/RL policy；
9. 最后再引入真实 LLM、DSH adapter 或外部 Agent framework，并保持核心 benchmark 与实验边界不变。

