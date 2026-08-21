from __future__ import annotations

from pathlib import Path

from scripts.run_episode import (
    NO_MEMORY_PAYLOAD,
    R1,
    execute_episode,
    hash_tree,
    host_verify,
    redact_secrets,
    render_prompt,
    summarize,
    validate_config,
)


def test_render_prompt_only_memory_payload_changes():
    task = "Implement calculate_drawdown(peak_price, current_price)."
    control = render_prompt(NO_MEMORY_PAYLOAD, task)
    treatment = render_prompt(R1["content"], task)

    assert control.replace(NO_MEMORY_PAYLOAD, "<PAYLOAD>") == treatment.replace(
        R1["content"], "<PAYLOAD>"
    )
    assert control != treatment
    assert control.count("<MEMORY_CONTEXT>") == 1
    assert treatment.count("<CURRENT_TASK>") == 1


def test_validate_config_has_stage0_guardrails():
    config_hash = validate_config()
    assert len(config_hash) == 64


def test_hash_tree_changes_on_file_change(tmp_path: Path):
    file_path = tmp_path / "sample.txt"
    file_path.write_text("one", encoding="utf-8")
    first = hash_tree(tmp_path)
    file_path.write_text("two", encoding="utf-8")
    assert hash_tree(tmp_path) != first


def test_host_verifier_rejects_float_and_accepts_decimal(tmp_path: Path):
    source_path = tmp_path / "src" / "finance.py"
    source_path.parent.mkdir()
    source_path.write_text(
        "def calculate_drawdown(peak_price, current_price):\n"
        "    return (peak_price - current_price) / peak_price\n",
        encoding="utf-8",
    )
    rejected = host_verify(tmp_path, "decimal_transfer_E2")
    assert rejected["passed"] is False
    assert rejected["error_type"] == "decimal_not_explicit"

    source_path.write_text(
        "from decimal import Decimal\n\n"
        "def calculate_drawdown(peak_price, current_price):\n"
        "    return Decimal(peak_price - current_price) / Decimal(peak_price)\n",
        encoding="utf-8",
    )
    accepted = host_verify(tmp_path, "decimal_transfer_E2")
    assert accepted["passed"] is True


def test_redact_secrets_drops_key_values():
    environment = {"DEMO_API_KEY": "secret-value-123"}
    output = redact_secrets("DEMO_API_KEY=secret-value-123", environment)
    assert "secret-value-123" not in output
    assert "[REDACTED]" in output


def test_core_redaction_handles_quoted_json_keys():
    from agent_memory.redaction import redact_text

    output = redact_text('{"api_key": "secret-value-123", "safe": "ok"}')
    assert "secret-value-123" not in output
    assert '"safe": "ok"' in output


def test_summary_computes_primary_delta(tmp_path: Path):
    run_dir = tmp_path / "run"
    common = {
        "run_id": "test-run",
        "run_dir": run_dir,
        "role": "test",
        "task_id": "decimal_transfer_E2",
        "config_hash": validate_config(),
        "provider": "test-provider",
        "model": "test-model",
        "max_tokens": 4096,
        "max_steps": 24,
        "timeout": 10,
        "dsh_command": "dsh",
        "dry_run": True,
    }
    control = execute_episode(condition="no_memory", **common)
    treatment = execute_episode(condition="relevant_memory", **common)
    control["behavior"]["first_attempt_compliance"] = False
    treatment["behavior"]["first_attempt_compliance"] = True

    result = summarize([control, treatment])
    assert result["isolation_valid"] is True
    assert result["delta_first_attempt_compliance"] == 1.0
