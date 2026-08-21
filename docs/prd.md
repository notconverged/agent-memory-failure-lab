# Coding Agent Memory v0 PRD

## Goal

Let a personal Coding Agent recover small, evidence-backed project state across
sessions without pretending that captured memory is always complete or correct.

## In scope

- one user and one Git repository with multiple branches;
- local Event Log, replayable SQLite projection, and read-only Markdown view;
- durable `Decision`, `Constraint`, `ProjectFact`, and conditional `Failure`;
- separate `ExecutionNode` plane for TODO and active progress;
- isolated compiler, strict/hybrid promotion, evidence-driven reconciliation;
- deterministic FTS5/anchor routing and bounded Codex delivery;
- human CLI, read-only＋feedback MCP, thin Codex plugin;
- Windows dogfood and Linux CI tests;
- Repo Evolution specification/materializer with C0–C5 conditions.

## Out of scope

Procedure, multi-user, multi-repository sharing, cloud sync, vector retrieval,
complete code dependency graphs, automated code rollback, full transcripts,
and public branding are not v0 features.

## Functional acceptance

1. Hook events survive process interruption in an atomic spool.
2. SQLite can be removed and rebuilt from `events.jsonl`.
3. Every memory edit creates a new immutable revision and branch ref.
4. Capture gaps prohibit automatic activation or supersession.
5. Code divergence creates a conflict for Decision/Constraint, not replacement.
6. ProjectFact may update from direct repository/test evidence.
7. Failure remains conditional and never automatically becomes a rule.
8. Router never injects stale/invalid states as facts.
9. PreToolUse fails open and records `GateUnavailable`; p95 target is ≤300 ms.
10. Agent MCP feedback cannot mutate active refs.
11. Procedure and TODO cannot enter the durable memory schema.

## Promotion policies

`strict` is the initial default. Explicit user/project norms authorize
Decision/Constraint; direct repository/test evidence authorizes verifiable
ProjectFact and observed Failure. Other candidates remain proposed.

`hybrid` additionally permits independently corroborated, non-normative
interpretations with no counterevidence. It may become default only after the
safety suite reports zero false activation, false supersession, and stale or
invalid injection while improving coverage or latency.

## Product evidence

Engineering completion and product benefit are separate. Replay, isolation,
permissions, latency, state-machine, and closed-loop tests establish v0
engineering completion. C3/C4 failing to beat controls is reported as an
inconclusive or negative hypothesis, without changing frozen tasks or metrics.

Repo Evolution is currently a draft specification and Git snapshot
materializer. It does not become product evidence until the Agent execution
adapter, scoring loop, protocol freeze, and confirmation runs are complete.
