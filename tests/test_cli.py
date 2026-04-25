from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path

import pytest
from typer.testing import CliRunner

from kalpa.cli import app, _parse_time_expression

runner = CliRunner()


class TestParseTimeExpression:
    def test_now(self):
        result = _parse_time_expression("now")
        assert result is not None
        assert abs(result - time.time()) < 0.1

    def test_seconds_ago(self):
        result = _parse_time_expression("30 seconds ago")
        assert result is not None
        assert abs(result - (time.time() - 30)) < 0.1

    def test_minutes_ago(self):
        result = _parse_time_expression("5 minutes ago")
        assert result is not None
        assert abs(result - (time.time() - 300)) < 0.1

    def test_hours_ago(self):
        result = _parse_time_expression("2 hours ago")
        assert result is not None
        assert abs(result - (time.time() - 7200)) < 0.1

    def test_days_ago(self):
        result = _parse_time_expression("1 day ago")
        assert result is not None
        assert abs(result - (time.time() - 86400)) < 0.1

    def test_weeks_ago(self):
        result = _parse_time_expression("1 week ago")
        assert result is not None
        assert abs(result - (time.time() - 604800)) < 0.1

    def test_ago_variants(self):
        result = _parse_time_expression("10 mins ago")
        assert result is not None
        assert abs(result - (time.time() - 600)) < 1.0

        result = _parse_time_expression("3 hrs ago")
        assert result is not None
        assert abs(result - (time.time() - 10800)) < 1.0

    def test_in_future(self):
        result = _parse_time_expression("in 1 hour")
        assert result is not None
        assert abs(result - (time.time() + 3600)) < 0.1

    def test_today(self):
        result = _parse_time_expression("today")
        assert result is not None
        today_midnight = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        ).timestamp()
        assert abs(result - today_midnight) < 0.1

    def test_yesterday(self):
        result = _parse_time_expression("yesterday")
        assert result is not None
        today_midnight = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        ).timestamp()
        assert abs(result - (today_midnight - 86400)) < 0.1

    def test_yesterday_with_time(self):
        result = _parse_time_expression("yesterday 6pm")
        assert result is not None
        today_midnight = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        ).timestamp()
        expected = today_midnight - 86400 + (18 * 3600)
        assert abs(result - expected) < 1.0

    def test_yesterday_with_colon_time(self):
        result = _parse_time_expression("yesterday 18:30")
        assert result is not None
        today_midnight = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        ).timestamp()
        expected = today_midnight - 86400 + (18 * 3600) + (30 * 60)
        assert abs(result - expected) < 1.0

    def test_today_with_time(self):
        result = _parse_time_expression("today 9am")
        assert result is not None
        today_midnight = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        ).timestamp()
        expected = today_midnight + (9 * 3600)
        assert abs(result - expected) < 1.0

    def test_today_with_colon_time(self):
        result = _parse_time_expression("today 09:30:00")
        assert result is not None
        today_midnight = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        ).timestamp()
        expected = today_midnight + (9 * 3600) + (30 * 60)
        assert abs(result - expected) < 1.0

    def test_absolute_timestamp(self):
        result = _parse_time_expression("2025-01-14 08:00:00")
        assert result is not None
        expected = datetime(2025, 1, 14, 8, 0, 0).timestamp()
        assert abs(result - expected) < 0.1

    def test_numeric_timestamp(self):
        ts = 1700000000.0
        result = _parse_time_expression(str(ts))
        assert result is not None
        assert abs(result - ts) < 0.1

    def test_invalid_expression(self):
        result = _parse_time_expression("not a time")
        assert result is None

    def test_empty_string(self):
        result = _parse_time_expression("")
        assert result is None


class TestCliCommands:
    def test_version(self):
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0, f"Exit: {result.exit_code}, out: {result.stdout!r}"
        assert "Kalpa v" in result.stdout

    def test_no_args_shows_help(self):
        result = runner.invoke(app, [])
        assert result.exit_code in (0, 2), f"Exit: {result.exit_code}, out: {result.stdout!r}"
        assert "Usage:" in result.stdout

    @pytest.fixture(autouse=True)
    def setup(self, temp_dir):
        self.test_dir = temp_dir

    def test_watch_nonexistent_folder(self):
        result = runner.invoke(app, ["watch", "/nonexistent/path/12345"])
        assert result.exit_code != 0
        assert "not a directory" in result.stdout

    def test_status_no_watch(self, temp_dir):
        result = runner.invoke(app, ["status", str(temp_dir)])
        assert result.exit_code == 0, f"Exit: {result.exit_code}, out: {result.stdout!r}"
        assert "Not watching" in result.stdout or "No active watch" in result.stdout

    def test_snapshot_no_watch(self, temp_dir):
        result = runner.invoke(app, ["snapshot", "--folder", str(temp_dir)])
        assert result.exit_code != 0

    def test_undo_no_watch(self, temp_dir):
        result = runner.invoke(app, ["undo", "--folder", str(temp_dir)])
        assert result.exit_code != 0

    def test_fork_no_watch(self, temp_dir):
        result = runner.invoke(app, [
            "fork", "--folder", str(temp_dir), "--from", "1 hour ago"
        ])
        assert result.exit_code != 0

    def test_replay_no_watch(self, temp_dir):
        result = runner.invoke(app, ["replay", "--folder", str(temp_dir)])
        assert result.exit_code != 0

    def test_timeline_no_watch(self, temp_dir):
        result = runner.invoke(app, ["timeline", "--folder", str(temp_dir)])
        assert result.exit_code != 0

    def test_diff_no_watch(self, temp_dir):
        result = runner.invoke(app, [
            "diff", "1 hour ago", "now", "--folder", str(temp_dir)
        ])
        assert result.exit_code != 0

    def test_stop_no_watch(self, temp_dir):
        result = runner.invoke(app, ["stop", "--folder", str(temp_dir)])
        assert result.exit_code != 0
