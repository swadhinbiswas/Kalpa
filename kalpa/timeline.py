from __future__ import annotations

import json
from datetime import datetime
from typing import Dict, List, Optional

from kalpa.snapshot import apply_delta
from kalpa.storage import Database, EventRecord


class Timeline:
    def __init__(self, db: Database, folder_id: str):
        self.db = db
        self.folder_id = folder_id

    def get_events(
        self,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        event_type: Optional[str] = None,
        path_pattern: Optional[str] = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> List[EventRecord]:
        return self.db.query_events(
            folder_id=self.folder_id,
            start_time=start_time,
            end_time=end_time,
            event_type=event_type,
            path_pattern=path_pattern,
            limit=limit,
            offset=offset,
        )

    def get_event_count(self) -> int:
        return self.db.get_event_count(self.folder_id)

    def get_file_history(self, path: str) -> List[EventRecord]:
        return self.db.query_events(
            folder_id=self.folder_id,
            path_pattern=path,
            limit=10000,
        )

    def _fetch_deltas_batch(self, delta_ids: list[int]) -> dict:
        if not delta_ids:
            return {}
        conn = self.db._get_conn()
        placeholders = ",".join("?" * len(delta_ids))
        rows = conn.execute(
            f"SELECT id, algorithm, delta_bytes FROM deltas WHERE id IN ({placeholders})",
            delta_ids,
        ).fetchall()
        return {row["id"]: row for row in rows}

    def reconstruct_file_at_time(
        self,
        path: str,
        target_time: float,
        before_event_id: Optional[int] = None,
    ) -> Optional[bytes]:
        latest_snapshot = self.db.get_latest_snapshot(
            self.folder_id, before=target_time
        )

        content: Optional[bytes] = None
        snapshot_time = 0.0
        manifest: Dict[str, str] = {}

        if latest_snapshot:
            try:
                manifest = json.loads(latest_snapshot.manifest)
            except (json.JSONDecodeError, TypeError):
                pass
            snapshot_time = latest_snapshot.timestamp

            snapshot_hash = manifest.get(path)
            if snapshot_hash:
                snapshot_events = self.db.query_events(
                    folder_id=self.folder_id,
                    end_time=snapshot_time,
                    path_pattern=path,
                    limit=1,
                )
                if snapshot_events:
                    last_event = snapshot_events[-1]
                    if last_event.file_hash == snapshot_hash and last_event.delta_id:
                        delta = self.db.get_delta(last_event.delta_id)
                        if delta:
                            content = apply_delta(
                                b"", delta.delta_bytes, delta.algorithm
                            )

        if content is None:
            content = b""

        events_after = self.db.query_events(
            folder_id=self.folder_id,
            start_time=snapshot_time,
            end_time=target_time,
            path_pattern=path,
            limit=100000,
        )

        delta_ids = [e.delta_id for e in events_after if e.delta_id is not None]
        delta_cache = self._fetch_deltas_batch(delta_ids) if delta_ids else {}

        for event in events_after:
            if before_event_id is not None and event.id and event.id >= before_event_id:
                continue
            if event.event_type == "delete":
                content = None
            elif event.event_type in ("create", "modify") and event.delta_id:
                delta_row = delta_cache.get(event.delta_id)
                if delta_row:
                    if content is not None:
                        content = apply_delta(
                            content, delta_row["delta_bytes"], delta_row["algorithm"]
                        )
                    else:
                        content = apply_delta(
                            b"", delta_row["delta_bytes"], delta_row["algorithm"]
                        )

        return content

    def get_folder_state_at_time(self, target_time: float) -> Dict[str, bytes]:
        state: Dict[str, bytes] = {}

        latest_snapshot = self.db.get_latest_snapshot(
            self.folder_id, before=target_time
        )

        manifest_files: Dict[str, str] = {}
        snapshot_time = 0.0
        if latest_snapshot:
            try:
                manifest_files = json.loads(latest_snapshot.manifest)
            except (json.JSONDecodeError, TypeError):
                pass
            snapshot_time = latest_snapshot.timestamp

        all_events = self.db.query_events(
            folder_id=self.folder_id,
            start_time=0,
            end_time=target_time,
            limit=200000,
        )

        changed_paths: set = set()
        for event in all_events:
            if event.event_type in ("create", "modify", "delete", "rename"):
                changed_paths.add(event.path)
                if event.old_path:
                    changed_paths.add(event.old_path)

        all_paths = set(manifest_files.keys()) | changed_paths

        delta_ids = [e.delta_id for e in all_events if e.delta_id is not None]
        delta_cache = self._fetch_deltas_batch(delta_ids) if delta_ids else {}

        for file_path_str in sorted(all_paths):
            content: Optional[bytes] = None

            snapshot_hash = manifest_files.get(file_path_str)
            if snapshot_hash:
                pre_snapshot_events = [
                    e for e in all_events
                    if e.path == file_path_str and e.timestamp <= snapshot_time
                ]
                if pre_snapshot_events:
                    last_event = pre_snapshot_events[-1]
                    if last_event.file_hash == snapshot_hash and last_event.delta_id:
                        delta_row = delta_cache.get(last_event.delta_id)
                        if delta_row:
                            content = apply_delta(
                                b"", delta_row["delta_bytes"], delta_row["algorithm"]
                            )

            if content is None:
                content = b""

            post_snapshot_events = [
                e for e in all_events
                if e.path == file_path_str and e.timestamp > snapshot_time
            ]

            for event in post_snapshot_events:
                if event.event_type == "delete":
                    content = None
                elif event.event_type in ("create", "modify") and event.delta_id:
                    delta_row = delta_cache.get(event.delta_id)
                    if delta_row:
                        if content is not None:
                            content = apply_delta(
                                content, delta_row["delta_bytes"], delta_row["algorithm"]
                            )
                        else:
                            content = apply_delta(
                                b"", delta_row["delta_bytes"], delta_row["algorithm"]
                            )

            if content is not None:
                state[file_path_str] = content

        return state

    def snapshot_timeline_summary(self) -> List[dict]:
        events = self.db.query_events(
            folder_id=self.folder_id, limit=100
        )
        summary = []
        for ev in events:
            dt = datetime.fromtimestamp(ev.timestamp)
            summary.append(
                {
                    "time": dt.strftime("%H:%M:%S"),
                    "type": ev.event_type,
                    "path": ev.path,
                    "old_path": ev.old_path,
                }
            )
        return summary
