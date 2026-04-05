from __future__ import annotations

import tempfile
import time
from pathlib import Path

import pytest

from kalpa.storage import Database, EventRecord
from kalpa.timeline import Timeline


@pytest.fixture
def db_and_timeline():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = Database(db_path)
        folder_id = db.register_folder("/test/path")

        events = [
            EventRecord(
                folder_id=folder_id,
                timestamp=float(i * 10),
                event_type=typ,
                path=path,
            )
            for i, (typ, path) in enumerate(
                [
                    ("create", "a.txt"),
                    ("modify", "a.txt"),
                    ("create", "b.txt"),
                    ("delete", "a.txt"),
                    ("modify", "b.txt"),
                ]
            )
        ]
        db.insert_events_batch(events)

        timeline = Timeline(db, folder_id)
        yield db, timeline
        db.close()


class TestTimeline:
    def test_get_events(self, db_and_timeline):
        db, timeline = db_and_timeline
        events = timeline.get_events(limit=10)
        assert len(events) == 5

    def test_get_events_with_filter(self, db_and_timeline):
        db, timeline = db_and_timeline
        events = timeline.get_events(event_type="delete")
        assert len(events) == 1
        assert events[0].event_type == "delete"

    def test_get_event_count(self, db_and_timeline):
        db, timeline = db_and_timeline
        assert timeline.get_event_count() == 5

    def test_get_file_history(self, db_and_timeline):
        db, timeline = db_and_timeline
        history = timeline.get_file_history("a.txt")
        assert len(history) >= 2

    def test_snapshot_timeline_summary(self, db_and_timeline):
        db, timeline = db_and_timeline
        summary = timeline.snapshot_timeline_summary()
        assert len(summary) == 5
        assert summary[0]["type"] == "create"
        assert summary[0]["path"] == "a.txt"
