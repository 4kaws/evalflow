"""
Leaderboard view — aggregate results across all output CSVs and rank models.
Shows: accuracy per task, overall ranking, and a side-by-side per-question diff.
"""

from pathlib import Path

import pandas as pd
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.widgets import Button, DataTable, Label, Select, Static, Sparkline

from config import config
from core.merger import discover_outputs


class LeaderboardView(Vertical):
    BINDINGS = [
        Binding("ctrl+r", "refresh", "Refresh", show=True, key_display="Ctrl+R"),
    ]

    DEFAULT_CSS = """
    LeaderboardView { padding: 0 1; height: 1fr; }

    .section-title {
        color: $primary;
        text-style: bold;
        margin-top: 0;
        margin-bottom: 0;
    }

    #top-bar {
        layout: horizontal;
        height: 3;
        align: left middle;
        margin-bottom: 0;
    }
    #top-bar Label { width: 14; color: $text-muted; }
    #top-bar Select { width: 32; margin-right: 2; }

    #leaderboard-table {
        height: 1fr;
        min-height: 4;
        border: solid $primary 15%;
        background: $surface;
    }

    #split-layout {
        layout: horizontal;
        height: 1fr;
        min-height: 4;
        margin-top: 0;
    }

    #task-breakdown {
        width: 1fr;
        border: solid $primary 15%;
        background: $surface;
        margin-right: 1;
    }

    #question-diff {
        width: 1fr;
        border: solid $primary 15%;
        background: $surface;
    }

    #diff-scroll { height: 1fr; padding: 0 1; }

    .diff-row-pass { color: $success; }
    .diff-row-fail { color: $error; }
    .diff-row-mixed { color: $warning; }

    #refresh-lb-btn { margin-left: 1; }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._df: pd.DataFrame = pd.DataFrame()
        self._tasks: list[str] = []

    def compose(self) -> ComposeResult:
        yield Static("Model Leaderboard", classes="section-title")

        with Horizontal(id="top-bar"):
            yield Label("Filter task:")
            yield Select([("All tasks", "all")], value="all", id="task-filter")
            yield Button("Refresh", id="refresh-lb-btn")

        yield DataTable(id="leaderboard-table", cursor_type="row", zebra_stripes=True)

        with Horizontal(id="split-layout"):
            with Vertical(id="task-breakdown"):
                yield Static(" Per-Task Accuracy", classes="section-title")
                yield DataTable(id="task-table", cursor_type="row", zebra_stripes=True)

            with Vertical(id="question-diff"):
                yield Static(" Question-by-Question Diff", classes="section-title")
                yield ScrollableContainer(
                    Static("Select a model row above to see per-question comparison.", id="diff-content"),
                    id="diff-scroll",
                )

    def on_mount(self) -> None:
        lb = self.query_one("#leaderboard-table", DataTable)
        lb.add_columns("Rank", "Model", "Overall %", "Pass", "Fail", "Tasks run", "Bar")

        tt = self.query_one("#task-table", DataTable)
        tt.add_columns("Task", "Model", "Accuracy %", "Pass", "Total")

    def on_activate(self) -> None:
        pass  # user must click Refresh to load

    # ------------------------------------------------------------------ #
    #  Data loading                                                        #
    # ------------------------------------------------------------------ #

    @work(thread=True, exclusive=True)
    def _load_all_outputs(self) -> None:
        csvs = discover_outputs(config.output_dir)
        if not csvs:
            return

        dfs = []
        for path in csvs:
            try:
                df = pd.read_csv(path)
                if {"model_name", "score", "question", "task_name"}.issubset(df.columns):
                    dfs.append(df)
            except Exception:
                continue

        if not dfs:
            return

        combined = pd.concat(dfs, ignore_index=True).drop_duplicates(
            subset=["model_name", "question", "task_name"]
        )
        tasks = sorted(combined["task_name"].unique().tolist())

        def _apply(combined=combined, tasks=tasks):
            self._df = combined
            self._tasks = tasks
            self.query_one("#task-filter", Select).set_options(
                [("All tasks", "all")] + [(t, t) for t in tasks]
            )
            self._rebuild_leaderboard()

        self.app.call_from_thread(_apply)

    def _rebuild_leaderboard(self, task_filter: str = "all") -> None:
        df = self._df.copy()
        if task_filter != "all":
            df = df[df["task_name"] == task_filter]

        if df.empty:
            return

        # Aggregate per model
        agg = (
            df.groupby("model_name")
            .agg(
                total=("score", "count"),
                passed=("score", "sum"),
                tasks=("task_name", "nunique"),
            )
            .reset_index()
        )
        agg["accuracy"] = (agg["passed"] / agg["total"] * 100).round(1)
        agg = agg.sort_values("accuracy", ascending=False).reset_index(drop=True)

        lb = self.query_one("#leaderboard-table", DataTable)
        lb.clear()

        lb_rows = []
        for i, row in agg.iterrows():
            rank_emoji = f"  {i + 1}."
            bar_width = int(row["accuracy"] / 5)
            bar = "█" * bar_width + "░" * (20 - bar_width)
            lb_rows.append((
                rank_emoji,
                row["model_name"].split("/")[-1],
                f"{row['accuracy']}%",
                str(int(row["passed"])),
                str(int(row["total"] - row["passed"])),
                str(int(row["tasks"])),
                bar,
            ))
        lb.add_rows(lb_rows)

        # Per-task breakdown
        task_agg = (
            df.groupby(["task_name", "model_name"])
            .agg(passed=("score", "sum"), total=("score", "count"))
            .reset_index()
        )
        task_agg["accuracy"] = (task_agg["passed"] / task_agg["total"] * 100).round(1)
        task_agg = task_agg.sort_values(["task_name", "accuracy"], ascending=[True, False])

        tt = self.query_one("#task-table", DataTable)
        tt.clear()
        tt.add_rows([
            (
                row["task_name"],
                row["model_name"].split("/")[-1],
                f"{row['accuracy']}%",
                str(int(row["passed"])),
                str(int(row["total"])),
            )
            for _, row in task_agg.iterrows()
        ])

    def _show_question_diff(self, model_name: str) -> None:
        """Show per-question pass/fail for selected model vs all others."""
        if self._df.empty:
            return

        df = self._df.copy()

        # Pivot: question → model → score
        pivot = df.pivot_table(
            index=["task_name", "question"],
            columns="model_name",
            values="score",
            aggfunc="first",
        ).reset_index()

        models = [c for c in pivot.columns if c not in ("task_name", "question")]
        if model_name not in models:
            return

        lines: list[str] = []
        lines.append(f"[bold]{model_name.split('/')[-1]}[/bold] vs others\n")

        for _, row in pivot.iterrows():
            q_short = str(row["question"])[:65] + ("…" if len(str(row["question"])) > 65 else "")
            my_score = row.get(model_name, None)
            other_scores = {m: row.get(m) for m in models if m != model_name and pd.notna(row.get(m))}

            if pd.isna(my_score):
                continue

            my_icon = "+" if my_score == 1 else "-"
            others_str = "  ".join(
                f"{m.split('/')[-1]}:{'+' if s == 1 else '-'}"
                for m, s in other_scores.items()
            )

            line_color = "diff-row-pass" if my_score == 1 else "diff-row-fail"
            lines.append(f"[{line_color}]{my_icon} {q_short}[/{line_color}]")
            if others_str:
                lines.append(f"    [{('dim')}]{others_str}[/dim]")
            lines.append("")

        content = "\n".join(lines) if lines else "No shared questions found across models."
        self.query_one("#diff-content").update(content)

    # ------------------------------------------------------------------ #
    #  Event handlers                                                      #
    # ------------------------------------------------------------------ #

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "task-filter":
            self._rebuild_leaderboard(str(event.value))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "refresh-lb-btn":
            self.action_refresh()

    def action_refresh(self) -> None:
        self._df = pd.DataFrame()
        self._load_all_outputs()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.data_table.id != "leaderboard-table":
            return

        # Get model from selected row
        row_key = event.cursor_row
        lb = self.query_one("#leaderboard-table", DataTable)
        # model name is col index 1 (short name)
        # We need to match back to full name
        short_name = str(lb.get_cell_at((row_key, 1)))

        # Find full model name
        models_full = self._df["model_name"].unique().tolist()
        full_name = next((m for m in models_full if m.split("/")[-1] == short_name), None)
        if full_name:
            self._show_question_diff(full_name)
