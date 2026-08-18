# Agent Memory Failure Lab 项目实施计划

## 1. 项目定位

本项目研究 Agent memory 的正向迁移（positive transfer）与负向迁移（negative transfer）。核心问题是：

> When does memory help an agent, and when does memory hurt it?

项目将 memory 当作被测变量，而不是把某个 Agent framework 当作项目本身。第一阶段使用 framework-independent experimental harness，后续再接入 Letta 或其他系统进行扩展验证。

## 2. 研究假设

### H1：有用经验可以提升后续任务表现

在后续任务需要复用前序反馈时，`Append-only Memory` 的 Task Success Rate 应高于 `No Memory`。

### H2：追加式 memory 会产生过期和冲突干扰

当项目规则发生更新时，`Append-only Memory` 仍可能召回旧规则，从而引入 stale memory error 或 memory-induced error。

### H3：冲突感知 memory 可以保留收益并降低错误

`Conflict-aware Memory` 应识别新旧规则之间的 contradiction，并将旧信息标记为 `superseded` 或 `invalidated`，在保留有用经验的同时降低冲突错误。

这些是假设，不是预先承诺的结论。实验结果可能支持、部分支持或否定它们。

## 3. 第一阶段实验边界

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

## 4. 实验条件

| 条件 | 跨 episode 状态 | 第一阶段作用 |
|---|---:|---|
| `NoMemory` | 无 | control / lower bound |
| `AppendOnlyMemory` | 追加所有有效 feedback | 测试经验迁移与 stale memory 风险 |
| `ConflictAwareMemory` | 更新、失效或 supersede 冲突信息 | 测试冲突处理是否降低负迁移 |

第一版允许 `ConflictAwareMemory` 只提供 interface 和最小行为，不要求一次完成完整的冲突解析系统。

## 5. 最小任务与数据结构

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
  "memory_condition": "stable"
}
```

后续可增加 `update`、`contradiction`、`irrelevant` 等 memory condition，并将 verifier 从字符串扩展为可调用的显式实现。

## 6. 实施阶段

### Phase 0：项目初始化

- [x] 明确研究问题、首轮 baseline 和参考项目边界；
- [x] 创建项目实施计划；
- [x] 建立项目级 agent 与代码规范；
- [x] 初始化 Git repository 与 GitHub remote；
- [ ] 记录 Python environment 与实际依赖版本。

### Phase 1：最小实验 harness

- [ ] 定义 `Memory`、`Agent`、`Task`、`Verifier` 的最小 interface；
- [ ] 实现 `NoMemory`；
- [ ] 实现 `AppendOnlyMemory`；
- [ ] 实现 mock agent，先不接 LLM；
- [ ] 实现顺序执行 episode 的 `runner`；
- [ ] 确保上一轮 verifier feedback 能进入下一轮 memory；
- [ ] 输出结构化的 `results.json`。

### Phase 2：可验证 benchmark

- [ ] 编写 3–5 个 sequential tasks；
- [ ] 为每个 task 编写确定性的 verifier；
- [ ] 添加 stable、update、contradiction、irrelevant 条件；
- [ ] 为任务 schema 和 verifier 写测试；
- [ ] 固定随机种子（如确实存在随机过程）。

### Phase 3：baseline 实验

- [ ] 在相同 task order、相同 agent policy 下运行三种 memory condition；
- [ ] 记录 task success、retrieved memory、verifier feedback 和错误归因；
- [ ] 生成最小结果表与 matplotlib 图表；
- [ ] 检查是否存在时间顺序破坏、未来信息泄露或不公平的 context 差异。

### Phase 4：failure analysis

- [ ] 区分 no-transfer failure、stale memory error、memory conflict error 和 irrelevant retrieval；
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

## 7. 指标

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

- `Recall Accuracy`：召回的 memory 是否与当前 task 相关；
- `Stale Memory Error Rate`：因过期 memory 导致的错误比例；
- `Conflict Resolution Accuracy`：冲突时是否选择当前有效规则；
- `Token Overhead`：memory context 带来的额外 token 或字符开销；
- `Trace Completeness`：失败是否能从日志中复盘。

所有指标都需要结合任务定义和错误样例解释，不能只给单一 aggregate number。

## 8. 运行与可复现性约束

- 实验按 episode 的时间顺序执行，不随机打乱 sequential tasks；
- train / validation / test（若后续引入）按时间或任务版本划分；
- 不能把后续 episode 的 feedback 提前写入当前 episode；
- 每次实验记录 config、task version、memory condition、seed 和依赖版本；
- 原始数据、密钥、`.env`、大型模型文件和临时 cache 不提交；
- 结果文件应能追溯到代码版本和运行参数；
- 不把 `D:\Vault\Reference\MemoryAgentBench` 这样的本地绝对路径写成项目硬依赖。

## 9. Definition of Done

第一版项目完成的最低标准：

1. clone 后能看到清晰的问题定义和运行说明；
2. 有 3–5 个可自动验证的 sequential tasks；
3. `NoMemory` 和 `AppendOnlyMemory` 可运行；
4. runner 能完整跑通 `task → answer → verifier → feedback → memory → next task`；
5. 生成一份结构化 `results.json`；
6. 至少报告 Task Success Rate，并给出失败样例；
7. 结果能够解释 memory 带来的收益和风险，而不是只展示 demo。

## 10. 下一步执行顺序

1. 建立 `src/memory.py` 的最小 interface；
2. 建立 `tasks/tasks.json` 的首批 episode；
3. 编写确定性 mock agent 与 verifier；
4. 完成 `runner.py` 并生成第一份结果；
5. 为 memory lifecycle 写单元测试；
6. 再决定是否引入真实 LLM 或外部 Agent framework。
