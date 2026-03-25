from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from kalpa.config import KALPA_DIR_NAME
from kalpa.snapshot import SnapshotEngine, apply_delta, compute_hash_from_bytes
from kalpa.storage import Database, EventRecord, SnapshotRecord


class Timeline:
    def __init__(self, db: Database, folder_id: str):
        self.db = db
        self.folder_id = folder_id
        self.snapshot_engine = SnapshotEngine()

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
            path_pattern=f"%{path}%",
            limit=10000,
        )

    def reconstruct_file_at_time(
        self, path: str, target_time: float
    ) -> Optional[bytes]:
        full_path = Path(path)

        latest_snapshot = self.db.get_latest_snapshot(
            self.folder_id, before=target_time
        )

        content: Optional[bytes] = None

        if latest_snapshot:
            manifest: dict = {}
            try:
                import json
                manifest = json.loads(latest_snapshot.manifest)
            except (json.JSONDecodeError, TypeError):
                pass

            if path in manifest:
                file_hash = manifest[path]
                if file_hash:
                    snapshot_events = self.db.query_events(
                        folder_id=self.folder_id,
                        end_time=latest_snapshot.timestamp,
                        path_pattern=path,
                        limit=1,
                    )
                    if snapshot_events:
                        last_event = snapshot_events[-1]
                        if last_event.file_hash == file_hash and last_event.delta_id:
                            delta = self.db.get_delta(last_event.delta_id)
                            if delta:
                                content = apply_delta(
                                    b"", delta.delta_bytes, delta.algorithm
                                )

        if content is None:
            try:
                with open(full_path, "rb") as f:
                    content = f.read()
            except OSError:
                pass

        events_after = self.db.query_events(
            folder_id=self.folder_id,
            start_time=(latest_snapshot.timestamp if latest_snapshot else 0),
            end_time=target_time,
            path_pattern=path,
            limit=10000,
        )

        for event in events_after:
            if event.event_type == "delete":
                content = None
            elif event.event_type in ("create", "modify") and event.delta_id:
                delta = self.db.get_delta(event.delta_id)
                if delta and content is not None:
                    content = apply_delta(content, delta.delta_bytes, delta.algorithm)
                elif delta and content is None:
                    content = apply_delta(b"", delta.delta_bytes, delta.algorithm)

        return content

    def get_folder_state_at_time(self, target_time: float) -> Dict[str, bytes]:
        state: Dict[str, bytes] = {}

        latest_snapshot = self.db.get_latest_snapshot(
            self.folder_id, before=target_time
        )

        manifest_files: Dict[str, str] = {}
        if latest_snapshot:
            import json
            try:
                manifest_files = json.loads(latest_snapshot.manifest)
            except (json.JSONDecodeError, TypeError):
                pass

        for file_path_str in list(manifest_files.keys()):
            content = self.reconstruct_file_at_time(file_path_str, target_time)
            if content is not None:
                state[file_path_str] = content

        events_since_snapshot = self.db.query_events(
            folder_id=self.folder_id,
            start_time=(latest_snapshot.timestamp if latest_snapshot else 0),
            end_time=target_time,
            limit=100000,
        )

        processed_paths: set = set()
        for event in events_since_snapshot:
            if event.event_type == "create" and event.path not in manifest_files:
                content = self.reconstruct_file_at_time(event.path, target_time)
                if content is not None:
                    state[event.path] = content
            elif event.event_type == "delete":
                state.pop(event.path, None)

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
