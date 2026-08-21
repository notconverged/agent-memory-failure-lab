from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from agent_memory.models import EventEnvelope

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS projected_events (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    occurred_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS repositories (
    repository_id TEXT PRIMARY KEY,
    root TEXT NOT NULL,
    git_common_dir TEXT NOT NULL,
    base_branch TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS memories (
    memory_id TEXT PRIMARY KEY,
    repository_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS revisions (
    memory_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    repository_id TEXT NOT NULL,
    branch TEXT NOT NULL,
    kind TEXT NOT NULL,
    claim TEXT NOT NULL,
    rationale TEXT NOT NULL,
    status TEXT NOT NULL,
    authority TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    anchors_json TEXT NOT NULL,
    supersedes_revision INTEGER,
    created_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    PRIMARY KEY (memory_id, revision),
    FOREIGN KEY (memory_id) REFERENCES memories(memory_id)
);

CREATE TABLE IF NOT EXISTS memory_refs (
    repository_id TEXT NOT NULL,
    branch TEXT NOT NULL,
    memory_id TEXT NOT NULL,
    current_revision INTEGER NOT NULL,
    status TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (repository_id, branch, memory_id),
    FOREIGN KEY (memory_id, current_revision)
        REFERENCES revisions(memory_id, revision)
);

CREATE TABLE IF NOT EXISTS dependency_edges (
    edge_id TEXT PRIMARY KEY,
    repository_id TEXT NOT NULL,
    branch TEXT NOT NULL,
    source_memory_id TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    status TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS execution_nodes (
    node_id TEXT PRIMARY KEY,
    repository_id TEXT NOT NULL,
    branch TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL,
    parent_id TEXT,
    details TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS compiler_jobs (
    job_id TEXT PRIMARY KEY,
    repository_id TEXT NOT NULL,
    branch TEXT NOT NULL,
    status TEXT NOT NULL,
    cursor TEXT NOT NULL,
    head TEXT NOT NULL,
    coverage_json TEXT NOT NULL,
    input_json TEXT NOT NULL,
    output_json TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS deliveries (
    delivery_id TEXT PRIMARY KEY,
    repository_id TEXT NOT NULL,
    branch TEXT NOT NULL,
    session_id TEXT NOT NULL,
    delivery_type TEXT NOT NULL,
    query TEXT NOT NULL,
    revisions_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    token_estimate INTEGER NOT NULL,
    delivered_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS feedback (
    feedback_id TEXT PRIMARY KEY,
    repository_id TEXT NOT NULL,
    branch TEXT NOT NULL,
    memory_id TEXT,
    verdict TEXT NOT NULL,
    comment TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS leases (
    lease_name TEXT PRIMARY KEY,
    owner TEXT NOT NULL,
    expires_at REAL NOT NULL
);
"""


class MemoryStore:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        database_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(database_path, timeout=5)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(SCHEMA)
        self._fts_enabled = self._create_fts()

    def close(self) -> None:
        self.connection.close()

    def _create_fts(self) -> bool:
        try:
            self.connection.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
                    repository_id UNINDEXED,
                    branch UNINDEXED,
                    memory_id UNINDEXED,
                    revision UNINDEXED,
                    claim,
                    rationale
                )
                """
            )
            self.connection.commit()
            return True
        except sqlite3.OperationalError:
            return False

    @property
    def fts_enabled(self) -> bool:
        return self._fts_enabled

    def has_event(self, event_id: str) -> bool:
        row = self.connection.execute(
            "SELECT 1 FROM projected_events WHERE event_id = ?", (event_id,)
        ).fetchone()
        return row is not None

    def project(self, event: EventEnvelope) -> bool:
        if self.has_event(event.event_id):
            return False
        handler = getattr(self, f"_on_{event.event_type}", None)
        if handler is not None:
            handler(event)
        self.connection.execute(
            "INSERT INTO projected_events VALUES (?, ?, ?)",
            (event.event_id, event.event_type, event.occurred_at),
        )
        self.connection.commit()
        return True

    def _on_repository_registered(self, event: EventEnvelope) -> None:
        value = event.payload
        self.connection.execute(
            """
            INSERT INTO repositories VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(repository_id) DO UPDATE SET
                root=excluded.root,
                git_common_dir=excluded.git_common_dir,
                base_branch=excluded.base_branch,
                updated_at=excluded.updated_at
            """,
            (
                event.repository_id,
                value["root"],
                value["git_common_dir"],
                value["base_branch"],
                event.occurred_at,
            ),
        )

    def _on_memory_revision_created(self, event: EventEnvelope) -> None:
        value = event.payload
        self.connection.execute(
            "INSERT OR IGNORE INTO memories VALUES (?, ?, ?, ?)",
            (
                value["memory_id"],
                value["repository_id"],
                value["kind"],
                value["created_at"],
            ),
        )
        self.connection.execute(
            """
            INSERT INTO revisions VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            (
                value["memory_id"],
                value["revision"],
                value["repository_id"],
                value["branch"],
                value["kind"],
                value["claim"],
                value["rationale"],
                value["status"],
                value["authority"],
                json.dumps(value["evidence"], ensure_ascii=False),
                json.dumps(value["anchors"], ensure_ascii=False),
                value.get("supersedes_revision"),
                value["created_at"],
                json.dumps(value.get("metadata", {}), ensure_ascii=False),
            ),
        )
        self._index_revision(value)

    def _index_revision(self, value: dict[str, Any]) -> None:
        if not self._fts_enabled:
            return
        self.connection.execute(
            """
            INSERT INTO memory_fts (
                repository_id, branch, memory_id, revision, claim, rationale
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                value["repository_id"],
                value["branch"],
                value["memory_id"],
                value["revision"],
                value["claim"],
                value["rationale"],
            ),
        )

    def _on_memory_ref_moved(self, event: EventEnvelope) -> None:
        value = event.payload
        self.connection.execute(
            """
            INSERT INTO memory_refs VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(repository_id, branch, memory_id) DO UPDATE SET
                current_revision=excluded.current_revision,
                status=excluded.status,
                updated_at=excluded.updated_at
            """,
            (
                event.repository_id,
                event.branch,
                value["memory_id"],
                value["revision"],
                value["status"],
                event.occurred_at,
            ),
        )

    def _on_delivery_recorded(self, event: EventEnvelope) -> None:
        value = event.payload
        self.connection.execute(
            """
            INSERT INTO deliveries VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.event_id,
                event.repository_id,
                event.branch,
                value["session_id"],
                value["delivery_type"],
                value["query"],
                json.dumps(value["revisions"]),
                value["payload_hash"],
                value["token_estimate"],
                event.occurred_at,
            ),
        )

    def _on_feedback_recorded(self, event: EventEnvelope) -> None:
        value = event.payload
        self.connection.execute(
            "INSERT INTO feedback VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                event.event_id,
                event.repository_id,
                event.branch,
                value.get("memory_id"),
                value["verdict"],
                value.get("comment", ""),
                event.occurred_at,
            ),
        )

    def _on_execution_node_upserted(self, event: EventEnvelope) -> None:
        value = event.payload
        self.connection.execute(
            """
            INSERT INTO execution_nodes VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(node_id) DO UPDATE SET
                title=excluded.title,
                status=excluded.status,
                parent_id=excluded.parent_id,
                details=excluded.details,
                updated_at=excluded.updated_at
            """,
            (
                value["node_id"],
                event.repository_id,
                event.branch,
                value["title"],
                value["status"],
                value.get("parent_id"),
                value.get("details", ""),
                value["updated_at"],
            ),
        )

    def _on_compiler_job_queued(self, event: EventEnvelope) -> None:
        value = event.payload
        self.connection.execute(
            """
            INSERT INTO compiler_jobs VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?
            )
            """,
            (
                value["job_id"],
                event.repository_id,
                event.branch,
                "pending",
                value["cursor"],
                value["head"],
                json.dumps(value["evidence_bundle"]["coverage"]),
                json.dumps(value, ensure_ascii=False),
                event.occurred_at,
                event.occurred_at,
            ),
        )

    def _on_compiler_job_finished(self, event: EventEnvelope) -> None:
        value = event.payload
        self.connection.execute(
            """
            UPDATE compiler_jobs SET status=?, output_json=?, error=?, updated_at=?
            WHERE job_id=?
            """,
            (
                value["status"],
                json.dumps(value.get("candidates", []), ensure_ascii=False),
                value.get("error"),
                event.occurred_at,
                value["job_id"],
            ),
        )

    def _on_dependency_edge_added(self, event: EventEnvelope) -> None:
        value = event.payload
        self.connection.execute(
            """
            INSERT INTO dependency_edges VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                value["edge_id"],
                event.repository_id,
                event.branch,
                value["source_memory_id"],
                value["target_type"],
                value["target_id"],
                value["status"],
                json.dumps(value.get("evidence", []), ensure_ascii=False),
                event.occurred_at,
            ),
        )

    def next_revision(self, memory_id: str) -> int:
        row = self.connection.execute(
            "SELECT MAX(revision) AS revision FROM revisions WHERE memory_id = ?",
            (memory_id,),
        ).fetchone()
        return int(row["revision"] or 0) + 1

    def get_current(
        self,
        repository_id: str,
        branch: str,
        memory_id: str,
        base_branch: str | None = None,
    ) -> dict[str, Any] | None:
        branches = [branch]
        if base_branch and base_branch != branch:
            branches.append(base_branch)
        placeholders = ",".join("?" for _ in branches)
        row = self.connection.execute(
            f"""
            SELECT r.* FROM memory_refs ref
            JOIN revisions r ON r.memory_id = ref.memory_id
                AND r.revision = ref.current_revision
            WHERE ref.repository_id = ? AND ref.branch IN ({placeholders})
                AND ref.memory_id = ?
            ORDER BY CASE WHEN ref.branch = ? THEN 0 ELSE 1 END
            LIMIT 1
            """,
            [repository_id, *branches, memory_id, branch],
        ).fetchone()
        return self._decode_revision(row) if row else None

    def history(self, memory_id: str) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT * FROM revisions WHERE memory_id = ? ORDER BY revision",
            (memory_id,),
        ).fetchall()
        return [self._decode_revision(row) for row in rows]

    def list_current(
        self,
        repository_id: str,
        branch: str,
        statuses: Iterable[str] | None = None,
        base_branch: str | None = None,
    ) -> list[dict[str, Any]]:
        branches = [branch]
        if base_branch and base_branch != branch:
            branches.append(base_branch)
        placeholders = ",".join("?" for _ in branches)
        parameters: list[Any] = [repository_id, *branches]
        status_clause = ""
        if statuses:
            status_values = list(statuses)
            status_clause = (
                f" AND ref.status IN ({','.join('?' for _ in status_values)})"
            )
            parameters.extend(status_values)
        rows = self.connection.execute(
            f"""
            SELECT r.*, ref.branch AS ref_branch FROM memory_refs ref
            JOIN revisions r ON r.memory_id = ref.memory_id
                AND r.revision = ref.current_revision
            WHERE ref.repository_id = ? AND ref.branch IN ({placeholders})
            {status_clause}
            ORDER BY r.created_at DESC
            """,
            parameters,
        ).fetchall()
        result: dict[str, dict[str, Any]] = {}
        for row in rows:
            decoded = self._decode_revision(row)
            existing = result.get(decoded["memory_id"])
            if existing is None or row["ref_branch"] == branch:
                result[decoded["memory_id"]] = decoded
        return list(result.values())

    def search_current(
        self,
        repository_id: str,
        branch: str,
        query: str,
        statuses: Iterable[str],
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        status_values = list(statuses)
        if not query.strip():
            return self.list_current(repository_id, branch, status_values)[:limit]
        placeholders = ",".join("?" for _ in status_values)
        if self._fts_enabled:
            safe_query = " OR ".join(
                f'"{token.replace(chr(34), "")}"' for token in query.split() if token
            )
            if safe_query:
                rows = self.connection.execute(
                    f"""
                    SELECT r.* FROM memory_fts f
                    JOIN memory_refs ref ON ref.repository_id=f.repository_id
                        AND ref.branch=f.branch AND ref.memory_id=f.memory_id
                        AND ref.current_revision=CAST(f.revision AS INTEGER)
                    JOIN revisions r ON r.memory_id=ref.memory_id
                        AND r.revision=ref.current_revision
                    WHERE f.repository_id=? AND f.branch=?
                        AND memory_fts MATCH ?
                        AND ref.status IN ({placeholders})
                    ORDER BY bm25(memory_fts) LIMIT ?
                    """,
                    [repository_id, branch, safe_query, *status_values, limit],
                ).fetchall()
                return [self._decode_revision(row) for row in rows]
        like = f"%{query}%"
        rows = self.connection.execute(
            f"""
            SELECT r.* FROM memory_refs ref
            JOIN revisions r ON r.memory_id=ref.memory_id
                AND r.revision=ref.current_revision
            WHERE ref.repository_id=? AND ref.branch=?
                AND ref.status IN ({placeholders})
                AND (r.claim LIKE ? OR r.rationale LIKE ?)
            ORDER BY r.created_at DESC LIMIT ?
            """,
            [repository_id, branch, *status_values, like, like, limit],
        ).fetchall()
        return [self._decode_revision(row) for row in rows]

    def delivered_revisions(
        self, repository_id: str, branch: str, session_id: str
    ) -> set[tuple[str, int]]:
        rows = self.connection.execute(
            """
            SELECT revisions_json FROM deliveries
            WHERE repository_id=? AND branch=? AND session_id=?
            """,
            (repository_id, branch, session_id),
        ).fetchall()
        delivered: set[tuple[str, int]] = set()
        for row in rows:
            delivered.update(tuple(item) for item in json.loads(row[0]))
        return delivered

    def pending_compiler_jobs(self, limit: int = 20) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """
            SELECT input_json FROM compiler_jobs
            WHERE status='pending' ORDER BY created_at LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def active_memory_dependents(
        self, repository_id: str, branch: str, memory_id: str
    ) -> list[str]:
        rows = self.connection.execute(
            """
            SELECT target_id FROM dependency_edges
            WHERE repository_id=? AND branch=? AND source_memory_id=?
                AND target_type='memory' AND status='active'
            """,
            (repository_id, branch, memory_id),
        ).fetchall()
        return [row[0] for row in rows]

    def acquire_lease(
        self, lease_name: str, owner: str, ttl_seconds: int = 300
    ) -> bool:
        now = time.time()
        with self.connection:
            self.connection.execute(
                "DELETE FROM leases WHERE lease_name=? AND expires_at<=?",
                (lease_name, now),
            )
            try:
                self.connection.execute(
                    "INSERT INTO leases VALUES (?, ?, ?)",
                    (lease_name, owner, now + ttl_seconds),
                )
            except sqlite3.IntegrityError:
                return False
        return True

    def release_lease(self, lease_name: str, owner: str) -> None:
        with self.connection:
            self.connection.execute(
                "DELETE FROM leases WHERE lease_name=? AND owner=?",
                (lease_name, owner),
            )

    def statistics(self, repository_id: str, branch: str) -> dict[str, Any]:
        counts = self.connection.execute(
            """
            SELECT status, COUNT(*) AS count FROM memory_refs
            WHERE repository_id=? AND branch=? GROUP BY status
            """,
            (repository_id, branch),
        ).fetchall()
        return {
            "repository_id": repository_id,
            "branch": branch,
            "counts": {row["status"]: row["count"] for row in counts},
            "fts5": self._fts_enabled,
        }

    @staticmethod
    def _decode_revision(row: sqlite3.Row) -> dict[str, Any]:
        value = dict(row)
        value.pop("ref_branch", None)
        value["evidence"] = json.loads(value.pop("evidence_json"))
        value["anchors"] = json.loads(value.pop("anchors_json"))
        value["metadata"] = json.loads(value.pop("metadata_json"))
        return value

    def clear_projection(self) -> None:
        tables = (
            "projected_events",
            "deliveries",
            "feedback",
            "execution_nodes",
            "dependency_edges",
            "memory_refs",
            "revisions",
            "memories",
            "repositories",
            "compiler_jobs",
            "leases",
        )
        with self.connection:
            for table in tables:
                self.connection.execute(f"DELETE FROM {table}")
            if self._fts_enabled:
                self.connection.execute("DELETE FROM memory_fts")
