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
  1  ⬇  Pull        Auto-discover and pull all task CSVs from a benchmark
  2  📊 Results     Browse, filter, and inspect pulled CSVs
  3  🏅 Leaderboard Cross-model accuracy ranking + per-question diff
  4  🔗 Merge       Produce evalflow_sft.csv and evalflow_preferences.csv
  5  🚀 Publish     Upload both files to Kaggle Datasets
  ?  Help           Show in-app help panel
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
from textual.widgets import ContentSwitcher, Footer, Static

from views.help_view import HelpView
from views.leaderboard_view import LeaderboardView
from views.merge_view import MergeView
from views.publish_view import PublishView
from views.pull_view import PullView
from views.results_view import ResultsView

EVALFLOW_THEME = Theme(
    name="evalflow",
    primary="#58a6ff",      # light blue
    secondary="#79c0ff",    # lighter blue
    warning="#d29922",      # amber
    error="#f85149",        # soft red
    success="#3fb950",      # green
    accent="#1f6feb",       # deep blue accent
    foreground="#e6edf3",   # near-white text
    background="#0d1117",   # near-black
    surface="#161b22",      # dark surface
    panel="#21262d",        # panel bg
    boost="#30363d",        # hover highlight
    dark=True,
)

NAV_ITEMS = [
    ("pull",        "Pull",        "1"),
    ("results",     "Results",     "2"),
    ("leaderboard", "Leaderboard", "3"),
    ("merge",       "Merge",       "4"),
    ("publish",     "Publish",     "5"),
]


class NavItem(Static):
    DEFAULT_CSS = """
    NavItem {
        padding: 0 2;
        color: $text-muted;
        height: 3;
        content-align: left middle;
    }
    NavItem:hover { background: $boost; color: $text; }
    NavItem.active {
        color: $primary;
        background: $primary 8%;
        border-left: outer $primary;
    }
    """

    def __init__(self, view_id: str, label: str, key: str):
        super().__init__(f"[dim]{key}[/dim]  {label}")
        self.view_id = view_id

    def on_click(self) -> None:
        self.app.switch_view(self.view_id)  # type: ignore


class EvalflowApp(App):
    """Evalflow — Kaggle Benchmark Puller & Dataset Publisher"""

    ENABLE_COMMAND_PALETTE = False
    LAYERS = ["default", "overlay"]

    CSS = """
    Screen { layout: vertical; }

    #app-header {
        height: 3;
        background: $surface;
        border: solid $primary 15%;
        content-align: center middle;
        color: $foreground;
        text-align: center;
    }

    #sidebar {
        width: 16;
        background: $background;
        border-right: solid $panel;
        padding-top: 1;
    }
    #sidebar-hint {
        padding: 1 2 0 2;
        color: $text-muted;
    }
    #main-layout { layout: horizontal; height: 1fr; }
    #content { width: 1fr; height: 1fr; background: $background; }
    ContentSwitcher { height: 1fr; }

    HelpView {
        layer: overlay;
        display: none;
    }
    HelpView.visible {
        display: block;
    }
    """

    BINDINGS = [
        Binding("q",      "quit",            "Quit",        show=True),
        Binding("?",      "toggle_help",     "Help",        show=True),
        Binding("1",      "nav_pull",        "Pull",        show=True),
        Binding("2",      "nav_results",     "Results",     show=True),
        Binding("3",      "nav_leaderboard", "Leaderboard", show=True),
        Binding("4",      "nav_merge",       "Merge",       show=True),
        Binding("5",      "nav_publish",     "Publish",     show=True),
        Binding("escape", "unfocus",         "Unfocus",     show=False),
        Binding("down",   "focus_next",      "",            show=False),
        Binding("up",     "focus_previous",  "",            show=False),
    ]

    def on_mount(self) -> None:
        self.register_theme(EVALFLOW_THEME)
        self.theme = "evalflow"
        # Clean outputs from the previous session so every run starts fresh.
        # .env (credentials) lives outside output_dir and is never touched.
        import shutil
        from config import config
        if config.output_dir.exists():
            shutil.rmtree(config.output_dir, ignore_errors=True)

    def compose(self) -> ComposeResult:
        yield Static(
            "[bold $primary]E  V  A  L  F  L  O  W[/bold $primary]"
            "   [dim]kaggle benchmark puller & dataset publisher[/dim]",
            id="app-header",
            markup=True,
        )
        with Horizontal(id="main-layout"):
            with Vertical(id="sidebar"):
                for view_id, label, key in NAV_ITEMS:
                    item = NavItem(view_id, label, key)
                    if view_id == "pull":
                        item.add_class("active")
                    yield item
                yield Static(
                    "[dim]─────────────────\n?  Help\nq  Quit\nEsc  Unfocus[/dim]",
                    id="sidebar-hint",
                )
            with ContentSwitcher(id="content", initial="pull"):
                yield PullView(id="pull")
                yield ResultsView(id="results")
                yield LeaderboardView(id="leaderboard")
                yield MergeView(id="merge")
                yield PublishView(id="publish")
        yield Footer()
        yield HelpView(id="help-overlay")   # rendered on overlay layer

    def switch_view(self, view_id: str) -> None:
        self.query_one(ContentSwitcher).current = view_id
        for item in self.query(NavItem):
            item.remove_class("active")
            if item.view_id == view_id:
                item.add_class("active")
        view = self.query_one(f"#{view_id}")
        if hasattr(view, "on_activate"):
            view.on_activate()
        # Drop focus so 1–5 keys keep working after switching
        self.set_focus(None)

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


# ------------------------------------------------------------------ #
#  Entry point                                                        #
# ------------------------------------------------------------------ #

if __name__ == "__main__":
    args = parse_args()   # handles --help and --version before TUI starts

    from setup_wizard import SetupWizard
    if not args.no_wizard:
        SetupWizard().run()

    EvalflowApp().run()
