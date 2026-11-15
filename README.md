# GitSpidy

> Analyse local Git repository statistics from the terminal — no internet required.

[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-GPLv3-blue)](LICENSE)
[![GitHub](https://img.shields.io/badge/github-Offensive94%2FGitSpidy-181717?logo=github)](https://github.com/Offensive94/GitSpidy)

---

## Features

- **CLI + GUI** — use from the terminal or open a graphical interface
- **Fully local** — reads your local Git history, nothing leaves your machine
- **Zero dependencies** — works with Python 3.11+ and Git, no third-party packages
- **Author filter** — case-insensitive partial name matching
- **Date filter** — pick a specific day, see all commits and recalculated stats
- **JSON output** — machine-readable output for scripting and integration
- **Colourful terminal output** — tables, ASCII activity bars, and a small spider logo

---

## Requirements

- **Python 3.11** or later
- **Git** — installed and available in `PATH`

---

## Installation

```bash
git clone https://github.com/Offensive94/GitSpidy.git
cd GitSpidy
```

No `pip install` needed — just clone and run.

---

## Usage

All commands should be run from the project root directory.  
If you need to run `gitspidy` from another directory, add the project path to `PYTHONPATH`.

### CLI

```bash
# Show help
python -m gitspidy

# Analyse the current repository
python -m gitspidy scan .

# Analyse a specific repository
python -m gitspidy scan /path/to/repo

# Filter by author (case-insensitive partial match)
python -m gitspidy scan . --author joost

# Filter by date (YYYY-MM-DD, author timezone)
python -m gitspidy scan . --date 2026-10-30

# Combine filters
python -m gitspidy scan . --author joost --date 2026-10-30

# JSON output
python -m gitspidy scan . --json

# Open the graphical interface
python -m gitspidy gui .
```

### GUI

The graphical interface provides:

- **Calendar heatmap** — colour-coded activity per day
- **Author filter** — pick an author from the dropdown to recalculate stats
- **Commit list** — paginated list of commits for a selected day
- **Commit details** — full SHA, author, timestamp, and message

```bash
python -m gitspidy gui .
```

A standalone binary `gitspidy-gui` is also available in releases for users who prefer a clickable application.

---

## How It Works

- History is fetched via `git log --all` — all unique commits from every local ref are included
- No data is downloaded from the internet
- Author date and timezone (as recorded in each commit) are used for analysis
- Day and hour activity is calculated in each commit's local time
- Authors are identified by exact name — `Joost` and `joost` are treated as different people
- When multiple days or hours share the same peak value, the earliest one is chosen
- First and last commits are determined by absolute author date

---

## Error Handling

| Scenario | Exit Code | Behaviour |
|---|---|---|
| Empty repository or no matching commits | `0` | All counters show `0`, uncomputable values show `—`, message "No commits found" |
| Invalid path / not a Git repository / Git unavailable | `1` | Clear error message, no traceback |
| Invalid command-line arguments | `2` | Parser error message |

---

## Testing

Tests use the built-in `unittest` framework:

```bash
python -m unittest discover -s tests
```

Tests automatically create temporary Git repositories, verify the analyser, and never touch your real data.

---

## Project Structure

```
gitspidy/
├── gitspidy/
│   ├── __init__.py      # package version and metadata
│   ├── __main__.py      # entry point for python -m gitspidy
│   ├── core.py          # git history, filtering, statistics
│   ├── cli.py           # CLI argument parsing and output formatting
│   ├── gui.py           # Tkinter graphical interface
│   └── gui_main.py      # standalone GUI entry point
├── tests/
│   └── test_core.py     # automated tests
├── README.md
├── LICENSE              # GNU General Public License v3.0
└── .gitignore
```

### Module overview

| Module | Responsibility |
|---|---|
| [`core.py`](gitspidy/core.py) | Run Git commands, parse commit data, filter commits, calculate statistics |
| [`cli.py`](gitspidy/cli.py) | Parse command-line arguments, format text and JSON reports |
| [`gui.py`](gitspidy/gui.py) | Tkinter GUI with calendar heatmap, commit list, and author filter |
| [`__main__.py`](gitspidy/__main__.py) | Enables `python -m gitspidy` |
| [`gui_main.py`](gitspidy/gui_main.py) | Standalone entry point for the GUI binary |
| [`test_core.py`](tests/test_core.py) | Unit and integration tests with temporary Git repos |

---

## Roadmap

See [milestone.md](milestone.md) for planned features and ideas.

---

## License

This project is licensed under the **GNU General Public License v3.0**.  
See [LICENSE](LICENSE) for details.
