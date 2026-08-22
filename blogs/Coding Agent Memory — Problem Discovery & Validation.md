Coding Agent 记忆系统的问题发现与需求验证

# Problem Validation
遇到了哪些真实的困境？
我识别的困境，但是下面这些困境哪些是真实存在的？哪些不是？

|Problem hypothesis|我的判断|第一版项目|
|---|---|---|
|跨 Session 无法恢复 task state|**真实且重要，但已有部分方案**|保留|
|长 Session / compaction 丢失关键信息|**非常真实，外部证据很强**|**核心**|
|决策原因、失败尝试、约束难以持久保存|**真实，且与前两者高度相关**|**核心**|
|多 Agent shared memory / 决策冲突|真实但问题层级更高|暂时排除|
总结下来，关键的问题是如何维护**什么信息该进入哪个层级？什么时候写入？什么时候重新验证？什么时候被替换？当前任务只应该取回哪一部分？** 也就是但在长周期开发中，仍缺少可靠维护动态 task state 的机制：哪些判断已经被验证或否定、哪些决策仍然有效、当前工作进行到哪里、旧信息何时已经失效，以及下一次 Agent 应该取回哪些信息。 这个问题，更严重的地方是旧的记忆要是不完全改掉，成为stale的记忆，还有可能影响别的。所以实际上**我们研究的可以拆解为两部分，第一部分是“如何让 Coding Agent 有长期记忆”，第二部分则是更核心的“如何维护一个不断变化、可验证、不会被旧状态污染的 `Dynamic Task State（动态任务状态）`”。**

## 信息来源
重点看了 **Claude Code / Codex 的 GitHub Issues & Discussions、Cursor Forum、Reddit 的 ClaudeCode / ClaudeAI / Codex 社区**

已经普遍在用 `CLAUDE.md / AGENTS.md + plan/handoff/docs` 做外部记忆；真正没有解决好的是动态 task state 的维护、compaction 后的 continuity、旧信息失效，以及“什么应该继续相信”。

## 1. 跨 Session：不是“读不到项目”，而是恢复不了上次工作的 execution state
### 问题存在：
你第一张图里的：昨天探索了一轮代码，第二天重新打开 Agent，需要重新告诉它现在卡在哪里、做过哪些尝试。

这个问题有很直接的公开证据。Cursor 用户明确描述了同样的现象：跨 session 后，Agent 忘记已经确定的 project-specific decisions、business logic，重新建议之前已经否决的实现，从而要求开发者不断 re-explain。给出的具体例子甚至包括“上次已经决定使用 MusicXML，下一次又建议 SVG”这种 rejected approach resurrection。

### 已有解决方案：
Codex 社区早在 2025 年就在讨论一种非常典型的 workflow：context 快满以后先让 Agent 把当前 progress 写进文档，然后 reset context，再从那个 stopping point 接着工作。也就是说，开发者已经自己发明了 **session checkpoint / handoff**。

最近 Claude 社区的实际工作流也非常一致：长期 session 不继续硬撑，而是生成 `handoff.md`，记录 progress、key decisions、next steps；另外维护 `decisions.md` / `rules.md` 之类文件保存被拒绝的方法和项目约束。

> **Cross-session Task State Reconstruction Cost**  
> 跨 Session 之后，repo 可以重新读取，但此前形成的 execution state——完成项、失败尝试、当前 blocker、已做决策、next action——需要重新构建。

## 2. 长 Session / Compaction：这是目前证据最强的问题
### 问题存在
> debugging 两小时后，文件、terminal output、失败尝试、临时推理越来越多；压缩的时候到底应该保留什么？

Claude Code 官方 GitHub 上有用户给出了非常完整的复现：2–3 小时开发 session 内发生多次 compaction，随后 Agent 忘掉之前写进 memory 文件的规则、搞错数据源、重复已经纠正的错误，最终需要开发者重新解释。

Codex 上今年 8 月更有一个非常贴近你原文的 feature request。用户描述 repeated compaction 后，**大目标往往还在，但 detailed agreements、user corrections、completed-vs-pending state、exact next action 会逐渐漂移**；因此要求 Codex 自动生成 `HANDOFF.md`，其中明确保存 current goal、constraints、rejected approaches、completed work、evidence、unresolved questions 和 next safe action。

Codex 还有实际 bug report：长时间多任务工作流里，已经被纠正的旧 conversation state 会重新出现，Agent 无法识别当前 workflow stage，甚至把 obsolete instruction 当成当前状态。

> **Compaction 无法稳定保留 execution frontier。**

### 已有解决方案：
这里的 **execution frontier** 其实和上一个是一样的，解决的是一个问题：上下文过长的时候就换一个session来做。

Codex 社区早在 2025 年就在讨论一种非常典型的 workflow：context 快满以后先让 Agent 把当前 progress 写进文档，然后 reset context，再从那个 stopping point 接着工作。也就是说，开发者已经自己发明了 **session checkpoint / handoff**。

最近 Claude 社区的实际工作流也非常一致：长期 session 不继续硬撑，而是生成 `handoff.md`，记录 progress、key decisions、next steps；另外维护 `decisions.md` / `rules.md` 之类文件保存被拒绝的方法和项目约束。

## 3. “昨天为什么这么做”也确实是问题，但开发者主要缺的不是 history，而是 decision state
### 问题存在：
> 为什么选择这个系统？  
> 哪些方案试过？  
> 当前约束是什么？

Cursor 的 project-memory feature request 不只是要求“remember code”，而是特别要求保存：
- technical / architecture decisions；
- corrections；
- rejected approaches；
- anti-patterns；
- domain-specific constraints。

更值得注意的是 Codex memory 的讨论。一位长期使用 Claude Code 的开发者提出：**project memory 不应该随便从 conversation 自动推断。** 因为用户经常开几个 conversation 探索互相冲突的方案，“多次出现”并不意味着它已经成为正确结论，它可能只是 hypothesis，最终甚至被 reject。对 project-level memory，他更希望明确确认，而且要求 citation / audit trail，才能知道某次错误行为究竟是来自模型、当前 prompt、stale memory 还是错误 retrieval。

### 当前解决方案：
当前确实还不知道关于这类对话进行过程中的状态维护是怎么做的。

## 4. 我这轮搜索反而发现了一个你原稿里还没有完全突出的问题：**Stale Memory 可能比 No Memory 更危险**
### 问题存在：
很多开发者的确已经采取了你说的办法： `AGENTS.md / CLAUDE.md` + 各种 markdown 文件

一个 Claude Code 用户描述得很典型：把 `CLAUDE.md` 当 memory 后，文件不断增长，产生 context bloat；架构发生变化以后又要人工更新，否则 Claude 会继续建议 outdated approaches。拆成多个 memory files 后，又出现整文件读取、无关信息进入 context、需要持续人工维护等问题。Codex 用户也明确指出 `.md` 文件会很快 stale，而且一个坏掉的 Markdown context 会直接把后续 planning 带偏，因此有时宁可重新 explore codebase。

最近 Claude 社区甚至把它总结得非常漂亮：**intent / rationale 适合记，current implementation state 更应该重新从代码读取。** 因为 memory 和代码冲突时，旧 memory 可能反而成为更强的错误 signal。

Codex 自己的 memory discussion 也提到 version-specific knowledge 会 stale：某个 SQLAlchemy 版本正确的规则，在另一个项目里可能直接是错的，因此 memory 需要 scope 和 version context。另外还有一个正在开放的 Codex issue，专门要求 memory 支持 global / project / thread scope，因为一个项目里的经验流入另一个项目会造成 **cross-project contamination**。

> **H4 — Memory Staleness / Validity Failure**  
> Coding memory 随项目变化而失效；缺少 scope、freshness、supersession 和 source-of-truth awareness 时，旧 memory 会被 Agent 当作当前事实使用。

观察到最后这一个问题是最严重的stale的记忆系统。

### 当前解决方案：

# 竞品分析
## 分析竞品的切入点

**现有产品空间实际剩下的四个 engineering seams（工程切口）**：

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

1：写入时内存编译器，**输入**：运行时观测到的行为、上下文观测 (observation)，**输出分类**：候选记忆 (candidate) / 已验证 (verified) / 拒绝 (rejected) / 最终决策 (decision)，**含义**：在代码编写过程中，实时把上下文观测编译、提炼成记忆单元，做记忆的提取、校验、过滤、固化。

2：State Reconciler 状态协调器：**输入**：新的证据 / 新事实 (new evidence)，**输出动作**：`supersede`旧状态被新证据直接覆盖替换，`invalidate`让旧状态失效作废， `dirty descendants`标记下游派生的依赖状态为脏，需要重新计算。**含义**：当外部出现新信息时，维护整套状态的一致性，处理状态过期、覆盖、级联失效。把 stale memory 拆开：其实至少有五种

|Failure|中文|例子|最接近的工作|
|---|---|---|---|
|**Fact Staleness**|事实过期|“项目用 SQLite”，现在已经 PostgreSQL|Graphiti|
|**Evidence / Artifact Drift**|证据/代码制品漂移|“这个 parser 已验证支持 X”，但它依赖的 config 已修改|GitHub Copilot Memory、EA-Graph|
|**Derived-State Cascade**|派生状态级联污染|A 失效，但由 A 得出的 B/C/summary 仍然 active|MemoRepair|
|**Execution Contamination**|执行链污染|错 memory 已经影响 plan、tool call、新 memory|Dependency-Guided Rollback、MAGE|
|**Delivery Failure**|记忆投递失败|memory 是对的，但需要它的时候没被带回 context|PMA、Claude-Mem|

3：Validity‑aware Context Router 感知有效性的上下文路由器：**输入筛选条件**：有效 (valid)、作用域隔离 (scoped)、内容相关 (relevant)，**输出动作**：检索 (retrieve)、注入 (inject) 到 LLM 上下文，**含义**：在给大模型喂上下文的时候，自动判断哪些记忆是有效、作用域匹配、相关的，做记忆检索和上下文注入。

4：交接实例化器：**输入**：标准归一化的当前状态 (canonical current state)，**输出**：对外交接 (HANDOFF)、状态上报 (STATUS)，**含义**：把内部抽象状态，变成外部可读、可交接、可展示的输出，用于跨会话交接、UI 状态展示。

其中 **1已经有人大量在做，4也已经比较成熟。** 真正空出来的是：

> **2State Reconciler + 3Validity-aware Context Router**

尤其是两者连起来，因为如果只做 ②，memory 被正确更新了，但 Agent 还是可能拿错旧 state。STALE 已经证明了这种情况。([arXiv](https://arxiv.org/abs/2605.06527?utm_source=chatgpt.com "STALE: Can LLM Agents Know When Their Memories Are No Longer Valid?"))。如果只做 ③ retrieval 很聪明，但底层 memory graph 里并不知道哪些 derived memories 已经受到了旧事实的污染。MemoRepair 指出的 cascade update 还在。([arXiv](https://arxiv.org/abs/2605.07242?utm_source=chatgpt.com "MEMOREPAIR: Barrier-First Cascade Repair in Agentic Memory"))

两者一起才是 **维护当前可信状态，并只让当前可信状态影响 Agent。** 也就是说，需要首先维护一个可信状态的显示记忆状态（需要根据实际情况变动说明），接下来需要确保Agent在读取记忆的时候读取到正确的记忆（作用范围相关，有效的决定）。

### 载体
`AGENTS.md → handoff → native memory → MCP memory → project journal` **不是一条依次经过的 pipeline**。它们是五种不同的 **memory carrier / interface（记忆载体 / 接口）**。真正应该沿着一条链拆的是 **Memory Lifecycle（记忆生命周期）**：

> **Capture → Classify/Scope → Ground → Maintain/Invalidate → Retrieve/Route → Inject → Materialize**

这次调研下来，一个相当清楚的结论是：

> **Capture、跨 Session 保存、Context 压缩和普通 Retrieval 已经相当拥挤；真正明显没有解决好的，是 Maintenance / Invalidation / Supersession，以及它和 Retrieval 之间的连接。**

最近的研究已经开始直接把这个问题叫作 **execution-state management（执行状态管理）**、**state revision（状态修订）** 和 **stale dependency repair（过期依赖修复）**。STALE benchmark 甚至专门测“新证据已经出现后，Agent 是否真的停止相信旧记忆”，最好的被测系统整体也只有 55.2%；MemoRepair 则进一步指出，一个底层事实失效以后，由它派生出的 summary、skill、cached result 等仍可能继续存在并影响 Agent，称为 **cascade update problem（级联更新问题）**。([arXiv](https://arxiv.org/abs/2605.06527?utm_source=chatgpt.com "STALE: Can LLM Agents Know When Their Memories Are No Longer Valid?"))

|载体|它真正擅长解决的事|给你的产品留下的接口|主要失败点|
|---|---|---|---|
|`AGENTS.md / CLAUDE.md / Rules`|稳定规则、架构约束、工作规范|**Classification / Scope**|动态状态变化太快；必须维护；旧规则会继续进入 context|
|`HANDOFF / PLAN / STATUS`|当前任务做到哪、下一步是什么|**Checkpoint / Materialization**|本质是某一时刻的 snapshot；继续开发后自己也会 stale|
|Native Memory|自动从历史中抽取、跨 Session recall|**Capture + Recall**|写入标准较黑盒；通常没有完整 validity lifecycle|
|MCP Memory|给 Agent 暴露外部 memory 的读写搜索能力|**Integration Surface**|MCP 本身不定义什么是真的、什么时候失效|
|Project Journal|保留事件、历史、决策和 evidence|**Evidence / Provenance**|历史越积越多；“发生过”不等于“现在仍然成立”|

这里第一个判断现在有很强的产品侧证据。

Claude Code 当前已经明确把 `CLAUDE.md` 定位为稳定 instructions，把 Auto Memory 定位为自己积累的 build commands、debugging insights、architecture notes 等；还专门提供 path-scoped rules。Cursor 也提供 Always / Auto Attached / Agent Requested / Manual 等 scoped rules；Codex 的 `AGENTS.md` 则按目录层级组合和 override。也就是说，**空间作用域（spatial scope）已经有人认真解决了。** ([Claude](https://code.claude.com/docs/en/memory?utm_source=chatgpt.com "How Claude remembers your project - Claude Code Docs"))

但它们没有自然解决 **temporal scope（时间作用域）**。

一个特别值得注意的细节是：Claude Code Auto Memory 默认以 Git repository 为单位，同一个 repo 下的不同 worktree 共享同一个 memory directory。也就是说它有 **repo scope**，但不是天然的 **branch / task / commit scope**。如果两个 worktree 正在探索不同方案，“这是这个 repo 的记忆”并不能推出“这是当前 branch 仍应相信的状态”。这是从官方行为可以直接推导出的风险。([Claude](https://code.claude.com/docs/en/memory?utm_source=chatgpt.com "How Claude remembers your project - Claude Code Docs"))

### 记忆的7个主要注意的层级

#### Stage 1：Capture / Extraction —— 什么东西有资格成为 memory candidate？【捕捉信息，属于1】

现有办法已经很多。

Claude Auto Memory 自己决定哪些信息“以后可能有用”；Cursor 用 sidecar model 从 conversation 中抽 memory，并要求用户批准后台生成的 memory；Codex 从符合条件的历史 chat 后台生成 local memories；Claude-Mem 更进一步，直接通过 `PostToolUse` 等 hooks 捕获 Coding Agent 的工具行为和 observation。([Claude](https://code.claude.com/docs/en/memory?utm_source=chatgpt.com "How Claude remembers your project - Claude Code Docs"))

所以 **自动 Capture 已经不是很好的产品楔子。**

但是真正的问题在 Capture 之后：

```text
Agent: “我怀疑数据库 timeout 是连接池太小。”
```

这究竟是：

```text
hypothesis
```

还是：

```text
verified diagnosis
```

还是：

```text
rejected hypothesis
```

单纯“觉得以后可能有用”是不够的。

最近的 Proactive Memory Agent 已经明确把 task execution state 拆成相对稳定的 `knowledge memory` 和记录尝试/结果的 `procedural memory`，并提供明确的 save/update/delete 操作；其中 failed attempt、ruled-out hypothesis 都单独记录，而不是混成普通摘要。([arXiv](https://arxiv.org/abs/2607.08716 "Remember When It Matters: Proactive Memory Agent for Long-Horizon Agents"))

**所以第一个可改进接口不是“记不记”，而是 Write-time Classification（写入时分类）。**

#### Stage 2：Classification & Scope —— 这条信息究竟属于哪一个项目层级？【记忆有效的范围属于3】

你刚才问：

> 什么信息进入哪个层级？

当前产品主要解决的是：

**stable vs reusable** 和 **directory / project scope**。

Claude 推荐 `CLAUDE.md` 保存每次 session 都需要的事实，把只针对某部分 codebase 的东西放到 path-scoped rules；Codex 可以让靠近当前目录的 `AGENTS.md` override 上层指导；Cursor 也支持按 glob 自动 attach rule。([Claude](https://code.claude.com/docs/en/memory?utm_source=chatgpt.com "How Claude remembers your project - Claude Code Docs"))

Letta 则更像一个通用 version：Memory Block 可以随任务 attach / detach，也可以在多个 Agent 之间共享，从而控制“什么信息现在应该进入这个 Agent 的工作空间”。([Letta Docs](https://docs.letta.com/tutorials/attaching-detaching-blocks/?utm_source=chatgpt.com "Attaching and detaching memory blocks | Letta Docs"))

但 Coding Task 真正需要的 scope 至少还包括：

```text
project
branch / worktree
task
subtask
file/module
environment
dependency version
time / validity interval
```

比如：

> “不能修改 `auth.py`”

可能是：

```text
整个项目永久不能修改
```

也可能只是：

```text
当前 migration task 期间不能修改
```

甚至：

```text
因为 test suite 目前 broken，所以暂时不动
```

这三个如果都变成一句 plain-text memory，风险完全不一样。

**因此这里的产品接口可以叫 `Memory Promotion & Scoping`：**

一条 observation 被写入以后，决定它是 ephemeral task state、project knowledge、project rule，还是仅仅保留在 historical journal。

这也是为什么我现在会非常不赞成让系统随便把 task state 自动写进 `AGENTS.md`。`AGENTS.md` 更适合成为 **promoted stable memory（晋升后的稳定记忆）**，而不是 memory dump。

#### Stage 3：Grounding & Provenance —— “它为什么是真的？”【需要将记忆与原项目代码对应，代码改动记忆也应该改动，属于2】

这是你项目里一个非常重要、但普通 memory 产品经常弱化的接口。

OpenAI 在 long-horizon Codex 的实际 workflow 里已经把 `Documentation.md` 明确作为 shared memory / audit log，里面维护 milestone status、decision + rationale、run/demo commands、known issues；ExecPlan 则要求 discoveries 带 evidence、decisions 带 rationale，并且每一个 stopping point 都要更新当前状态。([OpenAI Developers](https://developers.openai.com/blog/run-long-horizon-tasks-with-codex "Run long horizon tasks with Codex | OpenAI Developers"))

Graphiti 做得更系统：它不是只存“fact”，而是把原始 ingestion event 保存成 **Episode**，由 fact/entity 回溯到 episode；事实还有时间信息。也就是说，它已经在做：

> **memory → provenance source**

而不是单纯：

> **memory → text chunk**。([Zep](https://help.getzep.com/graphiti/getting-started/overview?utm_source=chatgpt.com "Overview | Zep Documentation"))

Coding memory 里的：

```text
Redis connection pool is the root cause
```

最好不能只是一个 string，至少逻辑上应该能够回答：

```text
为什么这样认为？
来自哪一次 test？
哪个 command？
哪个 commit？
哪个 file state？
用户确认过吗？
```

但是注意：**provenance 仍然不等于 validity。**

知道“这句话来自 test #17”，不等于 test #17 所依赖的代码今天还一样。

#### Stage 4：Maintenance / Invalidation / Supersession —— 这里才是目前最大的 gap【是否需要人工维护记忆系统，属于2】
##### 第一种是 Human / Agent Rewrite

最简单：改 `CLAUDE.md`、改 handoff、删 memory。

Anthropic 官方自己都建议定期 review CLAUDE.md，使内容保持最新；Auto Memory 也是 plain markdown，可以人工修改删除。([Claude](https://code.claude.com/docs/en/memory?utm_source=chatgpt.com "How Claude remembers your project - Claude Code Docs"))

问题很明显：

> **maintenance burden 被扔给人或主 Agent 了。**

这不是一个真正的 state-management system。

##### 第二种是 Temporal Invalidation

Graphiti 是目前成熟开源方案里最贴近你这个问题的。

它的 Fact 有：

```text
valid_at
invalid_at
```

新 evidence 出现时，旧 relationship 可以被标记为失效，而不是直接删掉，所以系统同时知道：

```text
过去什么时候是真的
现在是否还是真的
```

并保存历史。([Zep](https://help.getzep.com/facts?utm_source=chatgpt.com "Facts | Zep Documentation"))

这个方向非常值得你研究，因为它解决了：

> **old ≠ deleted；old = historically true but currently invalid**

但 Graphiti 主要建模的是 **entity–relationship facts**。

Coding task state 更复杂。例如：

```text
Test A failed
    ↓
推断 library X incompatible
    ↓
决定不用方案 Y
    ↓
采用 workaround Z
```

后来换了 library version：

```text
library X changed
```

真正的问题不是只把：

```text
"X incompatible"
```

设成 invalid。

而是：

> **“不用 Y”和“workaround Z”这两个由它派生出来的 memory 是不是也应该进入待验证状态？**

这就是第三种路线。

##### 第三种是 Dependency-aware Repair

MemoRepair 今年 5 月直接把这个问题形式化成了 **cascade update problem**

> source artifact 被删除、修正或因 API migration 失效以后，从它派生出的 summary、cache、skill、procedure 等仍可能存活，并继续影响未来动作。

它提出维护 influence provenance，然后 source invalidation 发生后，先让所有受影响 descendants 暂时退出可见状态，再修复、验证、重新发布。([arXiv](https://arxiv.org/abs/2605.07242?utm_source=chatgpt.com "MEMOREPAIR: Barrier-First Cascade Repair in Agentic Memory"))

这与你说的：

> “旧的记忆要是不完全改掉，成为 stale 的记忆，还有可能影响别的。”

几乎完全相同。

而 STALE benchmark 则从另一侧证明：**即使系统已经取回了新 evidence，也不代表 Agent 会停止根据旧 state 行动。** 它尤其发现 `Implicit Conflict（隐式冲突）` 很困难——新事实并没有说“旧事实错误”，但现实上已经让旧事实失效。([arXiv](https://arxiv.org/abs/2605.06527?utm_source=chatgpt.com "STALE: Can LLM Agents Know When Their Memories Are No Longer Valid?"))

所以这里我会明确地说：

> **你的产品 gap 已经不只是 Memory Staleness，而是 State Reconciliation + Dependency-aware Invalidation。**

这是目前比“persistent memory”更有研究价值也更有产品差异化的地方。

#### Stage 5：Retrieval / Routing —— 不是“找最相关的”，而是“先排除不能信的”【应该在说找回的事情，属于3】

目前 retrieval 已经做得相当丰富。

Claude-Mem 是一个很典型的 coding-specific solution。它采用 **Progressive Disclosure（渐进式披露）**：

```text
Search index
→ Timeline
→ Full observation
```

先只给 observation title、type、timestamp、token cost，再由 Agent 决定是否深入读取，避免整个历史一次性污染 context。([Claude-Mem Documentation](https://docs.claude-mem.ai/progressive-disclosure?utm_source=chatgpt.com "Progressive disclosure - Claude-Mem"))

Graphiti 则使用 semantic + keyword + graph + temporal information 做 hybrid retrieval。([Zep](https://help.getzep.com/graphiti/getting-started/overview?utm_source=chatgpt.com "Overview | Zep Documentation"))

这些很好地解决：

> **Which memory is relevant?**

但没有完全解决：

> **Which relevant memory is still valid?**

这是两个完全不同的 ranking dimension。

假设现在问：

```text
Why aren't we using architecture A?
```

一个 semantic retriever 很可能非常喜欢：

```text
Architecture A was rejected because API v1 does not support streaming.
```

因为语义完美匹配。

但如果 API 已经升级到 v2：

> 它是 **最 relevant 的 stale memory**。

这就是你可以插入的一个非常明确的产品层：

> **Validity Gate before Relevance Ranking**

即：

```text
candidate memories
        ↓
scope check
        ↓
validity / stale check
        ↓
supersession check
        ↓
dependency freshness check
        ↓
relevance ranking
        ↓
context
```

而不是现在常见的：

```text
candidate memories
        ↓
semantic similarity
        ↓
top-k
        ↓
context
```

MAGE 今年的思路也非常接近这个方向：它认为 semantic retrieval 会把 valid 和 erroneous traces 混在一起，于是不用 flat memory，而是维护一个 hierarchical execution-state tree；当前 Agent 主要沿着 active root-to-current path 工作，错误 branch 可以被隔离。([arXiv](https://arxiv.org/abs/2606.06090?utm_source=chatgpt.com "Beyond Semantic Organization: Memory as Execution State Management for Long-Horizon Agents"))

所以在 **Retrieval Stage**，你的潜在创新不是再优化 embedding，而是：

> **State-aware / validity-aware retrieval（状态感知 / 有效性感知检索）**。

#### Stage 6：Context Injection —— 即使是有效 memory，也不代表现在应该看到【记忆召回率，属于3】

这正好对应你问的：

> 当前任务只应该取回哪一部分？

Proactive Memory Agent 的结果非常有启发。

它维护一个独立 structured memory bank，但**不把整个 bank 全塞给主 Agent**。第二阶段专门决定：

```text
inject a targeted reminder
or
no intervention
```

实验里 selective intervention 比“把整个 memory bank 暴露给 Agent”表现更稳健。论文把这个问题称作：

> **whether, when, and how remembered execution state should enter the action context**。([arXiv](https://arxiv.org/abs/2607.08716 "Remember When It Matters: Proactive Memory Agent for Long-Horizon Agents"))

所以实际上：

**Storage Policy** 和 **Context Policy** 必须是两回事。

一个事实可以：

```text
应该永久保存
```

但：

```text
99% 的 step 都不应该进入 context
```

例如：

```text
“2026-08-12 曾因为 Node 版本问题导致 Windows build 失败”
```

值得保留。

但只有当：

```text
当前又在 Windows + Node build
```

的时候才应该重新激活。

Claude-Mem 的 Progressive Disclosure 和 Proactive Memory Agent 的 selective intervention，分别从 retrieval UX 和 agent policy 两个方向在解决这个问题。([Claude-Mem Documentation](https://docs.claude-mem.ai/progressive-disclosure?utm_source=chatgpt.com "Progressive disclosure - Claude-Mem"))

所以 **when to retrieve** 和 **what to store** 也不能混为一谈。

#### Stage7：最后才轮到 Handoff：它应该是 Materialized View，而不是另一个 Memory Source【属于1】

这一点我觉得对你最开始的认识是一个重要修正，现在社区常见的：

```text
context 快满了
↓
写 HANDOFF.md
↓
new agent read HANDOFF.md
```

没有错。

OpenAI 自己的 ExecPlan 也是这个思路：它要求 plan 是一个持续更新的 living document，Progress、Discoveries、Decision Log 等必须随着工作不断更新，让一个完全不知道历史的 Agent 可以重新进入任务。([OpenAI Developers](https://developers.openai.com/cookbook/articles/codex_exec_plans "Using PLANS.md for multi-hour problem solving"))

Basic Memory 现在也把这个 workflow 产品化成：

- `memory-capture`：捕获当前 thread state；
- `memory-continue`：恢复之前的工作；
- `memory-tasks`：让 task state 跨 compaction 存活。([Basic Memory](https://docs.basicmemory.com/whats-new/agent-skills?utm_source=chatgpt.com "Agent Skills - Basic Memory"))

但这里仍有一个结构性问题：

> **HANDOFF 自己也是一份会 stale 的复制品。**

如果：

```text
canonical memory
PLAN.md
HANDOFF.md
native memory
project journal
```

全部分别存一遍“当前状态”，你其实造出了五份 source of truth。

以后问题反而更严重。

所以更合理的抽象是：

> **Handoff = Materialized Current-State View（当前状态的物化视图）**

它应该由下面那个真正维护的 state 自动生成：

```text
Canonical Task State
        ↓
HANDOFF.md
```

而不是：

```text
HANDOFF.md
        ↓
又被当成永久 memory
        ↓
又生成下一份 HANDOFF.md
        ↓
越来越 stale
```

这部分是我根据前面系统行为做出的产品推论，不是某个现有产品已经完整实现的机制。
## 实战分析
至少逼自己产出 **5 个结论**：
1. **Problem Landscape**：Coding Agent Memory 到底有哪些真实需求。
2. **Solution Landscape**：现有系统主要有哪几种解决范式。
3. **Solved vs. Unsolved**：哪些已经解决得不错，哪些仍然存在系统性 failure。
4. **Reusable Components**：哪些东西没必要自己造，可以直接借鉴。
5. **Our Bet**：你真正要押注解决的 gap 是什么，以及为什么值得做。

如果最后没有得到第五条，那这次竞品分析大概率还只是“资料整理”；**当它开始改变你的产品定义、实验设计和开发优先级时，竞品分析才真正完成了任务。**

### 现有系统的解决范式和解决程度

| 方案                                    | 最强的地方                                                 | 对 stale memory 的处理           | 剩余问题                                              |
| ------------------------------------- | ----------------------------------------------------- | ---------------------------- | ------------------------------------------------- |
| Claude / Codex / Cursor Native Memory | 低摩擦 capture + recall                                  | 可编辑/删除、有限 scope              | validity / dependency lifecycle 暴露得很少             |
| `AGENTS.md / Rules`                   | 稳定规则 + scope                                          | 人工更新 / override              | 不适合 volatile task state                           |
| ExecPlan / Handoff                    | 当前 execution frontier                                 | 持续 rewrite                   | snapshot 会再次过期                                    |
| Claude-Mem                            | coding history capture + progressive retrieval        | 时间、类型、timeline               | 更擅长 relevance，不是 validity propagation             |
| Basic Memory                          | 可读 project journal + MCP + workflow skills            | 可人工/Agent 维护                 | “什么时候维护”仍依赖 skills / instruction                  |
| Letta                                 | memory tiering、attach/detach                          | block update / delete        | 生命周期判断仍交给 Agent / developer                       |
| Graphiti                              | **temporal fact + provenance + invalidation**         | **当前产品中最强之一**                | 通用 fact graph ≠ coding execution dependency graph |
| Proactive Memory Agent                | execution state + update/delete + selective injection | 显式 maintenance               | 额外 memory-agent cost；仍依赖模型正确判断                    |
| MAGE                                  | active execution branch / flawed branch isolation     | branch revision              | 更偏 agent architecture，不是通用 plug-in memory layer   |
| MemoRepair                            | **cascade invalidation / repair**                     | **非常直接解决 stale propagation** | 依赖 influence provenance，仍是研究方案                    |

其中几个重要判断都有直接来源：Graphiti 明确提供 bi-temporal fact invalidation 和 episode provenance；Basic Memory 自己也明确承认“接上 MCP 只给了 Agent 工具，并没有教它什么时候应该使用这些工具”；Letta 则提供 attach/detach/update primitives，而不是替应用决定何时状态已经失效。([Zep](https://help.getzep.com/graphiti/getting-started/overview?utm_source=chatgpt.com "Overview | Zep Documentation"))


> **你现在真正应该比较的，不是“谁有 memory”，而是谁对 memory lifecycle 中不同 failure mode 给出了什么机制。**

而且你原来的 ② `State Reconciler` 其实还可以再拆，因为目前相关工作处理的 stale memory 并不是一种问题。

先给结论：**Graphiti、EA-Graph、MemoRepair、Dependency-Guided Rollback Repair、MAGE、Proactive Memory Agent 值得单独拿出来讲；GitHub Copilot Memory 和 remem 也应该进入核心比较集。** Claude-Mem、Basic Memory、Letta、Native Memory、AGENTS/Rules、ExecPlan 更适合作为不同层次的 baseline，而不是与你的核心设计同级的“直接竞品”。

####  GitHub Copilot Memory：**Citation + Verify-on-Read**

GitHub 自己明确把核心问题表述为：**memory retrieval 并不是最困难的，困难的是 repository 在 branch 和时间上变化之后，memory 是否仍然 valid。** ([arXiv](https://arxiv.org/html/2605.06527v1?utm_source=chatgpt.com "STALE: Can LLM Agents Know When Their Memories Are ..."))它采取的路径不是持续清理整个 memory bank，而是 **Just-in-Time Verification，JIT Verification（即时/读时验证）**：

```text
coding experience
      ↓
agent decides to create memory
      ↓
memory:
  fact
  subject
  reason
  citations → specific code locations
      ↓
repository-scoped storage
      ↓
future retrieval
      ↓
BEFORE USE:
inspect cited code in current branch
      ↓
still supported?
 ├─ yes → use / refresh
 └─ no  → correct / replace memory
```

在 GitHub 的大规模环境里，持续 offline curation 会带来巨大的工程与模型调用成本，所以 JIT 很合理。但**个人用户 + 单 repo** 下，这个 trade-off 未必成立。这可以直接变成你的一个研究问题：
> 在个人 Coding Agent 场景里，主动维护 `canonical current state`，是否比每次召回后重新验证成本更低、错误更少？

####  Graphiti：**Temporal Truth，而不是 Code Dependency**

temporal fact + provenance + invalidation，Graphiti 的基本单元不是 document，而是 **temporal fact edge（时态事实边）**：

```text
episode
  ↓
entity / relation extraction
  ↓
(entity A) --fact--> (entity B)
                 +
              validity
                 +
             provenance
```

它会记录事实：
- 在现实世界何时成立；
- 何时被系统获知；
- 来源 episode 是什么。

即 **bi-temporal representation（双时态表示）**。旧 fact 被新事实 supersede 后通常不会直接删除，而是关闭它的 validity interval，因此可以询问“现在什么是真的”和“过去某时什么是真的”。([Zep](https://www.getzep.com/ai-agents/temporal-knowledge-graph/?utm_source=chatgpt.com "What Is a Temporal Knowledge Graph? Definition - Zep"))

```text
Fact A valid
     ↓
new episode
     ↓
Fact B contradicts / supersedes A
     ↓
A.invalid_at = t
B.valid_at = t
```

这正好对应你的：

```text
new evidence
→ supersede / invalidate
```

但**没有天然覆盖 `dirty descendants`**。

所以 Graphiti 非常值得拿出来，但定位应该是：

> **② State Reconciler 的 Temporal Truth baseline。**

你可以直接借它三个概念：**validity interval、supersession history、provenance。** 不要直接照搬整个 graph ontology。

#### EA-Graph：目前与你的 Coding 场景最贴的一篇

8 月 4 日的 **EA-Graph: Artifact-Anchored Verification Memory for Coding Agents under Upstream Drift**，直接研究的就是：

> 一个 coding agent 之前验证过的结论，在 upstream code/config/data 改变以后，还能不能继续信？

论文指出，普通 prose memory 的问题在于：

> 它保存了“结论”，却没有保存**建立这个结论时的程序状态**。([arXiv](https://arxiv.org/abs/2608.04278?utm_source=chatgpt.com "EA-Graph: Artifact-Anchored Verification Memory for Coding Agents under Upstream Drift"))

它的技术路径是：

```text
verification
     ↓
Claim
"X behavior has been verified"
     │
     ├── evidence strength
     │
     └── anchor
          ↓
 canonical artifact identity
 + sub-path
 + content digest
     ↓
future repo state
     ↓
compare current artifact
     ↓
unaffected / affected / unprovable
```

Artifact 不是 file，而可以是 sub-path。例如不是：

```text
config.yaml
```

而是：

```text
(config.yaml, database.pool.max_size)
```

或者一个：

- DB column；
- constant；
- GUID；
- exported symbol；
- lookup value。

这是 **sub-path granularity（子路径粒度）**。

原因很简单：

如果只绑定整个文件：

```text
config.yaml changed
→ 所有依赖 config.yaml 的 memory stale
```

会产生大量 **over-invalidation（过度失效）**。

EA-Graph 试图做到：

```text
exact supporting artifact changed
→ affected
```

而不是：

```text
somewhere in file changed
→ stale everything
```

这对你的项目特别重要。

Evidence strength 和 Freshness 分开

一个 memory 当初可能是：

> test 验证过，confidence 非常高。

但：

> supporting artifact 今天已经变了。

因此：

```text
high evidence ≠ currently valid
```

EA-Graph 把：

**Evidence Strength（证据强度）**

和

**Freshness（新鲜度/当前有效性）**

拆开。

这是一个非常应该直接借用的 schema。

它允许 `unprovable`

如果 supporting artifact 已经不可取得，它不会让模型硬猜：

```text
valid / invalid
```

而是：

```text
unprovable
```

也就是一种：

**Epistemic Abstention（认识层弃权）**。

这和你之前的：

```text
candidate
verified
rejected
```

结合起来之后，我觉得你甚至应该考虑：

```text
valid
invalid
dirty
unknown / unprovable
```

而不是所有东西都二值化。

EA-Graph 本身不解决 cascade repair，论文也明确没有声称解决 repair efficiency / repair quality。([arXiv](https://arxiv.org/abs/2608.04278?utm_source=chatgpt.com "EA-Graph: Artifact-Anchored Verification Memory for Coding Agents under Upstream Drift"))

所以它几乎正好停在：

```text
artifact changed
→ detect which claim can no longer be trusted
```

而你的：

```text
→ dirty descendants
→ selective revalidation
```

正好可以继续往后走。

**这个绝对值得单独拿出来。**

#### MemoRepair：你的 `dirty descendants` 最直接的理论竞品

MemoRepair 不是普通 memory product，而是非常明确地研究：

> 一个 source memory 失效以后，依赖它的 derived artifacts 怎么办？

论文把这个叫：

**Cascade Update Problem（级联更新问题）**。([arXiv](https://arxiv.org/html/2605.07242v1?utm_source=chatgpt.com "Barrier-First Cascade Repair in Agentic Memory"))

它假设已经有 **Influence Provenance（影响依赖溯源）**：

```text
A ──→ B ──→ D
│
└──→ C ──→ E
```

然后：

```text
A invalidated
     ↓
compute affected descendants
     ↓
B,C,D,E withdrawn FIRST
     ↓
repair
     ↓
validate successors
     ↓
republish safe predecessor-closed subset
```

这里最关键的是 **Barrier-First（屏障优先）**：

> 先把可能受污染的 descendant 从“可见 memory”中撤掉，然后慢慢 repair。

而不是：

```text
A stale
→ repair B
→ repair C
→ ...
```

在修的过程中让旧 B/C 继续被 Agent 使用。

这和数据库/缓存 consistency 很像：

> **Safety before completeness。宁可暂时没有，也不要继续暴露已知可能错误的状态。**

论文把选择哪些 successor 值得修复的问题进一步形式化为 **maximum-weight predecessor closure（最大权前驱闭包）**，并用一次 `s-t min-cut` 求解；在完整 influence provenance 的实验条件下，其 invalidated-memory exposure 可降为 0。([arXiv](https://arxiv.org/html/2605.07242v1?utm_source=chatgpt.com "Barrier-First Cascade Repair in Agentic Memory"))

这篇与你的：

```text
invalidate
→ dirty descendants
```

几乎是一一对应。

但是它留下一个巨大的前提：

> **你怎么得到 influence provenance？**

它自己也非常依赖完整的 dependency information。

而 Coding Agent 场景恰恰难在：

```text
这个 decision
到底依赖：
哪些 files？
哪些 tests？
哪个 tool observation？
哪个旧 decision？
```

所以你与 MemoRepair 的差异应该是：

> **在 coding trajectory 中如何低成本构造可靠的 influence provenance。**

#### Dependency-Guided Rollback：比 MemoRepair 又往后走了一步

这是 8 月 11 日刚出来的 **From Faulty Memories to Corrected Actions**。

MemoRepair 主要解决：

```text
bad memory
→ derived memory artifacts
```

> 错 memory 已经被 Agent 用了怎么办？

因为真实 Agent 可能已经发生：

```text
Faulty memory
     ↓
claim
     ↓
plan
     ↓
tool call
     ↓
new observation
     ↓
new memory
     ↓
answer
```

它构建的是一个 heterogeneous **Memory-to-Action Dependency Graph（记忆—行动依赖图）**：

```text
user input
memory
tool observation
claim
execution step
new memory
answer
```

边包括类似：

```text
cite
support
produce
update
supersede
derive
```

然后从已经诊断出来的 faulty memory 开始：

```text
fault
 ↓
trace downstream dependencies
 ↓
independent-support check
 ↓
unsupported descendants → deactivate
supported descendants   → preserve
 ↓
selective replay
```

特别重要的是它加入了：

**Independent Support Checking（独立支持检查）**。

假设：

```text
A faulty ──→ C
B valid  ──→ C
```

不能因为 C reachable from A，就直接把 C 删除。

如果 B 足够独立地支持 C：

> C 可以保留。

这解决 MemoRepair/简单 dependency propagation 很容易发生的：

**over-invalidation（过度失效）**。

论文报告的 controlled benchmark 上恢复率为 85.3%，相较其最强对照的 77.3%；在 trajectory-derived subset 上为 68% vs 54%。不过要特别注意：**它假设 faulty memory 已经被诊断出来，diagnosis 本身不是论文解决的问题。** ([arXiv](https://arxiv.org/abs/2608.10502?utm_source=chatgpt.com "From Faulty Memories to Corrected Actions: Dependency-Guided Rollback Repair for Memory-Augmented Agents"))更像：**post-failure agent-state recovery**

> `dirty descendants` 最终很可能不能只停留在 Memory → Memory graph，必须考虑 Memory → Action / Tool / Derived Memory。

#### MAGE：不是“长期事实 memory”，而是 Execution State

这里还要澄清一个名字冲突。我这里说的是 June 2026 的**MAGE = Memory as Agent-Guided Exploration**,它非常重要，因为它挑战了整个：store → semantic retrieval范式。MAGE 认为长任务真正的问题是：

> Agent 的 state 是一条依赖顺序很强的 execution trajectory，而 semantic retrieval 会把不同路径上的相似 fragment 混起来。([arXiv](https://arxiv.org/html/2606.06090v1?utm_source=chatgpt.com "Memory as Execution State Management for Long-Horizon ..."))

所以它不维护一个 flat memory bank，而是：

```text
                    root
                 /        \
             branch A     branch B
               /             \
          subgoal          subgoal
            ↓
        current node
```

Agent 当前 context 来自：

```text
active root → current node path
+
completed subgoal summaries
+
recent raw trace
+
selected hints from prior branches
```

它有四个操作：

```text
Grow
→ record new interaction

Compress
→ completed subgoal → summary

Maintain
→ validate summary / trace

Revise
→ restore earlier boundary
   create new branch
   isolate flawed branch
```

这就解决：

**Execution-Branch Contamination（执行分支污染）**。

比如你曾经尝试：

```text
方案 A
→ assumption X
→ command 1
→ command 2
→ test fails
```

然后走方案 B。

普通 vector memory 以后可能又把方案 A 中语义相似的东西召回来。

MAGE 的思路是：

> A 仍然存在于 history，但它不是 active execution branch。

这个概念对你很重要：

Durable project knowledge

```text
“为什么不用 Redis”
“auth architecture 是什么”
```

和

Active execution state

```text
“现在正在 debug 哪个问题”
“刚刚跑了哪个 test”
“下一步是什么”
```

**很可能根本不应该进入同一个 memory store/state model。**

#### Proactive Memory Agent：把 Memory Management 变成一个 Controller【这是控制记忆写入的时间】

PMA 的核心不是更好的 database，而是加一个独立 **Memory Agent（记忆控制 Agent）**。论文描述的 failure 是**Behavioral State Decay（行为状态衰减）**：任务还没结束，但 requirements、previous attempts、diagnosis、open subgoals 已经埋进很长 trajectory，导致行动 Agent 虽然“历史里有”，实际上行为上已经忘了。([arXiv](https://arxiv.org/abs/2607.08716?utm_source=chatgpt.com "Remember When It Matters: Proactive Memory Agent for Long-Horizon Agents"))

它的 architecture 是：

```text
         trajectory
             │
             ▼
       Memory Agent
       /          \
maintenance      intervention
    ↓                ↓
update          inject reminder
delete               OR
save             stay silent
    ↓
structured bank
```

Memory Agent 维护类似：

```text
status
knowledge
procedure
```

每条 entry 有 ID，所以可以显式：

```text
create
update
delete
```

然后另一个重要动作是：

> 每一步判断现在有没有必要提醒 Action Agent。

即：

```text
memory exists
≠
memory should be injected now
```

这非常接近你的：
2
```text
maintenance policy
```
3
```text
selective injection policy
```

但它把核心判断交给另一个 LLM Agent。

因此代价是：

- 额外 inference cost；
    
- memory-agent 自己也可能判断错；
    
- maintenance policy 不是 deterministic consistency rule。
    

所以它是你非常好的：

> **Learned/agentic Reconciler + Router baseline**

而 EA-Graph / MemoRepair 更偏 deterministic/structured mechanisms。

#### remem：目前和你“四层完整 lifecycle”最接近的工程系统之一

remem 值得比上一轮再提高一档，它有一个非常关键的概念**CurrentTruth（当前真值视图）**。它不是把“能搜索出来”视为“可以注入”缺乏：

- provenance；
- confidence；
- validity；
- mutable-state identity

的历史 memory 可以继续被 search/detail 找到，但会标记为类似 `legacy_unverified`，从默认 CurrentTruth / SessionStart context 中排除。所以它的逻辑更像：

```text
all historical memories
        │
        ├── searchable history
        │
        ▼
trust / provenance / validity gate
        │
        ▼
CurrentTruth
        │
scope + budget
        ▼
SessionStart context
```

这与：

```text
validity = admission gate
relevance = ranking signal
```

一致。remem 对 supersedes/conflicts/staleness、context selection/drop reason、injection audit 都比普通 memory layer 更系统，因此它是你很好的 **end-to-end competitor**。但我仍然没有在公开机制里看到一个与你：

```text
repo changed
→ affected memory nodes
→ transitive dirty descendants
```

等价的 coding dependency engine。

所以它和你的 gap 仍然存在：

> **CurrentTruth management 有了，但 CurrentTruth 如何由 repository evolution 自动维护，还没有完全解决。**

#### MOOSEDev：Coding-specific Memory Ontology

**2026年8 月 13 日**刚出的，它不是用：

```text
generic vector memory
```

而是把 coding knowledge 显式建模成：

- architectural decision；
- lesson；
- constraint；
- rationale；

并给记录加入：
- lifecycle status；
- provenance；
- supersession links。

当前 guidance 查询时会把 superseded records 从“当前答案”中排除。([arXiv](https://arxiv.org/abs/2608.13662?utm_source=chatgpt.com "Ontology-Grounded Project Memory for Coding Agents"))

它对你的①特别重要：

> **Memory Substance 应该有什么 ontology？**

同时又覆盖部分②：

> **explicit lifecycle + supersession**

但仍然主要是：

```text
record lifecycle
```

而不是：

```text
repository event
→ automatically discover affected memories
```

所以我会把它放在：

> **① Compiler 最重要的新竞品 + ② explicit lifecycle baseline。**

#### PROJECTMEM：Memory-as-Governance

它采用 **Event Sourcing（事件溯源）**：

```text
immutable typed event log
→ deterministic projection
```

记录 issue / attempt / fix / decision / note 等项目事件。

更有意思的是，它不是只允许 Agent search：

> 在 Agent 做动作之前，有一个 deterministic **pre-action gate（行动前闸门）**。

例如如果 Agent：

> 正准备再次采用一个过去已经失败的 fix；

或者：

> 要修改一个历史上已知 fragile 的文件；

系统可以主动 warning。([arXiv](https://arxiv.org/html/2606.12329v1?utm_source=chatgpt.com "PROJECTMEM: A Local-First, Event-Sourced Memory ... - arXiv"))

这叫：

**Memory-as-Governance（记忆作为治理机制）**。

它对你的③很有启发：

Router 不一定只有：

```text
query
→ retrieve relevant memory
```

还可以：

```text
proposed action
→ trigger applicable memory
→ inject / warn
```

即 **prospective retrieval（面向未来动作的召回）**。

#### 最终我建议你不要再用“一张竞品表”把所有东西压平

你现在其实已经能形成一张更像研究地图的东西：

```text
                CODING TRAJECTORY
                       │
                       ▼
              ① MEMORY COMPILER
                       │
        ┌──────────────┼───────────────┐
        │              │               │
   MemoraX        MOOSEDev        agentmemory
 coding types      ontology        consolidation
        │
        ▼
              persistent state
                       │
                       ▼
               ② RECONCILER

 Fact truth       Artifact truth        Dependency truth
     │                  │                    │
 Graphiti          EA-Graph /          MemoRepair
                  GitHub Copilot            │
                                           ▼
                                   Execution propagation
                                           │
                               Dependency-Guided Rollback

                       │
                       ▼
                  valid state
                       │
                       ▼
                ③ CONTEXT ROUTER
              /         |          \
       relevance      trigger      active state
      Claude-Mem     PROJECTMEM        MAGE
      agentmemory       PMA
                       │
                       ▼
              ④ HANDOFF MATERIALIZER
                       │
                ExecPlan / Cline
                ai-memory / event views
```

这时候你的 gap 会清楚很多。


#### 你表里的其他竞品，怎么重新定位

|方案|实际技术路径|主要覆盖|是否值得核心分析|
|---|---|---|---|
|**Claude Code Auto Memory**|correction / interaction → Claude 自主写 Markdown；repo scope；启动自动加载|①、③弱|Baseline|
|**Cursor Rules / Memories**|project-scoped persistent notes/rules；Agent 读取/写入；Automation 还有独立 `MEMORIES.md`|①、③|Baseline|
|**Codex AGENTS.md**|version-controlled persistent instruction|Policy plane|不当 memory competitor|
|**Codex ExecPlan**|self-contained living plan，持续 rewrite progress / decisions / next steps|④ + execution state|**值得作为④ baseline**|
|**Claude-Mem**|hooks 捕获 → observations → SQLite/summary → search → timeline → full observation progressive disclosure|**①③**|Retrieval baseline|
|**Basic Memory**|Markdown knowledge base + MCP CRUD/search + Skills 驱动 capture/reflect/defrag/lifecycle|①③④|Workflow baseline|
|**Letta**|attached blocks 常驻 context；archival memory 按需 search；block attach/detach/update/delete|memory tiering|Infrastructure baseline|
|**Graphiti**|episode → temporal fact graph → valid interval + provenance + invalidation|**② Fact truth**|**核心**|
|**PMA**|separate memory-agent → CRUD structured bank + selective reminder|**①②③**|**核心**|
|**MAGE**|hierarchical execution-state tree + active branch + Revise|**②③ execution state**|**核心但不同平面**|
|**MemoRepair**|influence DAG → barrier withdraw → cascade repair → validated republish|**② propagation**|**核心研究竞品**|

Claude Code 当前明确区分人为维护的 `CLAUDE.md` 与 Claude 自动积累的 Auto Memory；后者按 repository 保存、启动时加载，因此它是典型低摩擦 capture，但公开机制依然更像 agent-maintained notes，而不是 dependency-aware state machine。([Claude](https://code.claude.com/docs/en/memory?utm_source=chatgpt.com "How Claude remembers your project - Claude Code Docs"))

Codex 的 **ExecPlan** 反而比笼统所谓“Codex Native Memory”更适合作为你的④竞品：OpenAI 明确要求 ExecPlan 是 **living document（活文档）**，持续记录 progress、next steps 和 decisions，并保证只拿当前工作树和 ExecPlan 就可以恢复工作。([OpenAI Developers](https://developers.openai.com/cookbook/articles/codex_exec_plans?utm_source=chatgpt.com "Using PLANS.md for multi-hour problem solving"))

Claude-Mem 则非常明确是 **Progressive Disclosure（渐进式披露）**：先搜索约 50–100 token/result 的 index，再通过 timeline 查看周边上下文，最后只获取选中 observation 的完整内容。因此它解决的是 token-efficient relevance，而不是 stale dependency。([GitHub](https://github.com/thedotmack/claude-mem?utm_source=chatgpt.com "thedotmack/claude-mem: Persistent Context ..."))

Basic Memory 现在比你原表里写的稍微成熟一点：它已经提供 `memory-reflect`、`memory-defrag`、schema drift、lifecycle 等 Skills。但官方自己把 Skills 定义为“教 Agent 什么时候保存、怎么组织、怎么恢复”的 instructions；也就是说，**maintenance intelligence 主要位于 Skill/Agent policy layer，而不是 storage engine 自动检测 repo truth。** ([Basic Memory](https://docs.basicmemory.com/integrations/skills?utm_source=chatgpt.com "Agent Skills - Basic Memory"))

Letta 的定位也应该保持清楚：它很强的是 **memory residency hierarchy（记忆驻留层级）**——block 可以常驻 system context、attach/detach/update/delete，archival memory 则按需搜索。它提供的是 stateful-agent primitives，而不是“什么时候某个 coding decision 已经失效”的 reconciliation policy。([Letta Docs](https://docs.letta.com/v1-sdk/concepts/stateful-agents/?utm_source=chatgpt.com "Introduction to Stateful Agents"))

## 产品定义
**用现有方法解决 ① capture 和 ③ retrieval，把主要研发/实验资源集中在 ② repository-coupled reconciliation，然后让④成为 canonical state 的派生视图。**

也就是：

```text
① Compiler
借：MOOSEDev / MemoraX / agentmemory
          ↓
② Reconciler                     ← CORE
  temporal validity       ← Graphiti
  artifact freshness      ← EA-Graph
  verify-on-read baseline ← GitHub Copilot
  cascade dependency      ← MemoRepair
  execution rollback      ← Dependency-Guided
          ↓
③ Router
validity hard gate
→ trigger/scope
→ relevance ranking
借 remem / PMA / Claude-Mem
          ↓
④ Materializer
canonical state
→ STATUS / HANDOFF
借 ExecPlan / event-sourced projection
```

> **代码库变化不应该只让记忆变“旧”，而应该触发可解释的有效性状态迁移；若存在依赖溯源，则只沿真实依赖传播 dirty 状态，而不是简单删除、按时间衰减或全量重验证。**

而且我现在会给你的②再加一个非常重要的设计原则：

```text
Evidence changed
      ↓
affected?
 ├─ no  → VALID
 ├─ yes → DIRTY / INVALID
 └─ cannot determine → UNPROVABLE
      ↓
propagate only through
real dependency edges
      ↓
revalidate selectively
```

这里同时吸收了：

- Graphiti 的 **temporal validity**；
- EA-Graph 的 **artifact anchoring + unprovable**；
- MemoRepair 的 **cascade dependency**；
- Dependncy-Guided Rollback 的 **independent support**；
- GitHub Copilot 的 **current-repo verification**。

我认为这已经开始形成一个相当干净的、不是简单拼功能的技术主张了。

另外，**MAGE 给你的最大提醒是：不要把 durable project memory 和 volatile execution state 强行统一。** `current progress / current debugging branch / next action` 很可能应该属于 Execution State Plane；而 `decision / constraint / verified lesson` 才进入 Durable Knowledge Plane。否则你的 State Reconciler 最后会被迫同时处理两个生命周期完全不同的东西。([arXiv](https://arxiv.org/abs/2606.06090?utm_source=chatgpt.com "Beyond Semantic Organization: Memory as Execution State Management for Long-Horizon Agents"))

这也是这轮竞品分析里，我认为除了 stale propagation 之外最值得保留下来的一个新结论。