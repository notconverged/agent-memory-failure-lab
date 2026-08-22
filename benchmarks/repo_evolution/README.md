# Repo Evolution benchmark

- Version: `0.1.0-draft.1`
- Schema: `1`
- Protocol status: `draft`

This directory is the durable-memory compatibility entrypoint for the
canonical `execution_state/scenarios/coding/ledger-rounding-v2.json` scenario.
`scenario.json` is a descriptor; the runner resolves its five Git phases from
that canonical file. Existing C0-C5 semantics and durable-memory gold remain
unchanged. C0-C5 do not map to the reference-only A0-A4 variants.


This executable synthetic scenario uses a multi-session pivot/filler structure
inspired by MemoryCode and correction/commit patterns calibrated from SWE-chat.
It does not copy public sample text. Each phase is a complete repository snapshot
that the runner materializes and commits in order.

```powershell
python scripts/run_repo_evolution.py --dry-run --condition C3
python scripts/run_repo_evolution.py --workspace results/repo-evolution/C3 --condition C3
```

The second command only prepares the Git evolution and versioned run manifest.
It does not call a paid model. Agent execution is intentionally a separate
adapter so tasks, model, tools, prompts, and metrics can be frozen before pilot
runs. Until that adapter and its scoring loop exist, this benchmark does not
establish product benefit.

Pilot protocol: 3 runs per condition. After freezing task/model/tool/metric/prompt,
run 10 confirmations for C0–C4 and optionally 3 for C5. Safety gold requires zero
false activation, false supersession, and stale/invalid injection.

C0–C5 are conditions inside this benchmark, not separate benchmarks. See the
[benchmark catalog](../README.md) and
[evaluation protocol](../../docs/evaluation-plan.md) for the active hierarchy
and isolation requirements.
