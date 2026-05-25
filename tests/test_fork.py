from __future__ import annotations

from kalpa.fork import ForkEngine
from kalpa.snapshot import SnapshotEngine
from kalpa.storage import Database, DeltaRecord, EventRecord
from kalpa.timeline import Timeline


class TestForkEngine:
    def test_fork_folder(self, temp_dir):
        db_path = temp_dir / "test.db"
        db = Database(db_path)
        folder_id = db.register_folder(str(temp_dir))

        engine = SnapshotEngine(algorithm="raw")
        file_a_path = temp_dir / "file_a.txt"
        file_a_path.write_text("alpha")
        file_b_path = temp_dir / "file_b.txt"
        file_b_path.write_text("beta")
        subdir = temp_dir / "subdir"
        subdir.mkdir()
        nested_path = subdir / "nested.txt"
        nested_path.write_text("nested")

        ts = 1000.0
        raw_manifest = engine.build_file_manifest(temp_dir)
        manifest = {
            k: v for k, v in raw_manifest.items()
            if not k.endswith((".db", ".db-shm", ".db-wal"))
        }
        db.insert_snapshot(folder_id, ts, manifest, label="pre_fork")

        for rel_path, file_hash in manifest.items():
            full_path = temp_dir / rel_path
            if full_path.exists():
                content = full_path.read_bytes()
                new_hash = engine.hash_bytes(content)
                delta_bytes, algorithm = engine.create_delta(b"", content)
                delta_rec = DeltaRecord(
                    from_hash=None,
                    to_hash=new_hash,
                    algorithm=algorithm,
                    delta_bytes=delta_bytes,
                )
                delta_id = db.insert_delta(delta_rec)
                db.insert_event(
                    EventRecord(
                        folder_id=folder_id,
                        timestamp=ts - 1,
                        event_type="create",
                        path=rel_path,
                        file_hash=new_hash,
                        delta_id=delta_id,
                        size_after=len(content),
                    )
                )

        timeline = Timeline(db, folder_id)
        fork_engine = ForkEngine(timeline)

        output_path = temp_dir / "fork_output"
        fork_result = fork_engine.fork_folder(ts + 1, output_path)

        assert fork_result == output_path
        assert output_path.exists()
        assert (output_path / "file_a.txt").exists()
        assert (output_path / "file_b.txt").exists()
        assert (output_path / "subdir" / "nested.txt").exists()

        assert (output_path / "file_a.txt").read_text() == "alpha"
        assert (output_path / "subdir" / "nested.txt").read_text() == "nested"

        db.close()

    def test_fork_empty_folder(self, temp_dir):
        db_path = temp_dir / "test.db"
        db = Database(db_path)
        folder_id = db.register_folder(str(temp_dir))

        ts = 2000.0
        db.insert_snapshot(folder_id, ts, {}, label="empty")

        timeline = Timeline(db, folder_id)
        fork_engine = ForkEngine(timeline)

        output_path = temp_dir / "empty_fork"
        fork_result = fork_engine.fork_folder(ts, output_path)

        assert fork_result.exists()
        assert len(list(output_path.iterdir())) == 0

        db.close()

    def test_fork_overwrites_existing(self, temp_dir):
        db_path = temp_dir / "test.db"
        db = Database(db_path)
        folder_id = db.register_folder(str(temp_dir))

        engine = SnapshotEngine(algorithm="raw")
        file_path = temp_dir / "file.txt"
        file_path.write_text("content")

        ts = 3000.0
        manifest = {"file.txt": engine.hash_bytes(b"content")}
        db.insert_snapshot(folder_id, ts, manifest)

        content = file_path.read_bytes()
        new_hash = engine.hash_bytes(content)
        delta_bytes, algorithm = engine.create_delta(b"", content)
        delta_rec = DeltaRecord(
            from_hash=None, to_hash=new_hash,
            algorithm=algorithm, delta_bytes=delta_bytes,
        )
        delta_id = db.insert_delta(delta_rec)
        db.insert_event(
            EventRecord(
                folder_id=folder_id, timestamp=ts - 1,
                event_type="create", path="file.txt",
                file_hash=new_hash, delta_id=delta_id,
                size_after=len(content),
            )
        )

        output_path = temp_dir / "existing_dir"
        output_path.mkdir()
        (output_path / "old_file.txt").write_text("old")

        timeline = Timeline(db, folder_id)
        fork_engine = ForkEngine(timeline)
        fork_result = fork_engine.fork_folder(ts, output_path)

        assert fork_result == output_path
        assert (output_path / "file.txt").read_text() == "content"
        assert not (output_path / "old_file.txt").exists()

        db.close()
