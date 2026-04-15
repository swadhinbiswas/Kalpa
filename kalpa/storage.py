from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, List, Optional

from kalpa.config import KALPA_DIR_NAME

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS folders (
    id          TEXT PRIMARY KEY,
    path        TEXT NOT NULL UNIQUE,
    started_at  REAL NOT NULL,
    active      INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    folder_id   TEXT NOT NULL,
    timestamp   REAL NOT NULL,
    event_type  TEXT NOT NULL,
    path        TEXT NOT NULL,
    old_path    TEXT,
    file_hash   TEXT,
    delta_id    INTEGER REFERENCES deltas(id),
    size_before INTEGER,
    size_after  INTEGER
);

CREATE TABLE IF NOT EXISTS deltas (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    from_hash     TEXT,
    to_hash       TEXT NOT NULL,
    algorithm     TEXT DEFAULT 'zstd',
    delta_bytes   BLOB NOT NULL
);

CREATE TABLE IF NOT EXISTS snapshots (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    folder_id   TEXT NOT NULL,
    timestamp   REAL NOT NULL,
    label       TEXT,
    manifest    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_folder_time
    ON events(folder_id, timestamp);

CREATE INDEX IF NOT EXISTS idx_events_type
    ON events(event_type);

CREATE INDEX IF NOT EXISTS idx_events_path
    ON events(path);

CREATE INDEX IF NOT EXISTS idx_snapshots_folder_time
    ON snapshots(folder_id, timestamp);

CREATE INDEX IF NOT EXISTS idx_deltas_to_hash
    ON deltas(to_hash);
"""


@dataclass
class EventRecord:
    id: Optional[int] = None
    folder_id: str = ""
    timestamp: float = 0.0
    event_type: str = ""
    path: str = ""
    old_path: Optional[str] = None
    file_hash: Optional[str] = None
    delta_id: Optional[int] = None
    size_before: Optional[int] = None
    size_after: Optional[int] = None


@dataclass
class DeltaRecord:
    id: Optional[int] = None
    from_hash: Optional[str] = None
    to_hash: str = ""
    algorithm: str = "zstd"
    delta_bytes: bytes = b""


@dataclass
class SnapshotRecord:
    id: Optional[int] = None
    folder_id: str = ""
    timestamp: float = 0.0
    label: Optional[str] = None
    manifest: str = "{}"


class Database:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._local = threading.local()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(str(self.db_path))
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA synchronous=NORMAL")
            self._local.conn.execute("PRAGMA foreign_keys=ON")
        return self._local.conn

    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = self._get_conn()
        conn.executescript(SCHEMA_SQL)
        conn.commit()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        conn = self._get_conn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    # --- Folder operations ---

    def register_folder(self, path: str) -> str:
        folder_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).timestamp()
        with self.transaction() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO folders (id, path, started_at, active) VALUES (?, ?, ?, 1)",
                (folder_id, path, now),
            )
        return folder_id

    def get_folder(self, folder_id: str) -> Optional[dict]:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM folders WHERE id = ?", (folder_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_folder_by_path(self, path: str) -> Optional[dict]:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM folders WHERE path = ? AND active = 1", (path,)
        ).fetchone()
        return dict(row) if row else None

    def get_all_active_folders(self) -> List[dict]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM folders WHERE active = 1"
        ).fetchall()
        return [dict(r) for r in rows]

    def deactivate_folder(self, folder_id: str) -> None:
        with self.transaction() as conn:
            conn.execute(
                "UPDATE folders SET active = 0 WHERE id = ?", (folder_id,)
            )

    # --- Event operations ---

    def insert_event(self, event: EventRecord) -> int:
        with self.transaction() as conn:
            cursor = conn.execute(
                """INSERT INTO events
                   (folder_id, timestamp, event_type, path, old_path, file_hash, delta_id, size_before, size_after)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    event.folder_id,
                    event.timestamp,
                    event.event_type,
                    event.path,
                    event.old_path,
                    event.file_hash,
                    event.delta_id,
                    event.size_before,
                    event.size_after,
                ),
            )
            return cursor.lastrowid

    def insert_events_batch(self, events: List[EventRecord]) -> List[int]:
        with self.transaction() as conn:
            ids = []
            for event in events:
                cursor = conn.execute(
                    """INSERT INTO events
                       (folder_id, timestamp, event_type, path, old_path, file_hash, delta_id, size_before, size_after)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        event.folder_id,
                        event.timestamp,
                        event.event_type,
                        event.path,
                        event.old_path,
                        event.file_hash,
                        event.delta_id,
                        event.size_before,
                        event.size_after,
                    ),
                )
                ids.append(cursor.lastrowid)
            return ids

    def get_last_event(self, folder_id: str) -> Optional[EventRecord]:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM events WHERE folder_id = ? ORDER BY id DESC LIMIT 1",
            (folder_id,),
        ).fetchone()
        if row:
            return EventRecord(**dict(row))
        return None

    def get_events_since(
        self, folder_id: str, since_id: int = 0, limit: int = 1000
    ) -> List[EventRecord]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM events WHERE folder_id = ? AND id > ? ORDER BY id ASC LIMIT ?",
            (folder_id, since_id, limit),
        ).fetchall()
        return [EventRecord(**dict(r)) for r in rows]

    def query_events(
        self,
        folder_id: str,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        event_type: Optional[str] = None,
        path_pattern: Optional[str] = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> List[EventRecord]:
        conn = self._get_conn()
        clauses = ["folder_id = ?"]
        params: list = [folder_id]

        if start_time is not None:
            clauses.append("timestamp >= ?")
            params.append(start_time)
        if end_time is not None:
            clauses.append("timestamp <= ?")
            params.append(end_time)
        if event_type is not None:
            clauses.append("event_type = ?")
            params.append(event_type)
        if path_pattern is not None:
            clauses.append("path LIKE ?")
            params.append(path_pattern)

        query = (
            f"SELECT * FROM events WHERE {' AND '.join(clauses)} ORDER BY timestamp ASC LIMIT ? OFFSET ?"
        )
        rows = conn.execute(query, params + [limit, offset]).fetchall()
        return [EventRecord(**dict(r)) for r in rows]

    def get_event_count(self, folder_id: str) -> int:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM events WHERE folder_id = ?",
            (folder_id,),
        ).fetchone()
        return row["cnt"] if row else 0

    def get_destructive_events(
        self, folder_id: str, steps: int = 1
    ) -> List[EventRecord]:
        conn = self._get_conn()
        rows = conn.execute(
            """SELECT * FROM events
               WHERE folder_id = ? AND event_type IN ('delete', 'modify')
               ORDER BY id DESC LIMIT ?""",
            (folder_id, steps),
        ).fetchall()
        return [EventRecord(**dict(r)) for r in rows]

    # --- Delta operations ---

    def insert_delta(self, delta: DeltaRecord) -> int:
        with self.transaction() as conn:
            cursor = conn.execute(
                "INSERT INTO deltas (from_hash, to_hash, algorithm, delta_bytes) VALUES (?, ?, ?, ?)",
                (delta.from_hash, delta.to_hash, delta.algorithm, delta.delta_bytes),
            )
            return cursor.lastrowid

    def get_delta(self, delta_id: int) -> Optional[DeltaRecord]:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM deltas WHERE id = ?", (delta_id,)
        ).fetchone()
        if row:
            return DeltaRecord(**dict(row))
        return None

    def get_deltas_for_hashes(self, hashes: List[str]) -> List[DeltaRecord]:
        if not hashes:
            return []
        conn = self._get_conn()
        placeholders = ",".join("?" * len(hashes))
        rows = conn.execute(
            f"SELECT * FROM deltas WHERE to_hash IN ({placeholders})",
            hashes,
        ).fetchall()
        return [DeltaRecord(**dict(r)) for r in rows]

    # --- Snapshot operations ---

    def insert_snapshot(
        self, folder_id: str, timestamp: float, manifest: dict, label: Optional[str] = None
    ) -> int:
        with self.transaction() as conn:
            cursor = conn.execute(
                "INSERT INTO snapshots (folder_id, timestamp, label, manifest) VALUES (?, ?, ?, ?)",
                (folder_id, timestamp, label, json.dumps(manifest)),
            )
            return cursor.lastrowid

    def get_latest_snapshot(self, folder_id: str, before: Optional[float] = None) -> Optional[SnapshotRecord]:
        conn = self._get_conn()
        if before is not None:
            row = conn.execute(
                "SELECT * FROM snapshots WHERE folder_id = ? AND timestamp <= ? ORDER BY timestamp DESC LIMIT 1",
                (folder_id, before),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM snapshots WHERE folder_id = ? ORDER BY timestamp DESC LIMIT 1",
                (folder_id,),
            ).fetchone()
        if row:
            rec = SnapshotRecord(**dict(row))
            return rec
        return None

    def get_snapshots(
        self, folder_id: str, limit: int = 100
    ) -> List[SnapshotRecord]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM snapshots WHERE folder_id = ? ORDER BY timestamp DESC LIMIT ?",
            (folder_id, limit),
        ).fetchall()
        return [SnapshotRecord(**dict(r)) for r in rows]

    # --- Storage stats ---

    def get_storage_stats(self, folder_id: str) -> dict:
        conn = self._get_conn()
        event_count = self.get_event_count(folder_id)
        delta_size = conn.execute(
            "SELECT COALESCE(SUM(LENGTH(delta_bytes)), 0) as total FROM deltas d "
            "JOIN events e ON d.id = e.delta_id WHERE e.folder_id = ?",
            (folder_id,),
        ).fetchone()["total"]

        earliest = conn.execute(
            "SELECT MIN(timestamp) as t FROM events WHERE folder_id = ?",
            (folder_id,),
        ).fetchone()["t"]

        last_event = self.get_last_event(folder_id)
        last_event_str = ""
        if last_event:
            last_event_str = (
                f"{last_event.event_type} {last_event.path}"
            )

        return {
            "event_count": event_count,
            "delta_storage_bytes": delta_size,
            "earliest_timestamp": earliest,
            "last_event_str": last_event_str,
        }

    def close(self) -> None:
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close()
            self._local.conn = None

    def vacuum(self) -> None:
        conn = self._get_conn()
        conn.execute("VACUUM")
