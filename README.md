# Agent Memory Failure Lab

一个用于研究 Agent memory 何时帮助、何时伤害后续行为的可复现实验项目。

## 研究问题

> When does memory help an agent, and when does memory hurt it?

第一阶段通过 controlled experiment 比较三种 memory condition：

1. `No Memory`
2. `Append-only Text Memory`
3. `Conflict-aware Text Memory`

项目重点不是证明某个框架“能用”，而是定义可验证的 sequential tasks，观察跨 episode memory 对任务成功率、错误类型和额外开销的影响。

## 当前状态

项目目前处于文档与实验骨架阶段。下一步是实现最小 framework-independent harness，让下面的生命周期可以自动运行：

```text
task → agent → answer → verifier → feedback → memory → next task
```

## 项目结构

```text
agent-memory-failure-lab/
├── README.md
├── PROJECT_PLAN.md
├── agent.md
├── pyproject.toml
├── src/                 # 实验代码
├── tasks/               # sequential task 与 verifier 定义
├── tests/               # 自动化测试
└── results/             # 可追踪的实验输出；大型产物不提交
```

`MemoryAgentBench` 等外部参考项目不复制到本仓库。参考代码与本项目保持目录分离；未来若需要集成，应通过明确的依赖版本或 commit hash 保证可复现。

## 环境与运行

默认使用 Python 3.10+。当前仓库还没有可运行的实验入口；实现第一版 harness 后，将在这里补充：

```powershell
conda activate agent-memory-failure-lab
python -m pip install -e ".[dev]"
pytest
```

## 相关文档

- [项目实施计划](PROJECT_PLAN.md)
- [项目协作与代码规范](agent.md)
