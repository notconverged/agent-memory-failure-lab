# Benchmark catalog

This repository has two complementary benchmark entrypoints.

| Item | Definition |
|---|---|
| Execution State Gap | Active MAGE-inspired external gap protocol for unchanged v0, Mem0, and Graphiti |
| Reference A0–A4 | Positive-control sensitivity variants; not product configurations or a theoretical upper bound |
| Repo Evolution | Durable-memory C0–C5 compatibility entrypoint; ledger phases reference the canonical execution-state scenario |
| Reporting | Raw runs, black-box metrics, capability matrix, and limitations; never one overall leaderboard score |

Execution State Gap uses fixed coding traces and product-native ingestion and
retrieval. Its v0 path is a payload-compatible synthetic replay through the
production hook, not a live Codex session. Unsupported and unobservable
capabilities are reported as statuses rather than numeric zeroes.

```powershell
python scripts/run_repo_evolution.py --dry-run --condition C3
python scripts/run_execution_state.py validate
python scripts/run_execution_state.py reference --scenario all --variants A0,A1,A2,A3,A4 --fresh
python scripts/run_repo_evolution.py --workspace results/repo-evolution/C3 --condition C3
```

See [Execution State Gap](execution_state/README.md) and the
[evaluation protocol](../docs/evaluation-plan.md). C0–C5 are not A0–A4 and are
not separate benchmarks.
