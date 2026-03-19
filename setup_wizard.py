"""
Setup Wizard — shown on first run when credentials are not configured.
Guides the user through setting MODEL_PROXY_API_KEY and KAGGLE_* credentials,
then writes a .env file and re-launches the main app.
"""

import os
from pathlib import Path

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.theme import Theme
from textual.widgets import Button, Input, Label, Static

EVALFLOW_THEME = Theme(
    name="evalflow",
    primary="#58a6ff",
    secondary="#79c0ff",
    warning="#d29922",
    error="#f85149",
    success="#3fb950",
    accent="#1f6feb",
    foreground="#e6edf3",
    background="#0d1117",
    surface="#161b22",
    panel="#21262d",
    boost="#30363d",
    dark=True,
)

_ASCII_LOGO = """\
[bold $primary]███████╗██╗   ██╗ █████╗ ██╗     ███████╗██╗      ██████╗ ██╗    ██╗[/bold $primary]
[bold $primary]██╔════╝██║   ██║██╔══██╗██║     ██╔════╝██║     ██╔═══██╗██║    ██║[/bold $primary]
[bold $primary]█████╗  ╚██╗ ██╔╝███████║██║     █████╗  ██║     ██║   ██║██║ █╗ ██║[/bold $primary]
[bold $primary]██╔══╝   ╚████╔╝ ██╔══██║██║     ██╔══╝  ██║     ██║   ██║██║███╗██║[/bold $primary]
[bold $primary]███████╗  ╚██╔╝  ██║  ██║███████╗██║     ███████╗╚██████╔╝╚███╔███╔╝[/bold $primary]
[bold $primary]╚══════╝   ╚═╝   ╚═╝  ╚═╝╚══════╝╚═╝     ╚══════╝ ╚═════╝  ╚══╝╚══╝[/bold $primary]\
"""


ENV_FILE = Path(".env")

STEPS = [
    "welcome",
    "kaggle_api",
    "done",
]


class WizardStep(Vertical):
    DEFAULT_CSS = """
    WizardStep {
        width: 1fr;
        border: round $primary;
        padding: 2 4;
        background: $surface;
        margin-bottom: 1;
        height: auto;
    }
    WizardStep .step-title {
        color: $primary;
        text-style: bold;
        margin-bottom: 1;
    }
    WizardStep #wizard-logo {
        margin-bottom: 1;
    }
    WizardStep .step-body {
        color: $text;
        margin-bottom: 2;
    }
    WizardStep .field-label {
        color: $text;
        margin-bottom: 0;
    }
    WizardStep Input { margin-bottom: 1; width: 100%; }
    WizardStep Log { height: 10; }
    """


class SetupWizard(App):
    """First-run setup wizard for Evalflow."""

    CSS = """
    Screen { align: center middle; background: $background; }

    #wizard-container {
        width: 100%;
        height: auto;
        max-height: 95vh;
        padding: 0 2;
    }

    #step-counter {
        text-align: center;
        color: $text-muted;
        margin-bottom: 1;
    }
    #nav-row {
        height: 3;
        margin-top: 1;
        align: right middle;
    }
    #nav-row Button { margin-left: 1; }
    #skip-btn { color: $text-muted; }
    .hidden { display: none; }
    .note-optional {
        color: $warning;
        text-style: bold;
        margin-bottom: 1;
    }
    .note-info {
        color: $text-muted;
        margin-top: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "esc_key",   "Esc",   show=False),
        Binding("enter",  "next_step", "Next →", show=True),
        Binding("left",   "nav_left",  "←",     show=False),
        Binding("right",  "nav_right", "→",     show=False),
    ]

    def __init__(self):
        super().__init__()
        self._step_index = 0
        self._config: dict[str, str] = {}
        # Load existing values so we can pre-populate fields
        self._existing: dict[str, str] = {}
        if ENV_FILE.exists():
            for line in ENV_FILE.read_text().splitlines():
                if "=" in line and not line.startswith("#"):
                    k, _, v = line.partition("=")
                    self._existing[k.strip()] = v.strip()

    def compose(self) -> ComposeResult:
        with Vertical(id="wizard-container"):
            yield Static("", id="step-counter", markup=True)

            # Step 0: Welcome
            has_creds = bool(self._existing.get("KAGGLE_KEY"))
            welcome_msg = (
                "Credentials found. Review and update below, or press Skip setup to go straight to the app."
                if has_creds else
                "This wizard configures your Kaggle credentials so you can pull benchmark\n"
                "outputs and publish datasets. Press Next to continue."
            )
            yield WizardStep(
                Static(_ASCII_LOGO, markup=True, id="wizard-logo"),
                Static(welcome_msg, classes="step-body"),
                id="step-welcome",
            )

            # Step 1: Kaggle API credentials
            yield WizardStep(
                Static("Kaggle API Credentials", classes="step-title"),
                Static(
                    "Your Kaggle username and Legacy API key.\n"
                    "Used to pull benchmark output CSVs and publish datasets to Kaggle.",
                    classes="step-body",
                ),
                Static(
                    "How to get them:\n"
                    "  1. Go to kaggle.com → Settings → Account\n"
                    "  2. Scroll to 'Legacy API Credentials'\n"
                    "  3. Click 'Create Legacy API Key' — downloads kaggle.json\n"
                    "  4. Open that file: it contains your username and key\n\n"
                    "  Important: use the Legacy API Key from the JSON file,\n"
                    "  not the newer 'API tokens' listed above it on that page.",
                    classes="note-info",
                ),
                Label("KAGGLE_USERNAME:", classes="field-label"),
                Input(
                    value=self._existing.get("KAGGLE_USERNAME", ""),
                    placeholder="your-kaggle-username",
                    id="kaggle-username",
                ),
                Label("KAGGLE_KEY  (from kaggle.json):", classes="field-label"),
                Input(
                    value=self._existing.get("KAGGLE_KEY", ""),
                    placeholder="xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
                    id="kaggle-key",
                    password=True,
                ),
                id="step-kaggle-api",
                classes="hidden",
            )

            # Step 2: Done
            yield WizardStep(
                Static("All done!", classes="step-title"),
                Static("", id="done-summary", classes="step-body"),
                id="step-done",
                classes="hidden",
            )

            with Horizontal(id="nav-row"):
                yield Button("← Back",    id="back-btn", variant="default", classes="hidden")
                yield Button("Skip setup", id="skip-btn", variant="default")
                yield Button("Next →",    id="next-btn", variant="primary")

    def on_mount(self) -> None:
        self.register_theme(EVALFLOW_THEME)
        self.theme = "evalflow"
        self._update_step()
        self.query_one("#next-btn", Button).focus()

    def _update_step(self) -> None:
        step_ids = ["step-welcome", "step-kaggle-api", "step-done"]
        for i, sid in enumerate(step_ids):
            step = self.query_one(f"#{sid}")
            step.set_class(i != self._step_index, "hidden")

        total = len(step_ids)
        dots = "  ".join(
            "[bold $primary]●[/bold $primary]" if i == self._step_index else "[dim]○[/dim]"
            for i in range(total)
        )
        self.query_one("#step-counter").update(dots)

        is_last = self._step_index == total - 1
        self.query_one("#next-btn", Button).label = "Launch Evalflow →" if is_last else "Next →"
        self.query_one("#back-btn", Button).set_class(self._step_index == 0, "hidden")

    @on(Button.Pressed, "#next-btn")
    def on_next(self) -> None:
        self.action_next_step()

    @on(Button.Pressed, "#back-btn")
    def on_back(self) -> None:
        self.action_prev_step()

    @on(Button.Pressed, "#skip-btn")
    def on_skip(self) -> None:
        self.action_skip_wizard()

    @on(Input.Submitted)
    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.action_next_step()

    def action_next_step(self) -> None:
        if self._step_index == len(STEPS) - 1:
            self._launch_app()
            return

        self._collect_step()
        self._step_index += 1

        if self._step_index == len(STEPS) - 1:
            self._write_env()

        self._update_step()
        # Focus first input in the new step (if any)
        self._focus_first_input()

    def action_nav_left(self) -> None:
        if not isinstance(self.focused, Input):
            self.action_focus_previous()

    def action_nav_right(self) -> None:
        if not isinstance(self.focused, Input):
            self.action_focus_next()

    def action_esc_key(self) -> None:
        """Escape: unfocus an input so arrow keys work on buttons; skip only from welcome."""
        if isinstance(self.focused, Input):
            self.query_one("#next-btn", Button).focus()
        elif self._step_index == 0:
            self._launch_app()

    def action_prev_step(self) -> None:
        if self._step_index == 0:
            return
        self._step_index -= 1
        self._update_step()
        self._focus_first_input()

    def action_skip_wizard(self) -> None:
        self._launch_app()

    def _focus_first_input(self) -> None:
        step_ids = ["step-welcome", "step-kaggle-api", "step-done"]
        try:
            step = self.query_one(f"#{step_ids[self._step_index]}")
            inputs = step.query("Input")
            if inputs:
                inputs.first().focus()
            else:
                self.query_one("#next-btn", Button).focus()
        except Exception:
            pass

    def _collect_step(self) -> None:
        if self._step_index == 1:  # kaggle credentials
            self._config.update({
                "KAGGLE_USERNAME": self.query_one("#kaggle-username", Input).value.strip(),
                "KAGGLE_KEY":      self.query_one("#kaggle-key",      Input).value.strip(),
                "OUTPUT_DIR":      "outputs",
                "DATA_DIR":        "data",
            })

    def _write_env(self) -> None:
        if ENV_FILE.exists():
            ENV_FILE.rename(".env.bak")

        lines = []
        summary = []
        for key, value in self._config.items():
            if value:
                lines.append(f"{key}={value}")
                display = "*" * 8 if "KEY" in key else value
                summary.append(f"  ✅  {key} = {display}")
            else:
                summary.append(f"  ⬜  {key} = (not set)")

        ENV_FILE.write_text("\n".join(lines) + "\n")

        username = self._config.get("KAGGLE_USERNAME", "")
        has_key  = bool(self._config.get("KAGGLE_KEY"))
        status   = "Ready." if (username and has_key) else "Warning: credentials incomplete — pull/publish may fail."
        self.query_one("#done-summary").update(
            f"Configuration saved to .env\n\n"
            + "\n".join(summary)
            + f"\n\n{status}\nPress Launch to open Evalflow."
        )

    def _launch_app(self) -> None:
        self.exit()


def should_run_wizard() -> bool:
    """Return True if the wizard should be shown (no .env and no proxy key in environment)."""
    if ENV_FILE.exists():
        return False
    if os.getenv("MODEL_PROXY_API_KEY") or os.getenv("KAGGLE_KEY"):
        return False
    return True


if __name__ == "__main__":
    SetupWizard().run()
