from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from kalpa.storage import Database, EventRecord

REPLAY_COLORS = {
    "create": "green",
    "modify": "yellow",
    "delete": "red",
    "rename": "cyan",
}

REPLAY_ICONS = {
    "create": "+",
    "modify": "~",
    "delete": "-",
    "rename": "→",
}


@dataclass
class ReplayFrame:
    timestamp: float
    events: List[EventRecord] = field(default_factory=list)


class ReplayEngine:
    def __init__(
        self,
        db: Database,
        folder_id: str,
        speed: float = 1.0,
        frame_window_ms: int = 500,
    ):
        self.db = db
        self.folder_id = folder_id
        self.speed = speed
        self.frame_window_ms = frame_window_ms
        self.console = Console()

    def _group_into_frames(
        self, events: List[EventRecord]
    ) -> List[ReplayFrame]:
        if not events:
            return []

        frames: List[ReplayFrame] = []
        current_frame = ReplayFrame(timestamp=events[0].timestamp)

        for event in events:
            time_diff_ms = abs(event.timestamp - current_frame.timestamp) * 1000
            if time_diff_ms <= self.frame_window_ms:
                current_frame.events.append(event)
            else:
                if current_frame.events:
                    frames.append(current_frame)
                current_frame = ReplayFrame(
                    timestamp=event.timestamp, events=[event]
                )

        if current_frame.events:
            frames.append(current_frame)

        return frames

    def _render_frame(self, frame: ReplayFrame, frame_index: int, total: int) -> Panel:
        dt = datetime.fromtimestamp(frame.timestamp)
        time_str = dt.strftime("%H:%M:%S")

        table = Table.grid(padding=(0, 1))
        table.add_column()

        for event in frame.events:
            icon = REPLAY_ICONS.get(event.event_type, "?")
            color = REPLAY_COLORS.get(event.event_type, "white")

            text = Text()
            text.append(f" {icon} ", style=f"bold {color}")
            text.append(f"{event.path} ", style="bold")

            if event.event_type == "rename" and event.old_path:
                text.append(f"({event.old_path} → {event.path})", style="dim")

            if event.size_after is not None:
                text.append(f" [{event.size_after}B]", style="dim")

            table.add_row(text)

        panel = Panel(
            table,
            title=f"[bold]⏱ {time_str}[/bold]  [dim]frame {frame_index + 1}/{total}[/dim]",
            border_style="bright_blue",
            padding=(1, 2),
        )
        return panel

    def play(
        self,
        events: List[EventRecord],
        start_frame: int = 0,
        end_frame: Optional[int] = None,
    ) -> None:
        frames = self._group_into_frames(events)

        if not frames:
            self.console.print("[yellow]No events to replay.[/yellow]")
            return

        if end_frame is None:
            end_frame = len(frames)

        frames_to_play = frames[start_frame:end_frame]
        total = len(frames_to_play)

        with Live(console=self.console, refresh_per_second=10, screen=True) as live:
            for i, frame in enumerate(frames_to_play):
                panel = self._render_frame(frame, start_frame + i, len(frames))
                live.update(panel)

                if i < len(frames_to_play) - 1:
                    next_frame = frames_to_play[i + 1]
                    time_diff = next_frame.timestamp - frame.timestamp
                    sleep_time = max(0.01, time_diff / self.speed)
                    time.sleep(sleep_time)

        self.console.print(
            f"\n[bold green]Replay complete.[/bold green] "
            f"[dim]{total} frames played[/dim]"
        )
