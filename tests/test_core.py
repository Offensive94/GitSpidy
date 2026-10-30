"""tests with temporary git repositories"""

from __future__ import annotations

from contextlib import redirect_stdout, redirect_stderr
from datetime import date
import io
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

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

    def test_empty_repository(self) -> None:
        stats = calculate_stats(get_commits(self.path))
        self.assertEqual(stats.total_commits, 0)
        self.assertEqual(stats.contributors, 0)
        self.assertEqual(stats.active_days, 0)
        self.assertIsNone(stats.first_commit)
        self.assertIsNone(stats.peak_day)
        self.assertIsNone(stats.peak_hour)

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


if __name__ == "__main__":
    unittest.main()
