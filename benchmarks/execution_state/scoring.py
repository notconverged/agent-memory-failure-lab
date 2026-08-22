from __future__ import annotations

import re
import statistics
from collections import Counter, defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from benchmarks.execution_state.adapters.base import CAPABILITY_NAMES, write_json


def _matches(text: str, patterns: Iterable[str]) -> list[bool]:
    return [
        bool(re.search(pattern, text, re.IGNORECASE | re.DOTALL))
        for pattern in patterns
    ]


def score_basic(
    observations: dict[str, dict[str, Any]], gold: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any], bool]:
    black_box = gold["black_box"]
    final_step = str(black_box["final_checkpoint"])
    final = observations.get(
        final_step,
        {"query_status": "error", "retrieval_text": "", "error": "missing checkpoint"},
    )
    query_error = final.get("query_status") == "error"
    final_text = str(final.get("retrieval_text", ""))
    empty = final.get("query_status") == "empty" or not final_text.strip()
    required = _matches(final_text, black_box["required_final_assertions"])
    forbidden = _matches(final_text, black_box["forbidden_final_assertions"])
    required_recall = sum(required) / len(required) if required else 1.0
    forbidden_exclusion = (
        None
        if empty
        else (
            sum(not item for item in forbidden) / len(forbidden) if forbidden else 1.0
        )
    )
    final_score = {
        "required_recall": 0.0 if empty else required_recall,
        "forbidden_exclusion": forbidden_exclusion,
        "strict_final_state_pass": int(
            not empty and all(required) and not any(forbidden)
        ),
        "empty_retrieval": empty,
        "required_matches": required,
        "forbidden_matches": forbidden,
    }

    contaminated = clean = indeterminate = 0
    checkpoint_details: dict[str, Any] = {}
    for step, specification in black_box["contamination_checkpoints"].items():
        observation = observations.get(
            step,
            {
                "query_status": "error",
                "retrieval_text": "",
                "error": "missing checkpoint",
            },
        )
        status = observation.get("query_status")
        text = str(observation.get("retrieval_text", ""))
        if status == "error":
            query_error = True
            classification = "query_error"
            hits: list[bool] = []
        elif status == "empty" or not text.strip():
            indeterminate += 1
            classification = "indeterminate"
            hits = []
        else:
            hits = _matches(text, specification["forbidden_assertions"])
            if any(hits):
                contaminated += 1
                classification = "contaminated"
            else:
                clean += 1
                classification = "clean"
        checkpoint_details[step] = {
            "classification": classification,
            "forbidden_matches": hits,
        }
    scheduled = contaminated + clean + indeterminate
    eligible = contaminated + clean
    contamination = {
        "scheduled_checkpoint_count": scheduled,
        "eligible_checkpoint_count": eligible,
        "contaminated_count": contaminated,
        "clean_count": clean,
        "indeterminate_count": indeterminate,
        "error_contamination_rate": contaminated / eligible if eligible else None,
        "indeterminate_rate": indeterminate / scheduled if scheduled else None,
        "checkpoints": checkpoint_details,
    }
    return final_score, contamination, query_error


def _maintain_metrics(
    observed: dict[str, str], expected: dict[str, str]
) -> dict[str, Any]:
    tp = fp = fn = tn = 0
    for step, gold_value in expected.items():
        actual = observed.get(step)
        if gold_value == "fail" and actual == "fail":
            tp += 1
        elif gold_value == "pass" and actual == "fail":
            fp += 1
        elif gold_value == "fail" and actual != "fail":
            fn += 1
        else:
            tn += 1
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision is not None and recall is not None and precision + recall
        else None
    )
    return {
        "interpretation": "pipeline_conformance_not_detection_capability",
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "confusion_matrix": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
    }


def score_advanced(result: dict[str, Any], gold: dict[str, Any]) -> dict[str, Any]:
    capabilities = result["capabilities"]
    specification = gold["execution_state"]
    states = result.get("all_states", result.get("states", {}))
    advanced: dict[str, Any] = {}

    path_status = capabilities["active_path_integrity"]["support_status"]
    if path_status in {"native", "derived"}:
        checks = []
        for checkpoint in specification["checkpoints"]:
            state = states.get(str(checkpoint["step_index"]))
            checks.append(
                bool(state)
                and state["effective_active_raw_sequence"]
                == checkpoint["expected_active_raw_step_keys"]
                and state["cursor"]["revision_generation"]
                == checkpoint["expected_revision_generation"]
            )
        advanced["active_path_integrity"] = {
            "support_status": path_status,
            "value": sum(checks) / len(checks) if checks else None,
            "checkpoint_passes": checks,
        }
    else:
        advanced["active_path_integrity"] = {
            "support_status": path_status,
            "value": None,
        }

    branch_status = capabilities["branch_isolation"]["support_status"]
    if branch_status in {"native", "derived"}:
        final_state = states[str(max(map(int, states)))]
        active = set(final_state["effective_active_raw_sequence"])
        excluded = specification["excluded_step_keys_at_final"]
        contamination = [item for item in excluded if item in active]
        advanced["branch_isolation"] = {
            "support_status": branch_status,
            "value": int(not contamination),
            "contamination_count": len(contamination),
            "contaminating_step_keys": contamination,
        }
    else:
        advanced["branch_isolation"] = {
            "support_status": branch_status,
            "value": None,
        }

    compression_status = capabilities["compression_fidelity"]["support_status"]
    if compression_status in {"native", "derived"}:
        final_state = states[str(max(map(int, states)))]
        nodes_by_key = {item["step_key"]: item for item in final_state["nodes"]}
        node_id_to_key = {
            item["node_id"]: item["step_key"] for item in final_state["nodes"]
        }
        checks = []
        for assertion in specification["summary_assertions"]:
            node = nodes_by_key.get(assertion["step_key"])
            cover = (
                [node_id_to_key.get(item) for item in node["cover_node_ids"]]
                if node
                else []
            )
            content = str(node.get("summary", "")) if node else ""
            checks.append(
                bool(node)
                and cover == assertion["cover_step_keys"]
                and all(
                    re.search(pattern, content, re.IGNORECASE | re.DOTALL)
                    for pattern in assertion["must_include"]
                )
            )
        advanced["compression_fidelity"] = {
            "support_status": compression_status,
            "value": sum(checks) / len(checks) if checks else None,
            "summary_passes": checks,
        }
    else:
        advanced["compression_fidelity"] = {
            "support_status": compression_status,
            "value": None,
        }

    maintain_status = capabilities["maintain_precision"]["support_status"]
    if maintain_status in {"native", "derived"}:
        advanced["maintain_precision"] = {
            "support_status": maintain_status,
            "value": _maintain_metrics(
                result.get("maintain_decisions", {}),
                specification["maintain_decisions"],
            ),
        }
    else:
        advanced["maintain_precision"] = {
            "support_status": maintain_status,
            "value": None,
        }
    return advanced


def score_result(
    result: dict[str, Any], gold: dict[str, Any], gate_valid: bool = True
) -> dict[str, Any]:
    final, contamination, query_error = score_basic(result["observations"], gold)
    if not gate_valid:
        status = "invalid"
    elif query_error:
        status = "execution_failure"
    else:
        status = "valid"
    return {
        "system": result["system"],
        "scenario_id": result["scenario_id"],
        "run_id": result["run_id"],
        "variant": result.get("variant"),
        "run_status": status,
        "final_state_correctness": final,
        "error_contamination": contamination,
        "advanced": score_advanced(result, gold),
    }


def _metric_values(score: dict[str, Any]) -> dict[str, float | None]:
    return {
        "required_recall": score["final_state_correctness"]["required_recall"],
        "forbidden_exclusion": score["final_state_correctness"]["forbidden_exclusion"],
        "strict_final_state_pass": float(
            score["final_state_correctness"]["strict_final_state_pass"]
        ),
        "error_contamination_rate": score["error_contamination"][
            "error_contamination_rate"
        ],
        "indeterminate_rate": score["error_contamination"]["indeterminate_rate"],
    }


def aggregate_scores(scores: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[tuple[str, str, str | None], list[dict[str, Any]]] = defaultdict(list)
    for score in scores:
        groups[(score["system"], score["scenario_id"], score.get("variant"))].append(
            score
        )
    output: dict[str, Any] = {}
    for (system, scenario, variant), items in sorted(groups.items()):
        key = "/".join(part for part in (system, scenario, variant) if part)
        valid = [item for item in items if item["run_status"] == "valid"]
        metrics: dict[str, Any] = {}
        for metric in _metric_values(items[0]):
            raw = [
                _metric_values(item)[metric]
                for item in valid
                if _metric_values(item)[metric] is not None
            ]
            numeric = [float(item) for item in raw if item is not None]
            metrics[metric] = {
                "raw": raw,
                "min": min(numeric) if numeric else None,
                "median": statistics.median(numeric) if numeric else None,
                "max": max(numeric) if numeric else None,
                "range": max(numeric) - min(numeric) if numeric else None,
                "valid_value_count": len(numeric),
            }
            if metric == "strict_final_state_pass":
                metrics[metric]["pass_count"] = sum(item == 1.0 for item in numeric)
        capability_distribution: dict[str, Any] = {}
        for name in CAPABILITY_NAMES:
            statuses = [item["advanced"][name]["support_status"] for item in items]
            counts = Counter(statuses)
            capability_distribution[name] = {
                "counts": dict(sorted(counts.items())),
                "capability_status_inconsistent": len(counts) > 1,
            }
        output[key] = {
            "system": system,
            "scenario_id": scenario,
            "variant": variant,
            "run_ids": [item["run_id"] for item in items],
            "valid_run_count": len(valid),
            "failed_run_count": len(items) - len(valid),
            "comparison_status": "ready" if len(valid) >= 3 else "insufficient_runs",
            "metrics": metrics,
            "capabilities": capability_distribution,
        }
    return output


def render_report(aggregate: dict[str, Any], scores: list[dict[str, Any]]) -> str:
    lines = [
        "# MAGE-inspired execution-state gap report",
        "",
        "> This report evaluates fixed traces. It is not a fair product ranking, a live-agent evaluation, or a reproduction of MAGE/MemoryArena.",  # noqa: E501
        "",
        "## Protocol disclosures",
        "",
        "- v0 ingestion uses the production `handle_hook` entrypoint with synthetic, payload-compatible events; retrieval uses a `ContextRouter` probe.",  # noqa: E501
        "- Missing advanced capabilities remain `unsupported` or `not_observable`; they are not converted to zero.",  # noqa: E501
        "- Empty retrieval is indeterminate for contamination and cannot be counted as clean.",  # noqa: E501
        "- Formal comparison requires three valid runs. The report uses min/median/max/range, never a mean.",  # noqa: E501
        "- Deterministic Maintain measures pipeline conformance, not error-detection capability.",  # noqa: E501
        "",
        "## Raw runs",
        "",
        "| System | Scenario | Variant | Run | Status | Required recall | Strict pass | Contamination | Indeterminate |",  # noqa: E501
        "|---|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for score in sorted(
        scores,
        key=lambda item: (
            item["system"],
            item["scenario_id"],
            str(item.get("variant")),
            item["run_id"],
        ),
    ):
        values = _metric_values(score)
        lines.append(
            "| {system} | {scenario} | {variant} | {run} | {status} | {required} | {strict} | {contamination} | {indeterminate} |".format(  # noqa: E501
                system=score["system"],
                scenario=score["scenario_id"],
                variant=score.get("variant") or "-",
                run=score["run_id"],
                status=score["run_status"],
                required=_display(values["required_recall"]),
                strict=_display(values["strict_final_state_pass"]),
                contamination=_display(values["error_contamination_rate"]),
                indeterminate=_display(values["indeterminate_rate"]),
            )
        )
    lines.extend(["", "## Aggregates", ""])
    for key, value in aggregate.items():
        lines.extend(
            [
                f"### {key}",
                "",
                f"- Valid runs: {value['valid_run_count']} (status: `{value['comparison_status']}`)",  # noqa: E501
                f"- Failed/invalid runs: {value['failed_run_count']}",
                "",
                "| Metric | Raw | Min | Median | Max | Range |",
                "|---|---|---:|---:|---:|---:|",
            ]
        )
        for metric, summary in value["metrics"].items():
            lines.append(
                f"| {metric} | {summary['raw']} | {_display(summary['min'])} | {_display(summary['median'])} | {_display(summary['max'])} | {_display(summary['range'])} |"  # noqa: E501
            )
        lines.extend(["", "Capability status distribution:", ""])
        for name, distribution in value["capabilities"].items():
            suffix = (
                " (inconsistent)"
                if distribution["capability_status_inconsistent"]
                else ""
            )
            lines.append(f"- `{name}`: {distribution['counts']}{suffix}")
        lines.append("")
    lines.extend(
        [
            "## Interpretation limits",
            "",
            "The reference implementation is a harness positive control. Product runs may use different internal models, and three repetitions are descriptive rather than statistically conclusive.",  # noqa: E501
            "",
        ]
    )
    return "\n".join(lines)


def _display(value: Any) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def save_report(
    target: Path, aggregate: dict[str, Any], scores: list[dict[str, Any]]
) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_report(aggregate, scores), encoding="utf-8")
    write_json(target.with_suffix(".json"), aggregate)
