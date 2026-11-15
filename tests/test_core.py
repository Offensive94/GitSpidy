"""tests with temporary git repositories"""

from __future__ import annotations

from contextlib import redirect_stdout, redirect_stderr
from datetime import date
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

from gitspidy.cli import main
from gitspidy.core import GitSpidyError, calculate_stats, filter_commits, get_commits


class RepositoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.git("init", "-q")

    def git(self, *args: str, env: dict[str, str] | None = None) -> str:
        result = subprocess.run(
            ["git", "-C", str(self.path), *args],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )
        return result.stdout.strip()

    def commit(self, message: str, author: str, timestamp: str) -> None:
        env = os.environ.copy()
        env.update({
            "GIT_AUTHOR_NAME": author,
            "GIT_AUTHOR_EMAIL": "author@example.test",
            "GIT_AUTHOR_DATE": timestamp,
            "GIT_COMMITTER_NAME": "Test Committer",
            "GIT_COMMITTER_EMAIL": "committer@example.test",
            "GIT_COMMITTER_DATE": timestamp,
        })
        self.git("-c", "commit.gpgsign=false", "commit", "--allow-empty", "-q", "-m", message, env=env)

    def sample_history(self) -> None:
        self.commit("First message", "Joost", "2026-10-30T09:15:00+05:00")
        self.commit("Second\n\nMore detail", "joost", "2026-10-30T18:45:00+05:00")
        self.commit("Third", "Alice", "2026-10-31T09:00:00+02:00")

    def test_commit_count_and_message(self) -> None:
        self.sample_history()
        commits = get_commits(self.path)
        self.assertEqual(len(commits), 3)
        self.assertEqual(calculate_stats(commits).total_commits, 3)
        self.assertEqual(next(c.message for c in commits if c.author == "joost"), "Second\n\nMore detail")
        self.assertTrue(all(len(c.sha) == 40 for c in commits))

    def test_author_filter_and_recalculated_statistics(self) -> None:
        self.sample_history()
        chosen = filter_commits(get_commits(self.path), author="OOS")
        stats = calculate_stats(chosen)
        self.assertEqual(stats.total_commits, 2)
        self.assertEqual(stats.contributors, 2)  # names with different case count separately
        self.assertEqual(stats.active_days, 1)

    def test_date_filter_uses_author_local_date(self) -> None:
        self.sample_history()
        chosen = filter_commits(get_commits(self.path), day=date(2026, 10, 30))
        self.assertEqual(len(chosen), 2)
        self.assertTrue(all(c.authored_at.date() == date(2026, 10, 30) for c in chosen))

    def test_day_and_hour_activity(self) -> None:
        self.sample_history()
        stats = calculate_stats(get_commits(self.path))
        self.assertEqual(stats.contributors, 3)
        self.assertEqual(stats.active_days, 2)
        self.assertEqual(stats.daily_counts[date(2026, 10, 30)], 2)
        self.assertEqual(stats.hourly_counts[9], 2)
        self.assertEqual(stats.peak_day, date(2026, 10, 30))
        self.assertEqual(stats.peak_hour, 9)
        self.assertEqual(stats.first_commit.date(), date(2026, 10, 30))
        self.assertEqual(stats.last_commit.date(), date(2026, 10, 31))

    def test_streaks_and_breaks(self) -> None:
        """current streak, longest streak, and longest break from daily_counts"""
        # day 1 — streak of 1
        self.commit("a", "Joost", "2026-10-01T12:00:00+05:00")
        # gap of 5 days
        # day 7, 8, 9 — streak of 3
        self.commit("b", "Joost", "2026-10-07T12:00:00+05:00")
        self.commit("c", "Joost", "2026-10-08T12:00:00+05:00")
        self.commit("d", "Joost", "2026-10-09T12:00:00+05:00")
        # gap of 2 days
        # day 12, 13 — current streak of 2
        self.commit("e", "Joost", "2026-10-12T12:00:00+05:00")
        self.commit("f", "Joost", "2026-10-13T12:00:00+05:00")
        stats = calculate_stats(get_commits(self.path))
        self.assertEqual(stats.current_streak, 2)
        self.assertEqual(stats.longest_streak, 3)
        self.assertEqual(stats.longest_break, 5)

    def test_single_day_streaks(self) -> None:
        """single commit day — streak of 1, no break"""
        self.commit("only", "Joost", "2026-10-15T12:00:00+05:00")
        stats = calculate_stats(get_commits(self.path))
        self.assertEqual(stats.current_streak, 1)
        self.assertEqual(stats.longest_streak, 1)
        self.assertEqual(stats.longest_break, 0)

    def test_consecutive_days_no_break(self) -> None:
        """every day for a week — streak equals active_days, break is 0"""
        for day_offset in range(7):
            ts = f"2026-10-{15 + day_offset:02d}T12:00:00+05:00"
            self.commit(f"day {day_offset}", "Joost", ts)
        stats = calculate_stats(get_commits(self.path))
        self.assertEqual(stats.current_streak, 7)
        self.assertEqual(stats.longest_streak, 7)
        self.assertEqual(stats.longest_break, 0)

    def test_empty_repository(self) -> None:
        stats = calculate_stats(get_commits(self.path))
        self.assertEqual(stats.total_commits, 0)
        self.assertEqual(stats.contributors, 0)
        self.assertEqual(stats.active_days, 0)
        self.assertIsNone(stats.first_commit)
        self.assertIsNone(stats.peak_day)
        self.assertIsNone(stats.peak_hour)
        self.assertEqual(stats.current_streak, 0)
        self.assertEqual(stats.longest_streak, 0)
        self.assertEqual(stats.longest_break, 0)

    def test_invalid_path_and_non_repository(self) -> None:
        with self.assertRaisesRegex(GitSpidyError, "Директория не существует"):
            get_commits(self.path / "missing")
        with tempfile.TemporaryDirectory() as other:
            with self.assertRaisesRegex(GitSpidyError, "не является Git-репозиторием"):
                get_commits(other)

    def test_all_refs_deduplicates_shared_history(self) -> None:
        self.commit("Base", "Joost", "2026-10-30T09:00:00+05:00")
        self.git("branch", "feature")
        self.commit("Main", "Joost", "2026-10-30T10:00:00+05:00")
        self.git("checkout", "-q", "feature")
        self.commit("Feature", "Alice", "2026-10-30T11:00:00+05:00")
        self.assertEqual(len(get_commits(self.path)), 3)

    def test_cli_empty_filter_and_bad_date(self) -> None:
        self.sample_history()
        output = io.StringIO()
        with redirect_stdout(output):
            code = main(["scan", str(self.path), "--author", "Nobody"])
        self.assertEqual(code, 0)
        self.assertIn("Total commits    0", output.getvalue())
        self.assertIn("Peak day         —", output.getvalue())
        self.assertIn("Коммиты не найдены", output.getvalue())

        with redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as caught:
                main(["scan", str(self.path), "--date", "2026-13-99"])
        self.assertEqual(caught.exception.code, 2)

    def test_cli_json_output_is_machine_readable(self) -> None:
        self.sample_history()
        output = io.StringIO()
        with redirect_stdout(output):
            code = main(["scan", str(self.path), "--author", "joost", "--json"])
        self.assertEqual(code, 0)
        report = json.loads(output.getvalue())
        self.assertEqual(report["statistics"]["total_commits"], 2)
        self.assertEqual(report["statistics"]["contributors"], 2)
        self.assertEqual(len(report["commits"]), 2)
        self.assertEqual({commit["author"] for commit in report["commits"]}, {"Joost", "joost"})
        self.assertEqual(report["statistics"]["daily_counts"], {"2026-10-30": 2})

    def test_gui_command_dispatches_without_changing_scan(self) -> None:
        gui_main = Mock(return_value=0)
        gui_module = types.ModuleType("gitspidy.gui")
        gui_module.main = gui_main
        with patch.dict("sys.modules", {"gitspidy.gui": gui_module}):
            self.assertEqual(main(["gui", str(self.path)]), 0)
        gui_main.assert_called_once_with(str(self.path))
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main(["scan", str(self.path)]), 0)


if __name__ == "__main__":
    unittest.main()
