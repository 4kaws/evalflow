"""Results view — browse, filter, and inspect benchmark output CSVs."""

import pandas as pd
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.widgets import Button, DataTable, Label, Select, Static

from config import config
from views.widgets import PageHeader


class ResultsView(Vertical):
    _SELECT_IDS = ["task-filter", "model-filter", "score-filter"]

    BINDINGS = [
        Binding("ctrl+r", "refresh",   "Refresh", show=True, key_display="Ctrl+R"),
        Binding("left",   "nav_left",  show=False),
        Binding("right",  "nav_right", show=False),
        Binding("escape", "nav_esc",   show=False),
    ]

    def _fid(self) -> str | None:
        return self.app.focused.id if self.app.focused else None

    def action_nav_left(self) -> None:
        fid = self._fid()
        if fid in self._SELECT_IDS:
            idx = self._SELECT_IDS.index(fid)
            self.query_one(f"#{self._SELECT_IDS[(idx - 1) % 3]}", Select).focus()

    def action_nav_right(self) -> None:
        fid = self._fid()
        if fid in self._SELECT_IDS:
            idx = self._SELECT_IDS.index(fid)
            self.query_one(f"#{self._SELECT_IDS[(idx + 1) % 3]}", Select).focus()

    def action_nav_esc(self) -> None:
        self.app.action_unfocus()

    DEFAULT_CSS = """
    ResultsView { padding: 0; height: 1fr; }

    #results-body { padding: 1 3; height: 1fr; }

    .section-title { color: #636E7B; text-style: bold; margin-bottom: 0; margin-top: 1; }

    #filter-bar { height: 3; align: left middle; margin-bottom: 0; }
    #filter-bar Label { width: 8; height: 3; color: #636E7B; content-align: left middle; }
    #filter-bar Select { width: 24; margin-right: 2; }
    #refresh-btn { margin-left: 1; }

    #results-table {
        height: 1fr;
        min-height: 6;
        margin-top: 1;
        background: $surface;
        border: round #D0D7DE;
    }

    #stats-bar {
        color: #636E7B;
        height: 1;
        margin-top: 0;
        padding: 0 1;
    }

    #detail-scroll {
        height: 12;
        min-height: 6;
        margin-top: 1;
        background: $surface;
        border: round #D0D7DE;
        padding: 1 2;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._df: pd.DataFrame = pd.DataFrame()
        self._filtered_df: pd.DataFrame = pd.DataFrame()

    def compose(self) -> ComposeResult:
        yield PageHeader(
            "Results",
            "Browse, filter, and inspect every model response.",
        )
        with Vertical(id="results-body"):
            with Horizontal(id="filter-bar"):
                yield Label("Task:")
                yield Select([("All tasks", "all")], value="all", id="task-filter")
                yield Label("Model:")
                yield Select([("All models", "all")], value="all", id="model-filter")
                yield Label("Score:")
                yield Select(
                    [("All", "all"), ("Pass ✓", "1"), ("Fail ✗", "0")],
                    value="all",
                    id="score-filter",
                )
                yield Button("Refresh", id="refresh-btn", variant="default")

            yield DataTable(id="results-table", cursor_type="row", zebra_stripes=True)
            yield Static("", id="stats-bar")
            yield Static(
                "Select a task above to pull results, then pick a row to read the full response.",
                id="detail-panel",
                markup=True,
            )

    def on_mount(self) -> None:
        table = self.query_one("#results-table", DataTable)
        table.add_columns("Score", "Task", "Model", "Question")

    def on_activate(self) -> None:
        if self._df.empty:
            self._load_all_outputs()
        else:
            self.query_one("#task-filter",  Select).value = "all"  # type: ignore[assignment]
            self.query_one("#model-filter", Select).value = "all"  # type: ignore[assignment]
            self.query_one("#score-filter", Select).value = "all"  # type: ignore[assignment]
            self._apply_filters(auto_select=True)
        self.query_one("#task-filter", Select).focus()

    # ------------------------------------------------------------------ #
    #  Data loading                                                        #
    # ------------------------------------------------------------------ #

    @work(thread=True, exclusive=True)
    def _load_all_outputs(self) -> None:
        from core.merger import discover_outputs, parse_run_json

        run_files = discover_outputs(config.output_dir)
        if not run_files:
            def _empty():
                self._df = pd.DataFrame()
                self.query_one("#results-table", DataTable).clear()
                self.query_one("#stats-bar").update(
                    "  No .run.json files found — pull a benchmark first."
                )
                self.query_one("#detail-panel").update(
                    "No data loaded. Go to Pull and download a benchmark."
                )
            self.app.call_from_thread(_empty)
            return

        rows = []
        for path in run_files:
            row, _ = parse_run_json(path)
            if row:
                rows.append(row)

        if not rows:
            return

        df = pd.DataFrame(rows).drop_duplicates(subset=["model_name", "question", "task_name"])
        # Failures first — that's what the user wants to investigate
        df = df.sort_values("score", ascending=True).reset_index(drop=True)

        tasks  = sorted(df["task_name"].unique().tolist())
        models = sorted(df["model_name"].unique().tolist())

        def _apply(df=df, tasks=tasks, models=models):
            self._df = df

            self.query_one("#task-filter", Select).set_options(
                [("All tasks", "all")] + [(t, t) for t in tasks]
            )
            self.query_one("#model-filter", Select).set_options(
                [("All models", "all")] + [(m.split("/")[-1], m) for m in models]
            )
            self._apply_filters(auto_select=True)

        self.app.call_from_thread(_apply)

    def _apply_filters(self, auto_select: bool = False) -> None:
        df = self._df.copy()

        task  = str(self.query_one("#task-filter",  Select).value)
        model = str(self.query_one("#model-filter", Select).value)
        score = str(self.query_one("#score-filter", Select).value)

        if task  != "all" and "task_name"  in df.columns:
            df = df[df["task_name"] == task]
        if model != "all" and "model_name" in df.columns:
            df = df[df["model_name"] == model]
        if score != "all" and "score" in df.columns:
            df = df[df["score"] == int(score)]

        self._filtered_df = df.reset_index(drop=True)
        self._populate_table(self._filtered_df, auto_select=auto_select)

    def _populate_table(self, df: pd.DataFrame, auto_select: bool = False) -> None:
        table = self.query_one("#results-table", DataTable)
        table.clear()

        def _trunc(val: str, n: int) -> str:
            return val[:n] + "…" if len(val) > n else val

        def _col(name: str) -> list:
            return df[name].fillna("").astype(str).tolist() if name in df.columns else [""] * len(df)

        score_vals = df["score"].tolist() if "score" in df.columns else [0] * len(df)
        scores  = ["✓" if int(s) == 1 else "✗" for s in score_vals]
        tasks   = _col("task_name")
        models  = [m.split("/")[-1] for m in _col("model_name")]
        qs      = [_trunc(q, 80) for q in _col("question")]

        table.add_rows(zip(scores, tasks, models, qs))

        total  = len(df)
        passed = int(sum(1 for s in score_vals if int(s) == 1))
        acc    = f"{passed / total * 100:.1f}%" if total > 0 else "—"
        self.query_one("#stats-bar").update(
            f"  {total} responses  ·  {passed} passed  ·  {total - passed} failed  ·  accuracy {acc}"
            "  —  ↑/↓ to browse, ← / → to switch filters"
        )

        if auto_select and not df.empty:
            table.move_cursor(row=0)
            self._show_detail(0)

    def _show_detail(self, idx: int) -> None:
        if self._filtered_df.empty or idx >= len(self._filtered_df):
            return
        row = self._filtered_df.iloc[idx]

        score_int = int(row.get("score", 0))
        score_str = "[green]✓ PASS[/green]" if score_int == 1 else "[red]✗ FAIL[/red]"
        task      = row.get("task_name", "")
        model     = str(row.get("model_name", "")).split("/")[-1]
        question  = str(row.get("question",  ""))
        response  = str(row.get("llm_response", ""))
        reasoning = str(row.get("reasoning", "")).strip()
        judge     = str(row.get("judge_model", "")).strip()

        lines = [
            f"[bold]Task:[/bold] {task}   [bold]Model:[/bold] {model}   [bold]Score:[/bold] {score_str}",
            "",
            f"[bold]Question:[/bold]  {question}",
            "",
            f"[bold]Response:[/bold]  {response}",
        ]
        if reasoning:
            lines += ["", f"[bold]Failed assertions:[/bold]  {reasoning}"]
        if judge:
            lines += ["", f"[dim]Judge: {judge}[/dim]"]

        self.query_one("#detail-panel").update("\n".join(lines))

    # ------------------------------------------------------------------ #
    #  Event handlers                                                      #
    # ------------------------------------------------------------------ #

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id in self._SELECT_IDS and not self._df.empty:
            self._apply_filters()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "refresh-btn":
            self.action_refresh()

    def action_refresh(self) -> None:
        self._df = pd.DataFrame()
        self._load_all_outputs()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self._show_detail(event.cursor_row)
