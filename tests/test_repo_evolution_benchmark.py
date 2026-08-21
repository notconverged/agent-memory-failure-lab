from __future__ import annotations

import pytest

from scripts.run_repo_evolution import build_plan, load_spec, materialize

pytestmark = pytest.mark.evaluation


def test_repo_evolution_spec_freezes_c0_to_c5_and_excludes_procedure():
    scenario, conditions, gold = load_spec()
    expected_metadata = {
        "benchmark_id": "repo-evolution",
        "benchmark_version": "0.1.0-draft.1",
        "schema_version": 1,
        "protocol_status": "draft",
    }
    assert {key: scenario[key] for key in expected_metadata} == expected_metadata
    assert {key: gold[key] for key in expected_metadata} == expected_metadata
    assert set(conditions) == {"C0", "C1", "C2", "C3", "C4", "C5"}
    assert len(scenario["phases"]) == 5
    assert all(item["kind"] != "Procedure" for item in gold["expected_memories"])


def test_materialized_scenario_has_real_git_snapshots(tmp_path):
    scenario, _, _ = load_spec()
    workspace = tmp_path / "scenario"
    commits = materialize(workspace, scenario)
    assert len(commits) == len(scenario["phases"])
    assert len(set(commits)) == len(commits)
    assert "ROUND_HALF_EVEN" in (workspace / "src" / "ledger.py").read_text()


def test_materializer_refuses_to_overwrite_workspace(tmp_path):
    scenario, _, _ = load_spec()
    workspace = tmp_path / "existing"
    workspace.mkdir()
    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        materialize(workspace, scenario)


def test_run_plan_records_version_contract_and_repository_commit():
    scenario, conditions, _ = load_spec()
    plan = build_plan(scenario, conditions, "C3")
    assert plan["benchmark_id"] == "repo-evolution"
    assert plan["benchmark_version"] == "0.1.0-draft.1"
    assert plan["schema_version"] == 1
    assert plan["protocol_status"] == "draft"
    assert plan["product_version"] == "0.1.0"
    assert len(plan["git_commit"]) == 40
    assert plan["agent_executed"] is False
