from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

CAPABILITY_NAMES = (
    "active_path_integrity",
    "branch_isolation",
    "compression_fidelity",
    "maintain_precision",
)
SUPPORT_STATUSES = {"native", "derived", "not_observable", "unsupported"}


@dataclass(frozen=True)
class AdapterContext:
    system: str
    scenario: dict[str, Any]
    run_id: str
    workspace: Path
    data_dir: Path
    run_dir: Path


class SystemAdapter(Protocol):
    def execute(self, context: AdapterContext) -> dict[str, Any]: ...


def capability(
    support_status: str,
    *,
    value: Any = None,
    evidence_paths: list[str] | None = None,
    derivation: str,
    limitations: str,
    workaround: str | None = None,
) -> dict[str, Any]:
    if support_status not in SUPPORT_STATUSES:
        raise ValueError(f"invalid capability support status: {support_status}")
    if support_status == "unsupported" and not evidence_paths:
        raise ValueError("unsupported capabilities require evidence_paths")
    return {
        "support_status": support_status,
        "value": value,
        "evidence_paths": evidence_paths or [],
        "derivation": derivation,
        "limitations": limitations,
        "workaround": workaround,
    }


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    os.replace(temporary, path)


def tree_manifest(root: Path) -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    if root.exists():
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            relative = path.relative_to(root).as_posix()
            content = path.read_bytes()
            files.append(
                {
                    "path": relative,
                    "size": len(content),
                    "sha256": hashlib.sha256(content).hexdigest(),
                }
            )
    encoded = json.dumps(files, sort_keys=True, separators=(",", ":")).encode()
    return {
        "root": str(root.resolve()),
        "files": files,
        "sha256": hashlib.sha256(encoded).hexdigest(),
    }


def ensure_within(path: Path, root: Path) -> None:
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"storage path escapes run data directory: {path}")


def trace_text(scenario: dict[str, Any], start: int, end: int) -> str:
    lines: list[str] = []
    for event in scenario["timeline"]:
        step = int(event["step_index"])
        if start <= step <= end and event["operation"] == "grow":
            lines.extend(
                [
                    f"ACTION: {event['action']}",
                    f"OBSERVATION: {event['observation']}",
                ]
            )
    return "\n".join(lines)


def apply_session_files(workspace: Path, session: dict[str, Any]) -> str:
    tracked = subprocess.run(
        ["git", "ls-files"],
        cwd=workspace,
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    ).stdout.splitlines()
    desired = {Path(item) for item in session["files"]}
    for relative in (Path(item) for item in tracked):
        if relative not in desired:
            (workspace / relative).unlink(missing_ok=True)
    for relative, content in session["files"].items():
        target = workspace / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=workspace, check=True, timeout=15)
    subprocess.run(
        ["git", "commit", "--allow-empty", "-m", session["phase_id"]],
        cwd=workspace,
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    )
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=workspace,
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    ).stdout.strip()
