from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts import run_competitor_trial as trial
from scripts import score_competitor_trial as scoring


def test_competitor_trial_prepare_checkpoint_resume_and_score(
    tmp_path: Path, monkeypatch
):
    results = tmp_path / "results"
    local = tmp_path / "local"
    monkeypatch.setattr(trial, "RESULTS", results)
    monkeypatch.setattr(trial, "LOCAL", local)
    monkeypatch.setattr(scoring, "RESULTS", results)

    args = argparse.Namespace(
        system="codex-native",
        round="round-01",
        run_id="test-run",
        mode="manual",
        fresh=True,
    )
    manifest = trial.prepare(args)
    run_dir = results / "round-01" / "codex-native" / "test-run"
    assert Path(manifest["workspace"]).exists()
    assert (run_dir / "phases" / "S4_reentry" / "observation.json").exists()
    install = json.loads(
        (run_dir / "install" / "environment.json").read_text(encoding="utf-8")
    )
    assert set(install) == {
        "system",
        "system_version",
        "conda_env",
        "python_version",
        "dependency_lock_sha256",
        "model_provider",
        "model_id",
        "data_dir",
        "benchmark_version",
    }
    assert install["data_dir"] == manifest["data_dir"]

    phase_args = argparse.Namespace(
        system="codex-native",
        round="round-01",
        run_id="test-run",
        phase="S1_decimal_policy",
    )
    trial.apply_phase_command(phase_args)
    checkpoint = trial.checkpoint(phase_args)
    assert checkpoint["phase_id"] == "S1_decimal_policy"

    resume_args = argparse.Namespace(
        system="codex-native", round="round-01", run_id="test-run"
    )
    assert trial.resume(resume_args)["ok"] is True

    observation_path = run_dir / "phases" / "S4_reentry" / "observation.json"
    observation = json.loads(observation_path.read_text(encoding="utf-8"))
    observation["observer"] = "tester"
    observation["checks"] = {name: 1.0 for name in scoring.WEIGHTS}
    observation_path.write_text(json.dumps(observation, indent=2), encoding="utf-8")
    result = scoring.score(run_dir)
    assert result["total"] == 100
    assert result["unknown"] == []
