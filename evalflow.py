#!/usr/bin/env python3
"""
Evalflow — Kaggle Benchmark Puller & Dataset Publisher

Usage:
    python evalflow.py            Launch the TUI (setup wizard on first run)
    python evalflow.py --help     Show this help and exit
    python evalflow.py --version  Show version and exit

Headless / CI usage:
    python ci_runner.py --help
"""

import argparse
import sys

__version__ = "0.2.0"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="evalflow",
        description=(
            "Evalflow — pull Kaggle Community Benchmark results, merge them\n"
            "into SFT and preference-pair datasets, and publish to Kaggle Datasets."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
workflow:
  1. Write task notebooks on Kaggle using notebooks/notebook_template.ipynb
  2. Group them into a Benchmark on kaggle.com/benchmarks
  3. Click "Add Models" — Kaggle runs them for free
  4. Open Evalflow → Pull → paste your benchmark slug
  5. Merge → produces evalflow_sft.csv + evalflow_preferences.csv
  6. Publish → uploads both to Kaggle Datasets

tabs (keyboard shortcuts):
  1  Pull        Auto-discover and pull all task CSVs from a benchmark
  2  Results     Browse, filter, and inspect pulled CSVs
  3  Leaderboard Cross-model accuracy ranking + per-question diff
  4  Merge       Produce evalflow_sft.csv and evalflow_preferences.csv
  5  Publish     Upload both files to Kaggle Datasets
  6  Monitor     Watch benchmarks on a daily schedule
  ?  Help        Show in-app help panel
  q  Quit

credentials:
  Set KAGGLE_USERNAME and KAGGLE_KEY in .env, or run the setup wizard
  (launches automatically on first run when no .env is found).
  Get your API key at: kaggle.com → Settings → API → Create New Token

headless / ci:
  python ci_runner.py --help   pull + merge + publish without the TUI
        """,
    )
    p.add_argument(
        "--version", "-v",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    p.add_argument(
        "--no-wizard",
        action="store_true",
        help="Skip the setup wizard even if .env is missing",
    )
    return p.parse_args()


# ------------------------------------------------------------------ #
#  TUI                                                                #
# ------------------------------------------------------------------ #

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.events import Resize
from textual.theme import Theme
from textual.widgets import ContentSwitcher, Static

from views.help_view import HelpView
from views.leaderboard_view import LeaderboardView
from views.merge_view import MergeView
from views.monitor_view import MonitorView
from views.publish_view import PublishView
from views.pull_view import PullView
from views.results_view import ResultsView
from views.run_view import RunView

EVALFLOW_THEME = Theme(
    name="evalflow",
    primary    = "#0969DA",
    secondary  = "#0550AE",
    accent     = "#0969DA",
    foreground = "#1F2328",
    background = "#F6F8FA",
    surface    = "#FFFFFF",
    panel      = "#FFFFFF",
    boost      = "#F3F4F6",
    success    = "#1A7F37",
    warning    = "#9A6700",
    error      = "#CF222E",
    dark       = False,
)

NAV_ITEMS = [
    ("pull",        "Pull",        "1", "download runs"),
    ("results",     "Results",     "2", "browse responses"),
    ("leaderboard", "Leaderboard", "3", "model ranking"),
    ("merge",       "Merge",       "4", "build datasets"),
    ("publish",     "Publish",     "5", "upload to kaggle"),
    ("run",         "Run",         "6", "schedule own tasks"),
    ("monitor",     "Monitor",     "7", "daily watchers"),
]

_VIEW_LABELS = {v[0]: v[1] for v in NAV_ITEMS}


class TabItem(Static):
    DEFAULT_CSS = """
    TabItem {
        width: auto;
        height: 1;
        padding: 0 2;
        background: transparent;
        color: #636E7B;
        content-align: left middle;
    }
    TabItem:hover {
        background: $boost;
        color: $foreground;
    }
    TabItem.active {
        background: $primary;
        color: white;
    }
    """

    def __init__(self, view_id: str, label: str, key: str) -> None:
        super().__init__(f"[dim]{key}[/dim]  {label}", markup=True)
        self.view_id = view_id
        self._key    = key
        self._label  = label

    def set_compact(self, compact: bool) -> None:
        if compact:
            self.update(self._key)
            self.styles.padding = (0, 1, 0, 1)
        else:
            self.update(f"[dim]{self._key}[/dim]  {self._label}")
            self.styles.padding = (0, 2, 0, 2)

    def on_click(self) -> None:
        self.app.switch_view(self.view_id)  # type: ignore


class TabBar(Horizontal):
    DEFAULT_CSS = """
    TabBar {
        width: 100%;
        height: 1;
        background: $panel;
    }
    """

    def compose(self) -> ComposeResult:
        for view_id, label, key, _hint in NAV_ITEMS:
            item = TabItem(view_id, label, key)
            if view_id == "pull":
                item.add_class("active")
            yield item


class StatusBar(Horizontal):
    DEFAULT_CSS = """
    StatusBar {
        height: 1;
        background: $panel;
        border-top: hkey #D0D7DE;
        color: #636E7B;
    }
    StatusBar #sb-left {
        width: auto;
        padding: 0 2;
        content-align: left middle;
    }
    StatusBar #sb-center {
        width: 1fr;
        padding: 0 2;
        content-align: center middle;
    }
    StatusBar #sb-right {
        width: auto;
        padding: 0 2;
        content-align: right middle;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("", id="sb-left",   markup=True)
        yield Static("", id="sb-center", markup=True)
        yield Static("", id="sb-right",  markup=True)

    def on_mount(self) -> None:
        self.refresh_status("pull")

    def refresh_status(self, view_id: str) -> None:
        from config import config
        kaggle_ok = bool(config.kaggle_username and config.kaggle_key)
        dot = "[#34C759]●[/#34C759]" if kaggle_ok else "[#FF3B30]●[/#FF3B30]"
        self.query_one("#sb-left",   Static).update(f"{dot} kaggle")
        self.query_one("#sb-center", Static).update(
            "[dim]1–7[/dim] tabs  [dim]?[/dim] help  [dim]q[/dim] quit"
        )
        label = _VIEW_LABELS.get(view_id, "")
        self.query_one("#sb-right",  Static).update(f"evalflow · {label}")


class EvalflowApp(App):
    """Evalflow — Kaggle Benchmark Puller & Dataset Publisher"""

    ENABLE_COMMAND_PALETTE = False
    LAYERS = ["default", "overlay"]

    CSS = """
    Screen { layout: vertical; }

    ContentSwitcher {
        height: 1fr;
        background: $background;
    }

    /* ── Global button defaults ─────────────────────────────── */
    Button {
        border: round #D0D7DE;
        background: $surface;
        color: #636E7B;
    }
    Button:hover {
        background: $boost;
        border: round $primary;
        color: $primary;
    }
    Button:focus {
        border: round $primary;
        color: $primary;
    }
    Button.-primary {
        background: $primary;
        color: white;
        border: round $primary;
    }
    Button.-primary:hover {
        background: $primary;
        border: round $primary;
        color: white;
    }
    Button.-primary:focus {
        border: round $primary;
    }
    Button.-active {
        background: $boost;
    }

    /* ── Help overlay ───────────────────────────────────────── */
    HelpView {
        layer: overlay;
        display: none;
    }
    HelpView.visible {
        display: block;
    }

    /* ── Log header row (title + expand icon) ───────────────── */
    .log-header-row {
        height: 2;
        margin-top: 1;
        align: left middle;
    }
    .log-header-row .section-title {
        width: 1fr;
        margin-top: 0;
        height: 2;
        content-align: left middle;
    }

    /* ── Responsive breakpoints ─────────────────────────────── */
    /* narrow: < 110 cols — stack monitor panes                  */
    App.narrow #monitor-body { layout: vertical; }
    App.narrow #monitor-left {
        border-right: none;
        border-bottom: hkey #D0D7DE;
        height: auto;
    }
    App.narrow #monitor-right { height: 1fr; }
    App.narrow .field-label { width: 14; }
    App.narrow #tz-select { width: 1fr; max-width: 24; }

    /* tiny: < 85 cols — compact form labels                     */
    App.tiny .field-label { width: 10; padding-right: 1; }
    App.tiny #help-box { width: 95%; }

    /* short: < 42 rows — shrink fixed-size form widgets         */
    App.short #tasks-table   { height: 4; }
    App.short #models-list   { height: 4; }
    App.short #watcher-table { height: 4; }
    App.short #run-top       { height: 10; }
    App.short #runs-table    { height: 3; }
    App.short PageHeader               { min-height: 3; padding: 0 2; }
    App.short PageHeader #ph-subtitle  { display: none; }
    App.short #pull-body               { padding: 0 2; }
    App.short #merge-body              { padding: 0 2; }
    App.short #run-body                { padding: 0 2; }
    App.short #publish-body            { padding: 0 2; }

    /* tall: >= 55 rows — grow watcher table and run controls    */
    App.tall  #watcher-table { height: 10; }
    App.tall  #run-top       { height: 20; }
    App.tall  #runs-table    { height: 8; }
    """

    BINDINGS = [
        Binding("q",      "quit",                      "Quit",         show=False),
        Binding("?",      "toggle_help",               "Help",         show=False),
        Binding("w",      "open_wizard",               "Setup",        show=False),
        Binding("ctrl+l", "toggle_current_log_focus",  "Expand log",   show=False),
        Binding("1",      "nav_pull",        "Pull",        show=False),
        Binding("2",      "nav_results",     "Results",     show=False),
        Binding("3",      "nav_leaderboard", "Leaderboard", show=False),
        Binding("4",      "nav_merge",       "Merge",       show=False),
        Binding("5",      "nav_publish",     "Publish",     show=False),
        Binding("6",      "nav_run",         "Run",         show=False),
        Binding("7",      "nav_monitor",     "Monitor",     show=False),
        Binding("escape", "unfocus",         "Unfocus",     show=False),
        Binding("down",   "focus_next",      "",            show=False),
        Binding("up",     "focus_previous",  "",            show=False),
    ]

    def _apply_responsive(self) -> None:
        w, h = self.size.width, self.size.height
        self.set_class(w < 110, "narrow")
        self.set_class(w < 85,  "tiny")
        self.set_class(h < 42,  "short")
        self.set_class(h >= 55, "tall")
        compact = w < 85
        for tab in self.query(TabItem):
            tab.set_compact(compact)

    def on_resize(self, event: Resize) -> None:
        w, h = event.size.width, event.size.height
        self.set_class(w < 110, "narrow")
        self.set_class(w < 85,  "tiny")
        self.set_class(h < 42,  "short")
        self.set_class(h >= 55, "tall")
        compact = w < 85
        for tab in self.query(TabItem):
            tab.set_compact(compact)

    def on_mount(self) -> None:
        self.register_theme(EVALFLOW_THEME)
        self.theme = "evalflow"
        # Apply responsive classes for initial terminal size (on_resize may fire
        # before the first full render cycle so we also apply after refresh).
        self.call_after_refresh(self._apply_responsive)
        # Wipe outputs from last session so every run starts fresh.
        import shutil
        from config import config
        if config.output_dir.exists():
            shutil.rmtree(config.output_dir, ignore_errors=True)

    def compose(self) -> ComposeResult:
        yield TabBar()
        with ContentSwitcher(id="content", initial="pull"):
            yield PullView(id="pull")
            yield ResultsView(id="results")
            yield LeaderboardView(id="leaderboard")
            yield MergeView(id="merge")
            yield PublishView(id="publish")
            yield RunView(id="run")
            yield MonitorView(id="monitor")
        yield StatusBar()
        yield HelpView(id="help-overlay")

    def switch_view(self, view_id: str) -> None:
        self.query_one(ContentSwitcher).current = view_id
        for item in self.query(TabItem):
            item.remove_class("active")
            if item.view_id == view_id:
                item.add_class("active")
        view = self.query_one(f"#{view_id}")
        if hasattr(view, "on_activate"):
            view.on_activate()
        self.set_focus(None)
        self.query_one(StatusBar).refresh_status(view_id)

    def action_unfocus(self) -> None:
        """Escape — close help if open, otherwise blur the focused widget."""
        overlay = self.query_one("#help-overlay", HelpView)
        if "visible" in overlay.classes:
            overlay.remove_class("visible")
            return
        self.set_focus(None)

    def action_toggle_help(self) -> None:
        overlay = self.query_one("#help-overlay", HelpView)
        overlay.toggle_class("visible")
        if "visible" in overlay.classes:
            overlay.query_one("#help-scroll").focus()

    def action_toggle_current_log_focus(self) -> None:
        current = self.query_one(ContentSwitcher).current
        if not current:
            return
        try:
            view = self.query_one(f"#{current}")
            if hasattr(view, "action_toggle_log_focus"):
                view.action_toggle_log_focus()
        except Exception:
            pass

    def action_nav_pull(self):        self.switch_view("pull")
    def action_nav_results(self):     self.switch_view("results")
    def action_nav_leaderboard(self): self.switch_view("leaderboard")
    def action_nav_merge(self):       self.switch_view("merge")
    def action_nav_publish(self):     self.switch_view("publish")
    def action_nav_run(self):         self.switch_view("run")
    def action_nav_monitor(self):     self.switch_view("monitor")

    async def action_open_wizard(self) -> None:
        from setup_wizard import SetupWizard
        with self.app.suspend():
            await SetupWizard().run_async()
        from dotenv import load_dotenv
        import config as _cfg
        load_dotenv(override=True)
        _cfg.config.__dict__.update(_cfg.Config.load().__dict__)
        # Refresh status bar after potential credential update
        self.query_one(StatusBar).refresh_status(
            self.query_one(ContentSwitcher).current or "pull"
        )


# ------------------------------------------------------------------ #
#  Entry point                                                        #
# ------------------------------------------------------------------ #

if __name__ == "__main__":
    args = parse_args()

    from setup_wizard import SetupWizard, should_run_wizard
    if not args.no_wizard and should_run_wizard():
        SetupWizard().run()
        from dotenv import load_dotenv
        import config as _cfg
        load_dotenv(override=True)
        _cfg.config.__dict__.update(_cfg.Config.load().__dict__)

    EvalflowApp().run()
