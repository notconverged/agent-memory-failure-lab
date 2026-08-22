from __future__ import annotations

from benchmarks.execution_state.reference_impl.adapter import run_reference
from benchmarks.execution_state.reference_impl.state_machine import (
    ReferenceStateMachine,
    Variant,
)
from benchmarks.execution_state.scoring import score_result
from scripts.run_execution_state import load_gold, load_scenario, scenario_names


def test_reference_a0_is_a_positive_control_for_all_scenarios():
    for name in scenario_names():
        result = run_reference(load_scenario(name), "A0")
        result["run_id"] = f"test-{name}"
        score = score_result(result, load_gold(name))
        assert score["final_state_correctness"]["strict_final_state_pass"] == 1
        assert score["error_contamination"]["error_contamination_rate"] == 0
        assert score["advanced"]["active_path_integrity"]["value"] == 1
        assert score["advanced"]["branch_isolation"]["value"] == 1
        assert score["advanced"]["compression_fidelity"]["value"] == 1
        assert score["advanced"]["maintain_precision"]["value"]["f1"] == 1


def test_historical_state_remains_stable_before_and_after_revise():
    scenario = load_scenario("double-branch-v1")
    machine = ReferenceStateMachine(Variant("A0", True, True, True, False))
    for event in scenario["timeline"]:
        machine.apply(event)
    before = machine.materialize_state_at(8)
    after = machine.materialize_state_at(9)
    assert before.active_raw_path == ["parser_prefix", "regex_branch"]
    assert after.active_raw_path == ["parser_prefix"]
    assert machine.materialize_state_at(8).to_dict() == before.to_dict()
    assert machine.materialize_state().as_of_step_index == 13


def test_second_revise_reuses_equal_direct_child_without_rewriting_generation():
    result = run_reference(load_scenario("second-revise-v1"), "A0")
    reuse = next(item for item in result["operations"] if item["step_index"] == 10)
    assert reuse["status"] == "reused"
    assert reuse["existing_step_key"] == "global_key_attempt"
    state = result["all_states"]["13"]
    node = next(
        item for item in state["nodes"] if item["step_key"] == "global_key_attempt"
    )
    assert node["revision_generation"] == 0
    assert state["cursor"]["revision_generation"] == 1


def test_ablations_are_scored_on_the_same_checkpoint_timeline():
    scenario = load_scenario("double-branch-v1")
    gold = load_gold("double-branch-v1")
    scores = {}
    for variant in ("A0", "A1", "A2", "A3", "A4"):
        result = run_reference(scenario, variant)
        result["run_id"] = variant
        scores[variant] = score_result(result, gold)
        assert set(result["all_states"]) == {str(item) for item in range(1, 14)}
    assert scores["A0"]["advanced"]["active_path_integrity"]["value"] == 1
    assert scores["A1"]["advanced"]["compression_fidelity"]["value"] is None
    assert scores["A2"]["advanced"]["active_path_integrity"]["value"] < 1
    assert scores["A3"]["advanced"]["branch_isolation"]["value"] == 0
    assert scores["A4"]["advanced"]["branch_isolation"]["value"] is None


def test_corrupted_reference_state_is_detected_by_scorer():
    scenario = load_scenario("ledger-rounding-v2")
    result = run_reference(scenario, "A0")
    result["run_id"] = "corrupted"
    result["all_states"]["13"]["effective_active_raw_sequence"].append("float_failed")
    score = score_result(result, load_gold("ledger-rounding-v2"))
    assert score["advanced"]["active_path_integrity"]["value"] < 1
