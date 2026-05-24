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
from views.widgets import PageHeader

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
    PullView { padding: 0; height: 1fr; }

    #pull-body { padding: 1 3; height: 1fr; }

    .section-title {
        color: #86868B;
        text-style: bold;
        margin-top: 1;
        margin-bottom: 0;
    }
    .field-row {
        layout: horizontal;
        height: 3;
        align: left middle;
        margin-bottom: 0;
    }
    .field-label {
        width: 20;
        height: 3;
        color: #86868B;
        content-align: right middle;
        padding-right: 2;
    }
    #history-display {
        height: 3;
        width: 48;
        color: #86868B;
        content-align: left middle;
        padding-left: 1;
    }
    .field-input { width: 52; }

    #btn-row { layout: horizontal; height: 3; margin-top: 1; }
    #btn-row Button { margin-right: 1; }

    #pull-log {
        height: 1fr;
        min-height: 4;
        background: $surface;
        border: round #E5E5E7;
        margin-top: 1;
        padding: 0 1;
    }

    #pulled-table {
        height: 1fr;
        min-height: 4;
        background: $surface;
        border: round #E5E5E7;
        margin-top: 1;
    }

    #status-bar {
        color: #86868B;
        height: 1;
        margin-top: 0;
        padding: 0 1;
    }

    #creds-note { color: #86868B; margin-bottom: 0; }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._history: list[str] = _load_history()

    def compose(self) -> ComposeResult:
        yield PageHeader(
            "Pull",
            "Auto-discover and download all task runs from a Kaggle benchmark.",
        )
        with Vertical(id="pull-body"):
            yield Static(
                "Requires KAGGLE_USERNAME + KAGGLE_KEY  (set via wizard [dim]w[/dim] or .env).",
                id="creds-note",
                markup=True,
            )

            # Main input: benchmark slug
            with Horizontal(classes="field-row"):
                yield Label("Task prefix slug:", classes="field-label")
                yield Input(
                    placeholder="username/notebook-name  (from Kaggle benchmark URL)",
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
        table.add_columns("Task notebook", "File", "Size", "Task", "Model", "Score")
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
            log.write_line("[x] No slug entered.\n   Format: username/notebook-name")
            return
        if "/" not in slug:
            log.write_line(
                f"[x] Missing username in '{slug}'.\n\n"
                "   Format: username/notebook-name\n"
                "   The username is in the Kaggle URL:\n"
                "   kaggle.com/benchmarks/tasks/USERNAME/notebook-name"
            )
            return
        import re as _re
        # Normalise task names to URL slugs: "Should I walk?" → "should-i-walk"
        user, task = slug.split("/", 1)
        task = _re.sub(r"[^\w\s-]", "", task).strip().lower()
        task = _re.sub(r"[\s_]+", "-", task)
        slug = f"{user}/{task}"
        self._run_pull(slug, out_dir, download, auto_merge)

    # ------------------------------------------------------------------ #
    #  Core pull logic (runs in background thread)                        #
    # ------------------------------------------------------------------ #

    @work(thread=True)
    def _run_pull(self, slug: str, out_dir: Path, download: bool, auto_merge: bool) -> None:
        log = self.query_one("#pull-log", Log)

        # Authenticate
        try:
            import os
            from kagglesdk import KaggleClient
            from config import config

            if config.kaggle_username and config.kaggle_key:
                os.environ["KAGGLE_USERNAME"] = config.kaggle_username
                os.environ["KAGGLE_KEY"]      = config.kaggle_key

            if not config.kaggle_username or not config.kaggle_key:
                log.write_line(
                    "[x] Credentials not configured.\n\n"
                    "   Make sure one of these is configured:\n"
                    "   • KAGGLE_USERNAME + KAGGLE_KEY in .env\n"
                    "   • ~/.kaggle/kaggle.json\n"
                    "   Get your token: kaggle.com → Settings → API → Create New Token"
                )
                return

            # Do NOT pass username/api_token — that enables Bearer auth which
            # the Benchmark Tasks API rejects. KaggleClient() reads credentials
            # from env vars / ~/.kaggle/kaggle.json and uses basic auth instead.
            kag_client = KaggleClient()
            log.write_line("[ok] Authenticated with Kaggle API\n")
        except ImportError:
            log.write_line("[x] kaggle / kagglesdk package not installed.")
            return
        except (SystemExit, Exception) as exc:
            log.write_line(
                f"[x] Authentication failed: {exc}\n\n"
                "   Make sure KAGGLE_USERNAME + KAGGLE_KEY are set in .env"
            )
            return

        # Discover tasks via the leaderboard API
        task_slugs = self._discover_tasks(kag_client, slug, log)
        if not task_slugs:
            return

        if not download:
            return

        # Pull each task — one .run.json per model per task
        out_dir.mkdir(parents=True, exist_ok=True)
        all_downloaded:  list[tuple[str, Path]] = []
        denied_tasks:    list[str]              = []   # 403/404 — no access
        no_output_tasks: list[str]              = []   # no completed runs yet

        import time as _time
        for i, task_slug in enumerate(task_slugs, 1):
            if i > 1:
                _time.sleep(0.5)   # avoid 429 rate limit between tasks
            log.write_line(f"\n[{i}/{len(task_slugs)}] Pulling: {task_slug}")
            run_files = self._pull_one_task(kag_client, task_slug, out_dir, log)
            if run_files:
                all_downloaded.extend((task_slug, p) for p in run_files)
            elif run_files is None:
                denied_tasks.append(task_slug)
            else:
                no_output_tasks.append(task_slug)

        # Summary
        log.write_line(f"\n{'─'*50}")
        log.write_line(
            f"[ok] Pulled {len(all_downloaded)} .run.json file(s) from {len(task_slugs)} task(s)"
            f"  ({len(all_downloaded)} = tasks × models with completed runs)"
        )
        if denied_tasks:
            log.write_line(
                f"[!]  {len(denied_tasks)} task(s) not accessible: "
                + ", ".join(denied_tasks)
            )
        if no_output_tasks:
            log.write_line(
                f"[!]  {len(no_output_tasks)} task(s) returned no files "
                "(no completed runs, or rate-limited after retries — check log above): "
                + ", ".join(no_output_tasks)
            )

        def _finish() -> None:
            self._populate_table(all_downloaded, log)
            self._add_to_history(slug)
            self.query_one("#status-bar").update(
                f"  {len(all_downloaded)} run file(s) saved to {out_dir}"
                "  |  Switch to Merge to combine them."
            )
            # Refresh dependent views so they're ready without a manual Refresh
            if all_downloaded:
                from views.results_view import ResultsView
                from views.leaderboard_view import LeaderboardView
                try:
                    self.app.query_one("#results", ResultsView).action_refresh()
                    self.app.query_one("#leaderboard", LeaderboardView).action_refresh()
                except Exception:
                    pass
            if auto_merge and all_downloaded:
                self.app.switch_view("merge")  # type: ignore

        self.app.call_from_thread(_finish)

    # ------------------------------------------------------------------ #
    #  Task discovery                                                      #
    # ------------------------------------------------------------------ #

    def _discover_tasks(self, kag_client, benchmark_slug: str, log: Log) -> list[str]:
        """
        Find all tasks belonging to a benchmark via the leaderboard API.

        Expects "username/benchmark-name". Returns benchmark task slugs in
        "username/task-slug" form, suitable for the Benchmark Tasks API.
        """
        username, slug_name = benchmark_slug.split("/", 1)
        log.write_line(f">> Discovering tasks in: {benchmark_slug}\n")

        try:
            from kagglesdk.benchmarks.types.benchmarks_api_service import ApiGetBenchmarkLeaderboardRequest
            req = ApiGetBenchmarkLeaderboardRequest()
            req.owner_slug     = username
            req.benchmark_slug = slug_name
            lb = kag_client.benchmarks.benchmarks_api_client.get_benchmark_leaderboard(req)
            task_slugs: set[str] = set()
            for row in (lb.rows or []):
                for tr in (row.task_results or []):
                    if tr.benchmark_task_slug:
                        short = tr.benchmark_task_slug.rstrip("/").split("/")[-1]
                        task_slugs.add(short)
            if task_slugs:
                slugs = [f"{username}/{s}" for s in sorted(task_slugs)]
                log.write_line(f"   Found {len(slugs)} task(s) via leaderboard API:\n")
                for s in slugs:
                    log.write_line(f"   - {s}")
                return slugs
        except Exception as exc:
            log.write_line(f"   (leaderboard API failed: {exc})")

        log.write_line(
            f"\n[x] Could not discover tasks for '{benchmark_slug}'.\n"
            "   The benchmark may not have a leaderboard yet, or the slug is wrong.\n"
            "   Format: username/benchmark-name  (from kaggle.com/benchmarks/username/benchmark-name)"
        )
        return []

    # ------------------------------------------------------------------ #
    #  Single-task pull                                                    #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _api_call_with_retry(call, log: Log, label: str):
        """Call a zero-arg callable, retrying on 429 with exponential backoff."""
        import time
        delays = [2, 5, 15]
        for attempt, delay in enumerate(delays + [None]):
            try:
                return call()
            except Exception as exc:
                if "429" not in str(exc) or delay is None:
                    raise
                log.write_line(f"   (rate limited on {label}, retrying in {delay}s…)")
                time.sleep(delay)

    def _pull_one_task(
        self,
        kag_client,
        task_slug: str,
        out_dir: Path,
        log: Log,
    ) -> list[Path] | None:
        """Download .run.json outputs for a benchmark task via the Benchmark Tasks API.

        Returns:
            list[Path]  — downloaded files (empty if no completed runs yet)
            None        — 403/404: task not accessible
        """
        import io
        import zipfile

        from kagglesdk.benchmarks.types.benchmark_tasks_api_service import (
            ApiBenchmarkTaskSlug,
            ApiDownloadBenchmarkTaskRunOutputRequest,
            ApiListBenchmarkTaskRunsRequest,
            BenchmarkTaskRunState,
        )

        owner, slug_name = task_slug.split("/", 1)
        client = kag_client.benchmarks.benchmark_tasks_api_client

        # Collect all completed run IDs (paginated)
        completed_run_ids: list[int] = []
        page_token = ""
        try:
            while True:
                req = ApiListBenchmarkTaskRunsRequest()
                slug_obj = ApiBenchmarkTaskSlug()
                slug_obj.owner_slug = owner
                slug_obj.task_slug  = slug_name
                req.task_slug  = slug_obj
                req.page_size  = 100
                if page_token:
                    req.page_token = page_token
                resp = self._api_call_with_retry(
                    lambda r=req: client.list_benchmark_task_runs(r),
                    log, "list runs",
                )
                for run in resp.runs or []:
                    if run.state == BenchmarkTaskRunState.BENCHMARK_TASK_RUN_STATE_COMPLETED:
                        completed_run_ids.append(run.id)
                page_token = resp.next_page_token or ""
                if not page_token:
                    break
        except Exception as exc:
            exc_str = str(exc)
            if "403" in exc_str or "404" in exc_str:
                log.write_line(f"   [x] {task_slug}: no access ({exc_str[:80]})")
                return None
            log.write_line(f"   [x] Failed to list runs for {task_slug}: {exc_str}")
            return []

        if not completed_run_ids:
            log.write_line(f"   [!] No completed runs found for {task_slug}")
            return []

        log.write_line(f"   Found {len(completed_run_ids)} completed run(s)")

        saved: list[Path] = []
        for run_id in completed_run_ids:
            try:
                dl_req = ApiDownloadBenchmarkTaskRunOutputRequest()
                dl_req.run_id = run_id
                r = self._api_call_with_retry(
                    lambda req=dl_req: client.download_benchmark_task_run_output(req),
                    log, f"download run {run_id}",
                )
                if not r.ok:
                    log.write_line(f"   [!] Run {run_id}: HTTP {r.status_code}")
                    continue
                zf = zipfile.ZipFile(io.BytesIO(r.content))
                for name in zf.namelist():
                    if not name.endswith(".run.json"):
                        continue
                    dest = out_dir / name
                    if dest.exists():
                        saved.append(dest)
                        continue
                    dest.write_bytes(zf.read(name))
                    saved.append(dest)
                    log.write_line(f"   + {name}")
            except Exception as exc:
                log.write_line(f"   [!] Failed to download run {run_id}: {exc}")

        return saved

    # ------------------------------------------------------------------ #
    #  Table + history                                                     #
    # ------------------------------------------------------------------ #

    def _populate_table(self, items: list[tuple[str, Path]], log: Log) -> None:
        from core.merger import parse_run_json

        table = self.query_one("#pulled-table", DataTable)
        table.clear()

        for task_slug, path in items:
            size_kb = round(path.stat().st_size / 1024, 1)
            row, _ = parse_run_json(path)
            if row:
                task  = row.get("task_name", "?")
                model = row.get("model_name", "?").split("/")[-1]
                score = "pass" if row.get("score", 0) else "fail"
            else:
                task, model, score = "?", "?", "?"

            short_task = task_slug.split("/")[-1]
            table.add_row(short_task, path.name, f"{size_kb} KB", task, model, score)

    def _add_to_history(self, slug: str) -> None:
        if slug in self._history:
            self._history.remove(slug)
        self._history.insert(0, slug)
        _save_history(self._history)
        self._refresh_history_input()

    def _refresh_history_input(self) -> None:
        text = "  |  ".join(self._history[:3]) if self._history else "(none yet)"
        self.query_one("#history-display", Static).update(text)
