from __future__ import annotations

import json
import os

from scripts.competitor_adapters.base import (
    AdapterRequest,
    manual_required,
    to_jsonable,
)


def run_phase(request: AdapterRequest) -> dict:
    api_key = os.environ.get("LETTA_API_KEY")
    model = os.environ.get("AMLAB_LETTA_MODEL")
    embedding = os.environ.get("AMLAB_LETTA_EMBEDDING")
    if not api_key or not model or not embedding:
        return manual_required(
            request,
            "Set LETTA_API_KEY, AMLAB_LETTA_MODEL, and AMLAB_LETTA_EMBEDDING. "
            "The adapter will create one remote benchmark-only agent.",
        )

    from letta_client import Letta

    request.data_dir.mkdir(parents=True, exist_ok=True)
    agent_record = request.data_dir / "letta-agent.json"
    client = Letta(api_key=api_key)
    if agent_record.exists():
        agent_id = json.loads(agent_record.read_text(encoding="utf-8"))["agent_id"]
        created = False
    else:
        agent = client.agents.create(
            name=f"amlab-{request.run_id}",
            model=model,
            embedding=embedding,
            memory_blocks=[
                {
                    "label": "benchmark_project",
                    "value": "Repo Evolution benchmark memory. Preserve provenance.",
                },
                {
                    "label": "persona",
                    "value": (
                        "You are a coding agent participating in a "
                        "controlled benchmark."
                    ),
                },
            ],
        )
        agent_id = agent.id
        agent_record.write_text(
            json.dumps({"agent_id": agent_id}, indent=2), encoding="utf-8"
        )
        created = True
    response = client.agents.messages.create(
        agent_id=agent_id,
        messages=[{"role": "user", "content": request.prompt}],
    )
    blocks = client.agents.blocks.list(agent_id=agent_id)
    return {
        "status": "completed",
        "system": request.system,
        "run_id": request.run_id,
        "phase_id": request.phase_id,
        "agent_id": agent_id,
        "agent_created": created,
        "response": to_jsonable(response),
        "memory_blocks": to_jsonable(blocks),
        "cleanup": "Export blocks/messages before deleting this benchmark agent.",
    }
