from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from scripts.competitor_adapters.base import (
    AdapterRequest,
    manual_required,
    to_jsonable,
)


def run_phase(request: AdapterRequest) -> dict:
    config_value = os.environ.get("AMLAB_MEM0_CONFIG")
    if not config_value:
        return manual_required(
            request,
            "Set AMLAB_MEM0_CONFIG to an explicit Mem0 OSS JSON config. "
            "Defaults are rejected because they write to shared /tmp and home paths.",
        )
    config_path = Path(config_value).expanduser().resolve()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    request.data_dir.mkdir(parents=True, exist_ok=True)
    root = request.data_dir.resolve()
    vector = config.get("vector_store", {})
    vector_config = vector.get("config", {})
    vector_path = vector_config.get("path")
    history_path = config.get("history_db_path")

    def inside_run(value: object) -> bool:
        if not isinstance(value, str) or not value:
            return False
        return Path(value).expanduser().resolve().is_relative_to(root)

    def contains_inline_secret(value: object) -> bool:
        if isinstance(value, dict):
            for key, item in value.items():
                normalized = str(key).casefold().replace("-", "_")
                if ("api_key" in normalized or "token" in normalized) and item:
                    return True
                if contains_inline_secret(item):
                    return True
        if isinstance(value, list):
            return any(contains_inline_secret(item) for item in value)
        return False

    if (
        vector.get("provider") != "qdrant"
        or not inside_run(vector_path)
        or not inside_run(history_path)
    ):
        return manual_required(
            request,
            "Mem0 must use local Qdrant 'vector_store.config.path' and "
            "top-level 'history_db_path', both under this run data directory: "
            f"{request.data_dir}",
        )
    if contains_inline_secret(config):
        return manual_required(
            request,
            "Remove API keys/tokens from AMLAB_MEM0_CONFIG and provide them only "
            "through provider environment variables.",
        )
    from mem0 import Memory

    memory = Memory.from_config(config)
    filters = {
        "user_id": f"amlab-user-{request.run_id}",
        "agent_id": f"amlab-agent-{request.run_id}",
        "run_id": request.run_id,
    }
    added = memory.add(
        [{"role": "user", "content": request.prompt}],
        **filters,
        metadata={"phase_id": request.phase_id},
    )
    retrieved = memory.search(request.prompt, filters=filters)
    stored = memory.get_all(filters=filters)
    return {
        "status": "completed",
        "system": request.system,
        "run_id": request.run_id,
        "phase_id": request.phase_id,
        "config_sha256": hashlib.sha256(config_path.read_bytes()).hexdigest(),
        "scope": filters,
        "added": to_jsonable(added),
        "retrieved": to_jsonable(retrieved),
        "stored": to_jsonable(stored),
    }
