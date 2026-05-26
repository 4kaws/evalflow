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
    _BTN_IDS = ["pull-btn", "list-btn", "browse-btn", "open-btn"]

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
            self._select_btn(self._BTN_IDS[(idx - 1) % len(self._BTN_IDS)])

    def action_nav_right(self) -> None:
        fid = self._fid()
        if fid in self._BTN_IDS:
            idx = self._BTN_IDS.index(fid)
            self._select_btn(self._BTN_IDS[(idx + 1) % len(self._BTN_IDS)])

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
        color: #636E7B;
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
        color: #636E7B;
        content-align: right middle;
        padding-right: 2;
    }
    #history-display {
        height: 3;
        width: 1fr;
        color: #636E7B;
        content-align: left middle;
        padding-left: 1;
    }
    .field-input { width: 1fr; }

    #btn-row { layout: horizontal; height: 3; margin-top: 1; }
    #btn-row Button { margin-right: 1; }

    #pull-log {
        height: 1fr;
        min-height: 4;
        background: $surface;
        border: round #D0D7DE;
        margin-top: 1;
        padding: 0 1;
    }

    #pulled-table {
        height: 1fr;
        min-height: 4;
        background: $surface;
        border: round #D0D7DE;
        margin-top: 1;
    }

    #status-bar {
        color: #636E7B;
        height: 1;
        margin-top: 0;
        padding: 0 1;
    }

    #creds-note { color: #636E7B; margin-bottom: 0; }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._history: list[str] = _load_history()
        self._kernel_map_cache: dict[str, dict[str, str]] = {}  # owner → {task_slug → kernel_slug}

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

            # Mode and auto-navigate
            yield Checkbox(
                "Single task  (skip benchmark discovery — slug is a direct task, not a benchmark)",
                value=False,
                id="single-task-mode",
            )
            yield Checkbox("Go to Merge after pull", value=True, id="auto-merge-switch")

            with Horizontal(id="btn-row"):
                yield Button("Pull All Tasks",  id="pull-btn",   variant="primary")
                yield Button("List tasks only", id="list-btn",   variant="default")
                yield Button("Browse My Tasks", id="browse-btn", variant="default")
                yield Button("Open on Kaggle",  id="open-btn",   variant="default")

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
        elif bid == "browse-btn":
            self._browse_my_tasks()
        elif bid == "open-btn":
            slug = self.query_one("#slug-input", Input).value.strip()
            if slug:
                from views.widgets import open_url
                url = f"https://www.kaggle.com/benchmarks/{slug}"
                if not open_url(url):
                    self.query_one("#pull-log", Log).write_line(f">> {url}")
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
        auto_merge  = self.query_one("#auto-merge-switch", Checkbox).value
        single_task = self.query_one("#single-task-mode",  Checkbox).value
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
        # Accept owner/task-slug  or  owner/task-slug/version
        parts = [p.strip() for p in slug.split("/") if p.strip()]
        if len(parts) < 2:
            log.write_line("[x] Slug must include owner and task name: owner/task-name")
            return
        user      = parts[0].lower()
        task_part = _re.sub(r"[^\w\s-]", "", parts[1]).strip().lower()
        task_part = _re.sub(r"[\s_]+", "-", task_part)
        # Third part, if present, is the version number
        version: int | None = None
        if len(parts) >= 3 and parts[2].isdigit():
            version = int(parts[2])
        slug = f"{user}/{task_part}"
        self._run_pull(slug, out_dir, download, auto_merge, single_task, version=version)

    # ------------------------------------------------------------------ #
    #  Core pull logic (runs in background thread)                        #
    # ------------------------------------------------------------------ #

    @work(thread=True)
    def _run_pull(self, slug: str, out_dir: Path, download: bool, auto_merge: bool, single_task: bool = False, version: int | None = None) -> None:
        log = self.query_one("#pull-log", Log)

        # Authenticate
        try:
            from kagglesdk import KaggleClient
            from config import config

            if not config.kaggle_username or not config.kaggle_key:
                log.write_line(
                    "[x] Credentials not configured.\n\n"
                    "   Make sure one of these is configured:\n"
                    "   • KAGGLE_USERNAME + KAGGLE_KEY in .env\n"
                    "   • ~/.kaggle/kaggle.json\n"
                    "   Get your token: kaggle.com → Settings → API → Create New Token"
                )
                return

            # kagglesdk's KaggleClient() prefers Bearer auth (from KAGGLE_API_TOKEN env
            # var or ~/.kaggle/access_token file) over basic auth (kaggle.json). The
            # Benchmark Tasks API returns 403 on Bearer auth. Force basic auth by
            # initialising the session and then overriding its .auth tuple directly.
            config.ensure_kaggle_json()
            kag_client = KaggleClient()
            _http = kag_client._http_client
            _http._init_session()
            _http._session.auth = (config.kaggle_username, config.kaggle_key)
            _http._signed_in = True
            log.write_line(f"[ok] Authenticated as {config.kaggle_username}\n")
        except ImportError:
            log.write_line("[x] kaggle / kagglesdk package not installed.")
            return
        except (SystemExit, Exception) as exc:
            log.write_line(
                f"[x] Authentication failed: {exc}\n\n"
                "   Make sure KAGGLE_USERNAME + KAGGLE_KEY are set in .env"
            )
            return

        # Discover tasks — either via leaderboard API or treat slug as a single task
        if single_task:
            version_hint = f"  (version {version})" if version else ""
            log.write_line(f">> Single-task mode: treating '{slug}'{version_hint} as a direct task slug.\n")
            task_slugs = [slug]
        else:
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
            run_files = self._pull_one_task(kag_client, task_slug, out_dir, log, version=version)
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
            if (auto_merge or single_task) and all_downloaded:
                self.app.switch_view("merge")  # type: ignore

        self.app.call_from_thread(_finish)

    # ------------------------------------------------------------------ #
    #  Task discovery                                                      #
    # ------------------------------------------------------------------ #

    def _discover_tasks(self, kag_client, benchmark_slug: str, log: Log) -> list[str]:
        """Find all tasks in a benchmark via the leaderboard API."""
        from core.discovery import discover_tasks
        log.write_line(f">> Discovering tasks in: {benchmark_slug}\n")
        slugs = discover_tasks(kag_client, benchmark_slug, log=log.write_line)
        if slugs:
            log.write_line(f"   Found {len(slugs)} task(s) via leaderboard API:\n")
            for s in slugs:
                log.write_line(f"   - {s}")
            return slugs
        log.write_line(
            f"\n[x] Could not discover tasks for '{benchmark_slug}'.\n\n"
            "   If this is a single task slug (not a benchmark), check\n"
            "   the 'Single task' checkbox and pull again.\n\n"
            "   Otherwise the benchmark may not have a leaderboard yet, or the slug is wrong.\n"
            "   Benchmark format: username/benchmark-name  (from kaggle.com/benchmarks/username/benchmark-name)"
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
        version: int | None = None,
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
                if version is not None:
                    slug_obj.version_number = version
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
                # Benchmark Tasks API requires task ownership. Fall back to the
                # Kernels API, which works for any public task regardless of owner.
                log.write_line(f"   (Benchmark Tasks API: {exc_str[:50]} — trying Kernels API…)")
                return self._pull_one_task_kernels(kag_client, task_slug, out_dir, log)
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

    def _pull_one_task_kernels(
        self,
        kag_client,
        task_slug: str,
        out_dir: Path,
        log: Log,
        resolved_slug: str | None = None,
    ) -> list[Path] | None:
        """Fallback: list .run.json outputs via the Kernels API and download directly.

        Works for any public task regardless of ownership — used when the Benchmark
        Tasks API returns 403/404 because the authenticated user is not the task owner.
        Returns list[Path] on success (may be empty), None on 403/404.
        """
        import requests
        from kagglesdk.kernels.types.kernels_api_service import ApiListKernelSessionOutputRequest
        from config import config as _cfg

        owner, default_slug = task_slug.split("/", 1)
        kernel_slug = resolved_slug if resolved_slug is not None else default_slug
        all_run_files = []
        page_token = ""

        try:
            while True:
                req = ApiListKernelSessionOutputRequest()
                req.user_name   = owner
                req.kernel_slug = kernel_slug
                req.page_size   = 100
                if page_token:
                    req.page_token = page_token
                resp = self._api_call_with_retry(
                    lambda r=req: kag_client.kernels.kernels_api_client.list_kernel_session_output(r),
                    log, "list kernel outputs",
                )
                all_run_files += [
                    f for f in (resp.files or [])
                    if Path(f.file_name).name.endswith(".run.json")
                ]
                page_token = resp.next_page_token or ""
                if not page_token:
                    break
        except Exception as exc:
            exc_str = str(exc)
            if "403" in exc_str or "404" in exc_str:
                if resolved_slug is None:
                    # Direct slug failed — scan owner's notebooks to find the real kernel slug
                    km = self._kernel_map_cache.get(owner)
                    if km is None:
                        log.write_line(f"   (scanning {owner}'s notebooks to resolve task slug…)")
                        km = self._build_kernel_map(kag_client, owner, log)
                    hit = km.get(task_slug)
                    if hit:
                        log.write_line(f"   (found matching notebook: {owner}/{hit})")
                        return self._pull_one_task_kernels(
                            kag_client, task_slug, out_dir, log, resolved_slug=hit
                        )
                log.write_line(
                    f"   [x] {task_slug}: kernel not found (slug mismatch or private).\n"
                    f"   Authenticated as: {_cfg.kaggle_username or '(unknown)'}\n"
                    "   Most likely cause: the benchmark creator named their notebook\n"
                    "   generically (e.g. 'task-7') — it doesn't match the task slug.\n"
                    "   Other possibilities:\n"
                    "   • Notebook is private — only the owner can pull it\n"
                    "   • No model runs have completed yet"
                )
                return None
            log.write_line(f"   [x] Kernels API failed for {task_slug}: {exc_str}")
            return []

        if not all_run_files:
            log.write_line(f"   [!] No .run.json files found in kernel outputs for {task_slug}")
            return []

        log.write_line(f"   Found {len(all_run_files)} .run.json file(s) via Kernels API")
        saved: list[Path] = []
        for fi in all_run_files:
            dest = out_dir / Path(fi.file_name).name
            if dest.exists():
                saved.append(dest)
                continue
            try:
                r = requests.get(
                    fi.url,
                    auth=(_cfg.kaggle_username, _cfg.kaggle_key),
                    timeout=60,
                )
                r.raise_for_status()
                dest.write_bytes(r.content)
                saved.append(dest)
                log.write_line(f"   + {Path(fi.file_name).name}")
            except Exception as exc:
                log.write_line(f"   [!] Download failed for {fi.file_name}: {exc}")

        return saved

    def _build_kernel_map(self, kag_client, owner: str, log: Log) -> dict[str, str]:
        """List owner's kernels and build a task_slug → kernel_slug map.

        Checks each recently-active kernel's outputs for .run.json filenames, which
        embed the task name as a prefix (e.g. Task_Slug-run_id_N_…).  Populates
        self._kernel_map_cache[owner] and returns the map.
        """
        from kagglesdk.kernels.types.kernels_api_service import (
            ApiListKernelsRequest,
            ApiListKernelSessionOutputRequest,
        )

        # Note: benchmark task runs do NOT update a kernel's public last_run_time —
        # only manual notebook runs do. Kernels used exclusively as benchmark tasks
        # often have null or stale last_run_time even when they have recent outputs.
        # We must scan all kernels; the 200 cap bounds the cost.
        # ApiListKernelsRequest uses integer page pagination — next_page_token is never
        # populated by this endpoint, so we must increment req.page explicitly.
        import time as _time
        kernels = []
        page = 1
        while len(kernels) < 200:
            req = ApiListKernelsRequest()
            req.user      = owner
            req.page_size = 20
            req.page      = page
            try:
                resp = self._api_call_with_retry(
                    lambda r=req: kag_client.kernels.kernels_api_client.list_kernels(r),
                    log, f"list kernels/{owner} page {page}",
                )
            except Exception:
                break
            new_kernels = resp.kernels or []
            if not new_kernels:
                break
            kernels.extend(new_kernels)
            if len(new_kernels) < 20:
                break  # last partial page
            page += 1
            _time.sleep(0.2)

        log.write_line(f"   ({len(kernels)} recently-active notebook(s) found for {owner})")
        task_map: dict[str, str] = {}
        for i, k in enumerate(kernels):
            if i and i % 10 == 0:
                log.write_line(f"   (scanned {i}/{len(kernels)} notebooks…)")
            parts = (k.ref or "").split("/", 1)
            if len(parts) < 2:
                continue
            k_slug = parts[1]
            try:
                out_req = ApiListKernelSessionOutputRequest()
                out_req.user_name   = owner
                out_req.kernel_slug = k_slug
                out_req.page_size   = 100
                out_resp = self._api_call_with_retry(
                    lambda r=out_req: kag_client.kernels.kernels_api_client.list_kernel_session_output(r),
                    log, f"scan {k_slug}",
                )
                for fi in (out_resp.files or []):
                    fname = Path(fi.file_name).name
                    if not fname.endswith(".run.json"):
                        continue
                    if "-run_id_" in fname:
                        prefix = fname.split("-run_id_")[0]
                    else:
                        prefix = fname[: -len(".run.json")]
                    derived = prefix.lower().replace("_", "-")
                    task_map[f"{owner}/{derived}"] = k_slug
            except Exception:
                pass
            _time.sleep(0.1)

        log.write_line(f"   → {len(task_map)} task slug(s) mapped")
        self._kernel_map_cache[owner] = task_map
        return task_map

    # ------------------------------------------------------------------ #
    #  Browse own tasks                                                    #
    # ------------------------------------------------------------------ #

    @work(thread=True)
    def _browse_my_tasks(self) -> None:
        log = self.query_one("#pull-log", Log)
        log.clear()
        log.write_line(">> Listing your benchmark tasks…\n")

        try:
            from kagglesdk import KaggleClient
            from config import config as _cfg
            if not _cfg.kaggle_username or not _cfg.kaggle_key:
                log.write_line("[x] Credentials not configured. Run wizard (w) to set KAGGLE_USERNAME + KAGGLE_KEY.")
                return
            _cfg.ensure_kaggle_json()
            kag_client = KaggleClient()
            _http = kag_client._http_client
            _http._init_session()
            _http._session.auth = (_cfg.kaggle_username, _cfg.kaggle_key)
            _http._signed_in = True
        except Exception as exc:
            log.write_line(f"[x] Auth failed: {exc}")
            return

        try:
            from kagglesdk.benchmarks.types.benchmark_tasks_api_service import ApiListBenchmarkTasksRequest
            client = kag_client.benchmarks.benchmark_tasks_api_client
            page_token = ""
            count = 0
            while True:
                req = ApiListBenchmarkTasksRequest()
                req.page_size = 100
                if page_token:
                    req.page_token = page_token
                resp = client.list_benchmark_tasks(req)
                for t in resp.tasks or []:
                    slug_obj = t.slug
                    if slug_obj and hasattr(slug_obj, "owner_slug"):
                        owner = slug_obj.owner_slug or ""
                        tslug = slug_obj.task_slug  or ""
                        ver   = slug_obj.version_number or 0
                        slug_str = f"{owner}/{tslug}" + (f"/{ver}" if ver else "")
                    else:
                        slug_str = str(slug_obj or "(unknown)")
                    state = str(t.creation_state or "").replace(
                        "BENCHMARK_TASK_VERSION_CREATION_STATE_", "")
                    url = getattr(t, "url", "") or ""
                    log.write_line(f"  slug:  {slug_str}")
                    log.write_line(f"  url:   {url or '(none)'}")
                    log.write_line(f"  state: {state}")
                    log.write_line("")
                    count += 1
                page_token = resp.next_page_token or ""
                if not page_token:
                    break

            log.write_line(f"\n>> {count} task(s) found.")
            if count > 0:
                log.write_line(
                    "   Tip: copy the 'slug:' line above → paste into the slug field,\n"
                    "   check 'Single task' mode, then click Pull.\n"
                    "   Format: owner/task-slug  or  owner/task-slug/version"
                )
        except Exception as exc:
            log.write_line(f"[x] Failed to list tasks: {exc}")

    # ------------------------------------------------------------------ #
    #  Table + history                                                     #
    # ------------------------------------------------------------------ #

    def _populate_table(self, items: list[tuple[str, Path]], log: Log) -> None:
        from core.merger import parse_run_json

        table = self.query_one("#pulled-table", DataTable)
        table.clear()

        for task_slug, path in items:
            size_kb = round(path.stat().st_size / 1024, 1)
            file_rows, _ = parse_run_json(path)
            if file_rows:
                row   = file_rows[0]
                task  = row.get("task_name", "?")
                model = row.get("model_name", "?").split("/")[-1]
                score = "pass" if row.get("score", 0) >= 0.5 else "fail"
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
