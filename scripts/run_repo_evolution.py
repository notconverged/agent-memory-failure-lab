from __future__ import annotations

import argparse
import json
import subprocess
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "benchmarks" / "repo_evolution"
BENCHMARK_ID = "repo-evolution"
BENCHMARK_VERSION = "0.1.0-draft.1"
SCHEMA_VERSION = 1
PROTOCOL_STATUS = "draft"
EVIDENCE_FILES = (
    "input.json",
    "capture.json",
    "storage-before.json",
    "storage-after.json",
    "retrieval.json",
    "observation.json",
)
TEXT_EVIDENCE_FILES = ("delivered-context.txt", "first-action.patch", "test.log")


def load_spec() -> tuple[dict[str, Any], dict[str, str], dict[str, Any]]:
    descriptor = json.loads(
        (BENCHMARK / "scenario.json").read_text(encoding="utf-8")
    )
    canonical_path = (BENCHMARK / descriptor["canonical_scenario"]).resolve()
    canonical = json.loads(canonical_path.read_text(encoding="utf-8"))
    scenario = {
        **descriptor,
        "canonical_scenario_id": canonical["scenario_id"],
        "phases": [
            {
                "phase_id": session["phase_id"],
                "session": index,
                "instruction": session["instruction"],
                "files": session["files"],
            }
            for index, session in enumerate(canonical["sessions"])
        ],
    }
    conditions = json.loads((BENCHMARK / "conditions.json").read_text(encoding="utf-8"))
    gold = json.loads((BENCHMARK / "gold.json").read_text(encoding="utf-8"))
    validate_spec(scenario, conditions, gold)
    return scenario, conditions, gold


def validate_spec(
    scenario: dict[str, Any], conditions: dict[str, str], gold: dict[str, Any]
) -> None:
    expected_metadata = {
        "benchmark_id": BENCHMARK_ID,
        "benchmark_version": BENCHMARK_VERSION,
        "schema_version": SCHEMA_VERSION,
        "protocol_status": PROTOCOL_STATUS,
    }
    for name, document in (("scenario", scenario), ("gold", gold)):
        actual = {key: document.get(key) for key in expected_metadata}
        if actual != expected_metadata:
            raise ValueError(f"{name} benchmark metadata does not match the runner")
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


def product_version() -> str:
    try:
        return version("agent-memory-failure-lab")
    except PackageNotFoundError:
        package_init = ROOT / "src" / "agent_memory" / "__init__.py"
        for line in package_init.read_text(encoding="utf-8").splitlines():
            if line.startswith("__version__ = "):
                return line.split("=", maxsplit=1)[1].strip().strip('"')
        raise RuntimeError(
            "Unable to determine the Coding Agent Memory version"
        ) from None


def build_plan(
    scenario: dict[str, Any], conditions: dict[str, str], condition: str
) -> dict[str, Any]:
    return {
        "benchmark_id": BENCHMARK_ID,
        "benchmark_version": BENCHMARK_VERSION,
        "schema_version": SCHEMA_VERSION,
        "protocol_status": PROTOCOL_STATUS,
        "scenario_id": scenario["scenario_id"],
        "condition": condition,
        "condition_name": conditions[condition],
        "product_version": product_version(),
        "git_commit": _git(ROOT, "rev-parse", "HEAD"),
        "phases": [item["phase_id"] for item in scenario["phases"]],
        "agent_executed": False,
    }


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


def initialize_execution_evidence(
    output_dir: Path,
    workspace: Path,
    scenario: dict[str, Any],
    plan: dict[str, Any],
) -> Path:
    """Create explicit, non-fabricated evidence slots for a v0 execution run."""

    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"Refusing to overwrite existing run: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    run_manifest = {
        **plan,
        "workspace": str(workspace.resolve()),
        "execution_status": "awaiting_agent",
    }
    manifest = output_dir / "manifest.json"
    manifest.write_text(json.dumps(run_manifest, indent=2), encoding="utf-8")
    for phase in scenario["phases"]:
        phase_dir = output_dir / "phases" / phase["phase_id"]
        phase_dir.mkdir(parents=True, exist_ok=True)
        pending = {"phase_id": phase["phase_id"], "status": "not_recorded"}
        for name in EVIDENCE_FILES:
            payload = pending
            if name == "input.json":
                payload = {
                    **pending,
                    "prompt": phase.get("prompt", ""),
                    "expected_head": phase.get("expected_head"),
                }
            (phase_dir / name).write_text(
                json.dumps(payload, indent=2), encoding="utf-8"
            )
        for name in TEXT_EVIDENCE_FILES:
            (phase_dir / name).write_text("", encoding="utf-8")
    return manifest


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
    parser.add_argument("--results-dir", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    scenario, conditions, _ = load_spec()
    plan = build_plan(scenario, conditions, args.condition)
    if args.dry_run:
        print(json.dumps(plan, indent=2))
        return 0
    if args.workspace is None:
        parser.error("--workspace is required unless --dry-run is used")
    plan["commits"] = materialize(args.workspace, scenario)
    manifest = args.workspace / "benchmark-manifest.json"
    manifest.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    result = {"workspace": str(args.workspace), **plan}
    if args.results_dir is not None:
        evidence_manifest = initialize_execution_evidence(
            args.results_dir, args.workspace, scenario, plan
        )
        result["evidence_manifest"] = str(evidence_manifest)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
