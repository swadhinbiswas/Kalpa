from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

KALPA_DIR_NAME = ".kalpa"


@dataclass
class KalpaConfig:
    snapshot_interval_events: int = 100
    snapshot_interval_minutes: int = 60
    compression_algorithm: str = "zstd"
    compression_level: int = 3
    replay_default_speed: float = 2.0
    replay_frame_window_ms: int = 500
    undo_max_steps: int = 10
    max_event_batch_size: int = 1000

    @classmethod
    def default(cls) -> KalpaConfig:
        return cls()

    @classmethod
    def load(cls, path: Path) -> KalpaConfig:
        config_file = path / KALPA_DIR_NAME / "config.json"
        if config_file.exists():
            data = json.loads(config_file.read_text())
            return cls(**{k: v for k, v in data.items() if hasattr(cls, k)})
        return cls.default()

    def save(self, path: Path) -> None:
        config_dir = path / KALPA_DIR_NAME
        config_dir.mkdir(parents=True, exist_ok=True)
        config_file = config_dir / "config.json"
        config_file.write_text(
            json.dumps(
                {
                    "snapshot_interval_events": self.snapshot_interval_events,
                    "snapshot_interval_minutes": self.snapshot_interval_minutes,
                    "compression_algorithm": self.compression_algorithm,
                    "compression_level": self.compression_level,
                    "replay_default_speed": self.replay_default_speed,
                    "replay_frame_window_ms": self.replay_frame_window_ms,
                    "undo_max_steps": self.undo_max_steps,
                    "max_event_batch_size": self.max_event_batch_size,
                },
                indent=2,
            )
        )


def find_kalpa_dir(path: Optional[Path] = None) -> Optional[Path]:
    start = path or Path.cwd()
    for parent in [start] + list(start.parents):
        kalpa_dir = parent / KALPA_DIR_NAME
        if kalpa_dir.is_dir():
            return kalpa_dir
    return None


def get_kalpa_dir(watched_path: Path) -> Path:
    return watched_path / KALPA_DIR_NAME
