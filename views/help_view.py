"""Help view — keyboard-reference panel, opened with the ? key."""

from textual.app import ComposeResult
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.widgets import Button, Static


def _group(title: str, rows: list[tuple[str, str]]) -> str:
    """Render a shortcut group as Rich markup."""
    lines = [f"[bold #636E7B]{title}[/bold #636E7B]"]
    for key, desc in rows:
        if key:
            lines.append(f"  [bold $primary]{key:<12}[/bold $primary] {desc}")
        else:
            lines.append(f"  [dim]{desc}[/dim]")
    return "\n".join(lines)


HELP_SECTIONS = [
    _group("Navigation", [
        ("1 – 7",   "switch tab"),
        ("?",       "open / close this panel"),
        ("w",       "re-open setup wizard"),
        ("q",       "quit evalflow"),
        ("Esc",     "unfocus current field"),
    ]),
    _group("Within a page", [
        ("↑ / ↓",   "move between fields"),
        ("← / →",   "cycle between buttons / filters"),
        ("⏎",       "confirm / activate"),
        ("Ctrl+R",  "refresh (Results, Leaderboard, Run, Monitor)"),
        ("Ctrl+M",  "run merge (Merge tab)"),
        ("Ctrl+U",  "publish new (Publish tab)"),
    ]),
    _group("Workflow", [
        ("",  "1. Pull   → paste benchmark slug, hit ⏎"),
        ("",  "2. Results → inspect responses & failures"),
        ("",  "3. Leaderboard → cross-model accuracy"),
        ("",  "4. Merge  → build SFT + preference CSVs"),
        ("",  "5. Publish → upload to Kaggle Datasets"),
        ("",  "6. Run    → schedule runs on your own tasks"),
        ("",  "7. Monitor → set up daily auto-runs"),
    ]),
    _group("Output files", [
        ("",  "evalflow_sft.csv         — one row per passing response"),
        ("",  "evalflow_preferences.csv — chosen × rejected pairs"),
        ("",  "Both also produced as .parquet (requires pyarrow)"),
    ]),
    _group("Credentials", [
        ("",  "Set via setup wizard (w) or manually in .env:"),
        ("",  "  KAGGLE_USERNAME=your-username"),
        ("",  "  KAGGLE_KEY=your-legacy-api-key"),
        ("",  "Get key: kaggle.com → Settings → Legacy API"),
    ]),
]

HELP_TEXT = "\n\n".join(HELP_SECTIONS)


class HelpView(Vertical):
    BINDINGS = []

    DEFAULT_CSS = """
    HelpView {
        layer: overlay;
        align: center middle;
        background: $background 80%;
        width: 100%;
        height: 100%;
    }

    #help-box {
        width: 72;
        height: 88%;
        background: $surface;
        border: round #D0D7DE;
        padding: 0;
    }

    #help-header {
        height: 4;
        padding: 1 3;
        border-bottom: hkey #D0D7DE;
        align: left middle;
    }

    #help-title {
        width: 1fr;
        color: $foreground;
        text-style: bold;
        content-align: left middle;
    }

    #help-subtitle {
        width: 1fr;
        color: #636E7B;
        content-align: left middle;
    }

    #help-scroll {
        height: 1fr;
        padding: 2 3;
    }

    #help-close-row {
        height: 3;
        align: right middle;
        padding: 0 2;
        border-top: hkey #D0D7DE;
    }

    #help-close-btn {
        width: 18;
        border: round #D0D7DE;
        background: $surface;
        color: #636E7B;
    }

    #help-close-btn:hover {
        background: $boost;
        border: round #C8C8CC;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="help-box"):
            with Horizontal(id="help-header"):
                with Vertical():
                    yield Static("Keyboard reference",         id="help-title",    markup=True)
                    yield Static("Every action is keyboard-first.", id="help-subtitle", markup=True)
            yield ScrollableContainer(
                Static(HELP_TEXT, markup=True),
                id="help-scroll",
            )
            with Horizontal(id="help-close-row"):
                yield Button("Close  Esc / ?", id="help-close-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "help-close-btn":
            self.app.action_toggle_help()  # type: ignore
