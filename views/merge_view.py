"""Merge view — combine multiple task output CSVs into SFT + preference datasets."""

from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.widgets import Button, Checkbox, Input, Label, Log, Static

from config import config
from core.merger import discover_outputs, merge_outputs, validate_run_json
from views.widgets import LogExpandIcon, PageHeader


class MergeView(Vertical):
    _BTN_IDS = ["merge-btn", "refresh-btn", "selectall-btn"]

    BINDINGS = [
        Binding("ctrl+l", "toggle_log_focus", "Expand log", show=True, key_display="Ctrl+L", priority=True),
        Binding("ctrl+a", "select_all", "Select all", show=True, key_display="Ctrl+A"),
        Binding("ctrl+m", "merge",      "Merge",      show=True, key_display="Ctrl+M"),
        Binding("ctrl+r", "refresh",    "Refresh",    show=True, key_display="Ctrl+R"),
        Binding("down",   "nav_down",   show=False),
        Binding("up",     "nav_up",     show=False),
        Binding("left",   "nav_left",   show=False),
        Binding("right",  "nav_right",  show=False),
        Binding("escape", "nav_esc",    show=False),
    ]

    def _fid(self) -> str | None:
        return self.app.focused.id if self.app.focused else None

    def _select_btn(self, btn_id: str) -> None:
        for bid in self._BTN_IDS:
            self.query_one(f"#{bid}", Button).variant = (
                "primary" if bid == btn_id else "default"
            )
        self.query_one(f"#{btn_id}", Button).focus()

    def _reset_btns(self) -> None:
        self._select_btn("merge-btn")

    def action_nav_down(self) -> None:
        if self._fid() in self._BTN_IDS:
            return
        self.app.action_focus_next()

    def action_nav_up(self) -> None:
        if self._fid() in self._BTN_IDS:
            self._reset_btns()
            self.query_one("#passing-only-switch", Checkbox).focus()
        else:
            self.app.action_focus_previous()

    def action_nav_left(self) -> None:
        fid = self._fid()
        if fid in self._BTN_IDS:
            idx = self._BTN_IDS.index(fid)
            self._select_btn(self._BTN_IDS[(idx - 1) % 3])

    def action_nav_right(self) -> None:
        fid = self._fid()
        if fid in self._BTN_IDS:
            idx = self._BTN_IDS.index(fid)
            self._select_btn(self._BTN_IDS[(idx + 1) % 3])

    def action_nav_esc(self) -> None:
        if self._fid() in self._BTN_IDS:
            self._reset_btns()
        self.app.action_unfocus()

    def action_toggle_log_focus(self) -> None:
        self.toggle_class("log-focused")

    DEFAULT_CSS = """
    MergeView { padding: 0; height: 1fr; }

    MergeView.log-focused #merge-controls { display: none; }

    #merge-body { padding: 1 3; height: 1fr; }

    /* Controls section shrinks to fit form; results section expands to fill */
    #merge-controls { height: auto; }
    #merge-results  { height: 1fr; }

    .section-title { color: #636E7B; text-style: bold; margin-bottom: 0; margin-top: 1; }

    #file-list {
        height: 6;
        min-height: 3;
        background: $surface;
        border: round #D0D7DE;
        padding: 0 1;
        margin-bottom: 0;
        overflow-y: auto;
    }

    #btn-row { layout: horizontal; height: 3; margin-top: 1; margin-bottom: 0; }
    #btn-row Button { margin-right: 1; }

    #merge-log {
        height: 1fr;
        min-height: 4;
        background: $surface;
        border: round #D0D7DE;
        margin-top: 0;
        padding: 0 1;
    }

    #stats-panel {
        height: auto;
        background: $surface;
        border: round #D0D7DE;
        padding: 1 2;
        margin-top: 1;
        color: #636E7B;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._checkboxes: dict[str, Checkbox] = {}
        self._listed_files: list[str] = []

    def compose(self) -> ComposeResult:
        yield PageHeader(
            "Merge",
            "Combine every pulled run into two research-ready datasets.",
        )
        with Vertical(id="merge-body"):
            with Vertical(id="merge-controls"):
                yield Static(
                    "Select pulled .run.json files to merge. Two files will be produced:\n"
                    "  + evalflow_sft.csv / .parquet           — SFT / fine-tuning format (passing responses)\n"
                    "  + evalflow_preferences.csv / .parquet   — DPO preference pairs (prompt/chosen/rejected)",
                    id="format-note",
                )

                yield Static("Select files to merge:", classes="section-title")
                yield ScrollableContainer(id="file-list")

                yield Checkbox("Remove duplicate rows", value=True, id="dedup-switch")
                yield Checkbox(
                    "SFT: include passing responses only  (recommended for fine-tuning)",
                    value=True,
                    id="passing-only-switch",
                )

                with Horizontal(id="btn-row"):
                    yield Button("Merge Selected", id="merge-btn", variant="primary")
                    yield Button("Refresh",        id="refresh-btn")
                    yield Button("Select All",     id="selectall-btn")

            with Vertical(id="merge-results"):
                with Horizontal(classes="log-header-row"):
                    yield Static("Merge Log", classes="section-title")
                    yield LogExpandIcon()
                yield Log(id="merge-log", highlight=True)
                yield Static("", id="stats-panel")

    def on_mount(self) -> None:
        pass  # start empty — user clicks Refresh after pulling

    def on_activate(self) -> None:
        self._refresh_file_list()
        self.query_one("#merge-btn", Button).focus()

    # ------------------------------------------------------------------ #
    #  File list                                                           #
    # ------------------------------------------------------------------ #

    def _refresh_file_list(self) -> None:
        self._checkboxes.clear()
        file_list = self.query_one("#file-list")
        file_list.remove_children()

        csvs = discover_outputs(config.output_dir)
        self._listed_files = [str(p) for p in csvs]
        if not csvs:
            file_list.mount(Static("  No .run.json files found. Pull some from Kaggle first."))
            return

        for path in csvs:
            ok, msg = validate_run_json(path)
            icon = "[+]" if ok else "[!]"
            label = f" {icon}  {path.name}" + (f"  [{msg}]" if not ok else "")
            cb = Checkbox(label, value=ok)
            self._checkboxes[str(path)] = cb
            file_list.mount(cb)

    # ------------------------------------------------------------------ #
    #  Event handlers                                                      #
    # ------------------------------------------------------------------ #

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "merge-btn":
            self._do_merge()
        elif event.button.id == "refresh-btn":
            self._listed_files = []
            self._refresh_file_list()
        elif event.button.id == "selectall-btn":
            self.action_select_all()
        self._reset_btns()
        self.app.set_focus(None)

    def action_select_all(self) -> None:
        for cb in self._checkboxes.values():
            cb.value = True

    def action_merge(self) -> None:
        self._do_merge()

    def action_refresh(self) -> None:
        self._listed_files = []
        self._refresh_file_list()

    # ------------------------------------------------------------------ #
    #  Merge                                                               #
    # ------------------------------------------------------------------ #

    def _do_merge(self) -> None:
        log = self.query_one("#merge-log", Log)
        log.clear()
        self.query_one("#stats-panel").update("")

        selected = [Path(p) for p, cb in self._checkboxes.items() if cb.value]
        if not selected:
            log.write_line("[x] No files selected.")
            return

        dedup        = self.query_one("#dedup-switch",        Checkbox).value
        passing_only = self.query_one("#passing-only-switch", Checkbox).value
        log.write_line(f"Merging {len(selected)} file(s) into outputs/\n")

        try:
            sft_df, pref_df, stats = merge_outputs(
                json_paths=selected,
                output_dir=config.output_dir,
                deduplicate=dedup,
                passing_only=passing_only,
            )

            sft_note = " (passing only)" if passing_only else " (all responses)"
            log.write_line(f"[ok] evalflow_sft.csv         — {len(sft_df)} rows{sft_note}")
            log.write_line(f"[ok] evalflow_preferences.csv — {len(pref_df)} preference pairs")
            if stats.get("parquet_written"):
                log.write_line("[ok] .parquet variants written  (type-safe, HuggingFace-ready)")

            if stats["files_skipped"]:
                log.write_line(f"[!]  {stats['files_skipped']} file(s) skipped:")
                for fname, reason in stats.get("skipped_details", []):
                    log.write_line(f"       {fname}: {reason}")
            if stats["duplicates_removed"]:
                log.write_line(f"  -  {stats['duplicates_removed']} duplicate rows removed")

            if pref_df.empty:
                log.write_line(
                    "\n[!]  No preference pairs generated.\n"
                    "   Pairs require the same question answered by >=2 models\n"
                    "   where at least one passed and one failed.\n"
                    "   Pull outputs from more models on Kaggle and merge again."
                )

            log.write_line(f"\n>>  Saved to {config.output_dir}/")
            log.write_line("   Switch to Publish tab to upload both files to Kaggle Datasets.")
            self.call_after_refresh(lambda: log.scroll_end(animate=False))

            # Summary panel
            pref_q = stats["pref_questions"]
            self.query_one("#stats-panel").update(
                f"  SFT rows        : {stats['total_rows']}\n"
                f"  Preference pairs: {stats['preference_pairs']}  "
                f"({pref_q} question{'s' if pref_q != 1 else ''} with paired responses)\n"
                f"  Models          : {stats['models']}\n"
                f"  Tasks           : {stats['tasks']}\n"
                f"  Avg accuracy    : {stats['accuracy']}%"
            )

            # Hand both paths to publish view
            try:
                publish = self.app.query_one("#publish")
                if hasattr(publish, "set_merged_csvs"):
                    publish.set_merged_csvs(
                        Path(stats["sft_path"]),
                        Path(stats["pref_path"]),
                    )
            except Exception:
                pass

        except Exception as exc:
            log.write_line(f"[x] Merge failed: {exc}")
            self.call_after_refresh(lambda: log.scroll_end(animate=False))
