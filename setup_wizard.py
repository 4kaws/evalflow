"""
Setup Wizard — shown on first run when credentials are not configured.
Guides the user through Kaggle API key, Kaggle OAuth login, and GitHub
integration, then writes a .env file and re-launches the main app.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import urllib.parse
import uuid
from datetime import datetime, timedelta, timezone
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

_OAUTH_REDIRECT = "https://www.kaggle.com/account/api/oauth/token"
_OAUTH_SCOPE    = "resources.admin:*"
_OAUTH_CLIENT   = "kagglesdk"

STEPS = [
    "welcome",
    "kaggle_api",
    "oauth",
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
    #oauth-url-display {
        color: $primary;
        margin-top: 1;
        margin-bottom: 1;
    }
    #oauth-status {
        margin-top: 1;
        margin-bottom: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "esc_key",  "Esc", show=False),
        Binding("enter",  "enter_key", "",   show=False),
        Binding("left",   "nav_left",  "",   show=False),
        Binding("right",  "nav_right", "",   show=False),
    ]

    # Ordered input IDs for steps that have form fields.
    # Step 2 (oauth) is handled separately — the code input appears dynamically.
    _STEP_INPUTS: dict[int, list[str]] = {
        1: ["kaggle-username", "kaggle-key"],
        3: ["github-token", "github-repo"],
    }

    def __init__(self):
        super().__init__()
        self._step_index = 0
        self._config: dict[str, str] = {}
        self._oauth_state: dict | None = None
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

            # Step 2: Kaggle OAuth
            yield WizardStep(
                Static("Kaggle OAuth Login", classes="step-title"),
                Static(
                    "Optional — only needed for the Run tab (List My Tasks, Schedule Runs).\n"
                    "You can skip this now and click 'Kaggle Login' inside the Run tab later.",
                    classes="note-optional",
                ),
                Static(
                    "The Run tab calls a Benchmark Tasks API that requires an OAuth Bearer\n"
                    "token. Your API key alone is not enough for task management.\n\n"
                    "  1. Click Generate Login URL\n"
                    "  2. Open the URL in your browser and sign in to Kaggle\n"
                    "  3. Kaggle shows a verification code — paste it in the field below",
                    classes="step-body",
                ),
                Static("", id="oauth-status", classes="note-info"),
                Button("Generate Login URL", id="oauth-gen-btn", variant="primary"),
                Static("", id="oauth-url-display", classes="hidden"),
                Label("Verification code:", classes="field-label hidden", id="oauth-code-label"),
                Input(
                    id="oauth-code",
                    placeholder="Paste the code shown by Kaggle…",
                    classes="hidden",
                ),
                Button("Verify Code", id="oauth-verify-btn", variant="default", classes="hidden"),
                id="step-oauth",
                classes="hidden",
            )

            # Step 3: GitHub credentials
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

            # Step 4: Done
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
        self._prefill_oauth_status()
        self._update_step()
        self.query_one("#next-btn", Button).focus()

    def _prefill_oauth_status(self) -> None:
        creds_path = Path.home() / ".kaggle" / "credentials.json"
        try:
            if creds_path.exists():
                data = json.loads(creds_path.read_text())
                username = data.get("username", "unknown")
                self.query_one("#oauth-status").update(
                    f"Already authenticated as {username} — click Next to keep, "
                    "or Generate Login URL to switch accounts."
                )
            else:
                self.query_one("#oauth-status").update(
                    "Not yet authenticated — generate a login URL to enable the Run tab."
                )
        except Exception:
            pass

    def _update_step(self) -> None:
        step_ids = [
            "step-welcome", "step-kaggle-api", "step-oauth", "step-github", "step-done"
        ]
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
    #  Button handlers                                                      #
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

    @on(Button.Pressed, "#oauth-gen-btn")
    def _on_oauth_generate(self) -> None:
        username, api_key = self._get_kaggle_creds()
        if not username or not api_key:
            self.query_one("#oauth-status").update(
                "[!] Enter your Kaggle username and API key first (step 1)."
            )
            return

        code_verifier = secrets.token_urlsafe(64)
        digest = hashlib.sha256(code_verifier.encode()).digest()
        code_challenge = base64.urlsafe_b64encode(digest).decode()
        state = str(uuid.uuid4())

        self._oauth_state = {
            "code_verifier": code_verifier,
            "state": state,
            "username": username,
            "api_key": api_key,
        }

        # Scope must not be percent-encoded with quote_plus — Kaggle rejects %2A for *
        params = {
            "response_type": "code",
            "client_id": _OAUTH_CLIENT,
            "redirect_uri": _OAUTH_REDIRECT,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "response_mode": "query",
        }
        qs = urllib.parse.urlencode(params)
        scope_qs = urllib.parse.quote(_OAUTH_SCOPE, safe="*:")
        oauth_url = f"https://www.kaggle.com/api/v1/oauth2/authorize?{qs}&scope={scope_qs}"

        self.query_one("#oauth-url-display").update(oauth_url)
        self.query_one("#oauth-url-display").remove_class("hidden")
        self.query_one("#oauth-code-label").remove_class("hidden")
        self.query_one("#oauth-code").remove_class("hidden")
        self.query_one("#oauth-verify-btn").remove_class("hidden")
        self.query_one("#oauth-status").update("Waiting for verification code…")
        self.query_one("#oauth-code", Input).focus()

    @on(Button.Pressed, "#oauth-verify-btn")
    def _on_oauth_verify_btn(self) -> None:
        self._submit_oauth_code()

    # ------------------------------------------------------------------ #
    #  Input Enter                                                          #
    # ------------------------------------------------------------------ #

    @on(Input.Submitted)
    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "oauth-code":
            self._submit_oauth_code()
            return

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

    def _submit_oauth_code(self) -> None:
        code = self.query_one("#oauth-code", Input).value.strip()
        if not code:
            self.query_one("#oauth-status").update("[!] Paste the verification code first.")
            return
        if not self._oauth_state:
            self.query_one("#oauth-status").update("[!] Click Generate Login URL first.")
            return
        self._do_oauth_exchange(code)

    # ------------------------------------------------------------------ #
    #  OAuth exchange worker                                                #
    # ------------------------------------------------------------------ #

    @work(thread=True)
    def _do_oauth_exchange(self, code: str) -> None:
        self.call_from_thread(
            lambda: self.query_one("#oauth-status").update("Exchanging code with Kaggle…")
        )
        try:
            from kagglesdk import KaggleClient
            from kagglesdk.kaggle_creds import KaggleCredentials
            from kagglesdk.security.types.oauth_service import ExchangeOAuthTokenRequest

            state = self._oauth_state
            base_client = KaggleClient(
                username=state["username"],
                password=state["api_key"],
            )

            req = ExchangeOAuthTokenRequest()
            req.code = code
            req.code_verifier = state["code_verifier"]
            req.grant_type = "authorization_code"

            resp = base_client.security.oauth_client.exchange_oauth_token(req)
            creds = KaggleCredentials(
                client=base_client,
                refresh_token=resp.refreshToken,
                access_token=resp.accessToken,
                access_token_expiration=(
                    datetime.now(timezone.utc) + timedelta(seconds=resp.expires_in)
                ),
                username=resp.username,
                scopes=[_OAUTH_SCOPE],
            )
            creds.save()

            def _on_success(u=resp.username):
                self.query_one("#oauth-status").update(
                    f"Authenticated as {u} — success! Click Next to continue."
                )
                self.query_one("#oauth-code", Input).add_class("hidden")
                self.query_one("#oauth-verify-btn", Button).add_class("hidden")

            self.call_from_thread(_on_success)

        except Exception as exc:
            self.call_from_thread(
                lambda e=exc: self.query_one("#oauth-status").update(
                    f"Exchange failed: {e}"
                )
            )

    # ------------------------------------------------------------------ #
    #  Keyboard actions                                                     #
    # ------------------------------------------------------------------ #

    def action_enter_key(self) -> None:
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
        step_ids = [
            "step-welcome", "step-kaggle-api", "step-oauth", "step-github", "step-done"
        ]
        try:
            step = self.query_one(f"#{step_ids[self._step_index]}")
            inputs = step.query("Input")
            if inputs:
                inputs.first().focus()
            else:
                self.query_one("#next-btn", Button).focus()
        except Exception:
            pass

    def _get_kaggle_creds(self) -> tuple[str, str]:
        username = (self._config.get("KAGGLE_USERNAME") or
                    self._existing.get("KAGGLE_USERNAME", "")).strip()
        api_key  = (self._config.get("KAGGLE_KEY") or
                    self._existing.get("KAGGLE_KEY", "")).strip()
        return username, api_key

    def _collect_step(self) -> None:
        if self._step_index == 1:  # kaggle credentials
            self._config.update({
                "KAGGLE_USERNAME": self.query_one("#kaggle-username", Input).value.strip(),
                "KAGGLE_KEY":      self.query_one("#kaggle-key",      Input).value.strip(),
                "OUTPUT_DIR":      "outputs",
                "DATA_DIR":        "data",
            })
        elif self._step_index == 3:  # github credentials (was 2 before oauth step)
            self._config.update({
                "GITHUB_TOKEN": self.query_one("#github-token", Input).value.strip(),
                "GITHUB_REPO":  self.query_one("#github-repo",  Input).value.strip(),
            })
        # step 2 (oauth) writes directly to ~/.kaggle/credentials.json — nothing to collect

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
        ENV_FILE.chmod(0o600)

        username   = self._config.get("KAGGLE_USERNAME", "")
        has_key    = bool(self._config.get("KAGGLE_KEY"))
        has_github = bool(self._config.get("GITHUB_TOKEN")) and bool(self._config.get("GITHUB_REPO"))

        creds_path = Path.home() / ".kaggle" / "credentials.json"
        if creds_path.exists():
            try:
                oauth_user = json.loads(creds_path.read_text()).get("username", "?")
                oauth_line = f"  [+]   OAuth Bearer token for [{oauth_user}]"
            except Exception:
                oauth_line = "  [+]   OAuth Bearer token present"
        else:
            oauth_line = "  [!]   OAuth Bearer token not set — Run tab will be limited"

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
            + f"\n{oauth_line}"
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
        """
        token = self._config.get("GITHUB_TOKEN", "")
        repo  = self._config.get("GITHUB_REPO", "")
        if not token or not repo:
            return
        from core.github_secret import ensure_secret_seeded
        result = ensure_secret_seeded(token, repo, "EVALFLOW_MANIFEST", b"{}")
        self.call_from_thread(self._append_done_summary, result)

    def _append_done_summary(self, line: str) -> None:
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
