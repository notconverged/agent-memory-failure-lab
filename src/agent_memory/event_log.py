from __future__ import annotations

import json
import os
import uuid
from collections.abc import Iterable
from pathlib import Path

from agent_memory.models import EventEnvelope


class EventLog:
    """Append-only authority plus an atomic, hook-friendly spool."""

    def __init__(self, repository_dir: Path) -> None:
        self.repository_dir = repository_dir
        self.spool_dir = repository_dir / "spool"
        self.log_path = repository_dir / "events.jsonl"
        self.spool_dir.mkdir(parents=True, exist_ok=True)

    def write_spool(self, event: EventEnvelope) -> Path:
        name = f"{event.occurred_at.replace(':', '-')}-{event.event_id}.json"
        target = self.spool_dir / name
        temporary = target.with_suffix(f".tmp-{uuid.uuid4().hex}")
        temporary.write_text(
            json.dumps(event.to_dict(), ensure_ascii=False), encoding="utf-8"
        )
        os.replace(temporary, target)
        return target

    def append(self, event: EventEnvelope) -> None:
        self.repository_dir.mkdir(parents=True, exist_ok=True)
        line = json.dumps(event.to_dict(), ensure_ascii=False, separators=(",", ":"))
        with self.log_path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(line + "\n")
            stream.flush()
            os.fsync(stream.fileno())

    def iter_events(self) -> Iterable[EventEnvelope]:
        if not self.log_path.exists():
            return
        with self.log_path.open(encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, start=1):
                if not line.strip():
                    continue
                try:
                    payload = json.loads(line)
                    yield EventEnvelope(**payload)
                except (json.JSONDecodeError, TypeError) as error:
                    raise ValueError(
                        f"Invalid event log line {line_number}: {error}"
                    ) from error

    def pending_spool(self) -> list[Path]:
        return sorted(self.spool_dir.glob("*.json"))

    @staticmethod
    def read_spool(path: Path) -> EventEnvelope:
        return EventEnvelope(**json.loads(path.read_text(encoding="utf-8")))

    @staticmethod
    def acknowledge_spool(path: Path) -> None:
        path.unlink(missing_ok=True)
