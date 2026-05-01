# kalpa

> Time moves in cycles. So does your filesystem.

[![CI](https://github.com/swadhinbiswas/kalpa/actions/workflows/ci.yml/badge.svg)](https://github.com/swadhinbiswas/kalpa/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/kalpa)](https://pypi.org/project/kalpa/)
[![Python](https://img.shields.io/pypi/pyversions/kalpa)](https://pypi.org/project/kalpa/)
[![License](https://img.shields.io/pypi/l/kalpa)](LICENSE)
[![Code style](https://img.shields.io/badge/code%20style-ruff-000000)](https://github.com/astral-sh/ruff)

Kalpa is a **local-first filesystem timeline engine** for developers, writers, and
researchers. Watch any folder. Undo anything. Replay your project's history.
Fork old states into parallel workspaces.

No Git. No cloud. No config. Just time.

## Viral Demo (60 seconds)

```bash
# Start watching
kalpa watch ./my-project

# Do some work (or simulate it)
echo "auth logic" >> src/auth.py
rm -rf src/

# The "holy shit" moment — restore instantly
kalpa undo
# → Restored: src/ (1 file) from 4 seconds ago.

# The "wow" moment — watch it grow
kalpa replay --speed 3x

# The mind-bending moment — fork the past
kalpa fork --from "1 hour ago"
ls
# → my-project/    my-project_fork_1023/
```

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
# Start watching a folder (foreground)
kalpa watch ./my-project

# Or run in background
kalpa watch ./my-project --background

# View the timeline
kalpa timeline

# Undo the last destructive change
kalpa undo

# Watch your project grow like a timelapse
kalpa replay --speed 3x

# Fork the folder as it was 2 hours ago
kalpa fork --from "2 hours ago"

# Diff between two points in time
kalpa diff "2 hours ago" "now"

# Check watch status
kalpa status

# Create a manual snapshot
kalpa snapshot --label "checkpoint"
```

## Commands

| Command | Description |
|---|---|
| `kalpa watch <folder>` | Start tracking filesystem changes |
| `kalpa stop <folder>` | Stop watching a folder |
| `kalpa timeline` | View event history |
| `kalpa replay` | Animated history playback |
| `kalpa undo` | Restore last destructive change |
| `kalpa fork --from <time>` | Create parallel folder at past state |
| `kalpa diff <timeA> <timeB>` | Cross-time folder diff |
| `kalpa status` | Show watch state and stats |
| `kalpa snapshot` | Take manual full snapshot |

## Time Expressions

All time arguments support natural language:

| Expression | Example |
|---|---|
| Relative | `"5 minutes ago"`, `"2 hours ago"`, `"1 day ago"` |
| Future | `"in 1 hour"` |
| Named | `"now"`, `"today"`, `"yesterday"` |
| With clock | `"yesterday 6pm"`, `"today 9am"` |
| Absolute | `"2025-01-14 08:00:00"`, `"2025-01-14"` |

## Why Kalpa?

Because `rm -rf` shouldn't be permanent. Because watching a project grow from
nothing is magical. Because sometimes you need to go back — not to a commit,
but to a moment.

## Architecture

```
kalpa/
├── cli/              # typer-based CLI (9 commands)
├── watcher/          # watchdog file monitoring
├── snapshot_engine/  # incremental delta snapshots (zstd)
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
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
pytest tests/
```

## License

MIT — see [LICENSE](LICENSE).
