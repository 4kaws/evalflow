"""
Setup Wizard — shown on first run when credentials are not configured.
Guides the user through setting MODEL_PROXY_API_KEY and KAGGLE_* credentials,
then writes a .env file and re-launches the main app.
"""

import os
from pathlib import Path

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.theme import Theme
from textual.widgets import Button, Input, Label, Static

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
    "github",
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
        Binding("escape", "esc_key",  "Esc", show=False),
        Binding("enter",  "enter_key", "",   show=False),
        Binding("left",   "nav_left",  "",   show=False),
        Binding("right",  "nav_right", "",   show=False),
    ]

    # Ordered input IDs for each step that has form fields
    _STEP_INPUTS: dict[int, list[str]] = {
        1: ["kaggle-username", "kaggle-key"],
        2: ["github-token", "github-repo"],
    }

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

            # Step 2: GitHub credentials
            yield WizardStep(
                Static("GitHub Integration (optional)", classes="step-title"),
                Static(
                    "Used to sync your watcher list to GitHub Actions as a secret,\n"
                    "so the daily monitor can run in CI without exposing your config.",
                    classes="step-body",
                ),
                Static(
                    "How to create a token:\n"
                    "  1. Go to github.com → Settings → Developer settings\n"
                    "  2. Personal access tokens → Fine-grained tokens → Generate new token\n"
                    "  3. Under 'Repository permissions' → Secrets → Read and write\n"
                    "  4. Copy the token below\n\n"
                    "  GITHUB_REPO format: owner/repo  (e.g. 4kaws/evalflow)",
                    classes="note-info",
                ),
                Label("GITHUB_TOKEN:", classes="field-label"),
                Input(
                    value=self._existing.get("GITHUB_TOKEN", ""),
                    placeholder="github_pat_...",
                    id="github-token",
                    password=True,
                ),
                Label("GITHUB_REPO:", classes="field-label"),
                Input(
                    value=self._existing.get("GITHUB_REPO", ""),
                    placeholder="owner/repo",
                    id="github-repo",
                ),
                id="step-github",
                classes="hidden",
            )

            # Step 3: Done
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
        step_ids = ["step-welcome", "step-kaggle-api", "step-github", "step-done"]
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

    # ------------------------------------------------------------------ #
    #  Button handlers — call _advance_step directly (no action dispatch)  #
    # ------------------------------------------------------------------ #

    @on(Button.Pressed, "#next-btn")
    def on_next(self) -> None:
        self._advance_step()

    @on(Button.Pressed, "#back-btn")
    def on_back(self) -> None:
        self._prev_step()

    @on(Button.Pressed, "#skip-btn")
    def on_skip(self) -> None:
        self._launch_app()

    # ------------------------------------------------------------------ #
    #  Input Enter — cycle fields first, advance step on last field        #
    # ------------------------------------------------------------------ #

    @on(Input.Submitted)
    def on_input_submitted(self, event: Input.Submitted) -> None:
        fields = self._STEP_INPUTS.get(self._step_index, [])
        iid = event.input.id
        if iid in fields:
            idx = fields.index(iid)
            if idx < len(fields) - 1:
                self.query_one(f"#{fields[idx + 1]}", Input).focus()
            else:
                self.query_one("#next-btn", Button).focus()
            return
        self._advance_step()

    # ------------------------------------------------------------------ #
    #  Keyboard actions                                                     #
    # ------------------------------------------------------------------ #

    def action_enter_key(self) -> None:
        """Enter: activate focused button, or advance step if no button focused."""
        focused = self.focused
        if isinstance(focused, Button):
            focused.press()
            return
        self._advance_step()

    def action_nav_left(self) -> None:
        if isinstance(self.focused, Input):
            return
        btns = self._visible_btn_ids()
        fid  = self.focused.id if self.focused else None
        idx  = btns.index(fid) if fid in btns else 0
        self.query_one(f"#{btns[(idx - 1) % len(btns)]}", Button).focus()

    def action_nav_right(self) -> None:
        if isinstance(self.focused, Input):
            return
        btns = self._visible_btn_ids()
        fid  = self.focused.id if self.focused else None
        idx  = btns.index(fid) if fid in btns else -1
        self.query_one(f"#{btns[(idx + 1) % len(btns)]}", Button).focus()

    def action_esc_key(self) -> None:
        if isinstance(self.focused, Input):
            self.query_one("#next-btn", Button).focus()
        elif self._step_index == 0:
            self._launch_app()

    # ------------------------------------------------------------------ #
    #  Step logic                                                           #
    # ------------------------------------------------------------------ #

    def _advance_step(self) -> None:
        if self._step_index == len(STEPS) - 1:
            self._launch_app()
            return
        self._collect_step()
        self._step_index += 1
        if self._step_index == len(STEPS) - 1:
            self._write_env()
            self._bootstrap_manifest_secret()
        self._update_step()
        self._focus_first_input()

    def _prev_step(self) -> None:
        if self._step_index == 0:
            return
        self._step_index -= 1
        self._update_step()
        self._focus_first_input()

    def action_skip_wizard(self) -> None:
        self._launch_app()

    def _visible_btn_ids(self) -> list[str]:
        btns = []
        if self._step_index > 0:
            btns.append("back-btn")
        btns.append("skip-btn")
        btns.append("next-btn")
        return btns

    def _focus_first_input(self) -> None:
        step_ids = ["step-welcome", "step-kaggle-api", "step-github", "step-done"]
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
        elif self._step_index == 2:  # github credentials
            self._config.update({
                "GITHUB_TOKEN": self.query_one("#github-token", Input).value.strip(),
                "GITHUB_REPO":  self.query_one("#github-repo",  Input).value.strip(),
            })

    def _write_env(self) -> None:
        if ENV_FILE.exists():
            ENV_FILE.rename(".env.bak")

        lines = []
        summary = []
        for key, value in self._config.items():
            if value:
                value = value.replace("\r", "").replace("\n", "")
                lines.append(f"{key}={value}")
                _secret_key = any(s in key for s in ("KEY", "TOKEN", "PAT", "SECRET", "PASSWORD"))
                display = "*" * 8 if _secret_key else value
                summary.append(f"  [+]   {key} = {display}")
            else:
                summary.append(f"  [!]   {key} = (not set)")

        ENV_FILE.write_text("\n".join(lines) + "\n")

        username   = self._config.get("KAGGLE_USERNAME", "")
        has_key    = bool(self._config.get("KAGGLE_KEY"))
        has_github = bool(self._config.get("GITHUB_TOKEN")) and bool(self._config.get("GITHUB_REPO"))
        if username and has_key and has_github:
            status = (
                "Ready. GitHub sync enabled.\n\n"
                "  Checking EVALFLOW_MANIFEST secret on GitHub..."
            )
        elif username and has_key:
            status = "Ready. (GitHub sync not configured — 'Sync Watchers → Secret' won't work)"
        else:
            status = "Warning: Kaggle credentials incomplete — pull/publish may fail."
        self._done_summary_base = (
            f"Configuration saved to .env\n\n"
            + "\n".join(summary)
            + f"\n\n{status}\nPress Launch to open Evalflow."
        )
        self.query_one("#done-summary").update(self._done_summary_base)

    def _launch_app(self) -> None:
        self.exit()

    @work(thread=True)
    def _bootstrap_manifest_secret(self) -> None:
        """
        Background thread: seeds EVALFLOW_MANIFEST on GitHub with '{}' if it does not
        already exist. This runs automatically whenever the user completes the GitHub
        credentials step, so the daily CI schedule works immediately without any manual
        secret creation in GitHub Settings.

        If the secret already exists (re-running the wizard, or created by a prior monitor
        sync), it is left untouched. The result is appended to the done-screen summary.
        """
        token = self._config.get("GITHUB_TOKEN", "")
        repo  = self._config.get("GITHUB_REPO", "")
        if not token or not repo:
            return
        from core.github_secret import ensure_secret_seeded
        result = ensure_secret_seeded(token, repo, "EVALFLOW_MANIFEST", b"{}")
        self.call_from_thread(self._append_done_summary, result)

    def _append_done_summary(self, line: str) -> None:
        """Replaces the '...checking...' placeholder with the actual secret result."""
        try:
            base = self._done_summary_base.replace(
                "  Checking EVALFLOW_MANIFEST secret on GitHub...", f"  {line}"
            )
            self._done_summary_base = base
            self.query_one("#done-summary").update(base)
        except Exception:
            pass


def should_run_wizard() -> bool:
    """Return True if the wizard should be shown (no .env and no proxy key in environment)."""
    if ENV_FILE.exists():
        return False
    if os.getenv("MODEL_PROXY_API_KEY") or os.getenv("KAGGLE_KEY"):
        return False
    return True


if __name__ == "__main__":
    SetupWizard().run()
