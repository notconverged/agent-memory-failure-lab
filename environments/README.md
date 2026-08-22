# 实验环境与重装边界

Benchmark/v0 与竞品依赖必须分开。普通 benchmark 重跑只新建 `run_id`、数据目录和证据目录，不重装环境。

| 系统 | 环境 | 本地数据 |
|---|---|---|
| Benchmark/v0 | `agent-memory-failure-lab` | `results/runs/` 与 v0 ledger |
| Codex native | 当前 Codex App/CLI | 只记录全局 memory 前后快照，标记历史污染 |
| Claude-Mem | Node/Bun 原生安装 | `CLAUDE_MEM_DATA_DIR=.local-lab/competitors/claude-mem/data/<run-id>` |
| Basic Memory | `amlab-basic-memory` | `.local-lab/competitors/basic-memory/data/<run-id>/` |
| Mem0 | `amlab-mem0` | `.local-lab/competitors/mem0/data/<run-id>/` |
| Letta | `amlab-letta` | 远程 benchmark agent；本地保存 agent ID 与脱敏导出 |
| Graphiti | `amlab-graphiti` | `.local-lab/competitors/graphiti/data/<run-id>/graphiti.kuzu` |

API key 只能通过环境变量传入。YAML、lock、manifest、博客和截图都不得包含密钥。

## 第一次创建

```powershell
powershell -ExecutionPolicy Bypass `
  -File scripts/manage_competitor_env.ps1 `
  -Action create `
  -System mem0

powershell -ExecutionPolicy Bypass `
  -File scripts/manage_competitor_env.ps1 `
  -Action verify `
  -System mem0

powershell -ExecutionPolicy Bypass `
  -File scripts/manage_competitor_env.ps1 `
  -Action export-lock `
  -System mem0
```

`verify` 只做版本、import 和必需变量检查，不写正式记忆。成功后，lock 位于 `environments/locks/`。

## 普通重跑

```powershell
conda run -n agent-memory-failure-lab `
  python scripts/run_competitor_trial.py prepare `
  --system mem0 --round round-01 --fresh
```

命令会输出 `run_id`，并创建互不覆盖的 workspace、data_dir 和结果目录。随后逐阶段运行：

```powershell
conda run -n agent-memory-failure-lab `
  python scripts/run_competitor_trial.py execute `
  --system mem0 --round round-01 --run-id <run-id> `
  --phase S0_baseline

conda run -n agent-memory-failure-lab `
  python scripts/run_competitor_trial.py checkpoint `
  --system mem0 --round round-01 --run-id <run-id> `
  --phase S0_baseline
```

Python adapter 由 benchmark 环境发起，但真正通过 `conda run -n <竞品环境>` 执行。adapter request 和结果都写入对应 phase 目录。

## Adapter 显式配置

- Mem0：`AMLAB_MEM0_CONFIG` 指向 JSON。配置中的 Qdrant 与 history 路径必须位于当前 run 的 `data_dir`，否则 adapter 拒绝运行。
- Letta：设置 `LETTA_API_KEY`、`AMLAB_LETTA_MODEL`、`AMLAB_LETTA_EMBEDDING`。每个 run 创建并复用一个独立 agent；adapter 不自动删除 agent。
- Graphiti：当前首轮 adapter 使用官方 OpenAI 默认 provider，因此需要 `OPENAI_API_KEY`；Kuzu 路径由 run 强制指定。
- 统一记录模型：可设置 `AMLAB_MODEL_PROVIDER` 和 `AMLAB_MODEL_ID`，它们会进入 `install/environment.json`，密钥不会进入。

Basic Memory、Codex native 和 Claude-Mem 按 `benchmarks/repo_evolution/trials/competitor_v1/runbooks/` 人工操作。

## 中断恢复

```powershell
conda run -n agent-memory-failure-lab `
  python scripts/run_competitor_trial.py resume `
  --system mem0 --round round-01 --run-id <run-id>
```

恢复会核对环境声明 hash、checkpoint 和 Git HEAD。环境 YAML 或 lock 变化后，旧 run 会被拒绝，必须新建 `run_id`。

## 精确重装

只有 import 失败、依赖冲突、产品升级、lock 不一致或专门评测安装体验时才重装：

```powershell
powershell -ExecutionPolicy Bypass `
  -File scripts/manage_competitor_env.ps1 `
  -Action recreate `
  -System mem0 `
  -ConfirmRecreate
```

脚本只允许四个固定环境名，并要求显式 `-ConfirmRecreate`。重装后依次执行 `verify`、`export-lock`，再创建新 run；不得恢复旧 run。

## 结果检查

每个 run 的 `install/environment.json` 至少记录系统版本、Conda 环境、Python、lock hash、模型、benchmark 版本和真实数据目录。每个 phase 的 `observation.json` 初始分数为 `null`；只有检查原始存储和行为证据后才人工填写，未观察项不会自动算作通过。
