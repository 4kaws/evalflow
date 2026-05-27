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
from textual.containers import Horizontal, Vertical
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

# Pixel-art goose: head top-left, diagonal neck, wide oval body, two feet.
GOOSE = "     ▄▄▄\n  ▄▄██▀██\n    ▀▀██▀\n      ▀█▄\n        ▀█▄\n   ▄████████▄\n  ████████████\n   ▀▀█▀▀▀▀█▀▀"

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


class NavItem(Static):
    DEFAULT_CSS = """
    NavItem {
        width: 100%;
        height: 3;
        padding: 0 2;
        background: transparent;
        color: #636E7B;
        content-align: left middle;
    }
    NavItem:hover {
        background: $boost;
        color: $foreground;
    }
    NavItem.active {
        background: $primary;
        color: white;
    }
    NavItem.small {
        height: 2;
    }
    NavItem.danger {
        color: #636E7B;
    }
    NavItem.danger:hover {
        color: $error;
        background: $boost;
    }
    """

    def __init__(
        self,
        view_id: str,
        label: str,
        key: str,
        app_action: str = "",
        small: bool = False,
        danger: bool = False,
    ):
        super().__init__(f"[dim]{key}[/dim]  {label}", markup=True)
        self.view_id    = view_id
        self._app_action = app_action
        if small:
            self.add_class("small")
        if danger:
            self.add_class("danger")

    def on_click(self) -> None:
        if self._app_action:
            self.app.run_action(self._app_action)  # type: ignore
        elif self.view_id:
            self.app.switch_view(self.view_id)  # type: ignore


class BrandHeader(Horizontal):
    DEFAULT_CSS = """
    BrandHeader {
        width: 100%;
        height: 11;
        padding: 1 2;
        background: $panel;
        border-bottom: hkey #D0D7DE;
        align: left top;
    }
    BrandHeader #brand-goose {
        width: 15;
        height: 8;
        content-align: left top;
        background: transparent;
        color: #20BEFF;
    }
    BrandHeader #brand-name {
        width: 1fr;
        height: 8;
        padding: 0 0 0 1;
        content-align: left middle;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static(GOOSE, id="brand-goose")
        yield Static(
            f"[bold]evalflow[/bold]\n[dim]v{__version__}[/dim]",
            markup=True,
            id="brand-name",
        )


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
            "[dim]1–7[/dim] tabs  [dim]↑↓[/dim] navigate  [dim]?[/dim] help  [dim]q[/dim] quit"
        )
        label = _VIEW_LABELS.get(view_id, "")
        self.query_one("#sb-right",  Static).update(f"evalflow · {label}")


class EvalflowApp(App):
    """Evalflow — Kaggle Benchmark Puller & Dataset Publisher"""

    ENABLE_COMMAND_PALETTE = False
    LAYERS = ["default", "overlay"]

    CSS = """
    Screen { layout: vertical; }

    #app-shell {
        height: 1fr;
        layout: horizontal;
    }

    /* ── Sidebar ────────────────────────────────────────────── */
    #sidebar {
        width: 32;
        height: 100%;
        background: $panel;
        border-right: hkey #D0D7DE;
    }

    #sidebar-nav {
        height: auto;
        padding: 1 0;
        background: $panel;
    }

    #sidebar-spacer { height: 1fr; }

    #sidebar-foot {
        height: auto;
        padding: 1 0;
        border-top: hkey #D0D7DE;
        background: $panel;
    }

    /* ── Main column ────────────────────────────────────────── */
    #main {
        height: 100%;
        width: 1fr;
        background: $background;
    }

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
    /* narrow: < 110 cols — shrink sidebar, stack monitor panes  */
    App.narrow #sidebar { width: 22; }
    App.narrow #monitor-body { layout: vertical; }
    App.narrow #monitor-left {
        border-right: none;
        border-bottom: hkey #D0D7DE;
        height: auto;
    }
    App.narrow #monitor-right { height: 1fr; }
    App.narrow .field-label { width: 14; }
    App.narrow #tz-select { width: 1fr; max-width: 24; }

    /* tiny: < 85 cols — compact sidebar, smaller labels         */
    App.tiny #sidebar { width: 14; }
    App.tiny .field-label { width: 10; padding-right: 1; }
    App.tiny #help-box { width: 95%; }

    /* short: < 42 rows — shrink fixed-size form widgets         */
    App.short #tasks-table   { height: 4; }
    App.short #models-list   { height: 4; }
    App.short #watcher-table { height: 4; }
    App.short #run-top       { height: 10; }
    App.short #runs-table    { height: 3; }

    /* tall: >= 55 rows — grow watcher table and run controls    */
    App.tall  #watcher-table { height: 10; }
    App.tall  #run-top       { height: 20; }
    App.tall  #runs-table    { height: 8; }
    """

    BINDINGS = [
        Binding("q",      "quit",            "Quit",        show=False),
        Binding("?",      "toggle_help",     "Help",        show=False),
        Binding("w",      "open_wizard",     "Setup",       show=False),
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

    def on_resize(self, event: Resize) -> None:
        w = event.size.width
        h = event.size.height
        self.set_class(w < 110, "narrow")
        self.set_class(w < 85,  "tiny")
        self.set_class(h < 42,  "short")
        self.set_class(h >= 55, "tall")

    def on_mount(self) -> None:
        self.register_theme(EVALFLOW_THEME)
        self.theme = "evalflow"
        # Wipe outputs from last session so every run starts fresh.
        import shutil
        from config import config
        if config.output_dir.exists():
            shutil.rmtree(config.output_dir, ignore_errors=True)

    def compose(self) -> ComposeResult:
        with Horizontal(id="app-shell"):
            with Vertical(id="sidebar"):
                yield BrandHeader()
                with Vertical(id="sidebar-nav"):
                    for view_id, label, key, hint in NAV_ITEMS:
                        item = NavItem(view_id, label, key)
                        if view_id == "pull":
                            item.add_class("active")
                        yield item
                yield Static("", id="sidebar-spacer")
                with Vertical(id="sidebar-foot"):
                    yield NavItem("", "Help",         "?", app_action="toggle_help",  small=True)
                    yield NavItem("", "Setup wizard", "w", app_action="open_wizard",  small=True)
                    yield NavItem("", "Quit",         "q", app_action="quit",         small=True, danger=True)
            with Vertical(id="main"):
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
        for item in self.query(NavItem):
            if not item.has_class("small"):
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
