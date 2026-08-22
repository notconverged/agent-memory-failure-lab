from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone

from scripts.competitor_adapters.base import (
    AdapterRequest,
    manual_required,
    to_jsonable,
)


async def run_async(request: AdapterRequest) -> dict:
    from graphiti_core import Graphiti
    from graphiti_core.driver.kuzu_driver import KuzuDriver
    from graphiti_core.nodes import EpisodeType

    request.data_dir.mkdir(parents=True, exist_ok=True)
    database = request.data_dir / "graphiti.kuzu"
    graph = Graphiti(graph_driver=KuzuDriver(db=str(database)))
    try:
        await graph.build_indices_and_constraints()
        await graph.add_episode(
            name=f"{request.run_id}-{request.phase_id}",
            episode_body=request.prompt,
            source=EpisodeType.text,
            source_description="Repo Evolution controlled benchmark prompt",
            reference_time=datetime.now(timezone.utc),
            group_id=request.run_id,
        )
        results = await graph.search(request.prompt, group_id=request.run_id)
    finally:
        await graph.close()
    return {
        "status": "completed",
        "system": request.system,
        "run_id": request.run_id,
        "phase_id": request.phase_id,
        "kuzu_db": str(database.resolve()),
        "retrieved": to_jsonable(results),
    }


def run_phase(request: AdapterRequest) -> dict:
    if not os.environ.get("OPENAI_API_KEY"):
        return manual_required(
            request,
            "Set the configured Graphiti provider credentials. The first adapter "
            "implementation uses the official OpenAI defaults with persistent Kuzu.",
        )
    return asyncio.run(run_async(request))
