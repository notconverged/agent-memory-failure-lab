from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class AdapterRequest:
    system: str
    run_id: str
    phase_id: str
    workspace: Path
    data_dir: Path
    prompt: str


class CompetitorAdapter(Protocol):
    def run_phase(self, request: AdapterRequest) -> dict: ...


def manual_required(request: AdapterRequest, reason: str) -> dict:
    return {
        "status": "manual_required",
        "system": request.system,
        "run_id": request.run_id,
        "phase_id": request.phase_id,
        "reason": reason,
    }


def to_jsonable(value: Any) -> Any:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "model_dump"):
        return to_jsonable(value.model_dump(mode="json"))
    if is_dataclass(value):
        return to_jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple | set):
        return [to_jsonable(item) for item in value]
    return repr(value)
