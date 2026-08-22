# Mem0

1. 创建并验证 `amlab-mem0`。
2. 显式配置 LLM、embedding、Qdrant 和 history 路径。
3. 使用 run_id 作为隔离 filter，不使用默认 /tmp 或 home 数据。
4. 逐阶段执行 add/search/update/delete，并导出 history。
