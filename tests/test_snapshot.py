from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path

from kalpa.snapshot import (
    SnapshotEngine,
    apply_delta,
    apply_raw_diff,
    compute_delta,
    compute_hash,
    compute_hash_from_bytes,
    compute_raw_diff,
)


class TestSnapshot:
    def test_compute_hash_file(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"hello world")
            f.flush()
            file_hash = compute_hash(f.name)
            assert file_hash is not None
            expected = hashlib.sha256(b"hello world").hexdigest()
            assert file_hash == expected
        os.unlink(f.name)

    def test_compute_hash_nonexistent(self):
        assert compute_hash("/nonexistent/path") is None

    def test_compute_hash_from_bytes(self):
        h = compute_hash_from_bytes(b"test data")
        assert h == hashlib.sha256(b"test data").hexdigest()

    def test_hash_bytes(self):
        engine = SnapshotEngine()
        h = engine.hash_bytes(b"hello")
        assert h == hashlib.sha256(b"hello").hexdigest()

    def test_compute_raw_diff_equal(self):
        original = b"line1\nline2\nline3\n"
        modified = b"line1\nline2\nline3\n"
        diff = compute_raw_diff(original, modified)
        result = apply_raw_diff(original, diff)
        assert result == modified

    def test_compute_raw_diff_insert(self):
        original = b"line1\nline3\n"
        modified = b"line1\nline2\nline3\n"
        diff = compute_raw_diff(original, modified)
        result = apply_raw_diff(original, diff)
        assert result == modified

    def test_compute_raw_diff_delete(self):
        original = b"line1\nline2\nline3\n"
        modified = b"line1\nline3\n"
        diff = compute_raw_diff(original, modified)
        result = apply_raw_diff(original, diff)
        assert result == modified

    def test_compute_raw_diff_replace(self):
        original = b"line1\nOLD\nline3\n"
        modified = b"line1\nNEW\nline3\n"
        diff = compute_raw_diff(original, modified)
        result = apply_raw_diff(original, diff)
        assert result == modified

    def test_compute_raw_diff_empty_original(self):
        original = b""
        modified = b"hello\nworld\n"
        diff = compute_raw_diff(original, modified)
        result = apply_raw_diff(original, diff)
        assert result == modified

    def test_compute_raw_diff_empty_modified(self):
        original = b"hello\nworld\n"
        modified = b""
        diff = compute_raw_diff(original, modified)
        result = apply_raw_diff(original, diff)
        assert result == modified

    def test_compute_raw_diff_both_empty(self):
        original = b""
        modified = b""
        diff = compute_raw_diff(original, modified)
        result = apply_raw_diff(original, diff)
        assert result == modified

    def test_delta_roundtrip_raw(self):
        original = b"old content here\nwith multiple lines\n"
        modified = b"new content here\nwith more lines\nand even more\n"
        delta_bytes, algorithm = compute_delta(original, modified, algorithm="raw")
        assert algorithm == "raw"
        result = apply_delta(original, delta_bytes, algorithm)
        assert result == modified

    def test_delta_roundtrip_empty_original(self):
        original = b""
        modified = b"brand new file content\nwith multiple lines\n"
        delta_bytes, algorithm = compute_delta(original, modified, algorithm="raw")
        result = apply_delta(original, delta_bytes, algorithm)
        assert result == modified

    def test_delta_roundtrip_no_changes(self):
        original = b"same content\n"
        delta_bytes, algorithm = compute_delta(original, original, algorithm="raw")
        result = apply_delta(original, delta_bytes, algorithm)
        assert result == original

    def test_apply_raw_diff_corrupted_delta(self):
        original = b"some content"
        result = apply_raw_diff(original, b"corrupted data without separator")
        assert result == original

    def test_build_file_manifest(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            (path / "file1.txt").write_text("hello")
            (path / "file2.txt").write_text("world")
            os.makedirs(str(path / "subdir"))
            (path / "subdir" / "file3.txt").write_text("nested")

            engine = SnapshotEngine()
            manifest = engine.build_file_manifest(path)
            assert "file1.txt" in manifest
            assert "file2.txt" in manifest
            assert "subdir/file3.txt" in manifest
            assert len(manifest) == 3

    def test_manifest_excludes_kalpa_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            (path / "file1.txt").write_text("hello")
            os.makedirs(str(path / ".kalpa"))
            (path / ".kalpa" / "internal.db").write_text("data")

            engine = SnapshotEngine()
            manifest = engine.build_file_manifest(path)
            assert "file1.txt" in manifest
            assert ".kalpa/internal.db" not in manifest

    def test_manifest_empty_folder(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            engine = SnapshotEngine()
            manifest = engine.build_file_manifest(path)
            assert len(manifest) == 0

    def test_apply_delta_unknown_algorithm(self):
        original = b"test"
        result = apply_delta(original, b"delta", "unknown")
        assert result == original

    def test_snapshot_engine_create_and_apply_delta(self):
        engine = SnapshotEngine(algorithm="raw")
        original = b"line1\nline2\n"
        modified = b"line1\nmodified\nline3\n"
        delta_bytes, algorithm = engine.create_delta(original, modified)
        assert algorithm == "raw"
        result = engine.apply_delta(original, delta_bytes, algorithm)
        assert result == modified

    def test_compute_file_hash(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"hash test content")
            f.flush()
            engine = SnapshotEngine()
            file_hash = engine.compute_file_hash(f.name)
            assert file_hash is not None
            expected = hashlib.sha256(b"hash test content").hexdigest()
            assert file_hash == expected
        os.unlink(f.name)
