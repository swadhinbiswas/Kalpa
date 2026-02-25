# kalpa

> Time moves in cycles. So does your filesystem.

Kalpa is a **local-first filesystem timeline engine** for developers, writers, and
researchers. Watch any folder. Undo anything. Replay your project's history.
Fork old states into parallel workspaces.

No Git. No cloud. No config. Just time.

## Install

```bash
pip install kalpa
```

Or with TUI support:

```bash
pip install "kalpa[ui]"
```

## Quickstart

```bash
# Start watching a folder
kalpa watch ./my-project

# View the timeline
kalpa timeline

# Undo the last destructive change
kalpa undo

# Watch your project grow like a timelapse
kalpa replay --speed 3x

# Fork the folder as it was 2 hours ago
kalpa fork --from "2 hours ago"
```

## Commands

| Command | Description |
|---|---|
| `kalpa watch <folder>` | Start tracking filesystem changes |
| `kalpa timeline` | View event history (interactive TUI) |
| `kalpa replay` | Animated history playback |
| `kalpa undo` | Restore last destructive change |
| `kalpa fork --from <time>` | Create parallel folder at past state |
| `kalpa diff <timeA> <timeB>` | Cross-time folder diff |
| `kalpa status` | Show watch state and stats |
| `kalpa snapshot` | Take manual full snapshot |

## Why Kalpa?

Because `rm -rf` shouldn't be permanent. Because watching a project grow from
nothing is magical. Because sometimes you need to go back — not to a commit,
but to a moment.

## Architecture

```
kalpa/
├── cli/              # typer-based CLI
├── watcher/          # watchdog file monitoring
├── snapshot_engine/  # incremental delta snapshots
├── storage/          # SQLite + zstd compression
├── replay_engine/    # timeline reconstruction
├── fork_engine/      # folder materialization
├── diff_engine/      # cross-time comparison
├── timeline/         # event query layer
└── ui/               # Textual TUI + rich output
```

## Development

```bash
git clone https://github.com/swadhinbiswas/kalpa
cd kalpa
pip install -e ".[dev]"
pytest tests/
```

## License

MIT — see [LICENSE](LICENSE).
