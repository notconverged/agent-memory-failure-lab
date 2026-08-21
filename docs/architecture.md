# Coding Agent Memory v0 Architecture

## 1. Boundary

v0 is a host-independent, local-first Python Core. Codex is the first adapter,
not the product boundary. Procedure is deliberately inactive in v0.

```text
Codex hooks → atomic spool → Event Log → SQLite projection
                                ↓
                    isolated Compiler job
                                ↓
revision/ref state machine → Reconciler → Router → hook/MCP delivery
```

The durable memory kinds are exactly `Decision`, `Constraint`, `ProjectFact`,
and `Failure`. TODO, current progress, and plans belong to `ExecutionNode`, whose
states are `pending/active/blocked/completed/abandoned`.

## 2. Processes

- Hooks perform a small atomic spool write and never compile memory inline.
- A host-managed MCP stdio process serves read-only queries and feedback.
- `PostCompact`, `Stop`, or `SessionEnd` creates a bounded `CompilerJob` and
  launches a hidden one-shot worker.
- A repository-scoped lease allows only one compiler worker. It drains pending
  jobs and exits; there is no resident daemon.
- `CodexExecCompiler` runs `codex exec --ephemeral --ignore-user-config
  --sandbox read-only --output-schema`. A recursion marker disables plugin hooks
  inside the compiler process.

## 3. Authority and persistence

`events.jsonl` is the replay authority. SQLite stores revisions, branch refs,
jobs, FTS5, execution nodes, leases, deliveries, and feedback projections. The
Markdown Inspector is read-only. `agent-memory rebuild` deletes projections and
replays the Event Log.

Every `MemoryRevision` is immutable. A branch-level `MemoryRef` identifies the
current revision and status. The repository baseline branch is inherited by
other branches; a branch ref overlays the baseline ref with the same memory ID.

Normal deletion creates a `tombstoned` revision. Explicit `purge --yes` removes
all events that mention the memory, atomically replaces the log, and rebuilds
the projection.

## 4. Evidence and uncertainty

Hooks only capture allowed, bounded fields. Strings are redacted and truncated;
nested structures have depth/item limits. Complete transcripts, environment
variables, and large outputs are not read. Each repository has a conservative
256 MiB event payload quota.

The system must represent four failure modes instead of hiding them:

- incomplete capture → candidate remains `proposed`;
- uncertain freshness → `needs_revalidation`;
- implementation contradicts normative memory → `conflicted`;
- no longer provable → `unprovable`.

Decision and Constraint require normative evidence. Code divergence cannot
supersede them. Direct repo/test evidence may revise a ProjectFact. Failure is
conditional history and never becomes a prohibition automatically. Uncommitted
worktree changes can only mark memory `needs_revalidation`.

## 5. Routing and delivery

The fixed order is scope → status → supersession → freshness → anchor → FTS5 →
budget. `active` revisions may be delivered as facts. `conflicted`,
`unprovable`, and `needs_revalidation` are labeled warnings with evidence
pointers. Other states are not delivered.

Budgets are 180 estimated tokens at `SessionStart`, 800 at
`UserPromptSubmit`, and 200 at `PreToolUse`. Session delivery history suppresses
duplicate revisions. The PreToolUse path performs no LLM call, Git operation,
repository scan, or long transaction; failures are fail-open and captured as
`GateUnavailable`.

## 6. Trust boundary

The Agent-facing MCP surface is limited to `memory_status`, `memory_context`,
`memory_search`, `memory_get`, `memory_history`, and `memory_feedback`.
Feedback appends evidence but never moves an active ref. Editing, invalidation,
restore, purge, and rebuild remain human CLI operations.

Dependency edges are limited to direct file/symbol/config/test anchors and
evidence-backed memory-to-memory edges. Inferred edges remain proposed and do
not propagate dirtiness. Rollback is a read-only impact report in v0.
