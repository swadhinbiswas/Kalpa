# Changelog

## 0.1.0 (2026-05-25)

- `kalpa watch` — file system watcher with SQLite storage
- `kalpa timeline` — event history viewer
- `kalpa replay` — animated history playback
- `kalpa undo` — restore destructive changes
- `kalpa fork` — materialize past folder state
- `kalpa diff` — cross-time folder comparison
- `kalpa status` — watch state and statistics
- `kalpa snapshot` — manual full snapshots
- Incremental delta snapshots with zstd compression
- Rich terminal UI with Textual TUI
- Cross-platform background daemon mode
- PID file tracking for background watchers
- Natural language time parsing ("2 hours ago", "yesterday 6pm")
- Path traversal protection in all file operations
- 106 tests across all modules
- GitHub Actions CI (3 OS × 2 Python versions)
- Pre-commit hooks (ruff, mypy, bandit)
- Security policy and contributing guide
