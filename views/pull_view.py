"""
Pull view — download all task output CSVs from a Kaggle benchmark.

The user pastes one benchmark slug. Evalflow uses
  kaggle kernels list --parent <slug>
to discover all task notebooks, then pulls each one's output CSV.
"""

import json
from pathlib import Path

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Checkbox, DataTable, Input, Label, Log, Static

from config import config

_HISTORY_FILE = Path(".evalflow_slug_history.json")
_MAX_HISTORY  = 10


def _load_history() -> list[str]:
    try:
        return json.loads(_HISTORY_FILE.read_text())
    except Exception:
        return []

def _save_history(slugs: list[str]) -> None:
    try:
        _HISTORY_FILE.write_text(json.dumps(slugs[:_MAX_HISTORY]))
    except Exception:
        pass


class PullView(Vertical):
    _BTN_IDS = ["pull-btn", "list-btn", "open-btn"]

    BINDINGS = [
        Binding("down",   "nav_down",  show=False),
        Binding("up",     "nav_up",    show=False),
        Binding("left",   "nav_left",  show=False),
        Binding("right",  "nav_right", show=False),
        Binding("escape", "nav_esc",   show=False),
    ]

    def _fid(self) -> str | None:
        return self.app.focused.id if self.app.focused else None

    def _select_btn(self, btn_id: str) -> None:
        """Focus a button and make it primary; reset the others to default."""
        for bid in self._BTN_IDS:
            self.query_one(f"#{bid}", Button).variant = (
                "primary" if bid == btn_id else "default"
            )
        self.query_one(f"#{btn_id}", Button).focus()

    def _reset_btns(self) -> None:
        """Return button row to its default state (pull-btn highlighted)."""
        self._select_btn("pull-btn")

    def action_nav_down(self) -> None:
        if self._fid() in self._BTN_IDS:
            return  # vertical nav stops at button row
        self.app.action_focus_next()

    def action_nav_up(self) -> None:
        if self._fid() in self._BTN_IDS:
            self._reset_btns()
            self.query_one("#auto-merge-switch", Checkbox).focus()
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
            self.query_one("#slug-input", Input).focus()
        else:
            self.app.action_unfocus()

    DEFAULT_CSS = """
    PullView { padding: 0 1; height: 1fr; }

    .section-title {
        color: $primary;
        text-style: bold;
        margin-top: 0;
        margin-bottom: 0;
    }
    .field-row {
        layout: horizontal;
        height: 3;
        align: left middle;
        margin-bottom: 0;
    }
    .field-label {
        width: 24;
        height: 3;
        color: $text-muted;
        content-align: right middle;
        padding-right: 2;
    }
    #history-display {
        height: 3;
        width: 48;
        color: $text-muted;
        content-align: left middle;
        padding-left: 1;
    }
    .field-input { width: 48; }

    #btn-row { layout: horizontal; height: 3; margin-top: 0; }
    #btn-row Button { margin-right: 1; }

    #pull-log {
        height: 1fr;
        min-height: 4;
        border: solid $primary 15%;
        background: $surface;
        margin-top: 0;
    }

    #pulled-table {
        height: 1fr;
        min-height: 4;
        border: solid $primary 15%;
        background: $surface;
        margin-top: 0;
    }

    #status-bar {
        color: $text-muted;
        height: 2;
        margin-top: 0;
        padding: 0 1;
        background: $surface;
    }

    #creds-note { color: $warning; margin-bottom: 0; }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._history: list[str] = _load_history()

    def compose(self) -> ComposeResult:
        yield Static("Pull Benchmark from Kaggle", classes="section-title")
        yield Static(
            "Requires KAGGLE_USERNAME + KAGGLE_KEY  (set via wizard or .env).",
            id="creds-note",
        )

        # Main input: benchmark slug
        with Horizontal(classes="field-row"):
            yield Label("Task prefix slug:", classes="field-label")
            yield Input(
                placeholder="your-username/benchmark-name  (e.g. alice/my-benchmark)",
                id="slug-input",
                classes="field-input",
            )

        # Recent slugs (read-only display)
        with Horizontal(classes="field-row"):
            yield Label("Recent:", classes="field-label")
            yield Static("", id="history-display")

        # Output dir
        with Horizontal(classes="field-row"):
            yield Label("Save to:", classes="field-label")
            yield Input(
                value=str(config.output_dir),
                id="outdir-input",
                classes="field-input",
            )

        # Auto-navigate to merge
        yield Checkbox("Go to Merge after pull", value=True, id="auto-merge-switch")

        with Horizontal(id="btn-row"):
            yield Button("Pull All Tasks",  id="pull-btn",  variant="primary")
            yield Button("List tasks only", id="list-btn",  variant="default")
            yield Button("Open on Kaggle",  id="open-btn",  variant="default")

        yield Static("Pull Log", classes="section-title")
        yield Log(id="pull-log", highlight=True)

        yield Static("Downloaded Files", classes="section-title")
        yield DataTable(id="pulled-table", cursor_type="row", zebra_stripes=True)
        yield Static("", id="status-bar")

    def on_mount(self) -> None:
        table = self.query_one("#pulled-table", DataTable)
        table.add_columns("Task notebook", "File", "Size", "Rows", "Models", "Accuracy")
        self._refresh_history_input()

    # ------------------------------------------------------------------ #
    #  Events                                                              #
    # ------------------------------------------------------------------ #

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "pull-btn":
            self._do_pull(download=True)
        elif bid == "list-btn":
            self._do_pull(download=False)
        elif bid == "open-btn":
            slug = self.query_one("#slug-input", Input).value.strip()
            if slug:
                import webbrowser
                webbrowser.open(f"https://www.kaggle.com/code/{slug}")
        # Return focus to slug input and reset button highlight
        self._reset_btns()
        self.query_one("#slug-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "slug-input":
            self._do_pull(download=True)

    def action_pull(self) -> None:
        self._do_pull(download=True)

    def action_list_tasks(self) -> None:
        self._do_pull(download=False)

    # ------------------------------------------------------------------ #
    #  Worker entry point                                                  #
    # ------------------------------------------------------------------ #

    def _do_pull(self, download: bool = True) -> None:
        log = self.query_one("#pull-log", Log)
        log.clear()
        self.query_one("#status-bar").update("")
        slug    = self.query_one("#slug-input", Input).value.strip()
        out_dir = Path(self.query_one("#outdir-input", Input).value.strip())
        auto_merge = self.query_one("#auto-merge-switch", Checkbox).value
        if not slug:
            log.write_line("[x] No slug entered.\n   Format: username/task-prefix")
            return
        if "/" not in slug:
            log.write_line(f"[x] Slug looks incomplete: '{slug}'\n   It should be: username/prefix")
            return
        self._run_pull(slug, out_dir, download, auto_merge)

    # ------------------------------------------------------------------ #
    #  Core pull logic (runs in background thread)                        #
    # ------------------------------------------------------------------ #

    @work(thread=True)
    def _run_pull(self, slug: str, out_dir: Path, download: bool, auto_merge: bool) -> None:
        log = self.query_one("#pull-log", Log)

        # Authenticate
        try:
            from kaggle.api.kaggle_api_extended import KaggleApi
            api = KaggleApi()
            api.authenticate()
            log.write_line("[ok] Authenticated with Kaggle API\n")
        except ImportError:
            log.write_line("[x] kaggle package not installed. Run: pip install kaggle")
            return
        except (SystemExit, Exception) as exc:
            log.write_line(
                f"[x] Authentication failed: {exc}\n\n"
                "   Make sure one of these is configured:\n"
                "   • KAGGLE_USERNAME + KAGGLE_KEY in .env\n"
                "   • ~/.kaggle/kaggle.json\n"
                "   Get your token: kaggle.com → Settings → API → Create New Token"
            )
            return

        # Discover task notebooks
        task_slugs = self._discover_tasks(api, slug, log)
        if not task_slugs:
            return

        if not download:
            return

        # Pull each task
        out_dir.mkdir(parents=True, exist_ok=True)
        all_downloaded: list[tuple[str, Path]] = []
        failed_tasks:   list[str]              = []

        for i, task_slug in enumerate(task_slugs, 1):
            log.write_line(f"\n[{i}/{len(task_slugs)}] Pulling: {task_slug}")
            csvs = self._pull_one_task(api, task_slug, out_dir, log)
            if csvs:
                all_downloaded.extend((task_slug, p) for p in csvs)
            else:
                failed_tasks.append(task_slug)

        # Summary
        log.write_line(f"\n{'─'*50}")
        log.write_line(f"[ok] Pulled {len(all_downloaded)} CSV(s) from {len(task_slugs)} task(s)")
        if failed_tasks:
            log.write_line(f"[!]  {len(failed_tasks)} task(s) had no CSV output: {', '.join(failed_tasks)}")

        def _finish() -> None:
            self._populate_table(all_downloaded, log)
            self._add_to_history(slug)
            self.query_one("#status-bar").update(
                f"  {len(all_downloaded)} CSV(s) saved to {out_dir}"
                "  |  Switch to Merge to combine them."
            )
            if auto_merge and all_downloaded:
                self.app.switch_view("merge")  # type: ignore

        self.app.call_from_thread(_finish)

    # ------------------------------------------------------------------ #
    #  Task discovery                                                      #
    # ------------------------------------------------------------------ #

    def _discover_tasks(self, api, benchmark_slug: str, log: Log) -> list[str]:
        """
        Find all task notebooks belonging to a benchmark.

        Strategy — tried in order until one succeeds:
          1. REST API search (requests + Basic auth) — reliable across SDK versions
          2. kernels_list SDK call — fallback
          3. Treat benchmark_slug itself as a single task
        """
        import base64
        import requests

        from config import config

        username, slug_name = benchmark_slug.split("/", 1)
        log.write_line(f">> Discovering tasks under: {benchmark_slug}\n")

        # ── Strategy 1: REST API with Basic auth ──────────────────────
        if config.kaggle_username and config.kaggle_key:
            try:
                token = base64.b64encode(
                    f"{config.kaggle_username}:{config.kaggle_key}".encode()
                ).decode()
                resp = requests.get(
                    "https://www.kaggle.com/api/v1/kernels",
                    params={"userRef": username, "search": slug_name, "pageSize": 100},
                    headers={"Authorization": f"Basic {token}"},
                    timeout=30,
                )
                resp.raise_for_status()
                results = resp.json()
                if isinstance(results, list) and results:
                    slugs = [
                        f"{r['ref']}" if "/" in r.get("ref", "") else f"{username}/{r['ref']}"
                        for r in results
                        if r.get("ref") and slug_name in r.get("ref", "").lower()
                    ]
                    if slugs:
                        log.write_line(f"   Found {len(slugs)} notebook(s) matching '{slug_name}':\n")
                        for s in slugs:
                            log.write_line(f"   - {s}")
                        return slugs
            except Exception as exc:
                log.write_line(f"   (REST search failed: {exc})")

        # ── Strategy 2: SDK kernels_list ───────────────────────────────
        try:
            results = api.kernels_list(user=username, search=slug_name, page_size=100)
            if results:
                tasks = [k for k in results if k.ref and slug_name in k.ref.lower()]
                if tasks:
                    slugs = [k.ref for k in tasks]
                    log.write_line(f"   Found {len(slugs)} notebook(s) via SDK:\n")
                    for s in slugs:
                        log.write_line(f"   - {s}")
                    return slugs
        except Exception as exc:
            log.write_line(f"   (SDK search failed: {exc})")

        # ── Strategy 3: treat as single-task benchmark ────────────────
        log.write_line(
            f"\n   Could not find task notebooks automatically.\n"
            f"   Treating '{benchmark_slug}' as a single-task notebook.\n"
            f"\n   Tip: enter 'username/prefix' to find all matching notebooks.\n"
        )
        return [benchmark_slug]

    # ------------------------------------------------------------------ #
    #  Single-task pull                                                    #
    # ------------------------------------------------------------------ #

    def _pull_one_task(
        self,
        api,
        task_slug: str,
        out_dir: Path,
        log: Log,
    ) -> list[Path]:
        """Pull output CSVs from the latest run of one task/model kernel."""
        import shutil

        short_name = task_slug.split("/")[-1]
        tmp_dir = out_dir / f"_tmp_{short_name}"
        tmp_dir.mkdir(parents=True, exist_ok=True)

        try:
            api.kernels_output(task_slug, path=str(tmp_dir), force=True)

            csvs = list(tmp_dir.glob("*.csv"))
            if not csvs:
                log.write_line(f"   [!] No CSV output found for {task_slug}")
                return []

            # Remove any stale CSVs for this task before saving fresh ones
            for stale in out_dir.glob(f"{short_name}__*.csv"):
                stale.unlink()

            saved = []
            for csv in csvs:
                dest = out_dir / f"{short_name}__{csv.name}"
                csv.rename(dest)
                saved.append(dest)
                log.write_line(f"   + {dest.name}")

            return saved

        except Exception as exc:
            log.write_line(f"   [x] Failed to pull {task_slug}: {exc}")
            return []
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    # ------------------------------------------------------------------ #
    #  Table + history                                                     #
    # ------------------------------------------------------------------ #

    def _populate_table(self, items: list[tuple[str, Path]], log: Log) -> None:
        import pandas as pd

        table = self.query_one("#pulled-table", DataTable)
        table.clear()

        for task_slug, path in items:
            size_kb = round(path.stat().st_size / 1024, 1)
            try:
                df      = pd.read_csv(path)
                rows    = len(df)
                models  = df["model_name"].nunique() if "model_name" in df.columns else "?"
                acc     = f"{df['score'].mean() * 100:.1f}%" if "score" in df.columns else "?"
            except Exception:
                rows, models, acc = "?", "?", "?"

            short_task = task_slug.split("/")[-1]
            table.add_row(short_task, path.name, f"{size_kb} KB", str(rows), str(models), acc)

    def _add_to_history(self, slug: str) -> None:
        if slug in self._history:
            self._history.remove(slug)
        self._history.insert(0, slug)
        _save_history(self._history)
        self._refresh_history_input()

    def _refresh_history_input(self) -> None:
        text = "  |  ".join(self._history[:3]) if self._history else "(none yet)"
        self.query_one("#history-display", Static).update(text)
