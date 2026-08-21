# Repo-evolution benchmark

This executable synthetic scenario uses a multi-session pivot/filler structure
inspired by MemoryCode and correction/commit patterns calibrated from SWE-chat.
It does not copy public sample text. Each phase is a complete repository snapshot
that the runner materializes and commits in order.

```powershell
python scripts/run_repo_evolution.py --dry-run --condition C3
python scripts/run_repo_evolution.py --workspace results/repo-evolution/C3 --condition C3
```

The second command only prepares the Git evolution and frozen run manifest. It
does not call a paid model. Agent execution is intentionally a separate adapter
so tasks, model, tools, prompts, and metrics can be frozen before pilot runs.

Pilot protocol: 3 runs per condition. After freezing task/model/tool/metric/prompt,
run 10 confirmations for C0–C4 and optionally 3 for C5. Safety gold requires zero
false activation, false supersession, and stale/invalid injection.
