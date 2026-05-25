<p align="center">
  <img src="docs/kalpa-logo.svg" width="480" alt="kalpa">
</p>

<p align="center">
  <a href="https://github.com/swadhinbiswas/kalpa/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/swadhinbiswas/kalpa/ci.yml?branch=main&logo=github" alt="CI"></a>
  <a href="https://pypi.org/project/kalpa/"><img src="https://img.shields.io/pypi/v/kalpa?logo=pypi" alt="PyPI"></a>
  <a href="https://pypi.org/project/kalpa/"><img src="https://img.shields.io/pypi/pyversions/kalpa?logo=python" alt="Python"></a>
  <a href="LICENSE"><img src="https://img.shields.io/pypi/l/kalpa" alt="License"></a>
</p>

<p align="center">Watch any folder. Track every change. Rewind or fork the past.</p>

<p align="center">
  <img src="docs/kalpa-demo.svg" width="720" alt="Kalpa demo">
</p>

---

## What it does

Kalpa watches a directory and logs every filesystem event -- creates, edits, renames, deletes -- into a local SQLite database. Think of it as a lightweight, git-agnostic time machine for any folder on your machine.

You point it at a directory, it starts watching. Everything is stored locally in `.kalpa/` alongside your files. No remote server, no staging area, no commits. Just a rolling log of what changed and when.

**Why not just use git?** Git tracks intentional snapshots you choose to commit. Kalpa tracks everything that happens to a directory, whether you meant to or not. It's useful for folders that aren't (or shouldn't be) git repos -- config directories, data folders, scratch work, anything you might accidentally `rm -rf`.

## When it's useful

- You deleted a file and didn't notice until an hour later
- You want to see what a directory looked like yesterday afternoon
- You're iterating on something and want to fork the state at a checkpoint
- You need to diff a folder between two arbitrary points in time
- You want an undo button for filesystem operations without version control overhead

## Install

```bash
pip install kalpa
```

With optional TUI (terminal UI):

```bash
pip install "kalpa[ui]"
```

Requires Python 3.12+.

## Quick start

```bash
# Start watching a directory
kalpa watch ./my-project --background

# Make some changes, break something, then undo
rm -rf src/
kalpa undo              # restores what was just destroyed

# See what happened
kalpa timeline

# Replay the history at 3x speed
kalpa replay --speed 3x

# Fork the directory to its state from an hour ago
kalpa fork --from "1 hour ago"

# Diff between two points in time
kalpa diff "2 hours ago" "now"

# Take a named snapshot
kalpa snapshot --label "before-refactor"

# Stop watching
kalpa stop ./my-project
```

## Commands

| Command | What it does |
|---|---|
| `kalpa watch <folder>` | Start tracking filesystem changes |
| `kalpa stop <folder>` | Stop watching a folder |
| `kalpa status` | Show watch state and stats |
| `kalpa timeline` | View event history |
| `kalpa replay` | Animated history playback |
| `kalpa undo` | Restore last destructive change |
| `kalpa fork --from <time>` | Create a copy of the folder at a past state |
| `kalpa diff <t1> <t2>` | Compare the folder between two points in time |
| `kalpa snapshot` | Take a manual full snapshot |

## Time expressions

All time arguments accept natural language:

| Format | Examples |
|---|---|
| Relative | `"5 minutes ago"`, `"2 hours ago"`, `"1 day ago"` |
| Named | `"now"`, `"today"`, `"yesterday"` |
| With clock | `"yesterday 6pm"`, `"today 9am"` |
| Absolute | `"2026-01-14 08:00:00"`, `"2026-01-14"` |

## How it works

Kalpa uses [watchdog](https://github.com/gorakhargosh/watchdog) to monitor filesystem events in real time. Each event (create, modify, rename, delete) is logged to a SQLite database in `.kalpa/` inside the watched directory. File contents are stored as incremental deltas compressed with [zstandard](https://github.com/indygreg/python-zstandard), so storage stays small even for active directories.

The architecture is flat -- no daemon processes to manage, no background servers. The `--background` flag just forks the watcher into the background with a PID file.

```
kalpa/
├── cli.py            # typer-based CLI
├── watcher.py        # watchdog file monitoring
├── snapshot.py       # incremental delta snapshots
├── storage.py        # SQLite + zstd compression
├── replay.py         # timeline reconstruction
├── fork.py           # folder materialization
├── diff.py           # cross-time comparison
├── timeline.py       # event query layer
├── config.py         # settings management
└── ui.py             # Textual TUI + rich output
```

## Development

```bash
git clone https://github.com/swadhinbiswas/kalpa
cd kalpa
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
pytest tests/
```

106 tests across all modules. CI runs on GitHub Actions (Ubuntu, macOS, Windows × Python 3.12, 3.13).

## License

MIT. See [LICENSE](LICENSE).
