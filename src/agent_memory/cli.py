from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
import uuid
from pathlib import Path

from agent_memory.audit import (
    build_audit,
    render_dot,
    write_output,
)
from agent_memory.audit import (
    render_markdown as render_trace_markdown,
)
from agent_memory.compiler import CodexExecCompiler
from agent_memory.core import MemoryCore
from agent_memory.inspector import write_markdown
from agent_memory.models import (
    EvidenceAuthority,
    EvidenceRef,
    MemoryKind,
    MemoryStatus,
)
from agent_memory.paths import (
    default_data_root,
    discover_repository,
    register_repository,
)
from agent_memory.policy import PromotionPolicy
from agent_memory.worker import OneShotWorker


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agent-memory")
    parser.add_argument("--data-root", type=Path, default=default_data_root())
    parser.add_argument("--cwd", type=Path, default=Path.cwd())
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init")
    sub.add_parser("doctor")
    sub.add_parser("status")

    list_parser = sub.add_parser("list")
    list_parser.add_argument("--status", action="append")
    show = sub.add_parser("show")
    show.add_argument("memory_id")
    history = sub.add_parser("history")
    history.add_argument("memory_id")
    sub.add_parser("conflicts")

    edit = sub.add_parser("edit")
    edit.add_argument("memory_id", nargs="?")
    edit.add_argument("--kind", choices=[item.value for item in MemoryKind])
    edit.add_argument("--claim", required=True)
    edit.add_argument("--rationale", default="Manual edit")
    edit.add_argument(
        "--status",
        choices=[item.value for item in MemoryStatus],
        default=MemoryStatus.ACTIVE.value,
    )
    invalidate = sub.add_parser("invalidate")
    invalidate.add_argument("memory_id")
    invalidate.add_argument("--reason", required=True)
    restore = sub.add_parser("restore")
    restore.add_argument("memory_id")
    restore.add_argument("--revision", type=int, required=True)
    purge = sub.add_parser("purge")
    purge.add_argument("memory_id")
    purge.add_argument("--yes", action="store_true")
    sub.add_parser("rebuild")
    trace = sub.add_parser("trace")
    trace.add_argument("--session", required=True)
    trace.add_argument("--verify", action="store_true")
    trace.add_argument("--format", choices=("json", "markdown"), default="json")
    trace.add_argument("--output", type=Path)
    graph = sub.add_parser("graph")
    graph.add_argument("--session", required=True)
    graph.add_argument("--format", choices=("json", "dot"), default="json")
    graph.add_argument("--output", type=Path)
    worker = sub.add_parser("worker", help=argparse.SUPPRESS)
    worker.add_argument(
        "--policy",
        choices=[item.value for item in PromotionPolicy],
        default=PromotionPolicy.STRICT.value,
    )
    export = sub.add_parser("export")
    export.add_argument("target", type=Path)
    export.add_argument("--format", choices=("json", "markdown"), default="json")
    return parser


def _open(args: argparse.Namespace) -> tuple[MemoryCore, object]:
    context = discover_repository(args.cwd)
    core = MemoryCore(
        args.data_root,
        context.repository_id,
        context.branch,
        context.base_branch,
    )
    return core, context


def _print(value: object) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False, default=str))


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        core, context = _open(args)
    except Exception as error:
        _print({"ok": False, "error": str(error)})
        return 2
    try:
        if args.command == "init":
            register_repository(args.data_root, context)
            core.register_repository(context)
            _print(
                {
                    "ok": True,
                    "repository_id": context.repository_id,
                    "branch": context.branch,
                    "data_dir": str(core.repository_dir),
                }
            )
        elif args.command == "doctor":
            probe = sqlite3.connect(":memory:")
            try:
                probe.execute("CREATE VIRTUAL TABLE probe USING fts5(value)")
                fts = True
            except sqlite3.OperationalError:
                fts = False
            finally:
                probe.close()
            _print(
                {
                    "ok": True,
                    "python": sys.version.split()[0],
                    "git": shutil.which("git") is not None,
                    "codex": shutil.which("codex") is not None,
                    "fts5": fts,
                    "data_dir": str(core.repository_dir),
                }
            )
        elif args.command == "status":
            result = core.store.statistics(context.repository_id, context.branch)
            result["pending_spool"] = len(core.event_log.pending_spool())
            _print(result)
        elif args.command == "list":
            _print(
                core.store.list_current(
                    context.repository_id,
                    context.branch,
                    args.status,
                    context.base_branch,
                )
            )
        elif args.command == "show":
            _print(
                core.store.get_current(
                    context.repository_id,
                    context.branch,
                    args.memory_id,
                    context.base_branch,
                )
            )
        elif args.command == "history":
            _print(core.store.history(args.memory_id))
        elif args.command == "conflicts":
            _print(
                core.store.list_current(
                    context.repository_id,
                    context.branch,
                    [MemoryStatus.CONFLICTED.value],
                    context.base_branch,
                )
            )
        elif args.command == "edit":
            _print(_manual_edit(core, args).to_dict())
        elif args.command == "invalidate":
            revision = core.transition(
                args.memory_id, MemoryStatus.INVALIDATED, args.reason
            )
            _print(revision.to_dict())
        elif args.command == "restore":
            _print(_restore(core, args.memory_id, args.revision).to_dict())
        elif args.command == "purge":
            if not args.yes:
                raise ValueError("purge is irreversible; repeat with --yes")
            _print({"removed_events": core.purge(args.memory_id)})
        elif args.command == "rebuild":
            _print({"projected_events": core.rebuild()})
        elif args.command == "trace":
            audit = build_audit(core, args.session)
            content = (
                json.dumps(audit, indent=2, ensure_ascii=False)
                if args.format == "json"
                else render_trace_markdown(audit)
            )
            if args.output:
                _print({"target": str(write_output(args.output, content))})
            else:
                print(content)
            if args.verify and not audit["ok"]:
                return 3
        elif args.command == "graph":
            audit = build_audit(core, args.session)
            content = (
                json.dumps(
                    {"nodes": audit["nodes"], "edges": audit["edges"]},
                    indent=2,
                    ensure_ascii=False,
                )
                if args.format == "json"
                else render_dot(audit)
            )
            if args.output:
                _print({"target": str(write_output(args.output, content))})
            else:
                print(content)
        elif args.command == "worker":
            compiler = CodexExecCompiler(context.root)
            result = OneShotWorker(
                core,
                compiler,
                lambda: discover_repository(context.root).head,
                PromotionPolicy(args.policy),
            ).run()
            _print(result)
        elif args.command == "export":
            target = (
                core.export_json(args.target)
                if args.format == "json"
                else write_markdown(core, args.target)
            )
            _print({"target": str(target)})
        return 0
    except (KeyError, ValueError) as error:
        _print({"ok": False, "error": str(error)})
        return 2
    finally:
        core.close()


def _manual_edit(core: MemoryCore, args: argparse.Namespace):
    current = None
    memory_id = args.memory_id
    if memory_id:
        current = core.store.get_current(
            core.repository_id, core.branch, memory_id, core.base_branch
        )
        if current is None:
            raise KeyError(f"Unknown memory: {memory_id}")
    kind = MemoryKind(args.kind or (current and current["kind"]) or "ProjectFact")
    evidence = EvidenceRef(
        f"ev-{uuid.uuid4().hex}",
        EvidenceAuthority.EXPLICIT_USER,
        "manual_cli",
        "agent-memory edit",
        args.claim,
    )
    return core.create_memory(
        kind,
        args.claim,
        args.rationale,
        MemoryStatus(args.status),
        EvidenceAuthority.EXPLICIT_USER,
        (evidence,),
        memory_id=memory_id,
        metadata={"manual_edit": True},
    )


def _restore(core: MemoryCore, memory_id: str, revision: int):
    history = core.store.history(memory_id)
    source = next((item for item in history if item["revision"] == revision), None)
    if source is None:
        raise KeyError(f"Unknown revision: {memory_id}@{revision}")
    evidence = tuple(
        EvidenceRef(
            item["evidence_id"],
            EvidenceAuthority(item["authority"]),
            item["source_type"],
            item["source_ref"],
            item.get("excerpt", ""),
            item.get("content_hash", ""),
            item["captured_at"],
        )
        for item in source["evidence"]
    )
    return core.create_memory(
        MemoryKind(source["kind"]),
        source["claim"],
        source["rationale"],
        MemoryStatus.ACTIVE,
        EvidenceAuthority.EXPLICIT_USER,
        evidence,
        memory_id=memory_id,
        metadata={"restored_from_revision": revision},
    )


if __name__ == "__main__":
    raise SystemExit(main())
