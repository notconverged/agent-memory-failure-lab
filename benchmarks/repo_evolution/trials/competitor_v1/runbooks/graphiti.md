# Graphiti + Kuzu

1. 创建并验证 `amlab-graphiti`。
2. 将 `KUZU_DB` 指向本 run 的持久文件，禁止使用 :memory:。
3. 每阶段以独立 episode 写入，记录 episode UUID、valid_at 和 invalid_at。
4. S4 检查 temporal invalidation、provenance 和 fresh search。
