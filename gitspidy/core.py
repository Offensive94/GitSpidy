"""read git history and count stats"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
import subprocess
from typing import Iterable


class GitSpidyError(Exception):
    """an error we can show to the user"""


@dataclass(frozen=True)
class Commit:
    sha: str
    author: str
    authored_at: datetime
    message: str


@dataclass(frozen=True)
class Statistics:
    total_commits: int
    contributors: int
    first_commit: datetime | None
    last_commit: datetime | None
    active_days: int
    peak_day: date | None
    peak_hour: int | None
    top_authors: tuple[tuple[str, int], ...]
    daily_counts: dict[date, int]
    hourly_counts: dict[int, int]


def _run_git(path: Path, *arguments: str) -> bytes:
    try:
        result = subprocess.run(
            ["git", "-C", str(path), *arguments],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except FileNotFoundError as exc:
        raise GitSpidyError("Git не установлен или недоступен в PATH") from exc
    except OSError as exc:
        raise GitSpidyError(f"Не удалось запустить Git: {exc}") from exc
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise GitSpidyError(detail or "Не удалось прочитать историю Git")
    return result.stdout


def get_commits(path: str | Path) -> list[Commit]:
    """get each commit from local git refs once

    use the author's date and time zone
    zero bytes separate fields so messages can have multiple lines
    """
    repository = Path(path).expanduser()
    if not repository.is_dir():
        raise GitSpidyError(f"Директория не существует: {repository}")
    try:
        _run_git(repository, "rev-parse", "--git-dir")
    except GitSpidyError as exc:
        if "Git не установлен" in str(exc):
            raise
        raise GitSpidyError(f"Папка не является Git-репозиторием: {repository}") from exc

    raw = _run_git(
        repository,
        "log",
        "--all",
        "--format=%H%x00%an%x00%aI%x00%B%x00%x00",
    )
    commits: list[Commit] = []
    for record in raw.split(b"\x00\x00"):
        record = record.lstrip(b"\n")
        if not record.strip():
            continue
        fields = record.split(b"\x00", 3)
        if len(fields) != 4:
            raise GitSpidyError("Не удалось разобрать историю Git")
        sha, author, timestamp, message = (
            field.decode("utf-8", errors="replace") for field in fields
        )
        try:
            authored_at = datetime.fromisoformat(timestamp)
        except ValueError as exc:
            raise GitSpidyError("Некорректная дата коммита в истории Git") from exc
        commits.append(Commit(sha, author, authored_at, message.rstrip("\n")))
    return commits


def filter_commits(
    commits: Iterable[Commit], *, author: str | None = None, day: date | None = None
) -> list[Commit]:
    """filter by author name and date in the commit's time zone"""
    name = author.casefold() if author is not None else None
    return [
        commit
        for commit in commits
        if (name is None or name in commit.author.casefold())
        and (day is None or commit.authored_at.date() == day)
    ]


def calculate_stats(commits: Iterable[Commit]) -> Statistics:
    """calculate all stats from the given commits including filtered ones"""
    selected = list(commits)
    days = Counter(commit.authored_at.date() for commit in selected)
    hours = Counter(commit.authored_at.hour for commit in selected)
    authors = Counter(commit.author for commit in selected)
    first = min((commit.authored_at for commit in selected), default=None)
    last = max((commit.authored_at for commit in selected), default=None)
    peak_day = min(days, key=lambda value: (-days[value], value)) if days else None
    peak_hour = min(hours, key=lambda value: (-hours[value], value)) if hours else None
    return Statistics(
        total_commits=len(selected),
        contributors=len(authors),
        first_commit=first,
        last_commit=last,
        active_days=len(days),
        peak_day=peak_day,
        peak_hour=peak_hour,
        top_authors=tuple(sorted(authors.items(), key=lambda item: (-item[1], item[0].casefold(), item[0]))),
        daily_counts=dict(days),
        hourly_counts=dict(hours),
    )
