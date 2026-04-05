from __future__ import annotations

import tempfile
from pathlib import Path

from kalpa.config import KalpaConfig, find_kalpa_dir, get_kalpa_dir


class TestConfig:
    def test_default_config(self):
        config = KalpaConfig.default()
        assert config.snapshot_interval_events == 100
        assert config.snapshot_interval_minutes == 60
        assert config.compression_algorithm == "zstd"
        assert config.compression_level == 3
        assert config.replay_default_speed == 2.0

    def test_save_and_load(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            config = KalpaConfig(
                snapshot_interval_events=50,
                snapshot_interval_minutes=30,
                compression_algorithm="raw",
                compression_level=1,
                replay_default_speed=4.0,
                replay_frame_window_ms=250,
                undo_max_steps=5,
                max_event_batch_size=500,
            )
            config.save(path)

            loaded = KalpaConfig.load(path)
            assert loaded.snapshot_interval_events == 50
            assert loaded.snapshot_interval_minutes == 30
            assert loaded.compression_algorithm == "raw"
            assert loaded.replay_default_speed == 4.0
            assert loaded.undo_max_steps == 5

    def test_find_kalpa_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            assert find_kalpa_dir(path) is None

            kalpa_dir = path / ".kalpa"
            kalpa_dir.mkdir()
            found = find_kalpa_dir(path)
            assert found is not None
            assert found == kalpa_dir

    def test_find_kalpa_dir_parent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            kalpa_dir = path / ".kalpa"
            kalpa_dir.mkdir()

            subdir = path / "subdir" / "nested"
            subdir.mkdir(parents=True)

            found = find_kalpa_dir(subdir)
            assert found == kalpa_dir

    def test_get_kalpa_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            kalpa_dir = get_kalpa_dir(path)
            assert kalpa_dir == path / ".kalpa"
