from __future__ import annotations

from kalpa.diff import DiffEngine
from kalpa.snapshot import SnapshotEngine
from kalpa.storage import Database, DeltaRecord, EventRecord
from kalpa.timeline import Timeline


class TestDiffEngine:
    def test_diff_same_time(self, temp_dir):
        db_path = temp_dir / "test.db"
        db = Database(db_path)
        folder_id = db.register_folder(str(temp_dir))

        ts = 1000.0
        manifest = {"file.txt": "hash_same"}
        db.insert_snapshot(folder_id, ts, manifest)

        timeline = Timeline(db, folder_id)
        diff_engine = DiffEngine(timeline)

        diffs = diff_engine.diff_timestamps(ts, ts)
        assert len(diffs) == 0

        db.close()

    def test_diff_file_added(self, temp_dir):
        db_path = temp_dir / "test.db"
        db = Database(db_path)
        folder_id = db.register_folder(str(temp_dir))

        ts_a = 1000.0
        ts_b = 2000.0
        db.insert_snapshot(folder_id, ts_a, {"a.txt": "hash_a"})

        engine = SnapshotEngine(algorithm="raw")
        content = b"new file content"
        delta_bytes, algorithm = engine.create_delta(b"", content)
        delta_id = db.insert_delta(
            DeltaRecord(
                from_hash=None, to_hash="hash_b",
                algorithm=algorithm, delta_bytes=delta_bytes,
            )
        )
        db.insert_event(
            EventRecord(
                folder_id=folder_id, timestamp=ts_b - 1,
                event_type="create", path="b.txt",
                file_hash="hash_b", delta_id=delta_id,
                size_after=len(content),
            )
        )

        timeline = Timeline(db, folder_id)
        diff_engine = DiffEngine(timeline)

        diffs = diff_engine.diff_timestamps(ts_a, ts_b)
        assert "b.txt" in diffs

        db.close()

    def test_diff_file_deleted(self, temp_dir):
        db_path = temp_dir / "test.db"
        db = Database(db_path)
        folder_id = db.register_folder(str(temp_dir))

        engine = SnapshotEngine(algorithm="raw")
        content = b"file content to be deleted"
        file_hash = engine.hash_bytes(content)
        delta_bytes, algorithm = engine.create_delta(b"", content)
        delta_id = db.insert_delta(
            DeltaRecord(
                from_hash=None, to_hash=file_hash,
                algorithm=algorithm, delta_bytes=delta_bytes,
            )
        )

        ts_a = 1000.0
        ts_b = 2000.0
        db.insert_snapshot(folder_id, ts_a, {"a.txt": file_hash})

        db.insert_event(
            EventRecord(
                folder_id=folder_id, timestamp=ts_a - 1,
                event_type="create", path="a.txt",
                file_hash=file_hash, delta_id=delta_id,
                size_after=len(content),
            )
        )

        db.insert_event(
            EventRecord(
                folder_id=folder_id, timestamp=ts_b,
                event_type="delete", path="a.txt",
            )
        )

        timeline = Timeline(db, folder_id)
        diff_engine = DiffEngine(timeline)

        diffs = diff_engine.diff_timestamps(ts_a, ts_b)
        assert len(diffs) > 0

        db.close()

    def test_diff_no_changes(self, temp_dir):
        db_path = temp_dir / "test.db"
        db = Database(db_path)
        folder_id = db.register_folder(str(temp_dir))

        ts = 1000.0
        db.insert_snapshot(folder_id, ts, {"a.txt": "hash_a", "b.txt": "hash_b"})

        timeline = Timeline(db, folder_id)
        diff_engine = DiffEngine(timeline)

        diffs = diff_engine.diff_timestamps(ts, ts + 1)
        assert len(diffs) == 0

        db.close()
