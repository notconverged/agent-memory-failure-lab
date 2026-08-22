# Codex native memory

1. 使用 runner 创建隔离 workspace 和新 Codex 任务。
2. 运行前记录 `~/.codex/memories/` 文件名、时间戳和 hash，不复制无关私人内容。
3. 逐阶段执行 prompts，并在每阶段填写 observation。
4. S4 必须使用新任务。结果始终标记 `existing_global_history`。
