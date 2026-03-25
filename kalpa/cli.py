from __future__ import annotations

import os
import shutil
import signal
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.prompt import Confirm

from kalpa import __tagline__, __version__
from kalpa.config import KALPA_DIR_NAME, KalpaConfig, find_kalpa_dir, get_kalpa_dir
from kalpa.diff import DiffEngine
from kalpa.fork import ForkEngine
from kalpa.replay import ReplayEngine
from kalpa.snapshot import compute_hash
from kalpa.storage import Database
from kalpa.timeline import Timeline
from kalpa.ui import (
    render_status_panel,
    render_timeline_table,
    run_timeline_tui,
)
from kalpa.watcher import FolderWatcher

app = typer.Typer(
    name="kalpa",
    help=f"Kalpa — {__tagline__}",
    no_args_is_help=True,
    rich_markup_mode="rich",
)

console = Console()

_watcher_instance: Optional[FolderWatcher] = None


def _resolve_path(path_str: Optional[str]) -> Path:
    if path_str:
        return Path(path_str).resolve()
    return Path.cwd().resolve()


def _get_db_for_path(path: Path) -> Database:
    kalpa_dir = get_kalpa_dir(path)
    db_path = kalpa_dir / "kalpa.db"
    return Database(db_path)


def _get_timeline_for_path(path: Path) -> Optional[Timeline]:
    db = _get_db_for_path(path)
    folder = db.get_folder_by_path(str(path))
    if not folder:
        return None
    return Timeline(db, folder["id"])


def _parse_time_expression(expr: str) -> float:
    expr = expr.strip().lower()
    now = time.time()

    if expr == "now":
        return now

    if expr.startswith("now"):
        expr = expr[3:].strip()

    if expr.startswith("-"):
        expr = expr[1:].strip()

    parts = expr.split()
    if len(parts) == 2:
        try:
            value = float(parts[0])
            unit = parts[1]
            multipliers = {
                "second": 1,
                "seconds": 1,
                "sec": 1,
                "secs": 1,
                "minute": 60,
                "minutes": 60,
                "min": 60,
                "mins": 60,
                "hour": 3600,
                "hours": 3600,
                "hr": 3600,
                "hrs": 3600,
                "day": 86400,
                "days": 86400,
                "week": 604800,
                "weeks": 604800,
            }
            if unit in multipliers:
                return now - (value * multipliers[unit])

            # Try parsing as HH:MM:SS
            time_formats = [
                "%H:%M:%S",
                "%H:%M",
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d %H:%M",
                "%Y-%m-%d",
            ]
            for fmt in time_formats:
                try:
                    return datetime.strptime(expr, fmt).timestamp()
                except ValueError:
                    continue
        except ValueError:
            pass

    time_formats = [
        "%H:%M:%S",
        "%H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
    ]
    for fmt in time_formats:
        try:
            return datetime.strptime(expr, fmt).timestamp()
        except ValueError:
            continue

    try:
        return float(expr)
    except ValueError:
        pass

    return now


@app.callback()
def main_callback(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", "-V", help="Show version and exit"),
):
    if version:
        console.print(f"Kalpa v{__version__}")
        raise typer.Exit()


@app.command()
def watch(
    folder: Optional[str] = typer.Argument(
        None, help="Folder to watch (defaults to current directory)"
    ),
    background: bool = typer.Option(
        False, "--background", "-b", help="Run in background (daemonize)"
    ),
):
    """Start watching a folder for changes.

    Creates a .kalpa/ directory alongside the watched folder to store the
    timeline database and snapshots.
    """
    path = _resolve_path(folder)
    if not path.is_dir():
        console.print(f"[red]Error:[/red] '{path}' is not a directory")
        raise typer.Exit(code=1)

    kalpa_dir = get_kalpa_dir(path)
    if kalpa_dir.exists():
        db = _get_db_for_path(path)
        existing = db.get_folder_by_path(str(path))
        if existing:
            console.print(
                f"[yellow]Already watching:[/yellow] {path}\n"
                f"[dim]Use 'kalpa status' to view current state.[/dim]"
            )
            return
        else:
            shutil.rmtree(str(kalpa_dir))

    config = KalpaConfig.default()
    config.save(path)

    watcher = FolderWatcher(path=path, config=config)
    folder_id = watcher.start()

    watcher.take_snapshot(label="started watching")

    global _watcher_instance
    _watcher_instance = watcher

    console.print(
        f"[bold green]✓[/bold green] Watching [bold]{path}[/bold] — timeline started.\n"
        f"[dim]  .kalpa/ created at {kalpa_dir}[/dim]\n"
        f"[dim]  Folder ID: {folder_id}[/dim]"
    )

    if background:
        _daemonize(watcher)
    else:
        _run_forever(watcher)


def _daemonize(watcher: FolderWatcher) -> None:
    console.print("[dim]Running in background. Use 'kalpa stop' to stop.[/dim]")
    pid = os.fork()
    if pid > 0:
        return
    os.setsid()
    _run_forever(watcher)


def _run_forever(watcher: FolderWatcher) -> None:
    def _handle_signal(signum, frame):
        watcher.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    try:
        while watcher.is_running():
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        watcher.stop()


@app.command()
def stop(
    folder: Optional[str] = typer.Argument(
        None, help="Watched folder path (defaults to current directory)"
    ),
):
    """Stop watching a folder."""
    path = _resolve_path(folder)
    kalpa_dir = get_kalpa_dir(path)

    if not kalpa_dir.exists():
        console.print(f"[red]Error:[/red] No kalpa data found at {path}")
        raise typer.Exit(code=1)

    db = _get_db_for_path(path)
    folder_rec = db.get_folder_by_path(str(path))

    if folder_rec:
        db.deactivate_folder(folder_rec["id"])
        console.print(f"[green]Stopped watching:[/green] {path}")
    else:
        console.print(f"[yellow]Not currently watching:[/yellow] {path}")

    db.close()


@app.command()
def timeline(
    folder: Optional[str] = typer.Argument(
        None, help="Watched folder path (defaults to current directory)"
    ),
    interactive: bool = typer.Option(
        False, "--interactive", "-i", help="Open interactive TUI"
    ),
    limit: int = typer.Option(50, "--limit", "-n", help="Number of events to show"),
):
    """Show the event history for a watched folder.

    Opens a beautiful interactive terminal UI by default. Use --interactive
    to force the TUI, or pipe output for plain text.
    """
    path = _resolve_path(folder)
    db = _get_db_for_path(path)
    folder_rec = db.get_folder_by_path(str(path))

    if not folder_rec:
        console.print(
            f"[red]Error:[/red] No kalpa data found at {path}\n"
            f"  [dim]Start watching with: kalpa watch {path}[/dim]"
        )
        raise typer.Exit(code=1)

    timeline_obj = Timeline(db, folder_rec["id"])
    events = timeline_obj.get_events(limit=limit)

    if not events:
        console.print("[dim]No events recorded yet.[/dim]")
        return

    if interactive:
        run_timeline_tui(events)
    else:
        panel = render_timeline_table(events)
        console.print(panel)
        total = timeline_obj.get_event_count()
        console.print(f"\n[dim]Showing {len(events)} of {total} events[/dim]")

    db.close()


@app.command()
def replay(
    folder: Optional[str] = typer.Argument(
        None, help="Watched folder path (defaults to current directory)"
    ),
    speed: float = typer.Option(1.0, "--speed", "-s", help="Playback speed multiplier"),
    from_time: Optional[str] = typer.Option(
        None, "--from", help="Start time (e.g. '10 min ago', '2025-01-14 08:00:00')"
    ),
    to_time: Optional[str] = typer.Option(
        None, "--to", help="End time (e.g. '5 min ago', '2025-01-14 10:00:00')"
    ),
    limit: int = typer.Option(500, "--limit", "-n", help="Max events to replay"),
):
    """Animate the folder's history in the terminal.

    Files appear, grow, shrink, and delete in a cinematic playback.
    """
    path = _resolve_path(folder)
    db = _get_db_for_path(path)
    folder_rec = db.get_folder_by_path(str(path))

    if not folder_rec:
        console.print(
            f"[red]Error:[/red] No kalpa data found at {path}\n"
            f"  [dim]Start watching with: kalpa watch {path}[/dim]"
        )
        raise typer.Exit(code=1)

    start_ts = _parse_time_expression(from_time) if from_time else None
    end_ts = _parse_time_expression(to_time) if to_time else None

    events = db.query_events(
        folder_id=folder_rec["id"],
        start_time=start_ts,
        end_time=end_ts,
        limit=limit,
    )

    if not events:
        console.print("[yellow]No events found in the specified time range.[/yellow]")
        return

    engine = ReplayEngine(
        db=db,
        folder_id=folder_rec["id"],
        speed=speed,
    )
    engine.play(events)

    db.close()


@app.command()
def undo(
    folder: Optional[str] = typer.Argument(
        None, help="Watched folder path (defaults to current directory)"
    ),
    steps: int = typer.Option(1, "--steps", "-n", help="Number of destructive events to undo"),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would be restored without restoring"
    ),
):
    """Undo the last destructive change(s).

    No prompts by default. Fast. Safe. The "holy shit" safety net.
    """
    path = _resolve_path(folder)
    db = _get_db_for_path(path)
    folder_rec = db.get_folder_by_path(str(path))

    if not folder_rec:
        console.print(
            f"[red]Error:[/red] No kalpa data found at {path}\n"
            f"  [dim]Start watching with: kalpa watch {path}[/dim]"
        )
        raise typer.Exit(code=1)

    destructive_events = db.get_destructive_events(
        folder_id=folder_rec["id"], steps=steps
    )

    if not destructive_events:
        console.print("[dim]No destructive events to undo.[/dim]")
        return

    restored_count = 0
    restored_size = 0
    restored_files = []

    for event in destructive_events:
        if event.event_type == "delete" or event.event_type == "modify":
            target_path = path / event.path
            if dry_run:
                restored_files.append(event.path)
                restored_count += 1
                continue

            if event.event_type == "delete":
                timeline_obj = Timeline(db, folder_rec["id"])
                content = timeline_obj.reconstruct_file_at_time(
                    event.path, event.timestamp - 0.001
                )
                if content is not None:
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    target_path.write_bytes(content)
                    restored_files.append(event.path)
                    restored_count += 1
                    restored_size += len(content)

    if dry_run:
        console.print(
            f"[bold]Would restore {restored_count} file(s):[/bold]"
        )
        for f in restored_files:
            console.print(f"  [green]+[/green] {f}")
        return

    if restored_count > 0:
        console.print(
            f"[bold green]Restored:[/bold green] {restored_count} file(s), "
            f"{restored_size / 1024:.1f} KB"
        )
        for f in restored_files:
            console.print(f"  [green]↩[/green] {f}")
    else:
        console.print("[yellow]Nothing to restore.[/yellow]")

    db.close()


@app.command()
def fork(
    folder: Optional[str] = typer.Argument(
        None, help="Watched folder path (defaults to current directory)"
    ),
    from_time: str = typer.Option(
        ..., "--from", help="Timestamp or relative time (e.g. '2 hours ago')"
    ),
    output: Optional[str] = typer.Option(
        None, "--output", "-o", help="Output directory for the fork"
    ),
):
    """Create a parallel folder at a past state.

    The fork is a real, usable copy of the folder as it existed at the
    specified moment — not a symlink trick, but a proper materialized snapshot.
    """
    path = _resolve_path(folder)
    db = _get_db_for_path(path)
    folder_rec = db.get_folder_by_path(str(path))

    if not folder_rec:
        console.print(
            f"[red]Error:[/red] No kalpa data found at {path}\n"
            f"  [dim]Start watching with: kalpa watch {path}[/dim]"
        )
        raise typer.Exit(code=1)

    target_time = _parse_time_expression(from_time)

    timeline_obj = Timeline(db, folder_rec["id"])
    fork_engine = ForkEngine(timeline_obj)

    output_dir = Path(output) if output else path

    try:
        fork_path = fork_engine.fork_folder(
            target_time=target_time,
            output_path=output_dir,
        )
        console.print(
            f"[bold green]✓[/bold green] Forked: [bold]{path}[/bold] → [bold]{fork_path}[/bold]"
        )
    except Exception as e:
        console.print(f"[red]Error creating fork:[/red] {e}")
        raise typer.Exit(code=1)

    db.close()


@app.command()
def diff(
    folder: Optional[str] = typer.Argument(
        None, help="Watched folder path (defaults to current directory)"
    ),
    time_a: str = typer.Argument(
        ..., help="First timestamp (e.g. 'yesterday 6pm')"
    ),
    time_b: str = typer.Argument(
        ..., help="Second timestamp (e.g. 'today 9am')"
    ),
    max_files: int = typer.Option(
        20, "--max-files", "-m", help="Maximum number of files to show"
    ),
):
    """Show a rich terminal diff between two points in time across all files."""
    path = _resolve_path(folder)
    db = _get_db_for_path(path)
    folder_rec = db.get_folder_by_path(str(path))

    if not folder_rec:
        console.print(
            f"[red]Error:[/red] No kalpa data found at {path}\n"
            f"  [dim]Start watching with: kalpa watch {path}[/dim]"
        )
        raise typer.Exit(code=1)

    ts_a = _parse_time_expression(time_a)
    ts_b = _parse_time_expression(time_b)

    timeline_obj = Timeline(db, folder_rec["id"])
    diff_engine = DiffEngine(timeline_obj)

    diffs = diff_engine.diff_timestamps(ts_a, ts_b)

    if not diffs:
        console.print("[dim]No differences found between the two timestamps.[/dim]")
    else:
        console.print(
            f"[bold]Diff:[/bold] {time_a} [dim]→[/dim] {time_b}\n"
        )
        diff_engine.render_diff(diffs, max_files=max_files)

    db.close()


@app.command()
def status(
    folder: Optional[str] = typer.Argument(
        None, help="Watched folder path (defaults to current directory)"
    ),
):
    """Show current watch state, storage size, event count, and more."""
    path = _resolve_path(folder)
    kalpa_dir = get_kalpa_dir(path)

    if not kalpa_dir.exists():
        console.print(
            f"[yellow]Not watching:[/yellow] {path}\n"
            f"  [dim]Start with: kalpa watch {path}[/dim]"
        )
        return

    db = _get_db_for_path(path)
    folder_rec = db.get_folder_by_path(str(path))

    if not folder_rec:
        console.print(
            f"[yellow]Not watching:[/yellow] {path}\n"
            f"  [dim]Start with: kalpa watch {path}[/dim]"
        )
        return

    watcher = FolderWatcher(path=path, db=db)
    status_data = watcher.get_status()
    panel = render_status_panel(status_data)
    console.print(panel)

    db.close()


@app.command()
def snapshot(
    folder: Optional[str] = typer.Argument(
        None, help="Watched folder path (defaults to current directory)"
    ),
    label: Optional[str] = typer.Option(
        None, "--label", "-l", help="Label for the snapshot"
    ),
):
    """Take a manual full snapshot of the current folder state."""
    path = _resolve_path(folder)

    db = _get_db_for_path(path)
    folder_rec = db.get_folder_by_path(str(path))

    if not folder_rec:
        console.print(
            f"[red]Error:[/red] No kalpa data found at {path}\n"
            f"  [dim]Start watching with: kalpa watch {path}[/dim]"
        )
        raise typer.Exit(code=1)

    from kalpa.snapshot import SnapshotEngine
    engine = SnapshotEngine()
    manifest = engine.build_file_manifest(path)
    snapshot_id = db.insert_snapshot(
        folder_id=folder_rec["id"],
        timestamp=datetime.utcnow().timestamp(),
        manifest=manifest,
        label=label,
    )

    file_count = len(manifest)
    console.print(
        f"[bold green]✓[/bold green] Snapshot #{snapshot_id} created: "
        f"{file_count} files"
    )
    if label:
        console.print(f"  Label: {label}")

    db.close()


if __name__ == "__main__":
    app()
