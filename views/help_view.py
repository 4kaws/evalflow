"""Help view — in-app reference panel, opened with the ? key."""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import ScrollableContainer, Vertical
from textual.widgets import Button, Static

HELP_TEXT = """\
[bold $primary]Evalflow — Quick Reference[/bold $primary]

Evalflow pulls Kaggle Community Benchmark results, merges them into
research-ready datasets, and publishes them to Kaggle Datasets.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[bold]TABS[/bold]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  [bold $primary]Pull[/bold $primary]   [dim]key: 1[/dim]
  Paste a benchmark slug (username/benchmark-name).
  Evalflow auto-discovers all task notebooks and downloads
  every output CSV in one operation.

  [bold $primary]Results[/bold $primary]   [dim]key: 2[/dim]
  Browse pulled CSVs. Filter by model and pass/fail score.
  Click any row to read the full LLM response at the bottom.

  [bold $primary]Leaderboard[/bold $primary]   [dim]key: 3[/dim]
  Ranks models by accuracy across all pulled CSVs.
  Filter by task. Click a model row to see a per-question
  pass/fail diff vs every other model.

  [bold $primary]Merge[/bold $primary]   [dim]key: 4[/dim]
  Combines CSVs into two publication-ready files:
    + evalflow_sft.csv          — SFT / fine-tuning format
    + evalflow_preferences.csv  — RLHF / DPO preference pairs

  [bold $primary]Publish[/bold $primary]   [dim]key: 5[/dim]
  Uploads CSV + Parquet variants and a generated dataset card (README.md)
  to Kaggle Datasets as a public resource.

  [bold $primary]Monitor[/bold $primary]   [dim]key: 6[/dim]
  Watches benchmarks for new task notebooks and runs the full pipeline
  (pull → merge → publish) automatically on a daily GitHub Actions schedule.

  Setting up a watcher:
    1. Enter a benchmark slug (username/benchmark-name)
    2. Enter dataset slug + title (where results will be published)
    3. Click Save Watcher — the row appears in the table
    4. Enter a time (HH:MM, Europe/Bucharest) and click Save & Push
       This commits the cron schedule to .github/workflows/evalflow_ci.yml
       and pushes to GitHub so Actions picks it up.

  Button guide:
    Check All Now      — run all watchers immediately (pulls + merges + publishes)
    Check Selected     — same, for the highlighted row only
    Force Republish    — re-upload the current outputs/ files without re-pulling
    New Watcher        — clear the form to add a second watcher
    Remove Selected    — delete the highlighted watcher from the manifest
    Reset & Re-pull    — wipe known tasks so the next check re-downloads everything
    Sync → Secret      — encrypt the manifest and push it to the EVALFLOW_MANIFEST
                         GitHub Actions secret (requires PyNaCl + a PAT with secrets scope)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[bold]KEYBOARD NAVIGATION[/bold]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  [bold]1–6[/bold]       Switch tabs
  [bold]?[/bold]         Open / close this help panel
  [bold]q[/bold]         Quit
  [bold]Esc[/bold]       Unfocus current field
  [bold]↑ / ↓[/bold]    Move between fields on a page
  [bold]← / →[/bold]    Cycle between action buttons
  [bold]Enter[/bold]     Confirm / activate focused element

  Pull:     navigate fields with ↑/↓ down to the button row,
            then cycle Pull All Tasks / List tasks only / Open on Kaggle with ← / →

  Merge:    navigate to button row, cycle Merge Selected / Refresh / Select All

  Publish:  navigate fields with ↑/↓; after choosing a license the cursor
            jumps automatically to the button row (Publish New / Update Existing)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[bold]SHORTCUTS (per tab)[/bold]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Merge:    Ctrl+M  run merge     Ctrl+A  select all     Ctrl+R  refresh
  Publish:  Ctrl+U  publish new   Ctrl+E  update existing
  Monitor:  Ctrl+R  check all watchers now
  Results / Leaderboard:  Ctrl+R  refresh

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[bold]OUTPUT FORMATS[/bold]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  [bold]evalflow_sft.csv / .parquet[/bold] — one row per passing model response
    (.parquet requires: pip install pyarrow)
    task_name, task_description, task_definition
    model_name
    question, ground_truth, prompt_template
    llm_response
    messages          ← chat-format JSON, SFT-ready
    score             ← overall pass/fail (0/1)
    reasoning         ← failed assertion text
    assertions_json   ← all assertions with pass/fail status
    judge_model, input_tokens, output_tokens, timestamp

  [bold]evalflow_preferences.csv / .parquet[/bold] — sampled passing × failing pairs (capped per question)
    task_name, prompt, ground_truth
    chosen, chosen_model    ← a passing answer
    rejected, rejected_model ← a failing answer
    (column names match HuggingFace TRL DPOTrainer directly;
     Parquet variant preserves types — no json.loads() needed)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[bold]TYPICAL WORKFLOW[/bold]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  On Kaggle (browser):
    1. Write task notebooks using notebooks/notebook_template.ipynb
    2. Group them into a Benchmark on kaggle.com/benchmarks
    3. Click Add Models → Kaggle runs them for free

  In Evalflow (terminal):
    4. Pull    → paste benchmark slug, download all CSVs
    5. Merge   → produces evalflow_sft.csv + evalflow_preferences.csv
    6. Publish → uploads both to Kaggle Datasets

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[bold]CREDENTIALS[/bold]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Set via the setup wizard (auto-runs on first launch) or manually in .env:
    KAGGLE_USERNAME=your-username
    KAGGLE_KEY=your-legacy-api-key

  Get your key: kaggle.com → Settings → Account → Legacy API Credentials
  Credentials persist between sessions. All pulled CSVs are wiped on exit.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[bold]HEADLESS / CI[/bold]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  python ci_runner.py --help
  GitHub Actions: .github/workflows/evalflow_ci.yml
  automates the full pull → merge → publish pipeline.
"""


class HelpView(Vertical):
    BINDINGS = []

    DEFAULT_CSS = """
    HelpView {
        layer: overlay;
        align: center middle;
        background: $background 85%;
        width: 100%;
        height: 100%;
    }

    #help-box {
        width: 74;
        height: 90%;
        background: $surface;
        border: tall $panel;
        padding: 0;
    }

    #help-scroll {
        height: 1fr;
        padding: 2 3;
    }

    #help-close-row {
        height: 3;
        align: right middle;
        padding: 0 2;
        border-top: tall $panel;
    }
    #help-close-btn { width: 14; }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="help-box"):
            yield ScrollableContainer(
                Static(HELP_TEXT, markup=True),
                id="help-scroll",
            )
            with Vertical(id="help-close-row"):
                yield Button("Close  [dim]Esc[/dim]", id="help-close-btn", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "help-close-btn":
            self.app.action_toggle_help()  # type: ignore
