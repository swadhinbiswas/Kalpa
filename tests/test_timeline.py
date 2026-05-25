from __future__ import annotations

import pytest

from kalpa.storage import EventRecord
from kalpa.timeline import Timeline


@pytest.fixture
def db_and_timeline(db, folder_id):
    events = [
        EventRecord(
            folder_id=folder_id,
            timestamp=float(i * 10),
            event_type=typ,
            path=path,
        )
        for i, (typ, path) in enumerate([
            ("create", "a.txt"),
            ("modify", "a.txt"),
            ("create", "b.txt"),
            ("delete", "a.txt"),
            ("modify", "b.txt"),
        ])
    ]
    db.insert_events_batch(events)
    timeline = Timeline(db, folder_id)
    yield db, timeline, folder_id


class TestTimeline:
    def test_get_events(self, db_and_timeline):
        db, timeline, _ = db_and_timeline
        events = timeline.get_events(limit=10)
        assert len(events) == 5

    def test_get_events_with_filter(self, db_and_timeline):
        db, timeline, _ = db_and_timeline
        events = timeline.get_events(event_type="delete")
        assert len(events) == 1
        assert events[0].event_type == "delete"

    def test_get_events_with_time_range(self, db_and_timeline):
        db, timeline, _ = db_and_timeline
        events = timeline.get_events(start_time=15.0, end_time=35.0)
        assert len(events) == 2
        assert events[0].timestamp == 20.0
        assert events[1].timestamp == 30.0

    def test_get_event_count(self, db_and_timeline):
        db, timeline, _ = db_and_timeline
        assert timeline.get_event_count() == 5

    def test_get_file_history(self, db_and_timeline):
        db, timeline, _ = db_and_timeline
        history = timeline.get_file_history("a.txt")
        assert len(history) >= 2

    def test_reconstruct_file_not_found(self, db_and_timeline):
        db, timeline, _ = db_and_timeline
        content = timeline.reconstruct_file_at_time("nonexistent.txt", 100.0)
        assert content is not None
        assert content == b""

    def test_reconstruct_file_after_delete(self, db_and_timeline):
        db, timeline, folder_id = db_and_timeline
        content = timeline.reconstruct_file_at_time("a.txt", 25.0)
        assert content is None or content == b""

    def test_reconstruct_file_before_delete(self, db_and_timeline):
        db, timeline, folder_id = db_and_timeline
        content = timeline.reconstruct_file_at_time("a.txt", 20.0)
        assert content is not None

    def test_snapshot_timeline_summary(self, db_and_timeline):
        db, timeline, _ = db_and_timeline
        summary = timeline.snapshot_timeline_summary()
        assert len(summary) == 5
        assert summary[0]["type"] == "create"
        assert summary[0]["path"] == "a.txt"

    def test_get_folder_state_at_time_empty(self, db, folder_id):
        timeline = Timeline(db, folder_id)
        state = timeline.get_folder_state_at_time(1000.0)
        assert isinstance(state, dict)

    def test_reconstruct_file_before_event_id(self, db, folder_id):
        db.insert_event(
            EventRecord(
                folder_id=folder_id, timestamp=10.0,
                event_type="create", path="test.txt",
            )
        )
        db.insert_event(
            EventRecord(
                folder_id=folder_id, timestamp=20.0,
                event_type="modify", path="test.txt",
            )
        )
        events = db.query_events(folder_id=folder_id)
        modify_event = [e for e in events if e.event_type == "modify"][0]

        timeline = Timeline(db, folder_id)
        content = timeline.reconstruct_file_at_time(
            "test.txt", 25.0, before_event_id=modify_event.id
        )
        assert content is not None
