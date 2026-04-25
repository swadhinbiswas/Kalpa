from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path

import pytest

from kalpa.storage import Database, EventRecord


@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir)
        yield path


@pytest.fixture
def db():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_kalpa.db"
        database = Database(db_path)
        yield database
        database.close()


@pytest.fixture
def folder_id(db):
    return db.register_folder("/test/path")


@pytest.fixture
def sample_events(db, folder_id):
    events = [
        EventRecord(
            folder_id=folder_id,
            timestamp=float(i * 10),
            event_type=typ,
            path=path,
        )
        for i, (typ, path) in enumerate([
            ("create", "file_a.txt"),
            ("modify", "file_a.txt"),
            ("create", "file_b.txt"),
            ("delete", "file_a.txt"),
            ("modify", "file_b.txt"),
            ("rename", "file_c.txt"),
        ])
    ]
    events[5].old_path = "file_b.txt"
    db.insert_events_batch(events)
    return events


@pytest.fixture
def watched_folder(temp_dir):
    kalpa_dir = temp_dir / ".kalpa"
    kalpa_dir.mkdir()
    (temp_dir / "src").mkdir()
    (temp_dir / "src" / "main.py").write_text("print('hello')")
    (temp_dir / "README.md").write_text("# Test")
    return temp_dir
