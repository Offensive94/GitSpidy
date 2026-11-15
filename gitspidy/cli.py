"""gitspidy commands and text output"""

from __future__ import annotations

import argparse
from datetime import date
import json
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
    scan.add_argument("--json", action="store_true", help="вывести результат в формате JSON")
    gui = subparsers.add_parser("gui", help="открыть графический интерфейс")
    gui.add_argument("path", nargs="?", default=".", metavar="PATH", help="путь к репозиторию (по умолчанию текущая папка)")
    return parser


def _bar(count: int, maximum: int) -> str:
    if count == 0:
        return ""
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
        ("Current streak", f"{stats.current_streak} day{'s' if stats.current_streak != 1 else ''}"),
        ("Longest streak", f"{stats.longest_streak} day{'s' if stats.longest_streak != 1 else ''}"),
        ("Longest break", f"{stats.longest_break} day{'s' if stats.longest_break != 1 else ''}"),
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

    print("\nHourly distribution (24h)")
    print(f"{'Hour':<8} {'Commits':>7}  Activity")
    print("-" * 60)
    max_hour = max(stats.hourly_counts.values()) if stats.hourly_counts else 1
    for hour in range(24):
        count = stats.hourly_counts.get(hour, 0)
        print(f"{hour:02d}:00{'':>5} {count:>7}  {_bar(count, max_hour)}")

    if day is not None:
        print(f"\nCommits on {day.isoformat()}")
        print(f"{'SHA':<12} {'Time':<22} {'Author':<25} Message")
        print("-" * 90)
        for commit in sorted(commits, key=lambda item: (item.authored_at, item.sha)):
            summary = commit.message.splitlines()[0] if commit.message else ""
            print(f"{commit.sha[:12]:<12} {commit.authored_at.strftime('%H:%M:%S %z'):<22} {commit.author[:25]:<25} {summary}")


def _print_json(path: Path, commits: list, stats) -> None:
    """print a stable, machine-readable representation of the analysis"""
    payload = {
        "path": str(path),
        "statistics": {
            "total_commits": stats.total_commits,
            "contributors": stats.contributors,
            "first_commit": stats.first_commit.isoformat() if stats.first_commit else None,
            "last_commit": stats.last_commit.isoformat() if stats.last_commit else None,
            "active_days": stats.active_days,
            "peak_day": stats.peak_day.isoformat() if stats.peak_day else None,
            "peak_hour": stats.peak_hour,
            "current_streak": stats.current_streak,
            "longest_streak": stats.longest_streak,
            "longest_break": stats.longest_break,
            "top_authors": [
                {"author": author, "commits": count}
                for author, count in stats.top_authors
            ],
            "daily_counts": {
                day.isoformat(): count
                for day, count in sorted(stats.daily_counts.items())
            },
            "hourly_counts": {
                str(hour): count
                for hour, count in sorted(stats.hourly_counts.items())
            },
        },
        "commits": [
            {
                "sha": commit.sha,
                "author": commit.author,
                "authored_at": commit.authored_at.isoformat(),
                "message": commit.message,
            }
            for commit in commits
        ],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    if args.command == "gui":
        try:
            from .gui import main as gui_main
        except ImportError as exc:
            print(f"Ошибка: Tkinter недоступен: {exc}", file=sys.stderr)
            return 1
        return gui_main(args.path)
    try:
        commits = filter_commits(get_commits(args.path), author=args.author, day=args.date)
        stats = calculate_stats(commits)
    except GitSpidyError as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 1
    output_path = Path(args.path).expanduser()
    if args.json:
        _print_json(output_path, commits, stats)
    else:
        _print_report(output_path, commits, stats, args.date)
    return 0
