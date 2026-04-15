from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional, Set

from watchdog.events import (
    DirCreatedEvent,
    DirDeletedEvent,
    DirModifiedEvent,
    DirMovedEvent,
    FileCreatedEvent,
    FileDeletedEvent,
    FileModifiedEvent,
    FileMovedEvent,
    FileSystemEvent,
    FileSystemEventHandler,
)
from watchdog.observers import Observer

from kalpa.config import KALPA_DIR_NAME, KalpaConfig
from kalpa.snapshot import SnapshotEngine
from kalpa.storage import Database, DeltaRecord, EventRecord


class KalpaEventHandler(FileSystemEventHandler):
    def __init__(
        self,
        folder_id: str,
        db: Database,
        snapshot_engine: SnapshotEngine,
        watched_path: Path,
        event_callback: Optional[Callable[[EventRecord], None]] = None,
    ):
        super().__init__()
        self.folder_id = folder_id
        self.db = db
        self.snapshot_engine = snapshot_engine
        self.watched_path = watched_path
        self.event_callback = event_callback
        self._last_known_hashes: dict = {}
        self._lock = threading.Lock()
        self._event_buffer: list = []
        self._buffer_lock = threading.Lock()
        self._batch_size = 50

    def _is_kalpa_internal(self, path_str: str) -> bool:
        path = Path(path_str)
        kalpa_dir = self.watched_path / KALPA_DIR_NAME
        return kalpa_dir in path.parents or path == kalpa_dir

    def _make_rel_path(self, path_str: str) -> str:
        try:
            return str(Path(path_str).relative_to(self.watched_path))
        except ValueError:
            return path_str

    def _record_event(
        self,
        event_type: str,
        path: str,
        old_path: Optional[str] = None,
    ) -> None:
        if self._is_kalpa_internal(path):
            return
        if old_path and self._is_kalpa_internal(old_path):
            return

        rel_path = self._make_rel_path(path)
        rel_old_path = self._make_rel_path(old_path) if old_path else None
        timestamp = datetime.now(timezone.utc).timestamp()

        file_hash = None
        delta_id = None
        size_before = None
        size_after = None

        if event_type in ("create", "modify"):
            try:
                file_stat = os.stat(path)
                size_after = file_stat.st_size
                file_hash = self.snapshot_engine.compute_file_hash(path)
            except OSError:
                pass

            if event_type == "modify":
                last_hash = self._last_known_hashes.get(rel_path)
                if last_hash and last_hash != file_hash:
                    try:
                        with open(path, "rb") as f:
                            new_content = f.read()
                    except OSError:
                        new_content = b""

                    delta_bytes, algorithm = self.snapshot_engine.create_delta(
                        b"", new_content
                    )
                    delta_rec = DeltaRecord(
                        from_hash=last_hash,
                        to_hash=file_hash or "",
                        algorithm=algorithm,
                        delta_bytes=delta_bytes,
                    )
                    delta_id = self.db.insert_delta(delta_rec)
                    size_before = 0

                if file_hash:
                    self._last_known_hashes[rel_path] = file_hash

            elif event_type == "create" and file_hash:
                self._last_known_hashes[rel_path] = file_hash

        elif event_type == "delete":
            size_before = 0
            self._last_known_hashes.pop(rel_path, None)

        event = EventRecord(
            folder_id=self.folder_id,
            timestamp=timestamp,
            event_type=event_type,
            path=rel_path,
            old_path=rel_old_path,
            file_hash=file_hash,
            delta_id=delta_id,
            size_before=size_before,
            size_after=size_after,
        )

        with self._buffer_lock:
            self._event_buffer.append(event)

        if len(self._event_buffer) >= self._batch_size:
            self._flush_buffer()

        if self.event_callback:
            self.event_callback(event)

    def _flush_buffer(self) -> None:
        with self._buffer_lock:
            if not self._event_buffer:
                return
            batch = self._event_buffer[:]
            self._event_buffer.clear()
        self.db.insert_events_batch(batch)

    def flush(self) -> None:
        self._flush_buffer()

    def on_created(self, event: FileSystemEvent) -> None:
        if isinstance(event, FileCreatedEvent):
            self._record_event("create", event.src_path)
        elif isinstance(event, DirCreatedEvent):
            self._record_event("create", event.src_path)

    def on_deleted(self, event: FileSystemEvent) -> None:
        if isinstance(event, FileDeletedEvent):
            self._record_event("delete", event.src_path)
        elif isinstance(event, DirDeletedEvent):
            self._record_event("delete", event.src_path)

    def on_modified(self, event: FileSystemEvent) -> None:
        if isinstance(event, FileModifiedEvent):
            self._record_event("modify", event.src_path)

    def on_moved(self, event: FileSystemEvent) -> None:
        if isinstance(event, FileMovedEvent):
            self._record_event(
                "rename",
                event.dest_path,
                old_path=event.src_path,
            )
        elif isinstance(event, DirMovedEvent):
            self._record_event(
                "rename",
                event.dest_path,
                old_path=event.src_path,
            )


class FolderWatcher:
    def __init__(
        self,
        path: Path,
        db: Optional[Database] = None,
        config: Optional[KalpaConfig] = None,
    ):
        self.path = path.resolve()
        self.config = config or KalpaConfig.load(path)
        self.db = db or Database(self.path / KALPA_DIR_NAME / "kalpa.db")
        self.snapshot_engine = SnapshotEngine(
            algorithm=self.config.compression_algorithm,
            compression_level=self.config.compression_level,
        )
        self.observer: Optional[Observer] = None
        self.handler: Optional[KalpaEventHandler] = None
        self.folder_id: Optional[str] = None
        self._running = False
        self._watch_thread: Optional[threading.Thread] = None

    def start(self) -> str:
        existing = self.db.get_folder_by_path(str(self.path))
        if existing:
            self.folder_id = existing["id"]
        else:
            self.folder_id = self.db.register_folder(str(self.path))

        self.handler = KalpaEventHandler(
            folder_id=self.folder_id,
            db=self.db,
            snapshot_engine=self.snapshot_engine,
            watched_path=self.path,
        )

        self.observer = Observer()
        self.observer.schedule(self.handler, str(self.path), recursive=True)
        self.observer.start()
        self._running = True
        return self.folder_id

    def stop(self) -> None:
        self._running = False
        if self.handler:
            self.handler.flush()
        if self.observer:
            self.observer.stop()
            self.observer.join()

    def is_running(self) -> bool:
        return self._running

    def take_snapshot(self, label: Optional[str] = None) -> int:
        manifest = self.snapshot_engine.build_file_manifest(self.path)
        snapshot_id = self.db.insert_snapshot(
            folder_id=self.folder_id or "",
            timestamp=datetime.now(timezone.utc).timestamp(),
            manifest=manifest,
            label=label,
        )
        return snapshot_id

    def get_status(self) -> dict:
        stats = self.db.get_storage_stats(self.folder_id or "")
        return {
            "path": str(self.path),
            "folder_id": self.folder_id,
            "watching": self._running,
            "event_count": stats["event_count"],
            "storage_bytes": stats["delta_storage_bytes"],
            "earliest_timestamp": stats["earliest_timestamp"],
            "last_event": stats["last_event_str"],
        }
