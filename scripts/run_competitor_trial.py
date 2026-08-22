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
from scripts.run_repo_evolution import load_spec as load_repo_spec  # noqa: E402

BENCHMARK = ROOT / "benchmarks" / "repo_evolution"
TRIAL = BENCHMARK / "trials" / "competitor_v1"
RESULTS = ROOT / "results" / "runs" / "competitor-trials"
LOCAL = ROOT / ".local-lab"
DISTRIBUTIONS = {
    "basic-memory": "basic-memory",
    "mem0": "mem0ai",
    "letta": "letta-client",
    "graphiti": "graphiti-core",
}
CHECK_NAMES = (
    "capture_completeness",
    "structure_type_fidelity",
    "lifecycle_correctness",
    "provenance_traceability",
    "fresh_session_retrieval",
    "behavior_correctness",
    "controllability",
)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    os.replace(temporary, path)


def git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    )
    return result.stdout.strip()


def make_run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    try:
        suffix = git(ROOT, "rev-parse", "--short", "HEAD")
    except (OSError, subprocess.SubprocessError):
        suffix = "nogit"
    return f"{stamp}-{suffix}"


def environment_signature(system: str) -> dict[str, Any]:
    systems = load_json(TRIAL / "systems.json")
    config = systems[system]
    files = []
    if config.get("environment"):
        candidate = ROOT / "environments" / "competitors" / f"{system}.yml"
        if candidate.exists():
            files.append(candidate)
        lock = ROOT / "environments" / "locks" / f"{system}-windows.txt"
        if lock.exists():
            files.append(lock)
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.relative_to(ROOT).as_posix().encode())
        digest.update(path.read_bytes())
    return {
        "environment": config.get("environment"),
        "definition_hash": digest.hexdigest() if files else None,
        "python": platform.python_version(),
        "mode": config["mode"],
    }


def installation_record(
    system: str, data_dir: Path, benchmark_version: str
) -> dict[str, Any]:
    systems = load_json(TRIAL / "systems.json")
    config = systems[system]
    lock = ROOT / "environments" / "locks" / f"{system}-windows.txt"
    lock_hash = hashlib.sha256(lock.read_bytes()).hexdigest() if lock.exists() else None
    system_version = "not_recorded"
    env_name = config.get("environment")
    distribution = DISTRIBUTIONS.get(system)
    python_version = platform.python_version()
    if env_name and distribution:
        code = (
            "import json, platform; from importlib.metadata import version;"
            f"print(json.dumps({{'python': platform.python_version(), "
            f"'version': version({distribution!r})}}))"
        )
        probe = subprocess.run(
            ["conda", "run", "-n", env_name, "python", "-c", code],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if probe.returncode == 0:
            try:
                value = json.loads(probe.stdout.strip().splitlines()[-1])
                system_version = value["version"]
                python_version = value["python"]
            except (IndexError, json.JSONDecodeError, KeyError):
                system_version = "probe_output_invalid"
    return {
        "system": system,
        "system_version": system_version,
        "conda_env": env_name,
        "python_version": python_version,
        "dependency_lock_sha256": lock_hash,
        "model_provider": os.environ.get("AMLAB_MODEL_PROVIDER", "not_recorded"),
        "model_id": os.environ.get("AMLAB_MODEL_ID", "not_recorded"),
        "data_dir": str(data_dir.resolve()),
        "benchmark_version": benchmark_version,
    }


def verify_system(system: str) -> dict[str, Any]:
    systems = load_json(TRIAL / "systems.json")
    if system not in systems:
        raise ValueError(f"Unsupported system: {system}")
    config = systems[system]
    env_name = config.get("environment")
    import_name = config.get("import_name")
    if not env_name or not import_name:
        return {
            "ok": True,
            "system": system,
            "mode": config["mode"],
            "environment": env_name,
            "note": "Verify the native product with its runbook.",
        }
    distribution = DISTRIBUTIONS[system]
    code = (
        "import importlib, json, platform;"
        "from importlib.metadata import version;"
        f"m=importlib.import_module({import_name!r});"
        "print(json.dumps({'python':platform.python_version(),"
        "'module':m.__name__,'module_file':getattr(m,'__file__',None),"
        f"'version':version({distribution!r})}}))"
    )
    result = subprocess.run(
        ["conda", "run", "-n", env_name, "python", "-c", code],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    required = config.get("required_env", [])
    missing = [name for name in required if not os.environ.get(name)]
    probe_dir = LOCAL / "competitors" / system / "verify"
    probe_dir.mkdir(parents=True, exist_ok=True)
    probe_file = probe_dir / f"write-{os.getpid()}.tmp"
    data_dir_writable = False
    try:
        probe_file.write_text("probe", encoding="utf-8")
        data_dir_writable = probe_file.read_text(encoding="utf-8") == "probe"
    finally:
        probe_file.unlink(missing_ok=True)
    return {
        "ok": result.returncode == 0 and not missing and data_dir_writable,
        "system": system,
        "environment": env_name,
        "import_name": import_name,
        "probe": result.stdout.strip(),
        "error": result.stderr.strip() or None,
        "missing_environment_variables": missing,
        "data_dir_writable": data_dir_writable,
        "api_connectivity": "deferred_to_configured_phase_smoke",
    }


def phase_by_id(phase_id: str) -> dict[str, Any]:
    scenario, _, _ = load_repo_spec()
    for phase in scenario["phases"]:
        if phase["phase_id"] == phase_id:
            return phase
    raise ValueError(f"Unknown phase: {phase_id}")


def apply_phase(workspace: Path, phase: dict[str, Any]) -> str:
    known = {
        path.relative_to(workspace)
        for path in workspace.rglob("*")
        if path.is_file() and ".git" not in path.parts
    }
    desired = {Path(name) for name in phase["files"]}
    for stale in known - desired:
        stale_path = workspace / stale
        if stale_path.name != "benchmark-manifest.json":
            stale_path.unlink()
    for relative, content in phase["files"].items():
        target = workspace / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    git(workspace, "add", "-A")
    status = git(workspace, "status", "--porcelain")
    if status:
        git(workspace, "commit", "-m", phase["phase_id"])
    return git(workspace, "rev-parse", "HEAD")


def result_dir(round_id: str, system: str, identifier: str) -> Path:
    return RESULTS / round_id / system / identifier


def locate_run(round_id: str, system: str, identifier: str) -> tuple[Path, dict]:
    target = result_dir(round_id, system, identifier)
    manifest_path = target / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Unknown run: {target}")
    return target, load_json(manifest_path)


def create_slots(target: Path, scenario: dict[str, Any], prompts: dict) -> None:
    for phase in scenario["phases"]:
        phase_id = phase["phase_id"]
        directory = target / "phases" / phase_id
        directory.mkdir(parents=True)
        write_json(
            directory / "input.json",
            {
                "phase_id": phase_id,
                "session": phase["session"],
                "scenario_instruction": phase["instruction"],
                "trial_prompt": prompts[phase_id],
            },
        )
        write_json(directory / "capture.json", {"status": "not_observed", "items": []})
        write_json(directory / "storage-before.json", {"status": "not_observed"})
        write_json(directory / "storage-after.json", {"status": "not_observed"})
        write_json(
            directory / "retrieval.json",
            {"status": "not_observed", "items": []},
        )
        write_json(
            directory / "observation.json",
            {
                "phase_id": phase_id,
                "observer": "",
                "checks": {name: None for name in CHECK_NAMES},
                "storage_location": None,
                "memory_ids": [],
                "notes": "",
            },
        )
        (directory / "delivered-context.txt").write_text("", encoding="utf-8")
        (directory / "first-action.patch").write_text("", encoding="utf-8")
        (directory / "test.log").write_text("", encoding="utf-8")


def prepare(args: argparse.Namespace) -> dict[str, Any]:
    protocol = load_json(TRIAL / "protocol.json")
    systems = load_json(TRIAL / "systems.json")
    scenario, _, _ = load_repo_spec()
    prompts = load_json(TRIAL / "prompts.json")
    if args.system not in systems:
        raise ValueError(f"Unsupported system: {args.system}")
    identifier = args.run_id or make_run_id()
    target = result_dir(args.round, args.system, identifier)
    workspace = LOCAL / "worktrees" / f"competitor-{args.system}-{identifier}"
    data_dir = LOCAL / "competitors" / args.system / "data" / identifier
    if target.exists() or workspace.exists() or data_dir.exists():
        raise FileExistsError("Run paths already exist; choose a new run_id")
    target.mkdir(parents=True)
    workspace.mkdir(parents=True)
    data_dir.mkdir(parents=True)
    git(workspace, "init")
    git(workspace, "config", "user.name", "Memory Benchmark")
    git(workspace, "config", "user.email", "benchmark@example.invalid")
    head = apply_phase(workspace, scenario["phases"][0])
    create_slots(target, scenario, prompts)
    signature = environment_signature(args.system)
    manifest = {
        "run_id": identifier,
        "round": args.round,
        "system": args.system,
        "mode": args.mode or systems[args.system]["mode"],
        "benchmark_id": protocol["benchmark_id"],
        "benchmark_version": protocol["benchmark_version"],
        "scenario_id": scenario["scenario_id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_git_commit": git(ROOT, "rev-parse", "HEAD"),
        "workspace": str(workspace.resolve()),
        "data_dir": str(data_dir.resolve()),
        "current_phase": scenario["phases"][0]["phase_id"],
        "current_head": head,
        "environment": signature,
        "contamination": systems[args.system].get("contamination"),
    }
    write_json(target / "manifest.json", manifest)
    install = installation_record(args.system, data_dir, protocol["benchmark_version"])
    write_json(target / "install" / "environment.json", install)
    (target / "screenshots").mkdir()
    (target / "final").mkdir()
    return manifest


def assert_same_environment(manifest: dict[str, Any]) -> None:
    current = environment_signature(manifest["system"])
    if current != manifest["environment"]:
        raise RuntimeError(
            "Environment definition changed after this run started; create a new run_id"
        )


def apply_phase_command(args: argparse.Namespace) -> dict[str, Any]:
    target, manifest = locate_run(args.round, args.system, args.run_id)
    assert_same_environment(manifest)
    phase = phase_by_id(args.phase)
    head = apply_phase(Path(manifest["workspace"]), phase)
    manifest["current_phase"] = args.phase
    manifest["current_head"] = head
    write_json(target / "manifest.json", manifest)
    return {"run_id": args.run_id, "phase": args.phase, "head": head}


def checkpoint(args: argparse.Namespace) -> dict[str, Any]:
    target, manifest = locate_run(args.round, args.system, args.run_id)
    assert_same_environment(manifest)
    if args.phase != manifest["current_phase"]:
        raise RuntimeError("Checkpoint phase does not match the materialized phase")
    workspace = Path(manifest["workspace"])
    payload = {
        "run_id": args.run_id,
        "phase_id": args.phase,
        "git_head": git(workspace, "rev-parse", "HEAD"),
        "git_status": git(workspace, "status", "--porcelain"),
        "environment": manifest["environment"],
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    write_json(target / "phases" / args.phase / "checkpoint.json", payload)
    return payload


def resume(args: argparse.Namespace) -> dict[str, Any]:
    target, manifest = locate_run(args.round, args.system, args.run_id)
    assert_same_environment(manifest)
    checkpoint_path = target / "phases" / manifest["current_phase"] / "checkpoint.json"
    if not checkpoint_path.exists():
        raise RuntimeError("Current phase has no checkpoint")
    checkpoint_value = load_json(checkpoint_path)
    current_head = git(Path(manifest["workspace"]), "rev-parse", "HEAD")
    if current_head != checkpoint_value["git_head"]:
        raise RuntimeError("Workspace HEAD changed after the checkpoint")
    return {
        "ok": True,
        "run_id": args.run_id,
        "phase": manifest["current_phase"],
        "workspace": manifest["workspace"],
        "data_dir": manifest["data_dir"],
    }


def execute(args: argparse.Namespace) -> dict[str, Any]:
    target, manifest = locate_run(args.round, args.system, args.run_id)
    assert_same_environment(manifest)
    systems = load_json(TRIAL / "systems.json")
    config = systems[args.system]
    if args.system not in {"mem0", "letta", "graphiti"}:
        raise RuntimeError("This system uses the manual runbook")
    env_name = config.get("environment")
    if not env_name:
        raise RuntimeError("Adapter system has no isolated environment")
    phase_dir = target / "phases" / args.phase
    input_value = load_json(phase_dir / "input.json")
    request_path = phase_dir / "adapter-request.json"
    output_path = phase_dir / "execution-status.json"
    write_json(
        request_path,
        {
            "system": args.system,
            "run_id": args.run_id,
            "phase_id": args.phase,
            "workspace": manifest["workspace"],
            "data_dir": manifest["data_dir"],
            "prompt": input_value["trial_prompt"],
        },
    )
    command = [
        "conda",
        "run",
        "-n",
        env_name,
        "python",
        "-m",
        "scripts.competitor_adapters.runner",
        "--request",
        str(request_path.resolve()),
        "--output",
        str(output_path.resolve()),
    ]
    process = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    secrets = [
        value
        for key, value in os.environ.items()
        if (key.endswith("_KEY") or key.endswith("_TOKEN")) and len(value) >= 8
    ]

    def sanitized(value: str) -> str:
        for secret in secrets:
            value = value.replace(secret, "[REDACTED]")
        return value[-8_000:]

    write_json(
        phase_dir / "adapter-process.json",
        {
            "returncode": process.returncode,
            "stdout": sanitized(process.stdout),
            "stderr": sanitized(process.stderr),
        },
    )
    if not output_path.exists():
        result = {
            "status": "adapter_process_failed",
            "returncode": process.returncode,
            "error": sanitized(process.stderr),
        }
        write_json(output_path, result)
        return result
    return load_json(output_path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Competitor trial harness")
    sub = parser.add_subparsers(dest="command", required=True)
    verify = sub.add_parser("verify-env")
    verify.add_argument("--system", required=True)
    prepare_parser = sub.add_parser("prepare")
    prepare_parser.add_argument("--system", required=True)
    prepare_parser.add_argument("--round", default="round-01")
    prepare_parser.add_argument("--run-id")
    prepare_parser.add_argument("--mode", choices=("manual", "adapter"))
    prepare_parser.add_argument("--fresh", action="store_true", required=True)
    phase = sub.add_parser("apply-phase")
    phase.add_argument("--system", required=True)
    phase.add_argument("--round", default="round-01")
    phase.add_argument("--run-id", required=True)
    phase.add_argument("--phase", required=True)
    check = sub.add_parser("checkpoint")
    check.add_argument("--system", required=True)
    check.add_argument("--round", default="round-01")
    check.add_argument("--run-id", required=True)
    check.add_argument("--phase", required=True)
    resume_parser = sub.add_parser("resume")
    resume_parser.add_argument("--system", required=True)
    resume_parser.add_argument("--round", default="round-01")
    resume_parser.add_argument("--run-id", required=True)
    execute_parser = sub.add_parser("execute")
    execute_parser.add_argument("--system", required=True)
    execute_parser.add_argument("--round", default="round-01")
    execute_parser.add_argument("--run-id", required=True)
    execute_parser.add_argument("--phase", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "verify-env":
            value = verify_system(args.system)
        elif args.command == "prepare":
            value = prepare(args)
        elif args.command == "apply-phase":
            value = apply_phase_command(args)
        elif args.command == "checkpoint":
            value = checkpoint(args)
        elif args.command == "resume":
            value = resume(args)
        else:
            value = execute(args)
        print(json.dumps(value, indent=2, ensure_ascii=False))
        return 0 if value.get("ok", True) else 2
    except (FileNotFoundError, KeyError, RuntimeError, ValueError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
