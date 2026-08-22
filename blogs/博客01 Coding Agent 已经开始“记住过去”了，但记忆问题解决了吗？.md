>Memory 的价值不在于让 Agent 记得更多，而在于以低成本持续提供当前正确、可验证、与任务相关的信息。

# Memory的作用

Coding agent完成项目的能力已经很强。但仍然存在无法准确记录当前状况的问题，这会导致跨agent协作困难，上下文压缩丢失关键信息等情况。

对于个人开发者来说，前一天已经探索了一轮代码，第二天重新打开 Coding Agent，它虽然可以重新阅读代码库，但此前已经进行过的探索和判断往往需要重新建立。我需要再次告诉它项目进展、现在卡在哪里、昨天做过哪些尝试。单个agent持续工作时也会遇到上下文过长，需要自动压缩的情况。一个 debugging task 做了一两个小时，中间读文件、跑测试、讨论方案、修改代码，context 越来越长。context中包含了有价值的信息，已失败的尝试、临时猜测、terminal output，同时也包含了大量噪声信息例如已经过期的中间信息、大量临时推理等。但是哪些继续留在 working context，哪些压缩，哪些应该变成长期 Memory，决策不当会导致早期一些关键判断需要重新解释；但如果完全不压缩，大量 debugging 输出和已经没有价值的讨论又持续占据 token。

如果是集体项目，一个Coding Agent则还需要学习协作方式（尤其是git这类代码项目的使用规范）、理解当前项目的组织方式和分工模块，形成类似于多智能体合作的合理工作流。多智能体合作时，哪一个的决策是正确的？大型项目的协作记忆应该如何维护？这是记忆系统的另一个问题。

对于当前工作状态的选择和处理原因记忆不清会导致工程问题难以处理。作为需要长期运营的项目，Coding过程中会遇到很多工程问题，这时候每一次选择都很重要，我们希望Agent能够时刻保持项目部署服务器大小、项目什么最占据空间，以及选择这一系统的原因这类的记忆，但实际上这类考虑往往复杂，难以保存。

# 当前记忆的形式
当前，Coding Agent 的记忆机制主要依赖三类静态工件：持久化的指令配置文件（如 `.cursorrules` 或 `CODEBUDDY.md`）、自动生成的 Markdown 会话笔记（如决策日志、摘要快照），以及任务交接时由人工撰写的说明文档。这些手段虽能在短期内降低重复解释的边际成本，但本质上仍属于“碎片化信息存储”，因为它们记录的是孤立的事实，没有把项目历史视作一个可建模的对象系统。

我认为理想的项目记忆应当是一个**带证据、带状态、带可追溯关系**的结构化体系：每个历史事件都应附带可验证的产出证据（如变更集、测试通过率）、明确的生命周期状态（如待评审、已合入、已回滚），以及与其他事件之间的因果或时序关联（如“此修复依赖前一次重构”）。唯有如此，Agent 才能在后续推理中基于完整的历史上下文进行查询、回溯和因果推断，而非仅靠关键词匹配或最后一次会话的摘要。【尽管这样做的成本嘛……还有待实验】

然而，现有方案几乎都跳过了这一抽象层，它们把项目历史当作线性文档流，而不是带关系的对象图。这不仅限制了 Agent 对复杂决策链的复现能力，也使得跨任务的知识迁移始终停留在人工整理层面，无法真正实现可演进的“项目记忆体”。

## 记忆机制
当前两个主流的coding agent工具claude code和codex都有自己的记忆机制：
### Claude Code
来源：[How Claude remembers your project - Claude Code Docs](https://code.claude.com/docs/en/memory)
Claude Code中存在两种互补的记忆机制：
- 由团队人工维护的claude.md文档：一般是持久化 instructions，包括 coding standards、项目架构、构建命令和工作流，CLAUDE.md 文件无论长度如何都能完整加载，不过文件越短，保持一致性更好。
- 由Claude Code自己选择记录的Auto Memory：Claude 会按照项目自建文件夹，自动记录在这一个项目中它认为未来有用的 learnings and patterns，例如 build commands、debugging insights、architecture notes、偏好和 workflow habits。这部分文档统一存放在本机路径中：
```
~/.claude/projects/<project>/memory/
├── MEMORY.md
├── debugging.md
├── api-conventions.md
└── ...
```
其中`MEMORY.md` 作为内存目录的索引。Claude 会在整个会话中读写该目录中的文件，使用 `MEMORY.md` 来跟踪存储了什么。

`MEMORY.md` 的前 200 行，或者前 25KB，会在每次对话开始时加载。超过该阈值的内容不会在会话开始时加载。如果文件接近限制，Claude Code 会提醒 Claude 缩短。如果文件超过限制，写入仍然成功，但 Claude Code 会返回错误，要求 Claude 重写索引，因为超过限制的所有内容在下一次加载时都会被丢弃。

像 `debugging.md` 或 `patterns.md` 这样的主题文件在启动时不会加载。Claude 在需要信息时，会使用其标准文件工具按需阅读。它以 Git repository 为范围，同一仓库的 worktree 共享该目录。

### codex
来源：[工程技术：在智能体优先的世界中利用 Codex | OpenAI](https://openai.com/zh-Hans-CN/index/harness-engineering/)和[codex/codex-rs/memories/README.md at main · openai/codex](https://github.com/openai/codex/blob/main/codex-rs/memories/README.md)
codex的记忆可以通过下面三层理解：

第一层是 `AGENTS.md`。它是持久化项目指导文件，类似于claude.md。可以写项目规范、业务规则、已知陷阱和依赖信息。它主要是“给 Agent 的项目地图”，而不是自动生成的完整历史记忆。OpenAI 也明确建议把详细知识放在结构化 `docs/` 中，让简短的 `AGENTS.md` 负责导航。

第二层是任务工作流文档，包括PLANS.md、ExecPlan handoff.md和STATUS.md。它们更适合保存当前任务的当前目标、 已完成工作、下一步计划、发现和决策以及已知问题。它们主要是 execution state 和 checkpoint，不等于长期项目 memory。

第三层是 Codex 当前代码中的 experimental memory pipeline。官方 Codex 仓库显示，它已经有异步的两阶段流程：

```
Phase 1:
每个 thread / rollout
→ 提取 raw memory 和 rollout summary

Phase 2:
多个 thread 的候选记忆
→ 全局 consolidation
→ MEMORY.md / memory_summary.md / rollout_summaries/
→ 刷新磁盘上的记忆工作区，并生成/更新更高层级的整合记忆输出
```

这个流程会把候选记忆写入本地 memory workspace，并通过 read path 注入未来会话；它还会使用 Git-style workspace diff 维护记忆文件的增量变化，。因此，Codex 已经比单纯的 `AGENTS.md` 更进一步，但其最终产物仍主要是经过抽取和整合的文本记忆，还不是一个面向 Coding Project State 的 revision graph。

Claude Code 和 Codex 都已经对跨 session 工作进行了适应性改进，但它们的持久化记忆仍主要围绕 instructions、notes、summaries 和 handoff 文档展开，这些历史通常没有被统一建模为带类型、证据、版本、替代关系和有效性状态的项目记忆对象。

## 外挂记忆
除了 Coding Agent 自带的 memory 机制，市场上还出现了许多外接式记忆方案。它们通过项目文档、插件、MCP 服务或独立存储，为 Agent 提供跨 session 的上下文补充。这些方案通常不修改模型本身，而是尝试在 Agent 之外增加记忆的保存、更新和检索能力。

本节重点分析两类代表：以 Markdown 文件和工作流规范为核心的 Cline Memory Bank，以及通过外部工具或服务提供记忆能力的 MemoraX。比较重点包括：**它们记录什么、何时写入、如何更新、如何处理冲突和过期信息**，以及**最终如何将记忆重新注入 Agent**。
### Cline Memory Bank
Cline Memory Bank：文件优先、规则驱动、主要依赖 Agent 主动读写 Markdown


### Memorax


## **从“保存记忆”到“维护状态”：Coding Agent Memory 的四个待验证职责**

我最初把 Coding Agent Memory 理解得比较简单：把一次 session 中重要的内容总结下来，保存成文件，下一次 session 再读回来。这听起来足够直接，就像给 Agent 配了一本随时可翻的笔记本。就像Claude code和codex通过 `AGENTS.md`、`CLAUDE.md`、Auto Memory、任务计划或手写 handoff 文档获得一部分项目上下文。

但在实际使用 Codex 和 Claude Code 的过程中，我逐渐意识到，问题并不是 Agent 能不能记住当前状态，只记住当前状态是不够的。**项目开发从来不是一条直线。** 除了当前的代码状态，我们还经常经历多路线的方案试探、并行实验、中途放弃的方向，以及在不同阶段反复调整的决策。在这种动态环境下，仅仅告诉 Agent“当前项目长什么样”是不够的，它很容易“忘记”之前走过的弯路，于是重新提出已经被否决的假设，或者无视某个早已失效的约束，继续沿着错误方向修改代码。

我开始把这种反复出现的挫败拆解成几个更具体的困难：

#### **第一，这段信息到底是什么性质的？**

同样是一次开发过程，里面可能既有最终的架构决定，也有随手试了一把的临时方案，还有彻底失败的尝试，以及当前做到哪一步的状态。这些东西都能记录下来，但它们的分量完全不同。把“试过 Redis”当成“决定用 Redis”来用，是我见过最常见也最致命的错误。区分决策、约束、事实、失败经验、临时尝试和执行状态——这几类东西如果不分开，记忆就只是一团浆糊。

#### **第二，我凭什么相信它？它现在还对不对？**

“项目用 PostgreSQL”这句话，可能是我决定的尝试方向，也可能是从配置文件里读出来的，还可能是某个测试跑通之后推断的。不同的证据来源，可信度不一样。而且就算当时是对的，代码变了之后它还可能成立吗？配置改过没有？分支切了没有？有没有新的事实把它覆盖掉了？

更麻烦的是，有些重要的决策记忆根本没办法从当前代码里验证。比如“当时为什么放弃 Redis”，这个理由只存在于当时的讨论、测试结果或用户的口头决定里，代码里看不到。所以不能简单地说“和代码对不上就是错的”，有效性判断得比这更细致。

还有一个让我头疼了很久的问题：如果旧事实 A 被用来推导出摘要 B，B 又衍生出计划 C，后来 A 失效了，但 B 和 C 还被当作有效内容在使用。这就不只是一条老记录没更新，而是污染扩散出去了。系统得知道谁依赖谁，不能只存一堆彼此无关的文本片段。

#### **第三，这条信息应该留下来吗？留下来之后怎么用？**

这三个子问题是连着的：

- 要不要留？失败尝试可以留，但留它不等于要把它当真理，因为失败可能是由于当时的约束条件；
- 能不能作为事实来用？有的东西只配当历史参考，不够格作为当前决策依据；
- 当前这个任务里该不该拿出来？就算一条记忆正确且有资格被用，它也可能跟当前做的事情毫无关系，或者作用域不匹配，或者上下文已经塞不下了。

举几个例子可能更清楚：Redis 尝试失败，但可以留着，但不能当成“禁止用 Redis”的规则，只能在做 Redis 相关任务时作为提醒；当前用 PostgreSQL 的决策，留着，且作为有效事实，在 backend 任务里注入；已经被新决策覆盖的旧 SQLite 事实，留着但不作为当前事实注入；另一个模块的失败经验，可以保留或压缩，但当前任务不相关就不注入。

所以到最后我慢慢意识到，**记忆管理其实不是“存和取”的问题，而是一个完整的过程：先分清楚内容是什么，再维护它的可信度和有效性，然后决定要不要留、能不能用、什么时候给 Agent 看**。这三个维度不是先后顺序，而是每一条记忆同时都有的三个侧面。

基于这个理解，我在试着把这套想法拆成四个工程模块来实现，目前还是边写边改的状态，远没到“验证过”的程度：

- **Write-time Memory Compiler**：在 coding trajectory 流入时，先分类和提取候选记忆，而不是直接写入长期存储。它区分临时尝试与稳定结论，绑定证据和锚点，并保留不确定性。
- **State Reconciler**：当新证据出现时，负责处理旧记忆被替代、失效、需要重验证或产生冲突等情况，同时追踪依赖影响，避免派生状态污染。
- **Validity-aware Context Router**：在检索时不仅看相似度，还要判断记忆是否仍然有效、作用域是否匹配、与当前任务是否相关，最后才决定把哪些内容注入上下文。
- **Handoff Materializer**：将内部状态（版本、证据、冲突、新鲜度等）物化为面向 Agent 和人的交接材料，比如当前目标、已做工作、下一步安全行动，同时确保这份材料不是独立的新事实来源，而是内部状态的一个视图。

需要强调的是，这套四阶段划分并不是我认定所有记忆系统都必须遵循的终极架构，也不是已经通过 benchmark 验证的最优方案。它目前只是一个用于描述问题、组织代码并指导后续实验的工作模型。这些模块虽然已有初步工程实现，但它们是否能真正捕获真实 coding trajectory、能否减少过期状态污染、能否改善 Agent 连续开发表现，这些都还没有被实验证实。

```text
Coding trajectory
      │
      ▼
① Write-time Memory Compiler
   observation → candidate / verified / rejected / decision
      │
      ▼
② State Reconciler
   new evidence → supersede / invalidate / dirty descendants
      │
      ▼
③ Validity-aware Context Router
   valid + scoped + relevant → retrieve / inject
      │
      ▼
④ Handoff Materializer
   canonical current state → HANDOFF / STATUS
```

|Failure|中文|例子|最接近的工作|
|---|---|---|---|
|**Fact Staleness**|事实过期|“项目用 SQLite”，现在已经 PostgreSQL|Graphiti|
|**Evidence / Artifact Drift**|证据/代码制品漂移|“这个 parser 已验证支持 X”，但它依赖的 config 已修改|GitHub Copilot Memory、EA-Graph|
|**Derived-State Cascade**|派生状态级联污染|A 失效，但由 A 得出的 B/C/summary 仍然 active|MemoRepair|
|**Execution Contamination**|执行链污染|错 memory 已经影响 plan、tool call、新 memory|Dependency-Guided Rollback、MAGE|
|**Delivery Failure**|记忆投递失败|memory 是对的，但需要它的时候没被带回 context|PMA、Claude-Mem|

## 更多记忆失效问题和解决方案
我将以收集到产品解决的记忆失效问题，对应记忆失效问题发生的环节和对应的解决方案。
