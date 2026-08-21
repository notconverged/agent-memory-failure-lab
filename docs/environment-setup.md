# Windows 与 WSL 环境记录

## 结论

WSL Ubuntu 是一个独立的 Linux 用户空间。Windows 中安装的 Node.js、pnpm、
Git、DSH CLI、DSH 源码依赖和 shell 环境变量，不应假设会自动出现在
Ubuntu 中。

因此，如果实验改为在 Ubuntu 内执行，必须在 Ubuntu 内重新准备 Node.js、
pnpm、Git、DSH CLI 或源码依赖，以及 `DEEPSEEK_API_KEY` 等运行时变量。

项目源代码可以从 `/mnt/d/...` 访问，但正式实验建议把项目放在 WSL 的
Linux 文件系统中，例如 `~/projects/agent-memory-failure-lab`，减少跨文件
系统的权限、大小写、换行符和性能差异。Windows 与 WSL 的结果不能混合进
同一个 confirmation 统计；它们应视为不同的 runtime condition。

当前已记录的 Windows 状态：

```text
WSL executable: available
Ubuntu distribution: not installed or not initialized
Windows Node.js: v24.15.0
Windows pnpm: 11.19.0
Windows dsh: not found
```

本项目 Stage 0 原计划是 Windows native headless baseline：DSH
`v0.1.0-rc.7`、commit `99f6f02`。如果最终改用 WSL，必须在 manifest 中记录
`platform=linux`，并单独建立 WSL baseline。运行脚本现在会自动记录实际平台。

## 建议操作顺序

### 1. 在管理员 PowerShell 安装 Ubuntu

```powershell
wsl --install -d Ubuntu
```

如果系统要求重启，先重启，再从开始菜单打开 Ubuntu，完成 Linux 用户名和
密码初始化。参考[官方 WSL 安装文档](https://learn.microsoft.com/en-us/windows/wsl/install)
和[官方 WSL 基础命令文档](https://learn.microsoft.com/en-us/windows/wsl/basic-commands)。

安装后在 PowerShell 检查：

```powershell
wsl --status
wsl --list --verbose
```

目标是看到 Ubuntu 且 VERSION 为 `2`。

### 2. 在 Ubuntu 内准备基础工具

进入 Ubuntu：

```powershell
wsl -d Ubuntu
```

然后在 Ubuntu shell 中执行：

```bash
sudo apt update
sudo apt install -y git curl build-essential ca-certificates
```

Node.js 和 pnpm 要在 Ubuntu 内重新配置。Node 版本保持项目基线要求：
Node `22.19+` 或 `24+`；pnpm 固定为 `11.7.0`。

```bash
node --version
corepack enable
corepack prepare pnpm@11.7.0 --activate
pnpm --version
git --version
```

不要把 Windows 的 `node_modules`、全局 npm 包或 pnpm store 当作 Ubuntu 的
安装结果。

### 3. 在 Ubuntu 内安装或构建 DSH

需要。DSH 在哪个环境中执行，就必须在那个环境中可被该环境的 PATH 找到。
如果采用源码方式，流程是：

```bash
git clone https://github.com/deepseek-ai/deepseek-harness.git ~/src/deepseek-harness
cd ~/src/deepseek-harness
git fetch --all --tags
git checkout 99f6f02
corepack enable
corepack prepare pnpm@11.7.0 --activate
pnpm install --frozen-lockfile
```

构建和 CLI 启动命令以该 commit 的官方 CLI README 为准；完成后必须确认：

```bash
dsh --version
git rev-parse HEAD
```

如果 DSH 官方提供的是已打包 CLI，也可以按官方 README 使用包安装方式，
但仍然要在 Ubuntu 内安装，不能只依赖 Windows 的 `dsh`。

### 4. 配置 API key

API key 只放在 Ubuntu 的运行时环境中，不写入项目文件、manifest、trace 或
Git。当前 shell 临时配置可以使用：

```bash
read -rsp "DEEPSEEK_API_KEY: " DEEPSEEK_API_KEY
echo
export DEEPSEEK_API_KEY
test -n "$DEEPSEEK_API_KEY" && echo "API key is configured"
```

### 5. 准备项目工作区

推荐把项目复制或重新 clone 到 Ubuntu 文件系统：

```bash
mkdir -p ~/projects
cd ~/projects
# 使用项目对应的 GitHub remote clone agent-memory-failure-lab
cd agent-memory-failure-lab
```

然后在项目根目录执行：

```bash
python3 --version
python3 -m pytest -q
python3 scripts/run_episode.py --dry-run --condition no_memory
python3 scripts/run_episode.py --dry-run --condition relevant_memory
```

### 6. DSH preflight 与 Stage 0

确认 `dsh`、model、provider 和 API key 都在 Ubuntu shell 内可用后执行：

```bash
dsh --profile headless --patch configs/minimal.cordis.yml --dump-config
python3 scripts/run_episode.py --smoke
python3 scripts/run_episode.py --confirm --replicates 10
```

运行结果必须检查 manifest 中的 `platform=linux`、DSH commit、config hash、
Node/pnpm、provider/model，以及 WSL 的 session root、DSH home 和 workspace。

## 环境切换规则

```text
Windows native DSH
    ├─ Windows Node/pnpm/Git
    ├─ Windows DSH installation
    └─ platform = windows

WSL Ubuntu DSH
    ├─ Ubuntu Node/pnpm/Git
    ├─ Ubuntu DSH installation
    └─ platform = linux
```

两套环境可以使用同一份 Git 代码，但不能共享未审查的 session、workspace、
DSH home、node_modules 或实验结果。Stage 0 的比较只能在同一个 runtime
环境内部完成。
