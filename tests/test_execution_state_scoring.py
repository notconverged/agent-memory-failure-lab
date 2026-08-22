from __future__ import annotations

from benchmarks.execution_state.scoring import aggregate_scores, score_basic


def gold() -> dict:
    return {
        "black_box": {
            "final_checkpoint": 2,
            "required_final_assertions": ["current"],
            "forbidden_final_assertions": ["stale"],
            "contamination_checkpoints": {"1": {"forbidden_assertions": ["wrong"]}},
        }
    }


def test_empty_retrieval_is_indeterminate_not_clean():
    observations = {
        "1": {"query_status": "empty", "retrieval_text": ""},
        "2": {"query_status": "empty", "retrieval_text": ""},
    }
    final, contamination, query_error = score_basic(observations, gold())
    assert query_error is False
    assert final == {
        "required_recall": 0.0,
        "forbidden_exclusion": None,
        "strict_final_state_pass": 0,
        "empty_retrieval": True,
        "required_matches": [False],
        "forbidden_matches": [False],
    }
    assert contamination["eligible_checkpoint_count"] == 0
    assert contamination["error_contamination_rate"] is None
    assert contamination["indeterminate_rate"] == 1


def test_contamination_denominator_excludes_indeterminate():
    observations = {
        "1": {"query_status": "completed", "retrieval_text": "wrong branch"},
        "2": {"query_status": "completed", "retrieval_text": "current"},
    }
    _, contamination, _ = score_basic(observations, gold())
    assert contamination["eligible_checkpoint_count"] == 1
    assert contamination["error_contamination_rate"] == 1


def make_score(run_id: str, required: float, strict: int, status: str = "valid"):
    advanced = {
        name: {"support_status": "unsupported", "value": None}
        for name in (
            "active_path_integrity",
            "branch_isolation",
            "compression_fidelity",
            "maintain_precision",
        )
    }
    return {
        "system": "x",
        "scenario_id": "s",
        "run_id": run_id,
        "variant": None,
        "run_status": status,
        "final_state_correctness": {
            "required_recall": required,
            "forbidden_exclusion": 1.0,
            "strict_final_state_pass": strict,
        },
        "error_contamination": {
            "error_contamination_rate": 0.0,
            "indeterminate_rate": 0.0,
        },
        "advanced": advanced,
    }


def test_three_run_aggregation_uses_min_median_max_and_no_mean():
    aggregate = aggregate_scores(
        [
            make_score("r1", 0.0, 0),
            make_score("r2", 0.5, 1),
            make_score("r3", 1.0, 1),
        ]
    )["x/s"]
    required = aggregate["metrics"]["required_recall"]
    assert required["min"] == 0
    assert required["median"] == 0.5
    assert required["max"] == 1
    assert required["range"] == 1
    assert "mean" not in required
    assert aggregate["metrics"]["strict_final_state_pass"]["pass_count"] == 2
    assert aggregate["comparison_status"] == "ready"


def test_failed_run_is_not_hidden_by_valid_runs():
    value = aggregate_scores(
        [
            make_score("r1", 1, 1),
            make_score("r2", 1, 1),
            make_score("r3", 0, 0, "execution_failure"),
        ]
    )["x/s"]
    assert value["valid_run_count"] == 2
    assert value["failed_run_count"] == 1
    assert value["comparison_status"] == "insufficient_runs"
