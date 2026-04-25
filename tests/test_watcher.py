from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from kalpa.snapshot import SnapshotEngine
from kalpa.storage import Database, EventRecord
from kalpa.watcher import FolderWatcher, KalpaEventHandler


class TestKalpaEventHandler:
    def test_is_kalpa_internal(self, temp_dir, db, folder_id):
        watcher_path = temp_dir
        kalpa_dir = watcher_path / ".kalpa"
        kalpa_dir.mkdir()

        engine = SnapshotEngine()
        handler = KalpaEventHandler(
            folder_id=folder_id,
            db=db,
            snapshot_engine=engine,
            watched_path=watcher_path,
        )

        assert handler._is_kalpa_internal(str(kalpa_dir / "internal.db"))
        assert handler._is_kalpa_internal(str(kalpa_dir))
        assert not handler._is_kalpa_internal(str(watcher_path / "real_file.txt"))

    def test_make_rel_path(self, temp_dir, db, folder_id):
        engine = SnapshotEngine()
        handler = KalpaEventHandler(
            folder_id=folder_id,
            db=db,
            snapshot_engine=engine,
            watched_path=temp_dir,
        )

        test_file = temp_dir / "subdir" / "file.txt"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("test")

        rel = handler._make_rel_path(str(test_file))
        assert rel == "subdir/file.txt"

    def test_record_event_create(self, temp_dir, db, folder_id):
        engine = SnapshotEngine()
        handler = KalpaEventHandler(
            folder_id=folder_id,
            db=db,
            snapshot_engine=engine,
            watched_path=temp_dir,
        )

        test_file = temp_dir / "new_file.txt"
        test_file.write_text("hello world")
        handler._record_event("create", str(test_file))
        handler.flush()

        events = db.get_events_since(folder_id)
        assert len(events) == 1
        assert events[0].event_type == "create"
        assert events[0].file_hash is not None

    def test_record_event_delete(self, temp_dir, db, folder_id):
        engine = SnapshotEngine()
        handler = KalpaEventHandler(
            folder_id=folder_id,
            db=db,
            snapshot_engine=engine,
            watched_path=temp_dir,
        )

        test_file = temp_dir / "to_delete.txt"
        test_file.write_text("delete me")
        handler._record_event("create", str(test_file))
        handler._record_event("delete", str(test_file))
        handler.flush()

        events = db.get_events_since(folder_id)
        assert len(events) == 2
        assert events[1].event_type == "delete"

    def test_record_event_modify(self, temp_dir, db, folder_id):
        engine = SnapshotEngine()
        handler = KalpaEventHandler(
            folder_id=folder_id,
            db=db,
            snapshot_engine=engine,
            watched_path=temp_dir,
        )

        test_file = temp_dir / "modify_me.txt"
        test_file.write_text("original")
        handler._record_event("create", str(test_file))

        test_file.write_text("modified")
        handler._record_event("modify", str(test_file))
        handler.flush()

        events = db.get_events_since(folder_id)
        assert len(events) == 2
        assert events[1].event_type == "modify"
        assert events[1].delta_id is not None

    def test_kalpa_dir_excluded(self, temp_dir, db, folder_id):
        engine = SnapshotEngine()
        handler = KalpaEventHandler(
            folder_id=folder_id,
            db=db,
            snapshot_engine=engine,
            watched_path=temp_dir,
        )

        kalpa_file = temp_dir / ".kalpa" / "internal.db"
        kalpa_file.parent.mkdir(exist_ok=True)
        kalpa_file.write_text("internal")
        handler._record_event("create", str(kalpa_file))
        handler.flush()

        events = db.get_events_since(folder_id)
        assert len(events) == 0

    def test_event_buffer_flush(self, temp_dir, db, folder_id):
        engine = SnapshotEngine()
        handler = KalpaEventHandler(
            folder_id=folder_id,
            db=db,
            snapshot_engine=engine,
            watched_path=temp_dir,
        )
        handler._batch_size = 3

        for i in range(5):
            test_file = temp_dir / f"batch_{i}.txt"
            test_file.write_text(f"content_{i}")
            handler._record_event("create", str(test_file))
        handler.flush()

        events = db.get_events_since(folder_id)
        assert len(events) == 5


class TestFolderWatcher:
    def test_start_and_stop(self, temp_dir, db):
        watcher = FolderWatcher(path=temp_dir, db=db)
        folder_id = watcher.start()
        assert folder_id is not None
        assert watcher.is_running()
        watcher.stop()
        assert not watcher.is_running()

    def test_take_snapshot(self, watched_folder, db):
        watcher = FolderWatcher(path=watched_folder, db=db)
        watcher.folder_id = db.register_folder(str(watched_folder))
        snapshot_id = watcher.take_snapshot(label="test")
        assert snapshot_id > 0

        snapshot = db.get_latest_snapshot(watcher.folder_id)
        assert snapshot is not None
        assert snapshot.label == "test"

    def test_get_status(self, temp_dir, db):
        watcher = FolderWatcher(path=temp_dir, db=db)
        watcher.folder_id = db.register_folder(str(temp_dir))
        status = watcher.get_status()
        assert status["path"] == str(temp_dir.resolve())
        assert status["folder_id"] == watcher.folder_id

    def test_double_start(self, temp_dir, db):
        watcher = FolderWatcher(path=temp_dir, db=db)
        folder_id1 = watcher.start()

        watcher2 = FolderWatcher(path=temp_dir, db=db)
        folder_id2 = watcher2.start()

        assert folder_id1 == folder_id2

        watcher.stop()
        watcher2.stop()
