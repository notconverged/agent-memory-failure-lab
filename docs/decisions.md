# Decision Log

## 2026-08-19 — Make the product the repository mainline

### Decision

The repository builds a local-first Coding Agent Memory product. Research and
evaluation exist to test product risks; they do not define a second product
roadmap or replace the capture/compile/reconcile/route/delivery architecture.

### Consequence

Product code lives in `src/agent_memory`, Codex remains a thin adapter, and
evaluation reports engineering completion separately from behavioral benefit.

## 2026-08-21 — Freeze the v0 memory boundary

### Decision

Durable memory contains only Decision, Constraint, ProjectFact, and Failure.
Procedure is inactive in v0. TODO, plan, and current progress belong to a
separate Execution State plane.

The Event Log is authoritative; SQLite and Markdown are rebuildable
projections. Promotion defaults to strict, and capture gaps, freshness
uncertainty, conflicts, and unprovable claims remain explicit.

### Consequence

- uncommitted code cannot authorize durable truth;
- code cannot supersede normative memory;
- MCP is read-only plus feedback;
- no vector search, cloud sync, or automatic rollback enters v0.

## 2026-08-21 — Retire the Decimal Stage 0 harness

### Decision

Remove the paper-oriented Decimal runner, fixtures, DSH configuration, tests,
and dedicated documentation without an archive or compatibility wrapper.

### Rationale

That harness injected a fixed host-managed memory and did not exercise the
product Core, Hooks, Compiler, Reconciler, or Router. Passing it could not
establish product correctness or benefit, while keeping it created a second
roadmap and additional runtime maintenance.

### Consequence

Repo Evolution is the only active v0 benchmark. Fresh sessions, clean
workspaces, placebo controls, fixed experimental variables, versioned manifests,
and protocol freezing remain as general evaluation requirements.
