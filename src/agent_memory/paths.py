from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class RepositoryContext:
    repository_id: str
    root: Path
    git_common_dir: Path
    branch: str
    base_branch: str
    head: str


def default_data_root() -> Path:
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "CodingAgentMemory"
    if os.environ.get("XDG_DATA_HOME"):
        return Path(os.environ["XDG_DATA_HOME"]) / "coding-agent-memory"
    return Path.home() / ".local" / "share" / "coding-agent-memory"


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        timeout=5,
    )
    return result.stdout.strip()


def discover_repository(cwd: Path | None = None) -> RepositoryContext:
    working_dir = (cwd or Path.cwd()).resolve()
    root = Path(_git(working_dir, "rev-parse", "--show-toplevel")).resolve()
    common = _git(root, "rev-parse", "--git-common-dir")
    common_dir = (
        (root / common).resolve() if not Path(common).is_absolute() else Path(common)
    )
    branch = _git(root, "branch", "--show-current") or "detached"
    head = _git(root, "rev-parse", "HEAD")
    try:
        remote_head = _git(root, "symbolic-ref", "refs/remotes/origin/HEAD")
        base_branch = remote_head.rsplit("/", maxsplit=1)[-1]
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        base_branch = branch if branch != "detached" else "main"
    identity = str(common_dir).casefold() if os.name == "nt" else str(common_dir)
    repository_id = "repo-" + hashlib.sha256(identity.encode()).hexdigest()[:20]
    return RepositoryContext(
        repository_id=repository_id,
        root=root,
        git_common_dir=common_dir,
        branch=branch,
        base_branch=base_branch,
        head=head,
    )


def repository_data_dir(data_root: Path, repository_id: str) -> Path:
    return data_root / "repositories" / repository_id


def register_repository(data_root: Path, context: RepositoryContext) -> Path:
    registry = data_root / "registry"
    registry.mkdir(parents=True, exist_ok=True)
    target = registry / f"{context.repository_id}.json"
    payload = asdict(context)
    payload["root"] = str(context.root)
    payload["git_common_dir"] = str(context.git_common_dir)
    temp = target.with_suffix(".tmp")
    temp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(temp, target)
    return target
