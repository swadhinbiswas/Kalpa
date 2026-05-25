from __future__ import annotations

import pytest

from kalpa.replay import ReplayEngine, ReplayFrame
from kalpa.storage import Database, EventRecord


class TestReplayEngine:
    @pytest.fixture
    def engine_and_events(self, temp_dir):
        db_path = temp_dir / "test.db"
        db = Database(db_path)
        folder_id = db.register_folder(str(temp_dir))

        events = [
            EventRecord(
                folder_id=folder_id,
                timestamp=float(i * 100),
                event_type=typ,
                path=path,
            )
            for i, (typ, path) in enumerate([
                ("create", "a.txt"),
                ("modify", "a.txt"),
                ("create", "b.txt"),
                ("delete", "a.txt"),
            ])
        ]

        engine = ReplayEngine(db=db, folder_id=folder_id, speed=1.0, frame_window_ms=60)
        yield engine, events, folder_id
        db.close()

    def test_group_into_frames_close_events(self, engine_and_events):
        engine, events, folder_id = engine_and_events
        frames = engine._group_into_frames(events)

        assert len(frames) >= 1
        for frame in frames:
            assert isinstance(frame, ReplayFrame)
            assert len(frame.events) >= 1

    def test_group_into_frames_single_event(self, engine_and_events):
        engine, events, folder_id = engine_and_events
        single_event = [events[0]]
        frames = engine._group_into_frames(single_event)
        assert len(frames) == 1
        assert len(frames[0].events) == 1

    def test_group_into_frames_empty(self, engine_and_events):
        engine, events, folder_id = engine_and_events
        frames = engine._group_into_frames([])
        assert len(frames) == 0

    def test_group_into_frames_wide_window(self, engine_and_events):
        engine, events, folder_id = engine_and_events

        spaced_events = [
            EventRecord(
                folder_id=folder_id,
                timestamp=float(i * 1000),
                event_type="modify",
                path="file.txt",
            )
            for i in range(5)
        ]

        frames = engine._group_into_frames(spaced_events)
        assert len(frames) > 1

    def test_group_into_frames_narrow_window(self, engine_and_events):
        engine, events, folder_id = engine_and_events

        close_events = [
            EventRecord(
                folder_id=folder_id,
                timestamp=float(1000 + i * 0.01),
                event_type="modify",
                path="file.txt",
            )
            for i in range(5)
        ]

        frames = engine._group_into_frames(close_events)
        assert len(frames) == 1

    def test_render_frame_format(self, engine_and_events):
        engine, events, folder_id = engine_and_events
        frames = engine._group_into_frames(events)

        frame = frames[0]
        panel = engine._render_frame(frame, 0, len(frames))
        assert panel is not None
        assert "frame 1/" in (panel.title or "")
