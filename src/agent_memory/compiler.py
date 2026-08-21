from __future__ import annotations

import json
import os
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from agent_memory.models import (
    Anchor,
    CompilerJob,
    EvidenceAuthority,
    MemoryCandidate,
    MemoryKind,
)
from agent_memory.redaction import redact_text

OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["job_id", "cursor", "head", "candidates"],
    "properties": {
        "job_id": {"type": "string"},
        "cursor": {"type": "string"},
        "head": {"type": "string"},
        "candidates": {
            "type": "array",
            "maxItems": 50,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "candidate_id",
                    "kind",
                    "claim",
                    "rationale",
                    "evidence_ids",
                    "anchors",
                    "has_counterevidence",
                ],
                "properties": {
                    "candidate_id": {"type": "string"},
                    "kind": {
                        "type": "string",
                        "enum": [item.value for item in MemoryKind],
                    },
                    "claim": {"type": "string", "maxLength": 8000},
                    "rationale": {"type": "string", "maxLength": 8000},
                    "evidence_ids": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 20,
                        "items": {"type": "string"},
                    },
                    "anchors": {
                        "type": "array",
                        "maxItems": 20,
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["anchor_type", "target"],
                            "properties": {
                                "anchor_type": {
                                    "type": "string",
                                    "enum": ["file", "symbol", "config", "test"],
                                },
                                "target": {"type": "string", "maxLength": 1000},
                                "symbol": {
                                    "type": ["string", "null"],
                                    "maxLength": 500,
                                },
                                "content_hash": {
                                    "type": "string",
                                    "maxLength": 128,
                                },
                            },
                        },
                    },
                    "has_counterevidence": {"type": "boolean"},
                },
            },
        },
    },
}


class CompilerExecutor(Protocol):
    def compile(self, job: CompilerJob) -> list[MemoryCandidate]: ...


class CompilerValidationError(ValueError):
    pass


class CodexExecCompiler:
    """Run a bounded extraction job in an isolated, read-only Codex process."""

    def __init__(
        self,
        repository_root: Path,
        codex_command: str = "codex",
        model: str | None = None,
        timeout_seconds: int = 180,
        runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    ) -> None:
        self.repository_root = repository_root
        self.codex_command = codex_command
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.runner = runner

    def compile(self, job: CompilerJob) -> list[MemoryCandidate]:
        prompt = self._prompt(job)
        with tempfile.TemporaryDirectory(prefix="agent-memory-compiler-") as temp:
            temp_dir = Path(temp)
            schema_path = temp_dir / "output-schema.json"
            output_path = temp_dir / "compiler-output.json"
            schema_path.write_text(json.dumps(OUTPUT_SCHEMA), encoding="utf-8")
            command = [
                self.codex_command,
                "exec",
                "--ephemeral",
                "--ignore-user-config",
                "--sandbox",
                "read-only",
                "--skip-git-repo-check",
                "--output-schema",
                str(schema_path),
                "-o",
                str(output_path),
                "-C",
                str(self.repository_root),
            ]
            if self.model:
                command.extend(["--model", self.model])
            command.append("-")
            environment = os.environ.copy()
            environment["AGENT_MEMORY_COMPILER_MODE"] = "1"
            result = self.runner(
                command,
                input=prompt,
                text=True,
                capture_output=True,
                timeout=self.timeout_seconds,
                check=False,
                env=environment,
            )
            if result.returncode != 0:
                error = redact_text(result.stderr or result.stdout, 2_000)
                raise RuntimeError(f"Compiler process failed: {error}")
            if not output_path.exists():
                raise RuntimeError("Compiler process produced no output file")
            try:
                payload = json.loads(output_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as error:
                raise CompilerValidationError("Compiler output is not JSON") from error
        return validate_compiler_output(job, payload)

    @staticmethod
    def _prompt(job: CompilerJob) -> str:
        contract = {
            "task": "Extract durable coding-project memory candidates only.",
            "allowed_kinds": [item.value for item in MemoryKind],
            "rules": [
                (
                    "Do not emit TODO, progress, Procedure, preference, "
                    "or full transcript."
                ),
                "A temporary attempt is not a Decision.",
                "Failure must retain its environment, attempt, and outcome conditions.",
                "Use only supplied evidence_ids; never invent evidence or authority.",
                "Report counterevidence instead of resolving it silently.",
            ],
            "job": job.to_dict(),
        }
        return json.dumps(contract, ensure_ascii=False)


def validate_compiler_output(
    job: CompilerJob, payload: dict[str, Any]
) -> list[MemoryCandidate]:
    if not isinstance(payload, dict):
        raise CompilerValidationError("Compiler output must be an object")
    expected = {
        "job_id": job.job_id,
        "cursor": job.cursor,
        "head": job.head,
    }
    for field, value in expected.items():
        if payload.get(field) != value:
            raise CompilerValidationError(f"Compiler output has stale {field}")
    raw_candidates = payload.get("candidates")
    if not isinstance(raw_candidates, list) or len(raw_candidates) > 50:
        raise CompilerValidationError("candidates must be a bounded array")

    evidence_by_id = {item.evidence_id: item for item in job.evidence_bundle.evidence}
    candidates: list[MemoryCandidate] = []
    seen_ids: set[str] = set()
    for raw in raw_candidates:
        if not isinstance(raw, dict):
            raise CompilerValidationError("candidate must be an object")
        candidate_id = _required_text(raw, "candidate_id", 200)
        if candidate_id in seen_ids:
            raise CompilerValidationError("candidate_id must be unique within a job")
        seen_ids.add(candidate_id)
        try:
            kind = MemoryKind(raw.get("kind"))
        except ValueError as error:
            raise CompilerValidationError("unsupported memory kind") from error
        evidence_ids = raw.get("evidence_ids")
        if (
            not isinstance(evidence_ids, list)
            or not evidence_ids
            or len(evidence_ids) > 20
        ):
            raise CompilerValidationError("candidate must reference bounded evidence")
        if any(item not in evidence_by_id for item in evidence_ids):
            raise CompilerValidationError("candidate references unknown evidence")
        anchors = _parse_anchors(raw.get("anchors", []))
        counter = raw.get("has_counterevidence")
        if not isinstance(counter, bool):
            raise CompilerValidationError("has_counterevidence must be boolean")
        candidates.append(
            MemoryCandidate(
                candidate_id=candidate_id,
                kind=kind,
                claim=redact_text(_required_text(raw, "claim", 8_000), 8_000),
                rationale=redact_text(_required_text(raw, "rationale", 8_000), 8_000),
                evidence=tuple(evidence_by_id[item] for item in evidence_ids),
                anchors=anchors,
                has_counterevidence=counter,
            )
        )
    return candidates


def _required_text(value: dict[str, Any], field: str, limit: int) -> str:
    item = value.get(field)
    if not isinstance(item, str) or not item.strip() or len(item) > limit:
        raise CompilerValidationError(f"{field} must be non-empty bounded text")
    return item.strip()


def _parse_anchors(values: Any) -> tuple[Anchor, ...]:
    if not isinstance(values, list) or len(values) > 20:
        raise CompilerValidationError("anchors must be a bounded array")
    anchors: list[Anchor] = []
    for value in values:
        if not isinstance(value, dict):
            raise CompilerValidationError("anchor must be an object")
        anchor_type = value.get("anchor_type")
        if anchor_type not in {"file", "symbol", "config", "test"}:
            raise CompilerValidationError("unsupported anchor type")
        target = _required_text(value, "target", 1_000)
        anchors.append(
            Anchor(
                anchor_type=anchor_type,
                target=target,
                symbol=value.get("symbol"),
                content_hash=str(value.get("content_hash", ""))[:128],
            )
        )
    return tuple(anchors)


def highest_authority(candidate: MemoryCandidate) -> EvidenceAuthority:
    ranking = {
        EvidenceAuthority.EXPLICIT_USER: 6,
        EvidenceAuthority.PROJECT_NORM: 5,
        EvidenceAuthority.DIRECT_TEST: 4,
        EvidenceAuthority.DIRECT_REPO: 3,
        EvidenceAuthority.TOOL_RESULT: 2,
        EvidenceAuthority.AGENT_INFERENCE: 1,
    }
    return max(candidate.evidence, key=lambda item: ranking[item.authority]).authority
