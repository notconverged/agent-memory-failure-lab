from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "benchmarks" / "repo_evolution"


def load_spec() -> tuple[dict[str, Any], dict[str, str], dict[str, Any]]:
    scenario = json.loads((BENCHMARK / "scenario.json").read_text(encoding="utf-8"))
    conditions = json.loads((BENCHMARK / "conditions.json").read_text(encoding="utf-8"))
    gold = json.loads((BENCHMARK / "gold.json").read_text(encoding="utf-8"))
    validate_spec(scenario, conditions, gold)
    return scenario, conditions, gold


def validate_spec(
    scenario: dict[str, Any], conditions: dict[str, str], gold: dict[str, Any]
) -> None:
    expected = {f"C{index}" for index in range(6)}
    if set(conditions) != expected:
        raise ValueError("conditions must be exactly C0-C5")
    phases = scenario.get("phases", [])
    if len(phases) < 4 or len({item["phase_id"] for item in phases}) != len(phases):
        raise ValueError("scenario needs unique multi-session phases")
    if gold.get("scenario_id") != scenario.get("scenario_id"):
        raise ValueError("gold scenario_id does not match")
    kinds = {item["kind"] for item in gold.get("expected_memories", [])}
    if not kinds <= {"Decision", "Constraint", "ProjectFact", "Failure"}:
        raise ValueError("gold contains a non-v0 memory kind")


def materialize(workspace: Path, scenario: dict[str, Any]) -> list[str]:
    if workspace.exists():
        raise FileExistsError(f"Refusing to overwrite existing workspace: {workspace}")
    workspace.mkdir(parents=True)
    _git(workspace, "init")
    _git(workspace, "config", "user.name", "Memory Benchmark")
    _git(workspace, "config", "user.email", "benchmark@example.invalid")
    commits: list[str] = []
    known_files: set[Path] = set()
    for phase in scenario["phases"]:
        phase_files = {Path(path) for path in phase["files"]}
        for stale in known_files - phase_files:
            (workspace / stale).unlink(missing_ok=True)
        for relative, content in phase["files"].items():
            target = workspace / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        known_files = phase_files
        _git(workspace, "add", "-A")
        _git(workspace, "commit", "-m", phase["phase_id"])
        commits.append(_git(workspace, "rev-parse", "HEAD"))
    return commits


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return result.stdout.strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--condition", choices=[f"C{i}" for i in range(6)], required=True
    )
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    scenario, conditions, _ = load_spec()
    plan = {
        "scenario_id": scenario["scenario_id"],
        "condition": args.condition,
        "condition_name": conditions[args.condition],
        "phases": [item["phase_id"] for item in scenario["phases"]],
        "agent_executed": False,
    }
    if args.dry_run:
        print(json.dumps(plan, indent=2))
        return 0
    if args.workspace is None:
        parser.error("--workspace is required unless --dry-run is used")
    plan["commits"] = materialize(args.workspace, scenario)
    manifest = args.workspace / "benchmark-manifest.json"
    manifest.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    print(json.dumps({"workspace": str(args.workspace), **plan}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
