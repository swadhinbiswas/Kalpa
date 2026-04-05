from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

import pytest

from kalpa.storage import Database, DeltaRecord, EventRecord, SnapshotRecord


@pytest.fixture
def db():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_kalpa.db"
        db = Database(db_path)
        yield db
        db.close()


class TestDatabase:
    def test_init_creates_tables(self, db):
        conn = db._get_conn()
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        table_names = [t["name"] for t in tables]
        assert "events" in table_names
        assert "deltas" in table_names
        assert "snapshots" in table_names
        assert "folders" in table_names

    def test_register_folder(self, db):
        folder_id = db.register_folder("/test/path")
        assert folder_id is not None
        fetched = db.get_folder(folder_id)
        assert fetched is not None
        assert fetched["path"] == "/test/path"
        assert fetched["active"] == 1

    def test_get_folder_by_path(self, db):
        folder_id = db.register_folder("/test/path")
        fetched = db.get_folder_by_path("/test/path")
        assert fetched is not None
        assert fetched["id"] == folder_id

    def test_get_all_active_folders(self, db):
        db.register_folder("/path/one")
        db.register_folder("/path/two")
        folders = db.get_all_active_folders()
        assert len(folders) == 2

    def test_deactivate_folder(self, db):
        folder_id = db.register_folder("/test/path")
        db.deactivate_folder(folder_id)
        fetched = db.get_folder(folder_id)
        assert fetched["active"] == 0

    def test_insert_event(self, db):
        folder_id = db.register_folder("/test/path")
        event = EventRecord(
            folder_id=folder_id,
            timestamp=time.time(),
            event_type="create",
            path="test.txt",
            file_hash="abc123",
        )
        event_id = db.insert_event(event)
        assert event_id > 0

    def test_insert_events_batch(self, db):
        folder_id = db.register_folder("/test/path")
        events = [
            EventRecord(
                folder_id=folder_id,
                timestamp=time.time() + i,
                event_type="create",
                path=f"file{i}.txt",
            )
            for i in range(5)
        ]
        ids = db.insert_events_batch(events)
        assert len(ids) == 5

    def test_get_last_event(self, db):
        folder_id = db.register_folder("/test/path")
        event1 = EventRecord(
            folder_id=folder_id, timestamp=100.0, event_type="create", path="a.txt"
        )
        event2 = EventRecord(
            folder_id=folder_id, timestamp=200.0, event_type="modify", path="a.txt"
        )
        db.insert_event(event1)
        db.insert_event(event2)
        last = db.get_last_event(folder_id)
        assert last is not None
        assert last.event_type == "modify"

    def test_get_events_since(self, db):
        folder_id = db.register_folder("/test/path")
        ids = []
        for i in range(3):
            e = EventRecord(
                folder_id=folder_id,
                timestamp=float(i),
                event_type="create",
                path=f"f{i}.txt",
            )
            ids.append(db.insert_event(e))

        events = db.get_events_since(folder_id, since_id=ids[0], limit=10)
        assert len(events) == 2

    def test_query_events_with_filters(self, db):
        folder_id = db.register_folder("/test/path")
        db.insert_event(
            EventRecord(
                folder_id=folder_id,
                timestamp=100.0,
                event_type="create",
                path="a.txt",
            )
        )
        db.insert_event(
            EventRecord(
                folder_id=folder_id,
                timestamp=200.0,
                event_type="delete",
                path="a.txt",
            )
        )

        events = db.query_events(folder_id, event_type="delete")
        assert len(events) == 1
        assert events[0].event_type == "delete"

        events = db.query_events(folder_id, start_time=150.0)
        assert len(events) == 1

    def test_get_event_count(self, db):
        folder_id = db.register_folder("/test/path")
        assert db.get_event_count(folder_id) == 0
        db.insert_event(
            EventRecord(
                folder_id=folder_id, timestamp=1.0, event_type="create", path="a.txt"
            )
        )
        assert db.get_event_count(folder_id) == 1

    def test_get_destructive_events(self, db):
        folder_id = db.register_folder("/test/path")
        db.insert_event(
            EventRecord(
                folder_id=folder_id,
                timestamp=1.0,
                event_type="create",
                path="a.txt",
            )
        )
        db.insert_event(
            EventRecord(
                folder_id=folder_id,
                timestamp=2.0,
                event_type="delete",
                path="a.txt",
            )
        )
        db.insert_event(
            EventRecord(
                folder_id=folder_id,
                timestamp=3.0,
                event_type="modify",
                path="b.txt",
            )
        )

        destructive = db.get_destructive_events(folder_id, steps=2)
        assert len(destructive) == 2
        assert destructive[0].event_type == "modify"

    def test_insert_and_get_delta(self, db):
        delta = DeltaRecord(
            from_hash="oldhash", to_hash="newhash", algorithm="raw", delta_bytes=b"test"
        )
        delta_id = db.insert_delta(delta)
        assert delta_id > 0

        fetched = db.get_delta(delta_id)
        assert fetched is not None
        assert fetched.to_hash == "newhash"
        assert fetched.delta_bytes == b"test"

    def test_insert_snapshot(self, db):
        folder_id = db.register_folder("/test/path")
        manifest = {"file1.txt": "hash1", "file2.txt": "hash2"}
        snap_id = db.insert_snapshot(folder_id, 1000.0, manifest, label="test")
        assert snap_id > 0

        latest = db.get_latest_snapshot(folder_id)
        assert latest is not None
        assert latest.label == "test"
        loaded_manifest = json.loads(latest.manifest)
        assert loaded_manifest["file1.txt"] == "hash1"

    def test_get_latest_snapshot_before_time(self, db):
        folder_id = db.register_folder("/test/path")
        db.insert_snapshot(folder_id, 100.0, {}, label="old")
        db.insert_snapshot(folder_id, 200.0, {}, label="new")

        snap = db.get_latest_snapshot(folder_id, before=150.0)
        assert snap is not None
        assert snap.label == "old"

        snap = db.get_latest_snapshot(folder_id, before=250.0)
        assert snap is not None
        assert snap.label == "new"

    def test_get_storage_stats(self, db):
        folder_id = db.register_folder("/test/path")
        stats = db.get_storage_stats(folder_id)
        assert stats["event_count"] == 0
        assert stats["delta_storage_bytes"] == 0
