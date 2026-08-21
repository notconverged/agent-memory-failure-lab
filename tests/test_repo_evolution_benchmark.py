from __future__ import annotations

from scripts.run_repo_evolution import load_spec, materialize


def test_repo_evolution_spec_freezes_c0_to_c5_and_excludes_procedure():
    scenario, conditions, gold = load_spec()
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
