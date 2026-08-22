from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from benchmarks.execution_state.reference_impl.state_machine import (
    ReferenceStateMachine,
    Variant,
)

ROOT = Path(__file__).resolve().parents[1]


def load_variants() -> dict[str, dict[str, bool]]:
    return json.loads(
        (ROOT / "ablations" / "variants.json").read_text(encoding="utf-8")
    )


def capability(status: str, value: Any, derivation: str) -> dict[str, Any]:
    return {
        "support_status": status,
        "value": value,
        "evidence_paths": [],
        "derivation": derivation,
        "limitations": "Reference positive control; not a product result.",
        "workaround": None,
    }


def run_reference(scenario: dict[str, Any], variant_name: str) -> dict[str, Any]:
    variants = load_variants()
    if variant_name not in variants:
        raise ValueError(f"unknown reference variant: {variant_name}")
    config = variants[variant_name]
    machine = ReferenceStateMachine(Variant(variant_name, **config))
    for event in scenario["timeline"]:
        machine.apply(event)

    checkpoint_steps = {
        int(item["step_index"]) for item in scenario["product_checkpoints"]
    }
    states = {
        str(step): machine.materialize_state_at(step).to_dict()
        for step in sorted(checkpoint_steps)
    }
    all_states = {
        str(step): machine.materialize_state_at(step).to_dict()
        for step in sorted(machine.snapshots)
        if step
    }
    observations: dict[str, dict[str, Any]] = {}
    for checkpoint in scenario["product_checkpoints"]:
        step = int(checkpoint["step_index"])
        state = machine.materialize_state_at(step)
        retrieval = "\n".join(
            [*state.compressed_state]
            + [
                next(
                    (
                        node["observation"] or ""
                        for node in state.nodes
                        if node["step_key"] == step_key
                    ),
                    "",
                )
                for step_key in state.recent_raw
            ]
        ).strip()
        observations[str(step)] = {
            "query_status": "completed" if retrieval else "empty",
            "retrieval_text": retrieval,
            "query": checkpoint["query"],
        }
    advanced_status = "native" if variant_name == "A0" else "derived"
    return {
        "system": "reference",
        "variant": variant_name,
        "scenario_id": scenario["scenario_id"],
        "states": states,
        "all_states": all_states,
        "operations": machine.operations,
        "maintain_decisions": machine.maintain_decisions,
        "observations": observations,
        "capabilities": {
            "active_path_integrity": capability(
                advanced_status,
                None,
                "Canonical root-to-current path from the reference state machine.",
            ),
            "branch_isolation": capability(
                advanced_status if not config["flat"] else "unsupported",
                None,
                "Reference tree retains inactive siblings while materializing one path.",  # noqa: E501
            ),
            "compression_fidelity": capability(
                advanced_status if config["compress"] else "unsupported",
                None,
                "Reference summary nodes expose ordered cover_node_ids.",
            ),
            "maintain_precision": capability(
                advanced_status if config["maintain"] else "unsupported",
                None,
                "pipeline_conformance_not_detection_capability",
            ),
        },
    }
