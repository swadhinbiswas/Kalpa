from __future__ import annotations

import difflib
from typing import Dict, List

from rich.console import Console
from rich.syntax import Syntax
from rich.text import Text

from kalpa.timeline import Timeline


class DiffEngine:
    def __init__(self, timeline: Timeline):
        self.timeline = timeline
        self.console = Console()

    def diff_timestamps(
        self, time_a: float, time_b: float
    ) -> Dict[str, List[str]]:
        state_a = self.timeline.get_folder_state_at_time(time_a)
        state_b = self.timeline.get_folder_state_at_time(time_b)

        all_files: set = set(state_a.keys()) | set(state_b.keys())
        diffs: Dict[str, List[str]] = {}

        for file_path in sorted(all_files):
            content_a = state_a.get(file_path)
            content_b = state_b.get(file_path)

            if content_a == content_b:
                continue

            lines_a = content_a.decode("utf-8", errors="replace").splitlines(
                keepends=True
            ) if content_a else []
            lines_b = content_b.decode("utf-8", errors="replace").splitlines(
                keepends=True
            ) if content_b else []

            unified_diff = list(
                difflib.unified_diff(
                    lines_a,
                    lines_b,
                    fromfile=f"a/{file_path}",
                    tofile=f"b/{file_path}",
                )
            )

            if unified_diff:
                diffs[file_path] = unified_diff

        return diffs

    def render_diff(
        self,
        diffs: Dict[str, List[str]],
        max_files: int = 20,
    ) -> None:
        if not diffs:
            self.console.print("[dim]No differences found.[/dim]")
            return

        changed_files = len(diffs)
        self.console.print(
            f"\n[bold]Changed files:[/bold] {changed_files}\n"
        )

        for i, (file_path, diff_lines) in enumerate(diffs.items()):
            if i >= max_files:
                self.console.print(
                    f"[dim]... and {changed_files - max_files} more files changed[/dim]"
                )
                break

            diff_text = "".join(diff_lines)
            self.console.print(f"[bold underline]{file_path}[/bold underline]")

            try:
                syntax = Syntax(
                    diff_text,
                    "diff",
                    theme="monokai",
                    line_numbers=False,
                )
                self.console.print(syntax)
            except (ValueError, TypeError):
                for line in diff_lines:
                    style = "green" if line.startswith("+") else (
                        "red" if line.startswith("-") else "dim"
                    )
                    self.console.print(line, style=style)

            if i < len(diffs) - 1:
                self.console.print()
