"""Tkinter interface for the GitSpidy core."""

from __future__ import annotations

import calendar
from datetime import date
from pathlib import Path
from queue import Empty, Queue
from threading import Thread
import sys
import tkinter as tk
from tkinter import filedialog, ttk

from .core import Commit, Statistics, calculate_stats, get_commits


BG = "#10151c"
PANEL = "#1b2530"
BUTTON = "#293746"
TEXT = "#edf2f7"
MUTED = "#aab9c8"
ACCENT = "#64c7aa"
ERROR = "#ff8d8d"
HEAT = ("#25313d", "#24554f", "#287b66", "#38a47d", "#64c7aa")
PAGE_SIZE = 100
MONTHS = ("", "январь", "февраль", "март", "апрель", "май", "июнь",
          "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь")


def _month_shift(month: date, delta: int) -> date:
    index = month.year * 12 + month.month - 1 + delta
    year, month_index = divmod(index, 12)
    return date(year, month_index + 1, 1)


class GitSpidyGUI:
    def __init__(self, root: tk.Tk, path: str) -> None:
        self.root = root
        self.root.title("GitSpidy")
        self.root.configure(bg=BG)
        self.root.geometry("1050x700")
        self.root.minsize(860, 620)

        self._results: Queue[tuple[str, object, Exception | None]] = Queue()
        self._busy = False
        self._all_commits: list[Commit] = []
        self._selected_commits: list[Commit] = []
        self._day_commits: list[Commit] = []
        self._authors: tuple[str, ...] = ()
        self._stats = calculate_stats(())
        self._month = date.today().replace(day=1)
        self._day: date | None = None
        self._page = 0
        self._page_commits: list[Commit] = []

        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("Dark.TCombobox", fieldbackground=PANEL, background=BUTTON,
                        foreground=TEXT, arrowcolor=TEXT)
        style.map("Dark.TCombobox", fieldbackground=[("readonly", PANEL)],
                  foreground=[("readonly", TEXT)])
        root.option_add("*TCombobox*Listbox.background", PANEL)
        root.option_add("*TCombobox*Listbox.foreground", TEXT)
        root.option_add("*TCombobox*Listbox.selectBackground", BUTTON)

        outer = tk.Frame(root, bg=BG, padx=20, pady=16)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(4, weight=1)

        tk.Label(outer, text="GitSpidy", bg=BG, fg=TEXT,
                 font=("TkDefaultFont", 21, "bold")).grid(row=0, column=0, sticky="w")

        path_row = tk.Frame(outer, bg=BG)
        path_row.grid(row=1, column=0, sticky="ew", pady=(14, 6))
        path_row.columnconfigure(0, weight=1)
        self.path_var = tk.StringVar(value=str(Path(path).expanduser().resolve()))
        self.path_entry = tk.Entry(path_row, textvariable=self.path_var, bg=PANEL, fg=TEXT,
                                   insertbackground=TEXT, relief="flat", font=("TkDefaultFont", 11))
        self.path_entry.grid(row=0, column=0, sticky="ew", ipady=7)
        self.browse_button = self._button(path_row, "Выбрать папку", self._browse)
        self.browse_button.grid(row=0, column=1, padx=(8, 0))
        self.scan_button = self._button(path_row, "Анализировать", self._scan, accent=True)
        self.scan_button.grid(row=0, column=2, padx=(8, 0))

        self.status = tk.Label(outer, text="Выбери репозиторий и запусти анализ", bg=BG,
                               fg=MUTED, anchor="w")
        self.status.grid(row=2, column=0, sticky="ew", pady=(0, 12))

        metrics = tk.Frame(outer, bg=BG)
        metrics.grid(row=3, column=0, sticky="ew")
        for column in range(4):
            metrics.columnconfigure(column, weight=1, uniform="metric")
        self.metric_values: dict[str, tk.Label] = {}
        labels = (
            ("total_commits", "Коммиты"), ("contributors", "Авторы"),
            ("first_commit", "Первый коммит"), ("last_commit", "Последний коммит"),
            ("active_days", "Активные дни"), ("peak_day", "Пиковый день"),
            ("peak_hour", "Пиковый час"),
        )
        for index, (key, title) in enumerate(labels):
            card = tk.Frame(metrics, bg=PANEL, padx=12, pady=9)
            card.grid(row=index // 4, column=index % 4, sticky="ew", padx=3, pady=3)
            tk.Label(card, text=title, bg=PANEL, fg=MUTED, anchor="w").pack(fill="x")
            value = tk.Label(card, text="—", bg=PANEL, fg=TEXT, anchor="w",
                             font=("TkDefaultFont", 12, "bold"))
            value.pack(fill="x", pady=(3, 0))
            self.metric_values[key] = value

        content = tk.Frame(outer, bg=BG)
        content.grid(row=4, column=0, sticky="nsew", pady=(16, 0))
        content.columnconfigure(0, weight=1)
        content.columnconfigure(1, weight=2)
        content.rowconfigure(0, weight=1)

        left = tk.Frame(content, bg=PANEL, padx=14, pady=12)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        left.columnconfigure(0, weight=1)
        tk.Label(left, text="Автор", bg=PANEL, fg=MUTED, anchor="w").grid(row=0, column=0, sticky="ew")
        self.author_box = ttk.Combobox(left, state="disabled", style="Dark.TCombobox",
                                       values=("Все авторы",))
        self.author_box.current(0)
        self.author_box.grid(row=1, column=0, sticky="ew", pady=(4, 16))
        self.author_box.bind("<<ComboboxSelected>>", self._filter_author)

        month_row = tk.Frame(left, bg=PANEL)
        month_row.grid(row=2, column=0, sticky="ew")
        month_row.columnconfigure(1, weight=1)
        self._button(month_row, "‹", lambda: self._change_month(-1)).grid(row=0, column=0)
        self.month_label = tk.Label(month_row, bg=PANEL, fg=TEXT,
                                    font=("TkDefaultFont", 12, "bold"))
        self.month_label.grid(row=0, column=1)
        self._button(month_row, "›", lambda: self._change_month(1)).grid(row=0, column=2)

        calendar_frame = tk.Frame(left, bg=PANEL)
        calendar_frame.grid(row=3, column=0, sticky="nsew", pady=(12, 0))
        for column in range(7):
            calendar_frame.columnconfigure(column, weight=1, uniform="day")
        for column, name in enumerate(("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")):
            tk.Label(calendar_frame, text=name, bg=PANEL, fg=MUTED).grid(row=0, column=column)
        self.day_buttons: list[tk.Button] = []
        for index in range(42):
            button = tk.Button(calendar_frame, bg=HEAT[0], fg=TEXT, relief="flat",
                               activebackground=ACCENT, activeforeground=BG,
                               font=("TkDefaultFont", 9), height=2, bd=0)
            button.grid(row=1 + index // 7, column=index % 7, sticky="nsew", padx=2, pady=2)
            self.day_buttons.append(button)
        tk.Label(left, text="Цвет показывает число коммитов за день",
                 bg=PANEL, fg=MUTED).grid(row=4, column=0, sticky="w", pady=(12, 0))

        right = tk.Frame(content, bg=PANEL, padx=14, pady=12)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=2)
        right.rowconfigure(4, weight=1)
        self.day_label = tk.Label(right, text="Коммиты за день", bg=PANEL, fg=TEXT,
                                  anchor="w", font=("TkDefaultFont", 12, "bold"))
        self.day_label.grid(row=0, column=0, sticky="ew")
        list_frame = tk.Frame(right, bg=PANEL)
        list_frame.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)
        self.commit_list = tk.Listbox(list_frame, bg=BG, fg=TEXT, selectbackground=BUTTON,
                                      selectforeground=TEXT, relief="flat", exportselection=False,
                                      activestyle="none")
        self.commit_list.grid(row=0, column=0, sticky="nsew")
        self.commit_list.bind("<<ListboxSelect>>", self._show_commit)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.commit_list.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.commit_list.configure(yscrollcommand=scrollbar.set)

        pager = tk.Frame(right, bg=PANEL)
        pager.grid(row=2, column=0, sticky="ew", pady=(7, 12))
        self.prev_page = self._button(pager, "‹", lambda: self._change_page(-1))
        self.prev_page.pack(side="left")
        self.page_label = tk.Label(pager, text="0 коммитов", bg=PANEL, fg=MUTED)
        self.page_label.pack(side="left", padx=10)
        self.next_page = self._button(pager, "›", lambda: self._change_page(1))
        self.next_page.pack(side="left")
        tk.Label(right, text="Подробности коммита", bg=PANEL, fg=MUTED,
                 anchor="w").grid(row=3, column=0, sticky="ew")
        self.details = tk.Text(right, bg=BG, fg=TEXT, insertbackground=TEXT,
                               relief="flat", wrap="word", height=8, padx=9, pady=7)
        self.details.grid(row=4, column=0, sticky="nsew", pady=(6, 0))
        self.details.configure(state="disabled")

        self._render_stats()
        self._render_calendar()
        self._render_day()
        self.root.after(80, self._poll_results)

    @staticmethod
    def _button(parent: tk.Widget, label: str, command, *, accent: bool = False) -> tk.Button:
        bg = ACCENT if accent else BUTTON
        return tk.Button(parent, text=label, command=command, bg=bg, fg=BG if accent else TEXT,
                         activebackground="#8cdec4" if accent else "#3b4d5f",
                         activeforeground=BG if accent else TEXT, relief="flat", bd=0,
                         padx=12, pady=6, cursor="hand2")

    def _status(self, message: str, *, error: bool = False) -> None:
        self.status.configure(text=message, fg=ERROR if error else MUTED)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        state = "disabled" if busy else "normal"
        for widget in (self.path_entry, self.browse_button, self.scan_button):
            widget.configure(state=state)
        self.author_box.configure(state="disabled" if busy or not self._all_commits else "readonly")

    def _run(self, operation: str, task) -> None:
        self._set_busy(True)

        def worker() -> None:
            try:
                result = task()
                self._results.put((operation, result, None))
            except Exception as exc:
                self._results.put((operation, None, exc))

        Thread(target=worker, daemon=True).start()

    def _poll_results(self) -> None:
        try:
            while True:
                operation, result, error = self._results.get_nowait()
                self._set_busy(False)
                if error is not None:
                    self._status(f"Ошибка: {error}", error=True)
                    continue
                if operation == "scan":
                    self._all_commits, self._stats = result
                    self._selected_commits = self._all_commits
                    self._authors = tuple(author for author, _ in self._stats.top_authors)
                    self.author_box.configure(values=("Все авторы", *self._authors))
                    self.author_box.current(0)
                    self.author_box.configure(state="readonly" if self._authors else "disabled")
                    if self._stats.last_commit:
                        self._month = self._stats.last_commit.date().replace(day=1)
                    self._refresh_selection()
                    self._status(f"Готово: {len(self._all_commits):,} коммитов".replace(",", " "))
                elif operation == "filter":
                    self._selected_commits, self._stats = result
                    self._refresh_selection()
                    self._status(f"Найдено коммитов: {self._stats.total_commits:,}".replace(",", " "))
                elif operation == "day":
                    self._day_commits = result
                    self._page = 0
                    self._render_day()
                    self._status(f"Коммитов за {self._day.isoformat()}: {len(result):,}".replace(",", " "))
        except Empty:
            pass
        self.root.after(80, self._poll_results)

    def _browse(self) -> None:
        folder = filedialog.askdirectory(initialdir=self.path_var.get() or str(Path.home()))
        if folder:
            self.path_var.set(folder)

    def _scan(self) -> None:
        if self._busy:
            return
        path = self.path_var.get().strip()
        if not path:
            self._status("Укажи путь к репозиторию", error=True)
            return
        self._all_commits = []
        self._selected_commits = []
        self._authors = ()
        self._stats = calculate_stats(())
        self.author_box.configure(values=("Все авторы",))
        self.author_box.current(0)
        self._refresh_selection()
        self._status("Читаю историю Git…")
        self._run("scan", lambda: self._load(path))

    @staticmethod
    def _load(path: str) -> tuple[list[Commit], Statistics]:
        commits = get_commits(path)
        return commits, calculate_stats(commits)

    def _filter_author(self, _event=None) -> None:
        if self._busy:
            return
        index = self.author_box.current()
        author = self._authors[index - 1] if index > 0 else None
        self._status("Пересчитываю статистику…")

        def task() -> tuple[list[Commit], Statistics]:
            chosen = self._all_commits if author is None else [
                commit for commit in self._all_commits if commit.author == author
            ]
            return chosen, calculate_stats(chosen)

        self._run("filter", task)

    def _refresh_selection(self) -> None:
        self._day = None
        self._day_commits = []
        self._page = 0
        self._render_stats()
        self._render_calendar()
        self._render_day()

    def _render_stats(self) -> None:
        stats = self._stats
        values = {
            "total_commits": f"{stats.total_commits:,}".replace(",", " "),
            "contributors": str(stats.contributors),
            "first_commit": stats.first_commit.isoformat(sep=" ", timespec="minutes") if stats.first_commit else "—",
            "last_commit": stats.last_commit.isoformat(sep=" ", timespec="minutes") if stats.last_commit else "—",
            "active_days": str(stats.active_days),
            "peak_day": stats.peak_day.isoformat() if stats.peak_day else "—",
            "peak_hour": f"{stats.peak_hour:02d}:00" if stats.peak_hour is not None else "—",
        }
        for key, value in values.items():
            self.metric_values[key].configure(text=value)

    def _change_month(self, delta: int) -> None:
        self._month = _month_shift(self._month, delta)
        self._render_calendar()

    def _render_calendar(self) -> None:
        self.month_label.configure(text=f"{MONTHS[self._month.month]} {self._month.year}")
        weeks = calendar.Calendar(firstweekday=0).monthdatescalendar(
            self._month.year, self._month.month
        )
        dates = [day for week in weeks for day in week]
        counts = self._stats.daily_counts
        maximum = max((counts.get(day, 0) for day in dates if day.month == self._month.month), default=0)
        for index, button in enumerate(self.day_buttons):
            if index >= len(dates) or dates[index].month != self._month.month:
                button.configure(text="", state="disabled", bg=PANEL, command=lambda: None)
                continue
            day = dates[index]
            count = counts.get(day, 0)
            level = min(4, (count * 4 + maximum - 1) // maximum) if count and maximum else 0
            background = ACCENT if day == self._day else HEAT[level]
            foreground = BG if day == self._day or level == 4 else TEXT
            button.configure(text=f"{day.day}\n{count if count else ''}", state="normal",
                             bg=background, fg=foreground,
                             command=lambda selected=day: self._select_day(selected))

    def _select_day(self, day: date) -> None:
        if self._busy:
            return
        self._day = day
        self._day_commits = []
        self._page = 0
        self._render_calendar()
        self._render_day()
        if not self._stats.daily_counts.get(day):
            return
        commits = self._selected_commits
        self._status(f"Читаю коммиты за {day.isoformat()}…")

        def task() -> list[Commit]:
            return sorted((commit for commit in commits if commit.authored_at.date() == day),
                          key=lambda commit: (commit.authored_at, commit.sha))

        self._run("day", task)

    def _change_page(self, delta: int) -> None:
        next_page = self._page + delta
        if 0 <= next_page and next_page * PAGE_SIZE < len(self._day_commits):
            self._page = next_page
            self._render_day()

    def _render_day(self) -> None:
        self.day_label.configure(text=f"Коммиты за {self._day.isoformat()}" if self._day else "Коммиты за день")
        self.commit_list.delete(0, "end")
        self._page_commits = self._day_commits[self._page * PAGE_SIZE:(self._page + 1) * PAGE_SIZE]
        for commit in self._page_commits:
            summary = commit.message.splitlines()[0] if commit.message else ""
            self.commit_list.insert("end", f"{commit.authored_at:%H:%M}  {commit.sha[:8]}  {summary}")
        count = len(self._day_commits)
        start = self._page * PAGE_SIZE + 1 if count else 0
        end = min((self._page + 1) * PAGE_SIZE, count)
        self.page_label.configure(text=f"{start}–{end} из {count}" if count else "0 коммитов")
        self.prev_page.configure(state="normal" if self._page else "disabled")
        self.next_page.configure(state="normal" if end < count else "disabled")
        self._set_details("")

    def _show_commit(self, _event=None) -> None:
        selected = self.commit_list.curselection()
        if not selected or selected[0] >= len(self._page_commits):
            return
        commit = self._page_commits[selected[0]]
        self._set_details(
            f"SHA: {commit.sha}\nАвтор: {commit.author}\n"
            f"Дата: {commit.authored_at.isoformat(sep=' ', timespec='seconds')}\n\n"
            f"{commit.message}"
        )

    def _set_details(self, value: str) -> None:
        self.details.configure(state="normal")
        self.details.delete("1.0", "end")
        self.details.insert("1.0", value)
        self.details.configure(state="disabled")


def main(path: str = ".") -> int:
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        print(f"Ошибка: не удалось открыть окно Tkinter: {exc}", file=sys.stderr)
        return 1
    GitSpidyGUI(root, path)
    root.mainloop()
    return 0
