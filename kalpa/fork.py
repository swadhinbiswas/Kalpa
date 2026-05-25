from __future__ import annotations

import shutil
from pathlib import Path

from kalpa.timeline import Timeline


class ForkEngine:
    def __init__(self, timeline: Timeline):
        self.timeline = timeline

    def fork_folder(
        self,
        target_time: float,
        output_path: Path,
        include_kalpa_meta: bool = False,
    ) -> Path:
        state = self.timeline.get_folder_state_at_time(target_time)

        output_path = output_path.resolve()
        if output_path.exists():
            shutil.rmtree(str(output_path))
        output_path.mkdir(parents=True, exist_ok=True)

        for file_path_str, content in state.items():
            full_path = output_path / file_path_str
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_bytes(content)

        return output_path
