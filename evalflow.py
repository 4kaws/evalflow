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
from textual.theme import Theme
from textual.widgets import ContentSwitcher, Static

from views.help_view import HelpView
from views.leaderboard_view import LeaderboardView
from views.merge_view import MergeView
from views.monitor_view import MonitorView
from views.publish_view import PublishView
from views.pull_view import PullView
from views.results_view import ResultsView

EVALFLOW_THEME = Theme(
    name="evalflow",
    primary    = "#0071E3",
    secondary  = "#7DC8E8",
    accent     = "#0077ED",
    foreground = "#1D1D1F",
    background = "#F5F5F7",
    surface    = "#FFFFFF",
    panel      = "#FBFBFD",
    boost      = "#F0F0F2",
    success    = "#34C759",
    warning    = "#FF9500",
    error      = "#FF3B30",
    dark       = False,
)

# 4-row goose, brand-blue (#7DC8E8), facing right.
GOOSE = (
    " [#7DC8E8]▄██[/#7DC8E8]\n"
    "[#7DC8E8]▄███[/#7DC8E8]\n"
    "[#7DC8E8]████▀[/#7DC8E8]\n"
    " [#7DC8E8]▌ ▌[/#7DC8E8]"
)

NAV_ITEMS = [
    ("pull",        "Pull",        "1", "download runs"),
    ("results",     "Results",     "2", "browse responses"),
    ("leaderboard", "Leaderboard", "3", "model ranking"),
    ("merge",       "Merge",       "4", "build datasets"),
    ("publish",     "Publish",     "5", "upload to kaggle"),
    ("monitor",     "Monitor",     "6", "daily watchers"),
]

_VIEW_LABELS = {v[0]: v[1] for v in NAV_ITEMS}


class NavItem(Static):
    DEFAULT_CSS = """
    NavItem {
        width: 100%;
        height: 3;
        padding: 0 2;
        background: transparent;
        color: #86868B;
        content-align: left middle;
        border-left: thick $panel;
    }
    NavItem:hover {
        background: $boost;
        color: $foreground;
        border-left: thick #B0B0B8;
    }
    NavItem.active {
        background: $primary 15%;
        color: $primary;
        text-style: bold;
        border-left: thick $primary;
    }
    NavItem.small {
        height: 2;
    }
    NavItem.danger {
        color: #FF3B30;
    }
    NavItem.danger:hover {
        color: #FF3B30;
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
        height: 6;
        padding: 1 2;
        background: $panel;
        border-bottom: hkey #E5E5E7;
        align: left middle;
    }
    BrandHeader #brand-goose {
        width: 7;
        height: 4;
        content-align: left top;
    }
    BrandHeader #brand-name {
        width: 1fr;
        height: 4;
        padding: 0 0 0 1;
        content-align: left middle;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static(GOOSE, markup=True, id="brand-goose")
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
        border-top: hkey #E5E5E7;
        color: #86868B;
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
            "[dim]1–6[/dim] tabs  [dim]↑↓[/dim] navigate  [dim]?[/dim] help  [dim]q[/dim] quit"
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
        width: 28;
        height: 100%;
        background: $panel;
        border-right: hkey #E5E5E7;
    }

    #sidebar-nav {
        height: 1fr;
        padding: 1 0;
        background: $panel;
        overflow: hidden hidden;
    }

    #sidebar-spacer { height: 1fr; }

    #sidebar-foot {
        height: auto;
        padding: 1 0;
        border-top: hkey #E5E5E7;
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

    /* ── Global button defaults for light mode ──────────────── */
    Button {
        border: round #E5E5E7;
        background: $surface;
        color: #1D1D1F;
    }
    Button:hover {
        background: $boost;
        border: round #C8C8CC;
        color: #1D1D1F;
    }
    Button:focus {
        border: round $primary 60%;
        color: #1D1D1F;
    }
    Button.-primary {
        background: $primary 15%;
        color: $primary;
        border: round $primary 40%;
    }
    Button.-primary:hover {
        background: $primary 25%;
        border: round $primary 60%;
        color: $primary;
    }
    Button.-primary:focus {
        border: round $primary 90%;
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
        Binding("6",      "nav_monitor",     "Monitor",     show=False),
        Binding("escape", "unfocus",         "Unfocus",     show=False),
        Binding("down",   "focus_next",      "",            show=False),
        Binding("up",     "focus_previous",  "",            show=False),
    ]

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
