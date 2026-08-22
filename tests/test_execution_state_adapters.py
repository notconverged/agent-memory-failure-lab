from __future__ import annotations

import inspect

import pytest

from benchmarks.execution_state.adapters.base import capability
from benchmarks.execution_state.adapters.graphiti_adapter import (
    capabilities as graphiti_capabilities,
)
from benchmarks.execution_state.adapters.mem0_adapter import (
    capabilities as mem0_capabilities,
)
from benchmarks.execution_state.adapters.v0_adapter import V0Adapter


def test_unsupported_capability_requires_evidence():
    with pytest.raises(ValueError, match="require evidence"):
        capability(
            "unsupported",
            derivation="missing",
            limitations="none",
        )


def test_product_capabilities_are_explicit_and_never_numeric_zero():
    for values in (
        V0Adapter.capabilities(),
        mem0_capabilities(),
        graphiti_capabilities(),
    ):
        assert set(values) == {
            "active_path_integrity",
            "branch_isolation",
            "compression_fidelity",
            "maintain_precision",
        }
        for value in values.values():
            assert value["support_status"] in {
                "native",
                "derived",
                "not_observable",
                "unsupported",
            }
            assert value["value"] is None
            assert value["evidence_paths"]


def test_v0_adapter_does_not_call_low_level_product_writes():
    source = inspect.getsource(V0Adapter)
    assert "upsert_execution_node" not in source
    assert ".create_memory(" not in source
    assert ".transition(" not in source
    assert "handle_hook" in source
    assert "ContextRouter" in source
    assert "synthetic_hook_replay" in source
