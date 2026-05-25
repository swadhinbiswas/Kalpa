<p align="center">
  <img src="docs/kalpa-logo.svg" width="600" alt="kalpa">
</p>

<p align="center">
  <a href="https://github.com/swadhinbiswas/kalpa/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/swadhinbiswas/kalpa/ci.yml?branch=main&logo=github" alt="CI"></a>
  <a href="https://pypi.org/project/kalpa/"><img src="https://img.shields.io/pypi/v/kalpa?logo=pypi" alt="PyPI"></a>
  <a href="https://pypi.org/project/kalpa/"><img src="https://img.shields.io/pypi/pyversions/kalpa?logo=python" alt="Python"></a>
  <a href="LICENSE"><img src="https://img.shields.io/pypi/l/kalpa" alt="License"></a>
  <a href="https://github.com/astral-sh/ruff"><img src="https://img.shields.io/badge/code%20style-ruff-000000" alt="Ruff"></a>
</p>

<p align="center">Watch any folder, track every change, rewind or fork the past.</p>

<br>

<p align="center">
  <img src="docs/kalpa-demo.svg" width="720" alt="Kalpa Demo">
</p>

<br>

## What is this?

Kalpa watches a folder and records everything that happens — file creates,
edits, renames, deletes. Later you can:

- **Undo** accidental `rm -rf` by restoring files from seconds ago
- **Replay** change history like a timelapse video
- **Fork** the folder as it was at any point in time
- **Diff** the folder between two moments
- **Snapshot** checkpoints you can name

Everything stays local in a compressed SQLite database inside `.kalpa/`.
No Git repo, no cloud, no setup.

## Quick demo

```bash
# Watch a project
kalpa watch ./my-project --background

# Make some changes
echo "def authenticate(): pass" > src/auth.py
echo "server started" >> src/main.py

# Accidentally delete everything
rm -rf src/

# Restore it
kalpa undo
# → Restored: 1 file (0.0 KB)
# → src/auth.py

# See what happened
kalpa timeline
# → +19:15:11  create  src/auth.py · 30B
# → ~19:15:12  modify  src/main.py · 45B
# → -19:15:14  delete  src/auth.py

# Watch the project grow
kalpa replay --speed 3x

# Fork the past
kalpa fork --from "1 hour ago"
ls
# → my-project/    my-project_fork_1023/
```

## Install

```bash
pip install kalpa
```

With TUI support:

```bash
pip install "kalpa[ui]"
```

## Usage

```bash
# Start watching
kalpa watch ./my-project

# View timeline
kalpa timeline

# Restore last destructive change
kalpa undo

# Timelapse playback
kalpa replay --speed 3x

# Fork at a past state
kalpa fork --from "2 hours ago"

# Diff two points in time
kalpa diff "2 hours ago" "now"

# Show status
kalpa status

# Manual snapshot
kalpa snapshot --label "checkpoint"

# Stop watching
kalpa stop ./my-project
```

## Commands

| Command | Description |
|---|---|
| `kalpa watch <folder>` | Start tracking filesystem changes |
| `kalpa stop <folder>` | Stop watching a folder |
| `kalpa status` | Show watch state and stats |
| `kalpa timeline` | View event history |
| `kalpa replay` | Animated history playback |
| `kalpa undo` | Restore last destructive change |
| `kalpa fork --from <time>` | Create parallel folder at past state |
| `kalpa diff <timeA> <timeB>` | Cross-time folder diff |
| `kalpa snapshot` | Take manual full snapshot |

## Time expressions

All time arguments accept natural language:

| Expression | Example |
|---|---|
| Relative | `"5 minutes ago"`, `"2 hours ago"`, `"1 day ago"` |
| Future | `"in 1 hour"` |
| Named | `"now"`, `"today"`, `"yesterday"` |
| With clock | `"yesterday 6pm"`, `"today 9am"` |
| Absolute | `"2025-01-14 08:00:00"`, `"2025-01-14"` |

## Architecture

```
kalpa/
├── cli/              typer-based CLI (9 commands)
├── watcher/          watchdog file monitoring
├── snapshot_engine/  incremental delta snapshots (zstd)
├── storage/          SQLite + zstd compression
├── replay_engine/    timeline reconstruction
├── fork_engine/      folder materialization
├── diff_engine/      cross-time comparison
├── timeline/         event query layer
└── ui/               Textual TUI + rich output
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
