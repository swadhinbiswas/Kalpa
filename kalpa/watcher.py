from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from watchdog.events import (
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
        self._last_known_hashes: dict[str, str] = {}
        self._last_known_content: dict[str, bytes] = {}
        self._lock = threading.Lock()
        self._event_buffer: list[EventRecord] = []
        self._buffer_lock = threading.Lock()
        self._batch_size = 50
        self._last_flush_time = time.monotonic()
        self._max_buffer_age = 2.0

    def _is_kalpa_internal(self, path_str: str) -> bool:
        path = Path(path_str).resolve()
        kalpa_dir = (self.watched_path / KALPA_DIR_NAME).resolve()
        return kalpa_dir in path.parents or path == kalpa_dir

    def _make_rel_path(self, path_str: str) -> str:
        try:
            return str(Path(path_str).resolve().relative_to(self.watched_path.resolve()))
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

        file_hash: Optional[str] = None
        delta_id: Optional[int] = None
        size_before: Optional[int] = None
        size_after: Optional[int] = None

        if event_type in ("create", "modify"):
            try:
                content = Path(path).read_bytes()
                size_after = len(content)
                file_hash = self.snapshot_engine.hash_bytes(content)

                if event_type == "modify":
                    old_content = self._last_known_content.get(rel_path)
                    if old_content is not None and old_content != content:
                        delta_bytes, algorithm = self.snapshot_engine.create_delta(
                            old_content, content
                        )
                        delta_rec = DeltaRecord(
                            from_hash=self._last_known_hashes.get(rel_path),
                            to_hash=file_hash,
                            algorithm=algorithm,
                            delta_bytes=delta_bytes,
                        )
                        delta_id = self.db.insert_delta(delta_rec)
                        size_before = len(old_content)
                    elif old_content is None and file_hash:
                        delta_bytes, algorithm = self.snapshot_engine.create_delta(
                            b"", content
                        )
                        delta_rec = DeltaRecord(
                            from_hash=None,
                            to_hash=file_hash,
                            algorithm=algorithm,
                            delta_bytes=delta_bytes,
                        )
                        delta_id = self.db.insert_delta(delta_rec)

                self._last_known_hashes[rel_path] = file_hash
                self._last_known_content[rel_path] = content

            except OSError:
                pass

        elif event_type == "delete":
            size_before = 0
            self._last_known_hashes.pop(rel_path, None)
            self._last_known_content.pop(rel_path, None)

        elif event_type == "rename":
            rel_old = self._make_rel_path(old_path) if old_path else None
            if rel_old:
                old_hash = self._last_known_hashes.pop(rel_old, None)
                old_content = self._last_known_content.pop(rel_old, None)
                if old_hash:
                    self._last_known_hashes[rel_path] = old_hash
                if old_content:
                    self._last_known_content[rel_path] = old_content

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
        elif time.monotonic() - self._last_flush_time >= self._max_buffer_age:
            self._flush_buffer()

        if self.event_callback:
            self.event_callback(event)

    def _flush_buffer(self) -> None:
        with self._buffer_lock:
            if not self._event_buffer:
                return
            batch = self._event_buffer[:]
            self._event_buffer.clear()
            self._last_flush_time = time.monotonic()
        if batch:
            self.db.insert_events_batch(batch)

    def flush(self) -> None:
        self._flush_buffer()

    def on_created(self, event: FileSystemEvent) -> None:
        if isinstance(event, (FileCreatedEvent,)):
            self._record_event("create", event.src_path)

    def on_deleted(self, event: FileSystemEvent) -> None:
        if isinstance(event, (FileDeletedEvent,)):
            self._record_event("delete", event.src_path)

    def on_modified(self, event: FileSystemEvent) -> None:
        if isinstance(event, (FileModifiedEvent,)):
            self._record_event("modify", event.src_path)

    def on_moved(self, event: FileSystemEvent) -> None:
        if isinstance(event, (FileMovedEvent,)):
            self._record_event("rename", event.dest_path, old_path=event.src_path)


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
        self._event_count_since_snapshot = 0
        self._watch_start_time = time.monotonic()
        self._snapshot_interval_events = config.snapshot_interval_events if config else 100
        self._snapshot_interval_minutes = config.snapshot_interval_minutes if config else 60
        self._lock = threading.Lock()

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
            event_callback=self._on_event,
        )

        self.observer = Observer()
        self.observer.schedule(self.handler, str(self.path), recursive=True)
        self.observer.start()
        self._running = True
        return self.folder_id

    def _on_event(self, event: EventRecord) -> None:
        with self._lock:
            self._event_count_since_snapshot += 1

    def check_snapshot_trigger(self) -> None:
        with self._lock:
            if self._event_count_since_snapshot >= self._snapshot_interval_events:
                self._event_count_since_snapshot = 0
                elapsed = time.monotonic() - self._watch_start_time
                if elapsed >= self._snapshot_interval_minutes * 60:
                    self._watch_start_time = time.monotonic()
                self.take_snapshot(label="auto")

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
