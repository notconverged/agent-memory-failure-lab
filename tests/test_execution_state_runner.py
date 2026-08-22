from __future__ import annotations

import argparse
from pathlib import Path

import pytest

import scripts.run_execution_state as runner
from benchmarks.execution_state.adapters.v0_adapter import V0Adapter

pytestmark = pytest.mark.evaluation


def arguments(*, run_id: str = "run-001") -> argparse.Namespace:
    return argparse.Namespace(
        fresh=True,
        system="v0",
        scenario="ledger-rounding-v2",
        run_id=run_id,
        round="test-round",
    )


def isolate_runner(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(runner, "RESULTS", tmp_path / "results")
    monkeypatch.setattr(runner, "LOCAL", tmp_path / "local")


def successful_result(context: runner.AdapterContext) -> dict:
    (context.data_dir / "ledger.sqlite3").write_text("evidence", encoding="utf-8")
    observations = {
        str(item["step_index"]): {
            "query_status": "completed",
            "retrieval_text": "final corrected state",
            "query": item["query"],
        }
        for item in context.scenario["product_checkpoints"]
    }
    return {
        "system": "v0",
        "scenario_id": context.scenario["scenario_id"],
        "run_id": context.run_id,
        "storage_paths": [str(context.data_dir.resolve())],
        "observations": observations,
        "capabilities": V0Adapter.capabilities(),
    }


def test_prepare_records_isolated_synthetic_hook_manifest(monkeypatch, tmp_path):
    isolate_runner(monkeypatch, tmp_path)

    manifest = runner.prepare_command(arguments())

    assert manifest["ingestion_mode"] == "synthetic_hook_replay"
    assert manifest["production_entrypoint"] == "agent_memory.codex_hook.handle_hook"
    assert manifest["equivalence"] == "payload_compatible_not_live_codex_session"
    assert Path(manifest["data_dir"]).is_relative_to((tmp_path / "local").resolve())
    assert Path(manifest["workspace"]).is_relative_to((tmp_path / "local").resolve())


def test_execute_requires_storage_change_and_containment(monkeypatch, tmp_path):
    isolate_runner(monkeypatch, tmp_path)
    args = arguments()
    runner.prepare_command(args)
    monkeypatch.setattr(
        V0Adapter, "execute", lambda self, context: successful_result(context)
    )

    result = runner.execute_command(args)

    assert result["gate"]["valid"] is True
    checks = result["gate"]["checks"]
    assert checks["final_storage_diff"] is True
    assert checks["isolated_data_dir"] is True
    assert checks["isolated_workspace_process"] is True
    assert checks["cross_run_contamination"] is False


def test_storage_escape_invalidates_run(monkeypatch, tmp_path):
    isolate_runner(monkeypatch, tmp_path)
    args = arguments(run_id="run-escape")
    runner.prepare_command(args)

    def escaped(context: runner.AdapterContext) -> dict:
        value = successful_result(context)
        value["storage_paths"] = [str((tmp_path / "outside").resolve())]
        return value

    monkeypatch.setattr(V0Adapter, "execute", lambda self, context: escaped(context))
    result = runner.execute_command(args)

    assert result["gate"]["valid"] is False
    assert (
        result["gate"]["checks"]["storage_path_containment"][0]["inside_data_dir"]
        is False
    )
