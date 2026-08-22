# MAGE-inspired execution-state gap benchmark

> 本 benchmark 量化未修改 v0 与 MAGE-inspired execution-state 设计之间的能力差距，并观察 Mem0、Graphiti 在相同任务上的表现。benchmark 不要求或依赖 v0 实现 MAGE 机制；`reference_impl` 仅验证 harness 和 scorer，不属于 v0，也不代表 MAGE 或真实 Agent 的性能上限。

## What this benchmark establishes

The benchmark replays fixed coding traces. It measures black-box final-state
recall and error contamination for every system, then reports MAGE-inspired
capabilities separately as `native`, `derived`, `not_observable`, or
`unsupported`. Missing capabilities are never converted to zero-valued scores.

The in-memory reference implementation is a positive control for scenario,
checkpoint, and scorer correctness. Its A0-A4 results are harness sensitivity
checks, not task-success results or causal estimates of mechanism value.

## Systems and execution modes

| System | Input | Retrieval | Important limitation |
|---|---|---|---|
| reference | deterministic timeline | canonical state | harness control only |
| v0 | synthetic Codex hook replay through `handle_hook` | `ContextRouter` probe | not a live Codex session |
| mem0-vector | boundary trace through Mem0 OSS | Mem0 search | Qdrant-only configuration |
| graphiti | boundary trace as episodes | Graphiti search | graph retrieval, not execution branching |

The v0 adapter uses a production entrypoint with payload-compatible synthetic
events. Reports must retain `payload_compatible_not_live_codex_session`; poor
results cannot be presented without this protocol limitation.

## Metrics

Black-box metrics:

- `final_state_correctness`: required recall, forbidden exclusion, and a strict pass.
- `error_contamination`: contaminated checkpoints divided by non-empty eligible checkpoints.

An empty retrieval is `indeterminate`, never clean. If every scheduled
checkpoint is indeterminate, contamination rate is `null`.

Advanced capability observations:

- `active_path_integrity`
- `branch_isolation`
- `compression_fidelity`
- `maintain_precision`

The deterministic Maintain result is labelled
`pipeline_conformance_not_detection_capability`.

## Repetition and reporting

Keep every run. Formal comparison requires three valid runs per system and
scenario. Reports show raw values plus min, median, max, and range; they do not
show a mean or a single overall score. Fewer than three valid runs is
`insufficient_runs`.

## Commands

```powershell
python scripts/run_execution_state.py validate
python scripts/run_execution_state.py reference --scenario all --variants A0,A1,A2,A3,A4 --fresh
python scripts/run_execution_state.py report --round reference-01
```

Product runs are prepared and executed separately so environment installation
and benchmark repetition remain independent.
