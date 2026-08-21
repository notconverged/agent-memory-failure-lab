# Product Brief：Coding Agent Memory

## 一句话定义

一个 repo-scoped、local-first 的持久记忆层，让 Coding Agent 在新 session
中恢复会改变后续工作的项目状态。

## Target User

长期使用 Claude Code、Codex、DSH 或类似 Coding Agent 的个人开发者，尤其是：

- 经常跨天或跨 session 维护同一个 repository；
- 需要反复解释项目约束、架构决策和历史失败尝试；
- 希望 Agent 更懂项目，但不愿意把完整聊天历史永久注入上下文。

## Problem

跨 session 后，Agent 缺少稳定的 project context，导致重复扫描、重复试错、
错误违反项目约束，以及用户不断手动重建上下文。

## Current Workarounds

- README、AGENTS.md、CLAUDE.md 等项目文件；
- 手动维护 TODO 和架构记录；
- 复制上一 session 的总结；
- 依赖 Agent 自己记住或重新探索。

这些 workaround 可用，但通常没有统一的 provenance、retrieval、过期和纠错机制。

## Product Thesis

> Agent 不需要记住一切；它需要可靠地记住少量、相关、可解释、可纠正的 project state。

## Core Use Cases

1. 重新打开 repository 时恢复关键架构决策；
2. 提醒 Agent 某种已经失败的实现路径；
3. 在新任务中恢复 repo-specific constraint；
4. 通过独立 Execution State 继续未完成任务，而不把 TODO 编译成长期记忆；
5. 用户查看、修改、删除或标记某条 memory 已过期。

## MVP Hypothesis

先实现 repo-level、结构化、证据驱动且能表达不确定性的 memory，而不是静默
保存全部对话或假装自动提取永远正确：

```text
Hooks → isolated Compiler → strict promotion → revision/ref → Reconciler
      → bounded Router → Agent feedback/new evidence
```

Durable kinds are Decision, Constraint, ProjectFact, and conditional Failure.
Procedure is inactive in v0.

## Success Signals

- 相关 project context 的恢复率提高；
- first-attempt compliance 提高；
- 重复文件探索和重复错误减少；
- irrelevant/stale memory 注入率可测量且受控；
- 用户能够理解和纠正系统保存的内容。

## Non-goals

- 通用个人助理记忆；
- 完整聊天记录归档；
- 第一版多 Agent 共享 memory；
- 第一版 latent memory、RL policy 或复杂向量检索；
- 只展示“记住了”的 demo 而没有行为评测。

## Product Risks

- 自动 capture 产生噪声；
- retrieval 带入过期或无关信息；
- 用户无法发现错误 memory；
- memory context 增加 token 和认知负担；
- 不同 Agent harness 的 context/tool surface 造成不可比结果。
- capture gap、临时尝试误编译、错误 supersession 和 Agent 忽略 warning；
- host-assisted compiler 与主 Agent 争夺或污染上下文。

## Open Questions

- strict 与 hybrid 在真实 dogfood 中各自的 precision/recall 如何？
- 哪些 semantic boundary 最容易漏掉关键 evidence？
- 动作前 warning 在何种任务中会被遵守、忽略或无法判断？
- memory 的 validity 和 supersede 如何让用户理解？
- 本地存储是否足够，何时才需要同步或共享？
