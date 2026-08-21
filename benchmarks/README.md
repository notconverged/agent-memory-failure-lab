# Benchmark catalog

This repository has one active product benchmark.

| Item | Definition |
|---|---|
| Repo Evolution | The primary Coding Agent Memory v0 benchmark |
| C0–C5 | Experimental conditions inside Repo Evolution |
| Current status | Specification and Git snapshot materializer |
| Product evidence | Available only after the execution adapter and scoring loop exist |

Repo Evolution currently validates the scenario, gold memory objects, state
transitions, routing expectations, and reproducible Git snapshots. It does not
yet execute a Coding Agent or establish product benefit.

```powershell
python scripts/run_repo_evolution.py --dry-run --condition C3
python scripts/run_repo_evolution.py --workspace results/repo-evolution/C3 --condition C3
```

The benchmark has an independent version contract. A confirmation run must
record the benchmark version, schema version, product version, Git commit, and
condition. C0–C5 are not separate benchmarks.
