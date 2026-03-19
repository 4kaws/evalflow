"""Results view — browse, filter, and inspect benchmark output CSVs."""

from pathlib import Path

import pandas as pd
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, DataTable, Label, Select, Static

from config import config


class ResultsView(Vertical):
    _SELECT_IDS = ["file-select", "model-filter", "score-filter"]

    BINDINGS = [
        Binding("ctrl+r", "refresh",  "Refresh", show=True, key_display="Ctrl+R"),
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
    ResultsView { padding: 0 1; height: 1fr; }
    .section-title { color: $primary; text-style: bold; margin-bottom: 0; margin-top: 0; }
    #filter-bar { height: 3; align: left middle; margin-bottom: 0; }
    #filter-bar Label { width: 10; color: $text-muted; }
    #filter-bar Select { width: 28; margin-right: 2; }
    #results-table { height: 1fr; min-height: 4; }
    #stats-bar {
        color: $text-muted;
        height: 2;
        margin-top: 0;
        padding: 0 1;
        background: $surface;
    }
    #refresh-btn { margin-left: 1; }
    #detail-panel {
        height: 1fr;
        min-height: 4;
        border: solid $primary 15%;
        padding: 1;
        margin-top: 0;
        background: $surface;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._df: pd.DataFrame = pd.DataFrame()
        self._filtered_df: pd.DataFrame = pd.DataFrame()

    def compose(self) -> ComposeResult:
        yield Static("Benchmark Results", classes="section-title")

        with Horizontal(id="filter-bar"):
            yield Label("File:")
            yield Select([], id="file-select")
            yield Label("Model:")
            yield Select([("All", "all")], value="all", id="model-filter")
            yield Label("Score:")
            yield Select(
                [("All", "all"), ("PASS ✅", "1"), ("FAIL ❌", "0")],
                value="all",
                id="score-filter",
            )
            yield Button("Refresh", id="refresh-btn", variant="default")

        yield DataTable(id="results-table", cursor_type="row", zebra_stripes=True)
        yield Static("", id="stats-bar")
        yield Static("Select a row to see full LLM response below.", id="detail-panel")

    def on_mount(self) -> None:
        table = self.query_one("#results-table", DataTable)
        table.add_columns("Task", "Model", "Score", "Question", "Ground Truth", "LLM Answer (preview)")

    def on_activate(self) -> None:
        self.query_one("#file-select", Select).focus()

    # ------------------------------------------------------------------ #
    #  File management                                                     #
    # ------------------------------------------------------------------ #

    def _refresh_files(self) -> None:
        output_dir = config.output_dir
        if not output_dir.exists():
            return

        csvs = sorted(output_dir.glob("*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not csvs:
            return

        file_select = self.query_one("#file-select", Select)
        file_select.set_options([(p.name, str(p)) for p in csvs])
        if csvs:
            file_select.value = str(csvs[0])
            self._load_file(csvs[0])

    def _load_file(self, path: Path) -> None:
        try:
            self._df = pd.read_csv(path)
        except Exception as exc:
            self.query_one("#stats-bar").update(f"❌ Failed to load: {exc}")
            return

        # Populate model filter
        if "model_name" in self._df.columns:
            models = self._df["model_name"].unique().tolist()
        elif "chosen_model" in self._df.columns:
            models = self._df["chosen_model"].unique().tolist()
        else:
            models = []
        self.query_one("#model-filter", Select).set_options(
            [("All", "all")] + [(m, m) for m in models]
        )

        self._apply_filters()

    def _apply_filters(self) -> None:
        df = self._df.copy()

        model = str(self.query_one("#model-filter", Select).value)
        score = str(self.query_one("#score-filter", Select).value)

        if model != "all" and "model_name" in df.columns:
            df = df[df["model_name"] == model]
        if score != "all" and "score" in df.columns:
            df = df[df["score"] == int(score)]

        self._filtered_df = df
        self._populate_table(df)

    def _populate_table(self, df: pd.DataFrame) -> None:
        table = self.query_one("#results-table", DataTable)
        table.clear()

        def _trunc(val: str, n: int) -> str:
            return val[:n] + "…" if len(val) > n else val

        def _col(name: str) -> list:
            return df[name].fillna("").astype(str).tolist() if name in df.columns else [""] * len(df)

        tasks   = _col("task_name")
        models  = [m.split("/")[-1] for m in _col("model_name")]
        scores  = ["pass" if s == 1 else "fail" for s in (df["score"].tolist() if "score" in df.columns else [0] * len(df))]
        qs      = [_trunc(q, 55) for q in _col("question")]
        gts     = [_trunc(g, 35) for g in _col("ground_truth")]
        answers = [_trunc(a, 55) for a in _col("llm_response")]

        table.add_rows(zip(tasks, models, scores, qs, gts, answers))

        total = len(df)
        passed = df["score"].sum() if "score" in df.columns else 0
        acc = f"{passed / total * 100:.1f}%" if total > 0 else "—"
        self.query_one("#stats-bar").update(
            f"  {total} rows  |  {passed} passed  |  {total - passed} failed  |  accuracy: {acc}"
        )

    # ------------------------------------------------------------------ #
    #  Event handlers                                                      #
    # ------------------------------------------------------------------ #

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "file-select" and event.value:
            self._load_file(Path(str(event.value)))
        elif event.select.id in ("model-filter", "score-filter"):
            self._apply_filters()

    def on_button_pressed(self, event: "Button.Pressed") -> None:
        if event.button.id == "refresh-btn":
            self.action_refresh()

    def action_refresh(self) -> None:
        self._df = pd.DataFrame()
        self._refresh_files()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if self._filtered_df.empty:
            return
        idx = event.cursor_row
        if idx >= len(self._filtered_df):
            return
        row = self._filtered_df.iloc[idx]
        detail = (
            f"[bold]Question:[/bold] {row.get('question', '')}\n\n"
            f"[bold]Ground Truth:[/bold] {row.get('ground_truth', '')}\n\n"
            f"[bold]LLM Response:[/bold] {str(row.get('llm_response', ''))[:400]}"
        )
        self.query_one("#detail-panel").update(detail)
