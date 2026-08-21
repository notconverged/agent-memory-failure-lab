"""Run and audit the Stage 0 cross-session memory experiment.

The runner deliberately keeps memory outside the model-facing tool surface.
It creates a new workspace and session namespace for every episode, injects a
fixed prompt block, and performs the representation check in the host process.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
import time
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "configs" / "minimal.cordis.yml"
BENCHMARK_ROOT = ROOT / "benchmarks" / "decimal_transfer"
TEMPLATE_ROOT = BENCHMARK_ROOT / "template"
DEFAULT_RESULTS_ROOT = ROOT / "results" / "runs"

DSH_VERSION = os.getenv("DSH_VERSION", "v0.1.0-rc.7")
DSH_COMMIT = os.getenv("DSH_COMMIT", "99f6f02")
DEFAULT_PROVIDER = os.getenv("DSH_PROVIDER", "deepseek-official")
DEFAULT_MODEL = os.getenv("DSH_MODEL", "deepseek-v4-flash")
DEFAULT_REASONING_EFFORT = os.getenv("DSH_REASONING_EFFORT", "high")
DEFAULT_MAX_TOKENS = int(os.getenv("DSH_MAX_TOKENS", "4096"))
DEFAULT_MAX_STEPS = int(os.getenv("DSH_MAX_STEPS", "24"))
DEFAULT_TEMPERATURE = 0
SYSTEM_PROMPT = (
    "You are a careful software engineer. Inspect the workspace, implement the "
    "requested function, and run the visible tests."
)

NO_MEMORY_PAYLOAD = "No relevant prior experience is available."
R1 = {
    "id": "R1",
    "content": "Financial calculations must use Decimal, not float.",
    "source_episode": "E1",
    "valid_from": "E1",
    "valid_until": None,
}

PROMPT_TEMPLATE = """<MEMORY_CONTEXT>
{memory_payload}
</MEMORY_CONTEXT>

<CURRENT_TASK>
{task_text}
</CURRENT_TASK>"""

REQUIRED_CONFIG_MARKERS = (
    "@deepseek-ai/dsh-llm-deepseek",
    "@deepseek-ai/dsh-agent-spine-demo",
    "@deepseek-ai/dsh-tool-bash-persistent",
    "@deepseek-ai/dsh-tool-str-replace-editor",
    "@deepseek-ai/dsh-session-persistence-jsonl",
    "skills:",
    "enabled: false",
    "toolJobs: false",
    "workspaceContext: false",
    "includeRuntimeContext: false",
)
FORBIDDEN_CONFIG_MARKERS = (
    "memory_search",
    "memory_write",
    "memory_forget",
    "openviking",
    "hindsight",
    "mcp-memory",
)
TOOL_SCHEMA = {
    "bash": "@deepseek-ai/dsh-tool-bash-persistent",
    "editor": "@deepseek-ai/dsh-tool-str-replace-editor",
}


@dataclass(frozen=True)
class DshResult:
    returncode: int
    stdout_path: Path
    stderr_path: Path
    trace_files: tuple[Path, ...]
    timed_out: bool = False


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def hash_tree(root: Path) -> str:
    """Hash relative file names and bytes in deterministic order."""
    digest = hashlib.sha256()
    if not root.exists():
        return digest.hexdigest()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def task_path(task_id: str) -> Path:
    if task_id.endswith("_E1"):
        return BENCHMARK_ROOT / "E1.md"
    if task_id.endswith("_E2"):
        return BENCHMARK_ROOT / "E2.md"
    raise ValueError(f"Unsupported task id: {task_id}")


def load_task(task_id: str) -> str:
    return task_path(task_id).read_text(encoding="utf-8").strip()


def render_prompt(memory_payload: str, task_text: str) -> str:
    """Render both conditions with the same prompt structure."""
    return PROMPT_TEMPLATE.format(memory_payload=memory_payload, task_text=task_text)


def validate_config(path: Path = CONFIG_PATH) -> str:
    """Validate Stage 0 guardrails and return the config hash."""
    if not path.is_file():
        raise FileNotFoundError(f"Missing DSH config: {path}")
    content = path.read_text(encoding="utf-8")
    missing = [marker for marker in REQUIRED_CONFIG_MARKERS if marker not in content]
    if missing:
        raise ValueError(f"Stage 0 config is missing required markers: {missing}")
    found_forbidden = [
        marker for marker in FORBIDDEN_CONFIG_MARKERS if marker in content.lower()
    ]
    if found_forbidden:
        raise ValueError(
            f"Stage 0 config contains forbidden memory markers: {found_forbidden}"
        )
    return sha256_file(path)


def tool_schema_hash() -> str:
    return sha256_text(canonical_json(TOOL_SCHEMA))


def task_hash(task_id: str) -> str:
    return sha256_file(task_path(task_id))


def make_run_id(prefix: str = "stage0") -> str:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return f"{prefix}-{stamp}-{uuid.uuid4().hex[:8]}"


def resolve_results_root(value: str | None) -> Path:
    path = Path(value) if value else DEFAULT_RESULTS_ROOT
    return path if path.is_absolute() else ROOT / path


def redact_secrets(text: str, environment: dict[str, str] | None = None) -> str:
    """Remove common key/token values before writing diagnostic output."""
    redacted = text
    for key, value in (environment or os.environ).items():
        if (
            any(word in key.upper() for word in ("KEY", "TOKEN", "SECRET"))
            and len(value) >= 8
        ):
            redacted = redacted.replace(value, "[REDACTED]")
    return re.sub(
        r"(?i)(api[_-]?key|access[_-]?token|secret)\s*[:=]\s*[^\s,;]+",
        r"\1=[REDACTED]",
        redacted,
    )


def safe_env_metadata(environment: dict[str, str] | None = None) -> dict[str, str]:
    environment = environment or os.environ
    names = ("NODE_VERSION", "PNPM_VERSION", "DSH_PROVIDER", "DSH_MODEL")
    return {name: environment[name] for name in names if name in environment}


def command_parts(command: str) -> list[str]:
    return shlex.split(command, posix=False)


def discover_trace_files(*roots: Path) -> tuple[Path, ...]:
    paths: set[Path] = set()
    for root in roots:
        if root.exists():
            paths.update(path for path in root.rglob("*.jsonl") if path.is_file())
    return tuple(sorted(paths))


def read_jsonl(paths: Iterable[Path]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for path in paths:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        for line_number, line in enumerate(lines, 1):
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                value["_trace_file"] = path.as_posix()
                value["_trace_line"] = line_number
                events.append(value)
    return events


def collect_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from collect_strings(item)
    elif isinstance(value, list | tuple):
        for item in value:
            yield from collect_strings(item)


def event_text(event: dict[str, Any]) -> str:
    return "\n".join(collect_strings(event))


def is_write_event(event: dict[str, Any]) -> bool:
    text = event_text(event).lower()
    return any(
        marker in text for marker in ("str_replace_editor", "write_file", "writefile")
    )


def is_test_event(event: dict[str, Any]) -> bool:
    text = event_text(event).lower()
    return "pytest" in text or "python -m unittest" in text


def has_verifier_feedback(text: str) -> bool:
    lowered = text.lower()
    return any(
        marker in lowered
        for marker in ("expected decimal", "got float", "verifier", "[r1]", "typeerror")
    )


def analyze_trace(trace_files: Sequence[Path], memory_visible: bool) -> dict[str, Any]:
    events = read_jsonl(trace_files)
    writes = [event for event in events if is_write_event(event)]
    first_write_text = event_text(writes[0]) if writes else ""
    first_write_line = writes[0].get("_trace_line") if writes else None
    feedback_before_first_write = False
    if writes:
        first_file = writes[0].get("_trace_file")
        for event in events:
            if (
                event.get("_trace_file") == first_file
                and event.get("_trace_line", 0) < first_write_line
            ):
                if has_verifier_feedback(event_text(event)):
                    feedback_before_first_write = True
                    break
    first_attempt = None if not writes else ("decimal" in first_write_text.lower())
    utilized = bool(
        memory_visible and first_attempt is True and not feedback_before_first_write
    )
    return {
        "trace_available": bool(events),
        "tool_events": len(events),
        "test_executions": sum(is_test_event(event) for event in events),
        "first_write_found": bool(writes),
        "first_write_contains_decimal": first_attempt,
        "feedback_before_first_write": feedback_before_first_write,
        "first_attempt_compliance": first_attempt,
        "memory_utilized_before_feedback": utilized,
        "steps_observed": len(events) if events else None,
    }


def host_verify(workspace: Path, task_id: str) -> dict[str, Any]:
    """Run the oracle check outside the agent workspace and return safe facts."""
    source_path = workspace / "src" / "finance.py"
    result: dict[str, Any] = {
        "passed": False,
        "error_type": None,
        "uses_decimal": False,
        "source_exists": source_path.is_file(),
    }
    if not source_path.is_file():
        result["error_type"] = "missing_source"
        return result
    try:
        source = source_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        names = {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        }
        function_name = (
            "calculate_return" if task_id.endswith("_E1") else "calculate_drawdown"
        )
        if function_name not in names:
            result["error_type"] = "missing_function"
            return result
        result["uses_decimal"] = any(
            isinstance(node, ast.Name) and node.id == "Decimal"
            for node in ast.walk(tree)
        )
        namespace: dict[str, Any] = {"__name__": "stage0_finance"}
        exec(compile(tree, str(source_path), "exec"), namespace)
        from decimal import Decimal

        function = namespace[function_name]
        if task_id.endswith("_E1"):
            actual = function(Decimal("100"), Decimal("110"))
        else:
            actual = function(Decimal("100"), Decimal("90"))
        expected = Decimal("0.10")
        if not isinstance(actual, Decimal):
            result["error_type"] = "non_decimal_result"
        elif actual != expected:
            result["error_type"] = "incorrect_value"
        elif not result["uses_decimal"]:
            result["error_type"] = "decimal_not_explicit"
        else:
            result["passed"] = True
    except SyntaxError:
        result["error_type"] = "syntax_error"
    except Exception:
        result["error_type"] = "execution_error"
    return result


def copy_workspace(destination: Path) -> str:
    if destination.exists():
        raise FileExistsError(f"Workspace already exists: {destination}")
    shutil.copytree(TEMPLATE_ROOT, destination)
    return hash_tree(destination)


def runtime_versions() -> dict[str, str]:
    versions: dict[str, str] = {"python_version": sys.version.split()[0]}
    for executable, key in (("node", "node_version"), ("pnpm", "pnpm_version")):
        try:
            completed = subprocess.run(
                [executable, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if completed.returncode == 0:
                versions[key] = completed.stdout.strip()
        except (FileNotFoundError, subprocess.SubprocessError):
            pass
    return versions


def run_dsh(
    *,
    command: str,
    config_path: Path,
    prompt: str,
    workspace: Path,
    session_root: Path,
    dsh_home: Path,
    episode_dir: Path,
    session_id: str,
    provider: str,
    model: str,
    max_tokens: int,
    max_steps: int,
    timeout: int,
) -> DshResult:
    argv = command_parts(command) + [
        "--profile",
        "headless",
        "--patch",
        str(config_path),
        prompt,
    ]
    environment = os.environ.copy()
    environment.update(
        {
            "DSH_CWD": str(workspace),
            "DSH_SESSION_ROOT": str(session_root),
            "DSH_HOME": str(dsh_home),
            "DSH_SESSION_ID": session_id,
            "DSH_PROVIDER": provider,
            "DSH_MODEL": model,
            "DSH_MAX_TOKENS": str(max_tokens),
            "DSH_MAX_STEPS": str(max_steps),
            "DSH_SYSTEM_PROMPT": SYSTEM_PROMPT,
        }
    )
    raw_dir = episode_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = raw_dir / "dsh.stdout.txt"
    stderr_path = raw_dir / "dsh.stderr.txt"
    try:
        completed = subprocess.run(
            argv,
            cwd=workspace,
            env=environment,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        stdout_path.write_text(
            redact_secrets(completed.stdout, environment), encoding="utf-8"
        )
        stderr_path.write_text(
            redact_secrets(completed.stderr, environment), encoding="utf-8"
        )
        timed_out = False
        returncode = completed.returncode
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"DSH command was not found: {command!r}. "
            "Install DSH or pass --dsh-command."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        stdout_path.write_text(redact_secrets(stdout, environment), encoding="utf-8")
        stderr_path.write_text(redact_secrets(stderr, environment), encoding="utf-8")
        timed_out = True
        returncode = -1
    trace_files = discover_trace_files(session_root, dsh_home, workspace)
    return DshResult(returncode, stdout_path, stderr_path, trace_files, timed_out)


def dump_effective_config(command: str, run_dir: Path) -> str:
    """Ask DSH for its effective config before starting any episode."""
    preflight_dir = run_dir / "preflight"
    preflight_dir.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    environment.update(
        {
            "DSH_CWD": str(ROOT),
            "DSH_SESSION_ROOT": str(preflight_dir / "session"),
            "DSH_HOME": str(preflight_dir / "dsh-home"),
            "DSH_PROVIDER": DEFAULT_PROVIDER,
            "DSH_MODEL": DEFAULT_MODEL,
            "DSH_MAX_STEPS": str(DEFAULT_MAX_STEPS),
            "DSH_SYSTEM_PROMPT": SYSTEM_PROMPT,
        }
    )
    argv = command_parts(command) + [
        "--profile",
        "headless",
        "--patch",
        str(CONFIG_PATH),
        "--dump-config",
    ]
    try:
        completed = subprocess.run(
            argv,
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"DSH command was not found: {command!r}. "
            "Install DSH or pass --dsh-command."
        ) from exc
    output = redact_secrets(completed.stdout + completed.stderr, environment)
    dump_path = preflight_dir / "effective-config.txt"
    dump_path.write_text(output, encoding="utf-8")
    if completed.returncode != 0:
        raise RuntimeError(
            "DSH effective-config preflight failed "
            f"(exit {completed.returncode}); see {dump_path}"
        )
    return sha256_file(dump_path)


def episode_record(
    *,
    run_id: str,
    condition: str,
    role: str,
    session_id: str,
    workspace_id: str,
    initial_workspace_hash: str,
    task_id: str,
    memory_payload: str,
    config_hash: str,
    prompt: str,
    trace: dict[str, Any],
    verifier: dict[str, Any],
    dsh_result: DshResult | None,
    provider: str,
    model: str,
    max_tokens: int,
    max_steps: int,
    runtime: dict[str, str],
) -> dict[str, Any]:
    memory_visible = condition == "relevant_memory"
    payload_id = R1["id"] if memory_visible else None
    final_success = bool(verifier["passed"])
    return {
        "run_id": run_id,
        "role": role,
        "condition": condition,
        "session_id": session_id,
        "workspace_id": workspace_id,
        "workspace_snapshot": initial_workspace_hash,
        "task_id": task_id,
        "memory_channel": {
            "mode": "host_managed",
            "payload_id": payload_id,
            "injection_location": "memory_context_block",
            "payload_sha256": sha256_text(memory_payload),
        },
        "harness": {
            "dsh_version": DSH_VERSION,
            "dsh_commit": DSH_COMMIT,
            "runtime_mode": "headless",
            "platform": platform.system().lower(),
            "provider": provider,
            "model": model,
            "protocol": "provider_native_or_configured",
            "temperature": DEFAULT_TEMPERATURE,
            "reasoning_effort": DEFAULT_REASONING_EFFORT,
            "max_tokens": max_tokens,
            "max_steps": max_steps,
            "config_sha256": config_hash,
            "system_prompt_sha256": sha256_text(SYSTEM_PROMPT),
            "tool_schema_sha256": tool_schema_hash(),
            "task_sha256": task_hash(task_id),
            "runtime": runtime,
        },
        "prompt": {
            "template_sha256": sha256_text(PROMPT_TEMPLATE),
            "prompt_sha256": sha256_text(prompt),
            "memory_block_sha256": sha256_text(memory_payload),
        },
        "behavior": {
            "first_attempt_compliance": trace["first_attempt_compliance"],
            "memory_visible": memory_visible,
            "memory_utilized_before_feedback": trace["memory_utilized_before_feedback"],
            "tests_to_success": trace["test_executions"] or None,
            "steps_to_success": trace["steps_observed"] if final_success else None,
            "final_success": final_success,
            "trace_available": trace["trace_available"],
        },
        "verifier": verifier,
        "execution": {
            "status": "dry_run" if dsh_result is None else "completed",
            "returncode": None if dsh_result is None else dsh_result.returncode,
            "timed_out": False if dsh_result is None else dsh_result.timed_out,
            "trace_files": [
                path.as_posix()
                for path in (dsh_result.trace_files if dsh_result else ())
            ],
        },
    }


def execute_episode(
    *,
    run_id: str,
    run_dir: Path,
    condition: str,
    role: str,
    task_id: str,
    config_hash: str,
    provider: str,
    model: str,
    max_tokens: int,
    max_steps: int,
    timeout: int,
    dsh_command: str,
    dry_run: bool,
) -> dict[str, Any]:
    episode_id = f"{role}-{uuid.uuid4().hex[:8]}"
    episode_dir = run_dir / "episodes" / episode_id
    workspace = episode_dir / "workspace"
    session_root = episode_dir / "session"
    dsh_home = episode_dir / "dsh-home"
    workspace_id = f"workspace-{uuid.uuid4().hex}"
    session_id = f"session-{uuid.uuid4().hex}"
    episode_dir.mkdir(parents=True, exist_ok=True)
    session_root.mkdir(parents=True, exist_ok=True)
    dsh_home.mkdir(parents=True, exist_ok=True)
    initial_workspace_hash = copy_workspace(workspace)
    memory_payload = (
        R1["content"] if condition == "relevant_memory" else NO_MEMORY_PAYLOAD
    )
    prompt = render_prompt(memory_payload, load_task(task_id))
    dsh_result = None
    trace_files: tuple[Path, ...] = ()
    if not dry_run:
        dsh_result = run_dsh(
            command=dsh_command,
            config_path=CONFIG_PATH,
            prompt=prompt,
            workspace=workspace,
            session_root=session_root,
            dsh_home=dsh_home,
            episode_dir=episode_dir,
            session_id=session_id,
            provider=provider,
            model=model,
            max_tokens=max_tokens,
            max_steps=max_steps,
            timeout=timeout,
        )
        trace_files = dsh_result.trace_files
    trace = analyze_trace(trace_files, condition == "relevant_memory")
    verifier = host_verify(workspace, task_id)
    record = episode_record(
        run_id=run_id,
        condition=condition,
        role=role,
        session_id=session_id,
        workspace_id=workspace_id,
        initial_workspace_hash=initial_workspace_hash,
        task_id=task_id,
        memory_payload=memory_payload,
        config_hash=config_hash,
        prompt=prompt,
        trace=trace,
        verifier=verifier,
        dsh_result=dsh_result,
        provider=provider,
        model=model,
        max_tokens=max_tokens,
        max_steps=max_steps,
        runtime=runtime_versions(),
    )
    (episode_dir / "record.json").write_text(
        canonical_json(record) + "\n", encoding="utf-8"
    )
    return record


def summarize(records: Sequence[dict[str, Any]]) -> dict[str, Any]:
    by_condition: dict[str, dict[str, Any]] = {}
    for condition in ("no_memory", "relevant_memory"):
        condition_records = [
            record for record in records if record["condition"] == condition
        ]
        compliance = [
            record["behavior"]["first_attempt_compliance"]
            for record in condition_records
            if record["behavior"]["first_attempt_compliance"] is not None
        ]
        successes = [
            record["behavior"]["final_success"] for record in condition_records
        ]
        steps = [
            record["behavior"]["steps_to_success"]
            for record in condition_records
            if record["behavior"]["steps_to_success"] is not None
        ]
        by_condition[condition] = {
            "episodes": len(condition_records),
            "first_attempt_compliance_rate": (
                sum(compliance) / len(compliance) if compliance else None
            ),
            "final_success_rate": (
                sum(successes) / len(successes) if successes else None
            ),
            "mean_steps_to_success": (sum(steps) / len(steps)) if steps else None,
        }
    control = by_condition["no_memory"]["first_attempt_compliance_rate"]
    treatment = by_condition["relevant_memory"]["first_attempt_compliance_rate"]
    delta = None if control is None or treatment is None else treatment - control
    isolation = check_isolation(records)
    return {
        "stage": "stage0",
        "primary_metric": "first_attempt_compliance",
        "delta_first_attempt_compliance": delta,
        "isolation_valid": isolation["valid"],
        "isolation_checks": isolation["checks"],
        "by_condition": by_condition,
        "behavioral_signal": None if delta is None else delta >= 0.30,
        "interpretation": (
            "Stage 0 isolation passed, behavioral effect inconclusive"
            if isolation["valid"] and (delta is None or delta < 0.30)
            else None
        ),
    }


def check_isolation(records: Sequence[dict[str, Any]]) -> dict[str, Any]:
    control = [record for record in records if record["condition"] == "no_memory"]
    treatment = [
        record for record in records if record["condition"] == "relevant_memory"
    ]
    checks: dict[str, bool] = {}
    if not control or not treatment:
        return {"valid": False, "checks": {"both_conditions_present": False}}
    left = control[0]
    right = treatment[0]
    checks["both_conditions_present"] = True
    checks["session_ids_differ"] = left["session_id"] != right["session_id"]
    checks["workspace_snapshots_match"] = (
        left["workspace_snapshot"] == right["workspace_snapshot"]
    )
    same_keys = (
        "dsh_version",
        "dsh_commit",
        "provider",
        "model",
        "protocol",
        "temperature",
        "reasoning_effort",
        "max_tokens",
        "max_steps",
        "config_sha256",
        "system_prompt_sha256",
        "tool_schema_sha256",
        "task_sha256",
    )
    for key in same_keys:
        checks[f"same_{key}"] = left["harness"].get(key) == right["harness"].get(key)
    checks["prompt_template_matches"] = (
        left["prompt"]["template_sha256"] == right["prompt"]["template_sha256"]
    )
    checks["only_memory_payload_differs"] = (
        left["prompt"]["memory_block_sha256"] != right["prompt"]["memory_block_sha256"]
        and left["prompt"]["prompt_sha256"] != right["prompt"]["prompt_sha256"]
    )
    checks["control_has_no_payload_id"] = left["memory_channel"]["payload_id"] is None
    checks["treatment_has_r1"] = right["memory_channel"]["payload_id"] == "R1"
    return {"valid": all(checks.values()), "checks": checks}


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def write_jsonl(path: Path, values: Iterable[Any]) -> None:
    path.write_text(
        "\n".join(canonical_json(value) for value in values) + "\n", encoding="utf-8"
    )


def run_experiment(args: argparse.Namespace) -> Path:
    config_hash = validate_config()
    results_root = resolve_results_root(args.output_dir)
    results_root.mkdir(parents=True, exist_ok=True)
    run_id = make_run_id()
    run_dir = results_root / run_id
    run_dir.mkdir(parents=True)
    runtime = runtime_versions()
    provider = args.provider
    model = args.model
    records: list[dict[str, Any]] = []
    memory_events: list[dict[str, Any]] = []

    manifest = {
        "run_id": run_id,
        "stage": "stage0",
        "mode": args.mode,
        "replicates": args.replicates,
        "dsh_command": args.dsh_command,
        "dsh_version": DSH_VERSION,
        "dsh_commit": DSH_COMMIT,
        "runtime_mode": "headless",
        "platform": platform.system().lower(),
        "provider": provider,
        "model": model,
        "protocol": "provider_native_or_configured",
        "temperature": DEFAULT_TEMPERATURE,
        "reasoning_effort": DEFAULT_REASONING_EFFORT,
        "max_tokens": args.max_tokens,
        "max_steps": args.max_steps,
        "config_sha256": config_hash,
        "system_prompt_sha256": sha256_text(SYSTEM_PROMPT),
        "tool_schema_sha256": tool_schema_hash(),
        "runtime": runtime,
        "api_key_policy": "keys are read by DSH from environment and never serialized",
    }
    write_json(run_dir / "manifest.json", manifest)

    if args.mode == "dry_run":
        condition = args.condition
        task_id = "decimal_transfer_E2"
        records.append(
            execute_episode(
                run_id=run_id,
                run_dir=run_dir,
                condition=condition,
                role=f"dry_run_{condition}",
                task_id=task_id,
                config_hash=config_hash,
                provider=provider,
                model=model,
                max_tokens=args.max_tokens,
                max_steps=args.max_steps,
                timeout=args.timeout,
                dsh_command=args.dsh_command,
                dry_run=True,
            )
        )
    else:
        manifest["effective_config_dump_sha256"] = dump_effective_config(
            args.dsh_command, run_dir
        )
        write_json(run_dir / "manifest.json", manifest)
        seed = execute_episode(
            run_id=run_id,
            run_dir=run_dir,
            condition="seed",
            role="S1_seed",
            task_id="decimal_transfer_E1",
            config_hash=config_hash,
            provider=provider,
            model=model,
            max_tokens=args.max_tokens,
            max_steps=args.max_steps,
            timeout=args.timeout,
            dsh_command=args.dsh_command,
            dry_run=False,
        )
        records.append(seed)
        memory_events.append(
            {
                "event": "oracle_fact_created",
                "created_after_role": "S1_seed",
                "created_at_epoch": time.time(),
                "payload": R1,
                "payload_sha256": sha256_text(R1["content"]),
            }
        )
        replicates = 1 if args.mode == "smoke" else args.replicates
        for index in range(replicates):
            records.append(
                execute_episode(
                    run_id=run_id,
                    run_dir=run_dir,
                    condition="no_memory",
                    role=f"S2_control_{index + 1:02d}",
                    task_id="decimal_transfer_E2",
                    config_hash=config_hash,
                    provider=provider,
                    model=model,
                    max_tokens=args.max_tokens,
                    max_steps=args.max_steps,
                    timeout=args.timeout,
                    dsh_command=args.dsh_command,
                    dry_run=False,
                )
            )
            records.append(
                execute_episode(
                    run_id=run_id,
                    run_dir=run_dir,
                    condition="relevant_memory",
                    role=f"S2_memory_{index + 1:02d}",
                    task_id="decimal_transfer_E2",
                    config_hash=config_hash,
                    provider=provider,
                    model=model,
                    max_tokens=args.max_tokens,
                    max_steps=args.max_steps,
                    timeout=args.timeout,
                    dsh_command=args.dsh_command,
                    dry_run=False,
                )
            )
    write_jsonl(run_dir / "episodes.jsonl", records)
    write_jsonl(run_dir / "memory_events.jsonl", memory_events)
    summary = summarize(records)
    write_json(run_dir / "summary.json", summary)
    print(f"Run written to: {run_dir}")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return run_dir


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--dry-run", dest="mode", action="store_const", const="dry_run")
    modes.add_argument("--smoke", dest="mode", action="store_const", const="smoke")
    modes.add_argument("--confirm", dest="mode", action="store_const", const="confirm")
    parser.add_argument(
        "--condition",
        choices=("no_memory", "relevant_memory"),
        default="no_memory",
    )
    parser.add_argument("--replicates", type=int, default=10)
    parser.add_argument("--provider", default=DEFAULT_PROVIDER)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    parser.add_argument("--max-steps", type=int, default=DEFAULT_MAX_STEPS)
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--dsh-command", default=os.getenv("DSH_COMMAND", "dsh"))
    parser.add_argument("--output-dir", default=None)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.replicates < 1:
        raise SystemExit("--replicates must be at least 1")
    if args.max_tokens < 1:
        raise SystemExit("--max-tokens must be positive")
    if args.max_steps < 1:
        raise SystemExit("--max-steps must be positive")
    try:
        run_experiment(args)
    except (FileNotFoundError, RuntimeError, ValueError, OSError) as exc:
        print(f"Stage 0 run failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
