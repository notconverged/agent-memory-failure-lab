# Agent 协作与代码规范

本文档是 `agent-memory-failure-lab` 的项目级约束。所有后续协作、代码修改和实验记录都应遵守这些规则。

## 1. 项目目标与工作边界

- 项目目标是研究 Agent memory 的收益、失败模式和负迁移，而不是单纯展示某个框架的 API。
- 优先建设 framework-independent benchmark harness，再接入 Letta 或其他外部系统。
- 第一阶段只实现可解释、可自动验证的 baseline；不要提前引入 embedding、向量数据库、graph memory 或 latent memory。
- `Reference/MemoryAgentBench` 等外部资料只作为参考，不复制源码，也不把本地绝对路径作为项目依赖。

## 2. 修改代码前

每次修改前先说明：

1. 要修改哪些文件；
2. 修改解决什么问题；
3. 如何验证修改有效；
4. 是否会改变实验定义、数据顺序或评估口径。

优先小步修改。不要在没有测试或运行结果的情况下大范围重构。

## 3. Python 基础规范

- 使用 Python 3.10+；变量名和函数名使用 `snake_case`，类名使用 `PascalCase`。
- 保持函数职责单一，优先清晰的普通函数和数据结构，避免为了抽象而抽象。
- 公共 class、function 和复杂数据结构添加简短 docstring。
- 类型标注用于表达关键输入输出，尤其是 memory item、episode、verifier result 和实验结果。
- 使用 `pathlib.Path` 处理路径；禁止写死个人机器上的绝对路径。
- 不在库代码中使用 `print` 输出实验日志；使用标准 `logging` 或由 runner 统一处理。
- 不吞掉异常。只有在能明确解释和处理时才捕获 exception，并保留上下文。
- 随机过程必须显式传入 seed，并在结果中记录 seed。

## 4. 数据与实验规范

- 建模或实验前先检查字段、缺失值、重复值、异常值、日期/episode 范围和样本分布。
- sequential task 必须按既定顺序运行；不得随机打乱来获得更好的结果。
- 严格防止 future information leakage：当前 episode 不能读取未来 episode 的 feedback 或 memory。
- 每个 episode 记录 instruction、agent output、verifier result、feedback、retrieved memory、memory state 和 error type。
- 所有 baseline 使用相同 task order、相同 verifier 和尽可能相同的 agent policy。
- 先跑 `NoMemory` baseline，再跑 `AppendOnlyMemory`，最后实现 `ConflictAwareMemory`。
- 结果不能只报告一个指标；至少同时报告成功率、失败类型和必要的 memory overhead。

## 5. Memory interface 约束

第一版 memory interface 保持简单，建议至少包含：

```python
class Memory:
    def write(self, item):
        raise NotImplementedError

    def retrieve(self, query):
        raise NotImplementedError
```

- `NoMemory.retrieve()` 应返回空集合，不产生跨 episode 状态。
- `AppendOnlyMemory` 只追加可追踪的 memory item，不在第一版偷偷加入语义检索。
- `ConflictAwareMemory` 的更新、失效和 supersede 行为必须能从 trace 中解释。
- memory 组件不应直接决定任务成功；成功与否由 verifier 独立判断。

## 6. 测试与验证

- 新增行为先添加最小测试，再实现代码。
- 测试至少覆盖：空 memory、单条写入、多 episode 顺序、feedback 是否写入、冲突更新和结果序列化。
- 运行测试：

```powershell
pytest
```

- 运行静态检查：

```powershell
ruff check .
```

- 每次实验前后检查配置和结果文件是否对应同一份代码版本。
- 失败时先定位是 task、agent、verifier、memory 还是 runner 的问题，不要直接修改指标定义。

## 7. 文件与依赖规范

- 代码放在 `src/`，任务定义放在 `tasks/`，测试放在 `tests/`，实验输出放在 `results/`。
- 不提交 `.env`、API key、token、password、cache、模型权重和未经说明的大型数据文件。
- 新依赖必须说明用途、版本范围和是否能被最小 baseline 替代。
- 外部 benchmark 或 framework 需要记录 repository、版本/commit hash 和 adapter 说明。
- 结果文件使用结构化 JSON 或 CSV；图表应包含标题、坐标轴、图例和一句解释。

## 8. Git 规范

- `main` 保持可运行、可解释；新功能和实验优先使用 `feature/<topic>` 分支。
- commit message 使用清晰的 imperative English，例如 `Add sequential task schema`。
- 一个 commit 尽量只包含一个逻辑变化；不要把无关格式化和实验结果混在一起。
- 提交前检查：

```powershell
git status --short --branch
git diff --stat
git diff --cached
```

- 提交前检查潜在敏感信息：

```powershell
git grep -n "api_key\|secret\|token\|password" -- .
```

- 任何远程 push 前都要确认 remote、branch、待提交文件和 `.gitignore`。

## 9. 文档规范

- README 面向第一次 clone 项目的读者，说明问题、结构、环境和运行方式。
- 实验报告必须说明 task 定义、memory condition、verifier、指标、结果和局限性。
- 不把“跑通 demo”写成“证明 memory 有效”；明确区分 observation、interpretation 和 limitation。
- 如果实验设计改变，先更新 `PROJECT_PLAN.md`，再修改实现。
