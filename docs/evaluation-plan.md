# Coding Agent Memory v0 evaluation protocol

## Status

The active external gap protocol is `benchmarks/execution_state`, version
`0.1.0-draft.1`. It observes unchanged v0, Mem0, and Graphiti against a neutral
MAGE-inspired execution-state schema. It reports black-box retrieval metrics
and capability statuses, not one total product score or live-Agent performance.
The v0 adapter uses hook-compatible synthetic replay through the production
hook, not a live Codex session.

Repo Evolution remains the durable-memory C0-C5 compatibility entrypoint.
Its current version is
`0.1.0-draft.1`, with schema version `1` and protocol status `draft`.

The current runner validates the specification and materializes reproducible
Git snapshots. It does not yet execute an Agent or establish product benefit.
C0–C5 are experimental conditions inside Repo Evolution, not separate
benchmarks.

## Evaluation question

Does the complete capture → compile → reconcile → route → delivery system help
a Coding Agent recover current project state without introducing false,
superseded, stale, or irrelevant memory?

Engineering completion and product benefit are evaluated separately. Passing
replay, state-machine, permission, isolation, and latency tests establishes an
engineering result. Only frozen Agent runs can establish behavioral evidence.

## Conditions

| Condition | Definition |
|---|---|
| C0 | No cross-session memory |
| C1 | Length-matched placebo |
| C2 | Append-only memory without reconciliation |
| C3 | Strict promotion and reconciliation |
| C4 | Hybrid promotion and reconciliation |
| C5 | Oracle current project state |

C1 controls for additional context length. C5 is an upper bound, not a product
configuration. The primary product comparisons are C3/C4 against C0–C2.

## Isolation invariants

Every comparable run must keep the following fixed:

- exact model/provider/protocol and reasoning configuration;
- system prompt, tool schema, tool set, budgets, and maximum steps;
- benchmark version, scenario, task order, and verifier;
- Agent adapter and memory delivery location;
- initial repository snapshot.

Every phase must use a fresh Agent session and clean workspace. Session resume,
fork, previous-session references, hidden workspace instructions, shared cache,
copied traces, and any persistent memory channel outside the condition are
forbidden.

Only the declared memory policy and its delivered context may differ between
conditions. Placebo and treatment prompts must use the same envelope so a model
cannot identify the condition from prompt shape alone.

## Manifest contract

Every prepared or executed run records at least:

```json
{
  "benchmark_id": "repo-evolution",
  "benchmark_version": "0.1.0-draft.1",
  "schema_version": 1,
  "protocol_status": "draft",
  "condition": "C3",
  "product_version": "0.1.0",
  "git_commit": "...",
  "agent_executed": false
}
```

Executed runs additionally record model/provider/protocol, prompts and tool
schema hashes, budgets, session ids, initial workspace hashes, event coverage,
memory revisions, delivery records, behavior trace, verifier result, and cost.

## Metrics

Pre-registered metrics are:

- capture coverage, gap detection, and capture latency;
- candidate and activation precision/recall;
- false activation, false supersession, and missed invalidation;
- authorized retrieval recall and stale/invalid injection;
- first-action violation, Task Success, and repeated exploration;
- warning delivered/complied/ignored/indeterminate;
- capsule/compiler tokens and Router/hook latency.

The gold safety suite requires zero false activation, false supersession, and
stale/invalid injection before a policy can become the default.

## Pilot, freeze, and confirmation

Run three pilots per condition. Pilots may be used to fix implementation bugs
or unusable tasks, but every change must bump the draft benchmark version.

Before confirmation, freeze the benchmark version, tasks, model, provider,
tools, prompts, budgets, metrics, execution adapter, and code commit. Change
`protocol_status` to `frozen` only at that point.

Run ten confirmations for C0–C4 and optionally three for C5. If C3/C4 do not
improve on controls, report the hypothesis as inconclusive or negative. Do not
change frozen tasks or primary metrics after inspecting outcomes.

## Current commands

```powershell
python scripts/run_repo_evolution.py --dry-run --condition C3
python scripts/run_repo_evolution.py --workspace results/repo-evolution/C3 --condition C3
```

The second command creates Git snapshots and a manifest only. Paid-model Agent
execution is intentionally out of the current materializer.
