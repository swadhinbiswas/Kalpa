from __future__ import annotations

import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

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

        output_path.mkdir(parents=True, exist_ok=True)

        for file_path_str, content in state.items():
            full_path = output_path / file_path_str
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_bytes(content)

        timestamp_suffix = datetime.fromtimestamp(target_time).strftime("%H%M%S")
        fork_name = f"{output_path.name}_fork_{timestamp_suffix}"

        parent = output_path.parent
        final_path = parent / fork_name

        if final_path.exists():
            shutil.rmtree(str(final_path))

        shutil.copytree(str(output_path), str(final_path))

        shutil.rmtree(str(output_path))

        return final_path
