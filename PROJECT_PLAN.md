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
- [ ] 记录 Python environment 与实际依赖版本。

### Phase 1：最小实验 harness

- [ ] 定义 `Memory`、`Agent`、`Task`、`Verifier` 的最小 interface；
- [ ] 实现 `NoMemory`；
- [ ] 实现 `AppendOnlyMemory`；
- [ ] 实现 mock agent，先不接 LLM；
- [ ] 实现顺序执行 episode 的 `runner`；
- [ ] 确保上一轮 verifier feedback 能进入下一轮 memory；
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
6. 生成一份结构化 `results.json`，包含 session、workspace snapshot 和 memory trace；
7. 至少报告 Task Success Rate、Placebo Effect 和 Memory-induced Error Rate，并给出失败样例；
8. 结果能够解释 memory 带来的收益和风险，而不是只展示 demo。

## 11. 下一步执行顺序

1. 新建 `Experimental Isolation Spec`，明确 B0–B4、DSH profile、Session 边界和 workspace reset；
2. 在 `src/memory.py` 中定义 cross-session memory 的最小 interface；
3. 在 `tasks/tasks.json` 中建立第一批 3–5 个 sequential episodes；
4. 编写确定性 mock agent、verifier 和 clean-snapshot runner；
5. 为 memory lifecycle、session isolation 和 filesystem reset 写单元测试；
6. 先跑 B0、B1、B2，确认 placebo 与 relevant memory 的差异；
7. 再加入 B3、B4，分析 stale memory 与 freshness-aware maintenance；
8. 最后再决定是否引入真实 LLM、DSH adapter 或外部 Agent framework。

