from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmarks.execution_state.adapters.base import (  # noqa: E402
    AdapterContext,
    ensure_within,
    tree_manifest,
    write_json,
)
from benchmarks.execution_state.adapters.v0_adapter import V0Adapter  # noqa: E402
from benchmarks.execution_state.reference_impl import run_reference  # noqa: E402
from benchmarks.execution_state.scoring import (  # noqa: E402
    aggregate_scores,
    save_report,
    score_result,
)

BENCHMARK = ROOT / "benchmarks" / "execution_state"
SCENARIOS = BENCHMARK / "scenarios" / "coding"
GOLD = BENCHMARK / "gold"
RESULTS = ROOT / "results" / "runs" / "execution-state"
LOCAL = ROOT / ".local-lab"
REPORT = ROOT / "docs" / "competitor-trials" / "execution-state-gap-report.md"
BENCHMARK_VERSION = "0.1.0-draft.1"
SYSTEMS = {
    "v0": {"environment": "agent-memory-failure-lab", "mode": "local"},
    "mem0-vector": {"environment": "amlab-mem0", "mode": "conda"},
    "graphiti": {"environment": "amlab-graphiti", "mode": "conda"},
}
ADAPTER_MODULES = {
    "mem0-vector": "benchmarks.execution_state.adapters.mem0_adapter",
    "graphiti": "benchmarks.execution_state.adapters.graphiti_adapter",
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_scenario(name: str) -> dict[str, Any]:
    return load_json(SCENARIOS / f"{name}.json")


def load_gold(name: str) -> dict[str, Any]:
    return load_json(GOLD / f"{name}.json")


def scenario_names() -> list[str]:
    return sorted(path.stem for path in SCENARIOS.glob("*.json"))


def make_run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    try:
        suffix = git(ROOT, "rev-parse", "--short", "HEAD")
    except (OSError, subprocess.SubprocessError):
        suffix = "nogit"
    return f"{stamp}-{suffix}"


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
    ).stdout.strip()


def validate_contract() -> dict[str, Any]:
    schemas = [
        load_json(path) for path in sorted((BENCHMARK / "schema").glob("*.json"))
    ]
    if len(schemas) != 3:
        raise ValueError("execution-state benchmark requires exactly three schemas")
    variants = load_json(BENCHMARK / "ablations" / "variants.json")
    if set(variants) != {"A0", "A1", "A2", "A3", "A4"}:
        raise ValueError("reference variants must be exactly A0-A4")
    checked: list[str] = []
    for name in scenario_names():
        scenario = load_scenario(name)
        gold = load_gold(name)
        if scenario["scenario_id"] != name or gold["scenario_id"] != name:
            raise ValueError(f"scenario/gold identifier mismatch: {name}")
        if scenario["benchmark_version"] != BENCHMARK_VERSION:
            raise ValueError(f"unexpected benchmark version for {name}")
        steps = [int(item["step_index"]) for item in scenario["timeline"]]
        if steps != list(range(1, len(steps) + 1)):
            raise ValueError(f"{name}: timeline must be contiguous from 1")
        step_keys = [
            item["step_key"] for item in scenario["timeline"] if "step_key" in item
        ]
        if len(step_keys) != len(set(step_keys)):
            raise ValueError(f"{name}: step_key values must be unique")
        session_ids = {item["session_id"] for item in scenario["sessions"]}
        for checkpoint in scenario["product_checkpoints"]:
            if checkpoint["after_session_id"] not in session_ids:
                raise ValueError(f"{name}: checkpoint references unknown session")
            if int(checkpoint["step_index"]) not in steps:
                raise ValueError(f"{name}: checkpoint step is absent from timeline")
        if str(gold["black_box"]["final_checkpoint"]) not in {
            str(item["step_index"]) for item in scenario["product_checkpoints"]
        }:
            raise ValueError(f"{name}: final checkpoint is not scheduled")
        for checkpoint in gold["execution_state"]["checkpoints"]:
            if int(checkpoint["step_index"]) not in steps:
                raise ValueError(f"{name}: execution gold references absent step")
        checked.append(name)
    return {
        "ok": True,
        "benchmark_version": BENCHMARK_VERSION,
        "schemas": len(schemas),
        "scenarios": checked,
        "variants": sorted(variants),
    }


def _result_dir(round_name: str, system: str, scenario: str, run_id: str) -> Path:
    return RESULTS / round_name / system / scenario / run_id


def _write_observations(run_dir: Path, result: dict[str, Any]) -> None:
    for step, observation in result["observations"].items():
        checkpoint_dir = run_dir / "checkpoints" / step
        write_json(
            checkpoint_dir / "input.json", {"query": observation.get("query", "")}
        )
        write_json(checkpoint_dir / "raw-output.json", observation)
        (checkpoint_dir / "delivered-context.txt").write_text(
            str(observation.get("retrieval_text", "")), encoding="utf-8"
        )
        write_json(
            checkpoint_dir / "observation.json",
            {
                "query_status": observation.get("query_status"),
                "retrieval_text": observation.get("retrieval_text", ""),
                "capabilities": result["capabilities"],
            },
        )


def run_reference_command(args: argparse.Namespace) -> dict[str, Any]:
    names = scenario_names() if args.scenario == "all" else [args.scenario]
    variants = args.variants.split(",")
    outputs = []
    for name in names:
        scenario = load_scenario(name)
        gold = load_gold(name)
        for variant in variants:
            run_id = f"{make_run_id()}-{variant.lower()}"
            run_dir = _result_dir(args.round, "reference", name, run_id)
            if run_dir.exists():
                raise FileExistsError(f"refusing to overwrite run: {run_dir}")
            run_dir.mkdir(parents=True)
            result = run_reference(scenario, variant)
            result["run_id"] = run_id
            write_json(
                run_dir / "manifest.json",
                {
                    "benchmark_id": "execution-state-gap",
                    "benchmark_version": BENCHMARK_VERSION,
                    "system": "reference",
                    "scenario_id": name,
                    "variant": variant,
                    "run_id": run_id,
                    "validator_mode": "deterministic_script",
                    "maintain_metric_interpretation": "pipeline_conformance_not_detection_capability",  # noqa: E501
                    "reference_role": "harness_positive_control_not_theoretical_upper_bound",  # noqa: E501
                },
            )
            write_json(run_dir / "capabilities.json", result["capabilities"])
            write_json(run_dir / "raw-result.json", result)
            for step, state in result["all_states"].items():
                write_json(run_dir / "states" / f"{step}.json", state)
            _write_observations(run_dir, result)
            gate = {"valid": True, "checks": {"reference_in_memory": True}}
            write_json(run_dir / "final" / "gate-result.json", gate)
            score = score_result(result, gold, gate_valid=True)
            write_json(run_dir / "final" / "score.json", score)
            outputs.append({"run_dir": str(run_dir), "score": score})
    return {"ok": True, "runs": outputs}


def environment_signature(system: str) -> dict[str, Any]:
    config = SYSTEMS[system]
    digest = hashlib.sha256()
    candidates = []
    environment_file = (
        ROOT
        / "environments"
        / "competitors"
        / ("mem0.yml" if system == "mem0-vector" else f"{system}.yml")
    )
    lock_file = (
        ROOT
        / "environments"
        / "locks"
        / ("mem0-windows.txt" if system == "mem0-vector" else f"{system}-windows.txt")
    )
    for candidate in (environment_file, lock_file):
        if candidate.exists():
            candidates.append(candidate)
            digest.update(candidate.relative_to(ROOT).as_posix().encode())
            digest.update(candidate.read_bytes())
    return {
        "environment": config["environment"],
        "mode": config["mode"],
        "definition_hash": digest.hexdigest() if candidates else None,
        "python": platform.python_version(),
    }


def _init_workspace(path: Path) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite workspace: {path}")
    path.mkdir(parents=True)
    git(path, "init")
    git(path, "config", "user.name", "Execution State Benchmark")
    git(path, "config", "user.email", "benchmark@example.invalid")
    git(path, "commit", "--allow-empty", "-m", "benchmark-root")


def prepare_command(args: argparse.Namespace) -> dict[str, Any]:
    if not args.fresh:
        raise ValueError("prepare requires --fresh")
    if args.system not in SYSTEMS:
        raise ValueError(f"unsupported system: {args.system}")
    scenario = load_scenario(args.scenario)
    run_id = args.run_id or make_run_id()
    run_dir = _result_dir(args.round, args.system, args.scenario, run_id)
    data_dir = LOCAL / "competitors" / args.system / "data" / run_id
    workspace = LOCAL / "worktrees" / "execution-state" / run_id
    if run_dir.exists() or data_dir.exists() or workspace.exists():
        raise FileExistsError("fresh run target already exists")
    run_dir.mkdir(parents=True)
    data_dir.mkdir(parents=True)
    _init_workspace(workspace)
    before = tree_manifest(data_dir)
    manifest = {
        "benchmark_id": "execution-state-gap",
        "benchmark_version": BENCHMARK_VERSION,
        "system": args.system,
        "scenario_id": scenario["scenario_id"],
        "run_id": run_id,
        "round": args.round,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_git_commit": git(ROOT, "rev-parse", "HEAD"),
        "workspace": str(workspace.resolve()),
        "data_dir": str(data_dir.resolve()),
        "initial_storage_hash": before["sha256"],
        "environment": environment_signature(args.system),
        "status": "prepared",
    }
    if args.system == "v0":
        manifest.update(
            {
                "ingestion_mode": "synthetic_hook_replay",
                "production_entrypoint": "agent_memory.codex_hook.handle_hook",
                "equivalence": "payload_compatible_not_live_codex_session",
                "retrieval_entrypoint": "agent_memory.router.ContextRouter",
                "retrieval_probe_side_effect": "delivery_record_only",
            }
        )
    write_json(run_dir / "manifest.json", manifest)
    write_json(run_dir / "storage-before.json", before)
    write_json(
        run_dir / "install" / "environment.json",
        {
            "system": args.system,
            "environment": manifest["environment"],
            "model_provider": os.environ.get("AMLAB_MODEL_PROVIDER", "not_observable"),
            "model_id": os.environ.get("AMLAB_MODEL_ID", "not_observable"),
            "data_dir": manifest["data_dir"],
            "benchmark_version": BENCHMARK_VERSION,
        },
    )
    return manifest


def _external_execute(
    system: str, context: AdapterContext, environment: str
) -> dict[str, Any]:
    request_path = context.run_dir / "adapter-request.json"
    output_path = context.run_dir / "adapter-output.json"
    write_json(
        request_path,
        {
            "system": system,
            "scenario": context.scenario,
            "run_id": context.run_id,
            "workspace": str(context.workspace.resolve()),
            "data_dir": str(context.data_dir.resolve()),
        },
    )
    process = subprocess.run(
        [
            "conda",
            "run",
            "-n",
            environment,
            "python",
            "-m",
            ADAPTER_MODULES[system],
            str(request_path.resolve()),
            str(output_path.resolve()),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=900,
        check=False,
    )
    write_json(
        context.run_dir / "adapter-process.json",
        {
            "returncode": process.returncode,
            "stdout": process.stdout[-8000:],
            "stderr": process.stderr[-8000:],
        },
    )
    if not output_path.exists():
        raise RuntimeError(f"{system} adapter produced no output")
    result = load_json(output_path)
    if process.returncode != 0 or result.get("status") != "completed":
        raise RuntimeError(result.get("error") or process.stderr[-2000:])
    return result


def execute_command(args: argparse.Namespace) -> dict[str, Any]:
    run_dir = _result_dir(args.round, args.system, args.scenario, args.run_id)
    manifest = load_json(run_dir / "manifest.json")
    if manifest["environment"] != environment_signature(args.system):
        raise RuntimeError("environment changed after prepare; create a new run_id")
    if manifest["source_git_commit"] != git(ROOT, "rev-parse", "HEAD"):
        raise RuntimeError("source Git HEAD changed after prepare; create a new run_id")
    scenario = load_scenario(args.scenario)
    context = AdapterContext(
        args.system,
        scenario,
        args.run_id,
        Path(manifest["workspace"]),
        Path(manifest["data_dir"]),
        run_dir,
    )
    try:
        if args.system == "v0":
            result = V0Adapter().execute(context)
        else:
            result = _external_execute(
                args.system, context, SYSTEMS[args.system]["environment"]
            )
        result["run_id"] = args.run_id
        execution_error = None
    except Exception as error:
        result = {
            "system": args.system,
            "scenario_id": args.scenario,
            "run_id": args.run_id,
            "observations": {
                str(item["step_index"]): {
                    "query_status": "error",
                    "retrieval_text": "",
                    "query": item["query"],
                    "error": str(error),
                }
                for item in scenario["product_checkpoints"]
            },
            "capabilities": {},
            "execution_error": str(error),
        }
        execution_error = str(error)
    after = tree_manifest(context.data_dir)
    write_json(run_dir / "storage-after.json", after)
    path_checks = []
    for value in result.get("storage_paths", []):
        try:
            ensure_within(Path(value), context.data_dir)
            path_checks.append({"path": value, "inside_data_dir": True})
        except ValueError:
            path_checks.append({"path": value, "inside_data_dir": False})
    before = load_json(run_dir / "storage-before.json")
    unique_run_id = run_dir.name == args.run_id
    data_dir_isolated = (
        context.data_dir.resolve().is_relative_to(
            (LOCAL / "competitors" / args.system / "data").resolve()
        )
        and context.data_dir.name == args.run_id
    )
    workspace_isolated = (
        context.workspace.resolve().is_relative_to(
            (LOCAL / "worktrees" / "execution-state").resolve()
        )
        and context.workspace.name == args.run_id
    )
    storage_changed = before["sha256"] != after["sha256"]
    cross_run_contamination = bool(before["files"])
    gate = {
        "valid": (
            not before["files"]
            and unique_run_id
            and data_dir_isolated
            and workspace_isolated
            and all(item["inside_data_dir"] for item in path_checks)
            and storage_changed
            and not cross_run_contamination
            and execution_error is None
        ),
        "checks": {
            "initial_storage_empty": not before["files"],
            "unique_run_id": unique_run_id,
            "isolated_data_dir": data_dir_isolated,
            "isolated_workspace_process": workspace_isolated,
            "process_mode": SYSTEMS[args.system]["mode"],
            "storage_path_containment": path_checks,
            "final_storage_diff": storage_changed,
            "cross_run_contamination": cross_run_contamination,
        },
        "execution_error": execution_error,
    }
    write_json(run_dir / "final" / "gate-result.json", gate)
    write_json(run_dir / "raw-result.json", result)
    if result.get("capabilities"):
        write_json(run_dir / "capabilities.json", result["capabilities"])
        _write_observations(run_dir, result)
        score = score_result(result, load_gold(args.scenario), gate_valid=gate["valid"])
        write_json(run_dir / "final" / "score.json", score)
    else:
        score = None
    manifest["status"] = "completed" if gate["valid"] else "invalid"
    write_json(run_dir / "manifest.json", manifest)
    return {"run_dir": str(run_dir), "gate": gate, "score": score}


def report_command(args: argparse.Namespace) -> dict[str, Any]:
    round_dir = RESULTS / args.round
    scores = [
        load_json(path) for path in sorted(round_dir.glob("*/*/*/final/score.json"))
    ]
    if args.system:
        scores = [item for item in scores if item["system"] == args.system]
    aggregate = aggregate_scores(scores)
    target = Path(args.output) if args.output else REPORT
    save_report(target, aggregate, scores)
    return {"report": str(target), "runs": len(scores), "groups": len(aggregate)}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="MAGE-inspired gap benchmark")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate")

    reference = sub.add_parser("reference")
    reference.add_argument("--scenario", default="all")
    reference.add_argument("--variants", default="A0,A1,A2,A3,A4")
    reference.add_argument("--round", default="reference-01")
    reference.add_argument("--fresh", action="store_true", required=True)

    prepare = sub.add_parser("prepare")
    prepare.add_argument("--system", choices=sorted(SYSTEMS), required=True)
    prepare.add_argument("--scenario", choices=scenario_names(), required=True)
    prepare.add_argument("--round", default="smoke-01")
    prepare.add_argument("--run-id")
    prepare.add_argument("--fresh", action="store_true", required=True)

    execute = sub.add_parser("execute")
    execute.add_argument("--system", choices=sorted(SYSTEMS), required=True)
    execute.add_argument("--scenario", choices=scenario_names(), required=True)
    execute.add_argument("--round", default="smoke-01")
    execute.add_argument("--run-id", required=True)

    report = sub.add_parser("report")
    report.add_argument("--round", default="reference-01")
    report.add_argument("--system")
    report.add_argument("--output")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "validate":
            value = validate_contract()
        elif args.command == "reference":
            value = run_reference_command(args)
        elif args.command == "prepare":
            value = prepare_command(args)
        elif args.command == "execute":
            value = execute_command(args)
        else:
            value = report_command(args)
        print(json.dumps(value, indent=2, ensure_ascii=False))
        return 0
    except (FileNotFoundError, KeyError, RuntimeError, ValueError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
