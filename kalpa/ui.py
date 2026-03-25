from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import List, Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

from kalpa.storage import Database, EventRecord

try:
    from textual.app import App, ComposeResult
    from textual.containers import Container, Vertical
    from textual.reactive import reactive
    from textual.widgets import Header, Footer, ListView, ListItem, Label, Static
    from textual.screen import Screen

    TEXTUAL_AVAILABLE = True
except ImportError:
    TEXTUAL_AVAILABLE = False


EVENT_STYLES = {
    "create": ("+", "bold green"),
    "modify": ("~", "bold yellow"),
    "delete": ("-", "bold red"),
    "rename": ("→", "bold cyan"),
}


def format_event_row(event: EventRecord) -> Text:
    dt = datetime.fromtimestamp(event.timestamp)
    time_str = dt.strftime("%H:%M:%S")
    icon, style = EVENT_STYLES.get(event.event_type, ("?", "white"))

    text = Text()
    text.append(f" {icon} ", style=style)
    text.append(f"{time_str}  ", style="dim")
    text.append(f"{event.event_type:<8}", style=style)
    text.append(event.path, style="bold")

    if event.event_type == "rename" and event.old_path:
        text.append(f"  ({event.old_path} →)", style="dim")

    if event.size_after is not None:
        text.append(f"  [{event.size_after}B]", style="dim")

    return text


def render_timeline_table(
    events: List[EventRecord], title: str = "Timeline"
) -> Panel:
    table = Table.grid(padding=(0, 1))
    table.add_column()

    for event in events:
        text = format_event_row(event)
        table.add_row(text)

    return Panel(
        table,
        title=f"[bold blue]{title}[/bold blue]",
        border_style="bright_blue",
        padding=(1, 2),
    )


def render_status_panel(status: dict) -> Panel:
    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="bold")
    grid.add_column()

    grid.add_row("Watching:", status.get("path", "N/A"))
    grid.add_row("Events:", str(status.get("event_count", 0)))
    grid.add_row(
        "Storage:",
        f"{status.get('storage_bytes', 0) / 1024:.1f} KB (compressed)",
    )
    grid.add_row(
        "Since:",
        (
            datetime.fromtimestamp(status["earliest_timestamp"]).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            if status.get("earliest_timestamp")
            else "N/A"
        ),
    )
    grid.add_row("Last event:", status.get("last_event", "N/A"))

    return Panel(
        grid,
        title="[bold green]Kalpa Status[/bold green]",
        border_style="green",
        padding=(1, 2),
    )


if TEXTUAL_AVAILABLE:

    class TimelineItem(ListItem):
        def __init__(self, event: EventRecord) -> None:
            super().__init__()
            self.event = event

        def compose(self) -> ComposeResult:
            text = format_event_row(self.event)
            yield Label(text)

    class TimelineScreen(Screen):
        def __init__(self, events: List[EventRecord], title: str = "Timeline"):
            super().__init__()
            self._events = events
            self._title = title

        def compose(self) -> ComposeResult:
            yield Header()
            yield Container(
                ListView(
                    *[TimelineItem(ev) for ev in self._events],
                    id="timeline-list",
                ),
            )
            yield Footer()

        def on_list_view_selected(self, event) -> None:
            item = event.item
            if isinstance(item, TimelineItem):
                ev = item.event
                detail = (
                    f"[bold]{ev.event_type}[/bold] {ev.path}\n"
                    f"Time: {datetime.fromtimestamp(ev.timestamp).strftime('%Y-%m-%d %H:%M:%S')}\n"
                    f"Hash: {ev.file_hash or 'N/A'}"
                )
                self.notify(detail, title="Event Detail", timeout=5)

    class TimelineApp(App):
        def __init__(self, events: List[EventRecord]):
            super().__init__()
            self._events = events

        def compose(self) -> ComposeResult:
            yield Header()
            yield Container(
                ListView(
                    *[TimelineItem(ev) for ev in self._events],
                    id="timeline-list",
                ),
            )
            yield Footer()

        def on_list_view_selected(self, event) -> None:
            item = event.item
            if isinstance(item, TimelineItem):
                ev = item.event
                detail = (
                    f"[bold]{ev.event_type}[/bold] {ev.path}\n"
                    f"Time: {datetime.fromtimestamp(ev.timestamp).strftime('%Y-%m-%d %H:%M:%S')}\n"
                    f"Hash: {ev.file_hash or 'N/A'}"
                )
                self.notify(detail, title="Event Detail", timeout=5)

    def run_timeline_tui(events: List[EventRecord]) -> None:
        app = TimelineApp(events)
        app.run()

else:

    def run_timeline_tui(events: List[EventRecord]) -> None:
        console = Console()
        console.print(
            "[yellow]Textual is not installed. "
            "Install with: pip install 'kalpa[ui]'[/yellow]"
        )
        panel = render_timeline_table(events)
        console.print(panel)
