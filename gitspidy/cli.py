"""gitspidy commands and text output"""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
import sys

from .core import GitSpidyError, calculate_stats, filter_commits, get_commits


def _parse_date(value: str) -> date:
    try:
        parsed = date.fromisoformat(value)
        if parsed.isoformat() != value:
            raise ValueError
        return parsed
    except ValueError as exc:
        raise argparse.ArgumentTypeError("дата должна иметь формат YYYY-MM-DD") from exc


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Анализ истории локального Git-репозитория")
    subparsers = parser.add_subparsers(dest="command")
    scan = subparsers.add_parser("scan", help="показать статистику репозитория")
    scan.add_argument("path", metavar="PATH", help="путь к репозиторию")
    scan.add_argument("--author", metavar="NAME", help="часть имени автора, без учёта регистра")
    scan.add_argument("--date", metavar="YYYY-MM-DD", type=_parse_date, help="дата коммита автора")
    return parser


def _bar(count: int, maximum: int) -> str:
    return "█" * max(1, round(count / maximum * 24))


def _print_report(path: Path, commits: list, stats, day: date | None) -> None:
    dash = "—"
    print(f"GitSpidy — {path}")
    print("=" * 60)
    rows = (
        ("Total commits", str(stats.total_commits)),
        ("Contributors", str(stats.contributors)),
        ("First commit", stats.first_commit.isoformat(sep=" ", timespec="minutes") if stats.first_commit else dash),
        ("Last commit", stats.last_commit.isoformat(sep=" ", timespec="minutes") if stats.last_commit else dash),
        ("Active days", str(stats.active_days)),
        ("Peak day", stats.peak_day.isoformat() if stats.peak_day else dash),
        ("Peak hour", f"{stats.peak_hour:02d}:00" if stats.peak_hour is not None else dash),
    )
    for label, value in rows:
        print(f"{label:<16} {value}")

    if not commits:
        print("\nКоммиты не найдены")
        return

    print("\nTop authors")
    print(f"{'Author':<25} {'Commits':>7}  Activity")
    print("-" * 60)
    maximum = stats.top_authors[0][1]
    for author, count in stats.top_authors:
        print(f"{author[:25]:<25} {count:>7}  {_bar(count, maximum)}")

    print("\nActivity by day")
    print(f"{'Date':<12} {'Commits':>7}  Activity")
    print("-" * 60)
    maximum = max(stats.daily_counts.values())
    for active_day, count in sorted(stats.daily_counts.items()):
        print(f"{active_day.isoformat():<12} {count:>7}  {_bar(count, maximum)}")

    if day is not None:
        print(f"\nCommits on {day.isoformat()}")
        print(f"{'SHA':<12} {'Time':<22} {'Author':<25} Message")
        print("-" * 90)
        for commit in sorted(commits, key=lambda item: (item.authored_at, item.sha)):
            summary = commit.message.splitlines()[0] if commit.message else ""
            print(f"{commit.sha[:12]:<12} {commit.authored_at.strftime('%H:%M:%S %z'):<22} {commit.author[:25]:<25} {summary}")


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    try:
        commits = filter_commits(get_commits(args.path), author=args.author, day=args.date)
        stats = calculate_stats(commits)
    except GitSpidyError as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 1
    _print_report(Path(args.path).expanduser(), commits, stats, args.date)
    return 0
