from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path

import pytest

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

    def test_compute_raw_diff_empty(self):
        original = b""
        modified = b"hello\nworld\n"
        diff = compute_raw_diff(original, modified)
        result = apply_raw_diff(original, diff)
        assert result == modified

    def test_delta_roundtrip_raw(self):
        original = b"old content here\n"
        modified = b"new content here\nwith more lines\n"
        delta_bytes, algorithm = compute_delta(original, modified, algorithm="raw")
        assert algorithm == "raw"
        result = apply_delta(original, delta_bytes, algorithm)
        assert result == modified

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
