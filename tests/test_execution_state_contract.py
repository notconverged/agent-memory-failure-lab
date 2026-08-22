from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.run_execution_state import (
    BENCHMARK,
    load_gold,
    load_scenario,
    scenario_names,
    validate_contract,
)

pytestmark = pytest.mark.evaluation


def test_execution_state_contract_has_three_scenarios_and_a0_to_a4():
    result = validate_contract()
    assert result["ok"] is True
    assert result["scenarios"] == [
        "double-branch-v1",
        "ledger-rounding-v2",
        "second-revise-v1",
    ]
    assert result["variants"] == ["A0", "A1", "A2", "A3", "A4"]


def test_every_product_checkpoint_has_independent_gold():
    for name in scenario_names():
        scenario = load_scenario(name)
        gold = load_gold(name)
        scheduled = {
            str(item["step_index"]) for item in scenario["product_checkpoints"]
        }
        assert str(gold["black_box"]["final_checkpoint"]) in scheduled
        assert set(gold["black_box"]["contamination_checkpoints"]) <= scheduled


def test_schema_support_status_excludes_manual_workaround():
    schema = json.loads(
        (BENCHMARK / "schema" / "system-observation.schema.json").read_text(
            encoding="utf-8"
        )
    )
    statuses = schema["$defs"]["capability"]["properties"]["support_status"]["enum"]
    assert statuses == ["native", "derived", "not_observable", "unsupported"]
    assert "workaround" in schema["$defs"]["capability"]["properties"]


def test_reference_implementation_does_not_import_product_package():
    reference = BENCHMARK / "reference_impl"
    for path in reference.glob("*.py"):
        assert "agent_memory" not in path.read_text(encoding="utf-8")


def test_repo_has_no_product_edits_for_this_benchmark():
    root = Path(__file__).resolve().parents[1]
    import subprocess

    changed = subprocess.run(
        ["git", "diff", "--name-only", "--", "src/agent_memory", "plugins"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert changed == ""
