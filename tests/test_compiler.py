from __future__ import annotations

import json
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from agent_memory.compiler import (
    CodexExecCompiler,
    CompilerValidationError,
    validate_compiler_output,
)
from agent_memory.models import (
    CandidateOperation,
    CaptureCoverage,
    CompilerJob,
    EvidenceAuthority,
    EvidenceBundle,
    EvidenceRef,
    SessionStateSnapshot,
)


def make_job() -> CompilerJob:
    evidence = EvidenceRef(
        "evidence-1",
        EvidenceAuthority.EXPLICIT_USER,
        "user_prompt",
        "session-1:prompt-1",
        "Use Decimal for money",
    )
    bundle = EvidenceBundle(
        "bundle-1",
        "cursor-2",
        "repo-1",
        "main",
        "abc123",
        CaptureCoverage(True, ("prompt",), ("prompt",), ()),
        (evidence,),
    )
    return CompilerJob(
        "job-1",
        "repo-1",
        "main",
        "cursor-2",
        "abc123",
        bundle,
        SessionStateSnapshot("session-1", "Implement money module"),
    )


def valid_output() -> dict:
    return {
        "job_id": "job-1",
        "cursor": "cursor-2",
        "head": "abc123",
        "candidates": [
            {
                "candidate_id": "candidate-1",
                "kind": "Constraint",
                "claim": "Use Decimal for money",
                "rationale": "Explicit user requirement",
                "evidence_ids": ["evidence-1"],
                "anchors": [{"anchor_type": "file", "target": "src/money.py"}],
                "has_counterevidence": False,
            }
        ],
    }


def test_compiler_output_must_match_job_cursor_and_head():
    payload = valid_output()
    payload["head"] = "stale"
    with pytest.raises(CompilerValidationError, match="stale head"):
        validate_compiler_output(make_job(), payload)


def test_compiler_output_cannot_invent_evidence():
    payload = valid_output()
    payload["candidates"][0]["evidence_ids"] = ["invented"]
    with pytest.raises(CompilerValidationError, match="unknown evidence"):
        validate_compiler_output(make_job(), payload)


def test_prompt_explicitly_excludes_procedure_and_todo(tmp_path):
    prompt = CodexExecCompiler(tmp_path)._prompt(make_job())
    contract = json.loads(prompt)
    rules = " ".join(contract["rules"])
    assert "Procedure" in rules
    assert "TODO" in rules
    assert contract["allowed_kinds"] == [
        "Decision",
        "Constraint",
        "ProjectFact",
        "Failure",
    ]


def test_valid_output_reuses_authoritative_evidence_object():
    candidate = validate_compiler_output(make_job(), valid_output())[0]
    assert candidate.evidence[0].authority is EvidenceAuthority.EXPLICIT_USER
    assert candidate.anchors[0].target == "src/money.py"


def test_codex_executor_uses_ephemeral_read_only_isolation(tmp_path):
    captured = {}

    def runner(command, **kwargs):
        captured["command"] = command
        captured["env"] = kwargs["env"]
        output = Path(command[command.index("-o") + 1])
        output.write_text(json.dumps(valid_output()), encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")

    candidates = CodexExecCompiler(tmp_path, runner=runner).compile(make_job())
    command = captured["command"]
    assert "--ephemeral" in command
    assert "--ignore-user-config" in command
    assert command[command.index("--sandbox") + 1] == "read-only"
    assert "--output-schema" in command
    assert captured["env"]["AGENT_MEMORY_COMPILER_MODE"] == "1"
    assert candidates[0].kind.value == "Constraint"


def test_revise_must_target_a_current_memory_of_the_same_kind():
    job = replace(
        make_job(),
        current_memories=(
            {
                "memory_id": "memory-1",
                "revision": 1,
                "kind": "Constraint",
                "claim": "Use Decimal",
                "status": "active",
                "authority": "explicit_user",
                "anchors": [],
            },
        ),
    )
    payload = valid_output()
    payload["candidates"][0].update(
        {"operation": "revise", "target_memory_id": "memory-1"}
    )
    candidate = validate_compiler_output(job, payload)[0]
    assert candidate.operation is CandidateOperation.REVISE
    assert candidate.target_memory_id == "memory-1"

    payload["candidates"][0]["target_memory_id"] = "unknown"
    with pytest.raises(CompilerValidationError, match="current memory"):
        validate_compiler_output(job, payload)
