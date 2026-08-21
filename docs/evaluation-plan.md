# v0 evaluation preregistration

Stage 0 remains unchanged and isolates memory utilization from capture,
compilation, reconciliation, and retrieval. The repo-evolution benchmark tests
the full system with C0 no cross-session memory, C1 length-matched placebo, C2
append-only, C3 strict, C4 hybrid, and C5 oracle current state.

Before confirmation, run three pilots per condition and then freeze the tasks,
model, provider, tools, prompts, budgets, metrics, and code commit. Run ten
confirmations for C0–C4 and optionally three for C5.

Pre-registered metrics:

- capture coverage, gap detection, and capture latency;
- candidate and activation precision/recall;
- false activation, false supersession, and missed invalidation;
- authorized retrieval recall and stale/invalid injection;
- first-action violation, Task Success, and repeated exploration;
- warning delivered/complied/ignored/indeterminate;
- capsule/compiler tokens and Router/hook latency.

The gold safety suite requires zero false activation, false supersession, and
stale/invalid injection. A policy that violates any threshold cannot become the
default. Engineering completion is independent of product benefit: if C3/C4 do
not improve on controls, report the hypothesis as inconclusive or negative and
do not alter frozen tasks or primary metrics after seeing results.
