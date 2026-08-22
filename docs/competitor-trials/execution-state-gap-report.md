# MAGE-inspired execution-state gap report

> Status: protocol implemented; product comparison is pending valid smoke and repeated runs.

This report evaluates fixed coding traces. It is not a fair product ranking, a
live-agent evaluation, or a reproduction of MAGE/MemoryArena.

## Protocol disclosures

- v0 remains unchanged. Ingestion uses `handle_hook` with synthetic,
  payload-compatible Codex events; retrieval uses a `ContextRouter` probe.
- `reference_impl` is a harness positive control, not a product or theoretical
  performance upper bound.
- Missing advanced capabilities remain `unsupported` or `not_observable` and
  are never converted to zero-valued scores.
- Empty retrieval is indeterminate for contamination and cannot count as clean.
- Formal comparison requires three valid runs for each system and scenario.
- Deterministic Maintain measures pipeline conformance, not detection ability.

## Current result status

Implementation verification on 2026-08-22:

- All 15 offline reference cells (three scenarios by A0-A4) executed; A0 passed
  every registered assertion and A1-A4 produced the registered missing-mechanism
  differences.
- v0 smoke `v0-ledger-smoke-20260822` was correctly marked invalid: hook capture
  wrote isolated evidence, but the first compiler job failed with Windows
  access-denied (`WinError 5`). No retrieval score was produced.
- `amlab-mem0` exists, but explicit benchmark config/model credentials are absent.
- `amlab-graphiti` is not installed. Neither product row has been fabricated.
The offline reference suite can be generated with:

```powershell
python scripts/run_execution_state.py reference `
  --scenario all `
  --variants A0,A1,A2,A3,A4 `
  --round reference-01 `
  --fresh

python scripts/run_execution_state.py report --round reference-01
```

Real v0, Mem0, and Graphiti rows must only be added from valid isolated runs.
The report generator replaces this placeholder with raw runs, min/median/max
tables, capability distributions, and explicit failure counts.
