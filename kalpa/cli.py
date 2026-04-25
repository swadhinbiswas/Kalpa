from __future__ import annotations

import multiprocessing
import os
import re
import shutil
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from kalpa import __tagline__, __version__
from kalpa.config import KalpaConfig, get_kalpa_dir
from kalpa.diff import DiffEngine
from kalpa.fork import ForkEngine
from kalpa.replay import ReplayEngine
from kalpa.snapshot import SnapshotEngine
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

ACTIVE_WATCHERS: dict[str, FolderWatcher] = {}

_TIME_MULTIPLIERS = {
    "second": 1, "seconds": 1, "sec": 1, "secs": 1,
    "minute": 60, "minutes": 60, "min": 60, "mins": 60,
    "hour": 3600, "hours": 3600, "hr": 3600, "hrs": 3600,
    "day": 86400, "days": 86400,
    "week": 604800, "weeks": 604800,
}

_TIME_FORMATS = [
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
    "%H:%M:%S",
    "%H:%M",
]


def _resolve_path(folder: Optional[str]) -> Path:
    if folder:
        return Path(folder).resolve()
    return Path.cwd().resolve()


def _get_db_for_path(path: Path) -> Database:
    kalpa_dir = get_kalpa_dir(path)
    return Database(kalpa_dir / "kalpa.db")


def _get_folder_or_exit(db: Database, path: Path) -> dict:
    folder = db.get_folder_by_path(str(path))
    if not folder:
        console.print(
            f"[red]Error:[/red] No kalpa data found at {path}\n"
            f"  [dim]Start watching with: kalpa watch {path}[/dim]"
        )
        raise typer.Exit(code=1)
    return folder


def _parse_time_expression(expr: str) -> Optional[float]:
    expr = expr.strip().lower()
    now = time.time()

    if expr == "now":
        return now

    today_midnight = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    ).timestamp()

    if expr == "today":
        return today_midnight

    if expr == "yesterday":
        return today_midnight - 86400

    ago_match = re.match(
        r"^(-?\d+(?:\.\d+)?)\s+(second|seconds|sec|secs|minute|minutes|min|mins|hour|hours|hr|hrs|day|days|week|weeks)\s+(ago|before)$",
        expr,
    )
    if ago_match:
        value = float(ago_match.group(1))
        unit = ago_match.group(2)
        return now - (value * _TIME_MULTIPLIERS[unit])

    in_match = re.match(
        r"^(in)\s+(-?\d+(?:\.\d+)?)\s+(second|seconds|sec|secs|minute|minutes|min|mins|hour|hours|hr|hrs|day|days|week|weeks)$",
        expr,
    )
    if in_match:
        value = float(in_match.group(2))
        unit = in_match.group(3)
        return now + (value * _TIME_MULTIPLIERS[unit])

    def _parse_time_with_ampm(prefix: str, time_part: str) -> float:
        base_ts = today_midnight if prefix == "today" else today_midnight - 86400
        time_part = time_part.strip()
        ampm = ""
        for suffix in ("am", "pm"):
            if time_part.endswith(suffix):
                ampm = suffix
                time_part = time_part[:-len(suffix)].strip()
                break

        parts = time_part.split(":")
        h = int(parts[0]) if parts else 0
        m = int(parts[1]) if len(parts) > 1 else 0
        s = int(parts[2]) if len(parts) > 2 else 0

        if ampm == "pm" and h < 12:
            h += 12
        elif ampm == "am" and h == 12:
            h = 0
        return base_ts + (h * 3600) + (m * 60) + s

    yesterday_tm = re.match(r"^yesterday\s+(.+)", expr)
    if yesterday_tm:
        return _parse_time_with_ampm("yesterday", yesterday_tm.group(1))

    today_tm = re.match(r"^today\s+(.+)", expr)
    if today_tm:
        return _parse_time_with_ampm("today", today_tm.group(1))

    parts = expr.split()
    if len(parts) == 2:
        try:
            value = float(parts[0])
            unit = parts[1]
            if unit in _TIME_MULTIPLIERS:
                prefix = parts[0][0] if parts[0] and parts[0][0] in ("+", "-") else "-"
                abs_value = abs(value)
                offset = abs_value * _TIME_MULTIPLIERS[unit]
                return now - offset if prefix == "-" else now + offset
        except ValueError:
            pass

    for fmt in _TIME_FORMATS:
        try:
            return datetime.strptime(expr, fmt).timestamp()
        except ValueError:
            continue

    try:
        return float(expr)
    except ValueError:
        pass

    return None


def _version_callback(value: bool):
    if value:
        console.print(f"Kalpa v{__version__}")
        raise typer.Exit()

@app.callback()
def main_callback(
    ctx: typer.Context,
    version: bool = typer.Option(
        False, "--version", "-V", help="Show version and exit",
        callback=_version_callback, is_eager=True,
    ),
):
    pass


def _run_watcher_forever(watcher: FolderWatcher) -> None:
    def _handle_signal(signum, frame):
        watcher.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    try:
        while watcher.is_running():
            watcher.check_snapshot_trigger()
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        watcher.stop()


def _write_pid_file(kalpa_dir: Path) -> None:
    pid_file = kalpa_dir / "watcher.pid"
    pid_file.write_text(str(os.getpid()))


def _read_pid_file(kalpa_dir: Path) -> Optional[int]:
    pid_file = kalpa_dir / "watcher.pid"
    if pid_file.exists():
        try:
            return int(pid_file.read_text().strip())
        except (ValueError, OSError):
            return None
    return None


def _remove_pid_file(kalpa_dir: Path) -> None:
    pid_file = kalpa_dir / "watcher.pid"
    if pid_file.exists():
        pid_file.unlink()


def _run_watcher_in_child(path_str: str) -> None:
    path = Path(path_str)
    config = KalpaConfig.load(path)
    watcher = FolderWatcher(path=path, config=config)
    watcher.start()
    _run_watcher_forever(watcher)


@app.command()
def watch(
    folder: Optional[str] = typer.Argument(
        None, help="Folder to watch (defaults to current directory)"
    ),
    background: bool = typer.Option(
        False, "--background", "-b", help="Run in background"
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
        existing_pid = _read_pid_file(kalpa_dir)
        if existing_pid:
            try:
                os.kill(existing_pid, 0)
                console.print(
                    f"[yellow]Already watching:[/yellow] {path}\n"
                    f"[dim]Watcher PID: {existing_pid}[/dim]"
                )
                return
            except OSError:
                _remove_pid_file(kalpa_dir)

        db = _get_db_for_path(path)
        existing = db.get_folder_by_path(str(path))
        if existing:
            console.print(
                f"[yellow]Re-attaching to existing watch:[/yellow] {path}"
            )
        else:
            shutil.rmtree(str(kalpa_dir))

    config = KalpaConfig.default()
    config.save(path)

    watcher = FolderWatcher(path=path, config=config)
    folder_id = watcher.start()
    watcher.take_snapshot(label="started watching")

    ACTIVE_WATCHERS[str(path)] = watcher

    console.print(
        f"[bold green]✓[/bold green] Watching [bold]{path}[/bold] — timeline started.\n"
        f"[dim]  .kalpa/ created at {kalpa_dir}[/dim]\n"
        f"[dim]  Folder ID: {folder_id}[/dim]"
    )

    if background:
        watcher.stop()
        _write_pid_file(kalpa_dir)
        proc = multiprocessing.Process(
            target=_run_watcher_in_child, args=(str(path),), daemon=False
        )
        proc.start()
        console.print(
            f"[dim]Background watcher PID: {proc.pid}[/dim]\n"
            f"[dim]Use 'kalpa stop' to stop.[/dim]"
        )
    else:
        _run_watcher_forever(watcher)


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

    pid = _read_pid_file(kalpa_dir)
    if pid:
        try:
            os.kill(pid, signal.SIGTERM)
            _remove_pid_file(kalpa_dir)
        except ProcessLookupError:
            _remove_pid_file(kalpa_dir)
        except OSError:
            pass

    watcher = ACTIVE_WATCHERS.pop(str(path), None)
    if watcher:
        watcher.stop()

    db = _get_db_for_path(path)
    folder_rec = db.get_folder_by_path(str(path))
    if folder_rec:
        db.deactivate_folder(folder_rec["id"])
        console.print(f"[green]Stopped watching:[/green] {path}")
    else:
        console.print(f"[yellow]No active watch found at:[/yellow] {path}")

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
    folder_rec = _get_folder_or_exit(db, path)

    timeline_obj = Timeline(db, folder_rec["id"])
    events = timeline_obj.get_events(limit=limit)

    if not events:
        console.print("[dim]No events recorded yet.[/dim]")
        db.close()
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
    folder_rec = _get_folder_or_exit(db, path)

    start_ts = _parse_time_expression(from_time) if from_time else None
    end_ts = _parse_time_expression(to_time) if to_time else None

    if from_time and start_ts is None:
        console.print(f"[yellow]Warning:[/yellow] Could not parse --from '{from_time}', ignoring.")
    if to_time and end_ts is None:
        console.print(f"[yellow]Warning:[/yellow] Could not parse --to '{to_time}', ignoring.")

    events = db.query_events(
        folder_id=folder_rec["id"],
        start_time=start_ts,
        end_time=end_ts,
        limit=limit,
    )

    if not events:
        console.print("[yellow]No events found in the specified time range.[/yellow]")
        db.close()
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
    folder_rec = _get_folder_or_exit(db, path)

    destructive_events = db.get_destructive_events(
        folder_id=folder_rec["id"], steps=steps
    )

    if not destructive_events:
        console.print("[dim]No destructive events to undo.[/dim]")
        db.close()
        return

    restored_count = 0
    restored_size = 0
    restored_files = []

    timeline_obj = Timeline(db, folder_rec["id"])

    for event in destructive_events:
        if event.event_type not in ("delete", "modify", "rename"):
            continue

        should_restore = False
        restore_path_str = ""

        if event.event_type == "delete":
            restore_path_str = event.path
            should_restore = True
        elif event.event_type == "modify":
            restore_path_str = event.path
            should_restore = True
        elif event.event_type == "rename":
            restore_path_str = event.old_path or event.path
            should_restore = True

        if not should_restore:
            continue

        target_path = (path / restore_path_str).resolve()
        watched_path_resolved = path.resolve()
        if not str(target_path).startswith(str(watched_path_resolved)):
            console.print(
                f"[red]Security warning:[/red] Skipping path outside watched folder: "
                f"{restore_path_str}"
            )
            continue

        if dry_run:
            restored_files.append(restore_path_str)
            restored_count += 1
            continue

        event_id = event.id or 0
        content = timeline_obj.reconstruct_file_at_time(
            restore_path_str, event.timestamp, before_event_id=event_id
        )
        if content is not None:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_bytes(content)
            restored_files.append(restore_path_str)
            restored_count += 1
            restored_size += len(content)

    if dry_run:
        console.print(f"[bold]Would restore {restored_count} file(s):[/bold]")
        for f in restored_files:
            console.print(f"  [green]+[/green] {f}")
        db.close()
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
    folder_rec = _get_folder_or_exit(db, path)

    target_time = _parse_time_expression(from_time)
    if target_time is None:
        console.print(f"[red]Error:[/red] Could not parse time expression: '{from_time}'")
        raise typer.Exit(code=1)

    timeline_obj = Timeline(db, folder_rec["id"])
    fork_engine = ForkEngine(timeline_obj)

    if output:
        output_dir = Path(output).resolve()
    else:
        timestamp_suffix = datetime.fromtimestamp(target_time).strftime("%Y%m%d_%H%M%S")
        output_dir = path.parent / f"{path.name}_fork_{timestamp_suffix}"

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
    time_a: str = typer.Argument(
        ..., help="First timestamp (e.g. '2 hours ago', '2025-01-14 08:00')"
    ),
    time_b: str = typer.Argument(
        ..., help="Second timestamp (e.g. 'now', '2025-01-14 10:00')"
    ),
    folder: Optional[str] = typer.Option(
        None, "--folder", "-f", help="Watched folder path (defaults to current directory)"
    ),
    max_files: int = typer.Option(
        20, "--max-files", "-m", help="Maximum number of files to show"
    ),
):
    """Show a rich terminal diff between two points in time across all files."""
    path = _resolve_path(folder)
    db = _get_db_for_path(path)
    folder_rec = _get_folder_or_exit(db, path)

    ts_a = _parse_time_expression(time_a)
    ts_b = _parse_time_expression(time_b)

    if ts_a is None:
        console.print(f"[red]Error:[/red] Could not parse time_a: '{time_a}'")
        raise typer.Exit(code=1)
    if ts_b is None:
        console.print(f"[red]Error:[/red] Could not parse time_b: '{time_b}'")
        raise typer.Exit(code=1)

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
            f"[yellow]No active watch:[/yellow] {path}\n"
            f"  [dim]Start with: kalpa watch {path}[/dim]"
        )
        db.close()
        return

    stats = db.get_storage_stats(folder_rec["id"])
    pid = _read_pid_file(kalpa_dir)
    status_data = {
        "path": str(path),
        "folder_id": folder_rec["id"],
        "watching": pid is not None,
        "pid": pid,
        "event_count": stats["event_count"],
        "storage_bytes": stats["delta_storage_bytes"],
        "earliest_timestamp": stats["earliest_timestamp"],
        "last_event": stats["last_event_str"],
    }
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
    folder_rec = _get_folder_or_exit(db, path)

    engine = SnapshotEngine()
    manifest = engine.build_file_manifest(path)
    snapshot_id = db.insert_snapshot(
        folder_id=folder_rec["id"],
        timestamp=datetime.now(timezone.utc).timestamp(),
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
