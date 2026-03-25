"""Monitor view — watch benchmarks for new tasks and auto-pull/publish."""

import json
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Checkbox, DataTable, Input, Label, Log, Static

from config import config

MANIFEST_FILE = Path(".evalflow_manifest.json")


def _load_manifest() -> dict:
    try:
        return json.loads(MANIFEST_FILE.read_text())
    except Exception:
        return {}


def _save_manifest(manifest: dict) -> None:
    try:
        MANIFEST_FILE.write_text(json.dumps(manifest, indent=2))
    except Exception:
        pass


_CRON_MARKER = "# evalflow-monitor"
_WORKDIR     = str(Path(__file__).parent.parent)
# Prefer the project venv if it exists, fall back to system python3
_VENV_PYTHON = Path(_WORKDIR) / "venv" / "bin" / "python"
_PYTHON      = str(_VENV_PYTHON) if _VENV_PYTHON.exists() else "python3"
_SCRIPT      = str(Path(__file__).parent.parent / "monitor.py")


def _cron_line(hh: int, mm: int) -> str:
    return (
        f"{mm} {hh} * * *  cd {_WORKDIR} && {_PYTHON} {_SCRIPT} --all"
        f" >> {_WORKDIR}/monitor.log 2>&1  {_CRON_MARKER}"
    )


def _read_crontab() -> str:
    try:
        r = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        return r.stdout if r.returncode == 0 else ""
    except Exception:
        return ""


def _write_crontab(content: str) -> None:
    subprocess.run(["crontab", "-"], input=content, text=True, check=True)


def _get_schedule() -> tuple[bool, int, int]:
    for line in _read_crontab().splitlines():
        if _CRON_MARKER in line and not line.strip().startswith("#"):
            parts = line.split()
            try:
                return True, int(parts[1]), int(parts[0])
            except (IndexError, ValueError):
                pass
    return False, 11, 0


def _set_schedule(enabled: bool, hh: int, mm: int) -> None:
    lines = [l for l in _read_crontab().splitlines() if _CRON_MARKER not in l]
    if enabled:
        lines.append(_cron_line(hh, mm))
    _write_crontab("\n".join(lines) + "\n")


def _next_run_text(enabled: bool, hh: int, mm: int) -> str:
    if not enabled:
        return "Schedule disabled"
    from datetime import timedelta
    now = datetime.now()
    next_run = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if next_run <= now:
        next_run += timedelta(days=1)
    delta = next_run - now
    hours, rem = divmod(int(delta.total_seconds()), 3600)
    mins = rem // 60
    return f"Next run: {next_run.strftime('%Y-%m-%d %H:%M')}  (in {hours}h {mins}m)"


def _discover_tasks(api, benchmark_slug: str, kag_client=None, log=None) -> list[str]:
    """
    Return all task notebook slugs inside a benchmark.

    Strategy 1: get_benchmark_leaderboard — extracts task slugs directly from
                the leaderboard API (benchmark_task_slug field).
    Strategy 2: kernels_list(parent=) — official parent/child API.
    Strategy 3: treat the slug itself as a single task.
    """
    def write(msg):
        if log:
            log(msg)

    username, slug_name = benchmark_slug.split("/", 1)

    # Strategy 1: benchmark leaderboard API → task slugs
    if kag_client is not None:
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
                        short = tr.benchmark_task_slug.rstrip('/').split('/')[-1]
                        task_slugs.add(short)
            if task_slugs:
                slugs = [f"{username}/{s}" for s in sorted(task_slugs)]
                write(f"   Found {len(slugs)} task(s) via leaderboard API")
                return slugs
        except Exception as exc:
            write(f"   (leaderboard API failed: {exc})")

    # Strategy 2: kernels_list parent lookup
    try:
        children = api.kernels_list(parent=benchmark_slug, page_size=100)
        if children:
            slugs = [k.ref for k in children if k.ref]
            if slugs:
                write(f"   Found {len(slugs)} task(s) via parent lookup")
                return slugs
    except Exception:
        pass

    # Strategy 3: treat as single task
    write(f"   Treating '{benchmark_slug}' as a single task")
    return [benchmark_slug]


class MonitorView(Vertical):
    _BTN_IDS = ["check-btn", "add-btn", "remove-btn"]

    BINDINGS = [
        Binding("ctrl+r", "check_all", "Check All", show=True, key_display="Ctrl+R"),
    ]

    DEFAULT_CSS = """
    MonitorView { padding: 0 1; height: 1fr; }
    .section-title { color: $primary; text-style: bold; margin-top: 0; margin-bottom: 0; }

    #watcher-table {
        height: 8;
        min-height: 4;
        border: solid $primary 15%;
        background: $surface;
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
        color: $text-muted;
        content-align: right middle;
        padding-right: 2;
    }
    .field-input { width: 46; }

    #add-row { layout: horizontal; height: 3; margin-bottom: 0; }
    #add-row Button { margin-right: 1; }

    #btn-row { layout: horizontal; height: 3; margin-top: 0; margin-bottom: 0; }
    #btn-row Button { margin-right: 1; }

    #monitor-log {
        height: 1fr;
        min-height: 4;
        border: solid $primary 15%;
        background: $surface;
        margin-top: 0;
    }

    #schedule-panel {
        height: 3;
        border: solid $primary 15%;
        background: $surface;
        padding: 0 1;
        margin-top: 0;
        color: $success;
    }
    #schedule-row { layout: horizontal; height: 3; align: left middle; margin-bottom: 0; }
    #time-input { width: 16; }
    #save-schedule-btn { margin-left: 1; }
    #log-title-row { layout: horizontal; height: 3; align: left middle; }
    #log-title-row .section-title { width: 1fr; }
    #load-log-btn { margin-left: 1; }

    #publish-check { margin-bottom: 0; }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._manifest: dict = _load_manifest()
        self._log_file_pos: int = 0   # byte offset — only new lines are appended

    def compose(self) -> ComposeResult:
        yield Static("Monitor — Auto-Watch Benchmarks", classes="section-title")

        yield DataTable(id="watcher-table", cursor_type="row", zebra_stripes=True)

        with Horizontal(id="btn-row"):
            yield Button("Check All Now", id="check-btn", variant="primary")
            yield Button("Check Selected", id="check-sel-btn", variant="default")
            yield Button("Remove Selected", id="remove-btn", variant="default")

        yield Static("Add / Edit Watcher", classes="section-title")

        with Horizontal(classes="field-row"):
            yield Label("Benchmark slug:", classes="field-label")
            yield Input(placeholder="username/benchmark-name", id="slug-input", classes="field-input")

        with Horizontal(classes="field-row"):
            yield Label("Dataset slug:", classes="field-label")
            yield Input(placeholder="my-benchmark-results", id="dataset-slug-input", classes="field-input")

        with Horizontal(classes="field-row"):
            yield Label("Dataset title:", classes="field-label")
            yield Input(placeholder="My Benchmark Results", id="dataset-title-input", classes="field-input")

        yield Checkbox("Auto-publish when new tasks found", value=True, id="publish-check")

        with Horizontal(id="add-row"):
            yield Button("Add / Update Watcher", id="add-btn", variant="primary")
            yield Button("Force Republish Selected", id="republish-btn", variant="default")
            yield Button("Push to GitHub", id="push-github-btn", variant="default")

        with Horizontal(id="log-title-row"):
            yield Static("Monitor Log", classes="section-title")
            yield Button("Load log file", id="load-log-btn", variant="default")
        yield Log(id="monitor-log", highlight=True)

        yield Static("Daily Schedule", classes="section-title")

        with Horizontal(id="schedule-row"):
            yield Label("Run daily at:", classes="field-label")
            yield Input(value="11:00", id="time-input")
            yield Checkbox("Enable", value=False, id="schedule-enable")
            yield Button("Save Schedule", id="save-schedule-btn", variant="default")

        yield Static("", id="schedule-panel")

    def on_mount(self) -> None:
        table = self.query_one("#watcher-table", DataTable)
        table.add_columns("Benchmark", "Known Tasks", "Last Checked", "Last Pull", "Dataset", "Publish")
        self._refresh_table()
        self.set_interval(5, self._poll_log_file)

    def on_activate(self) -> None:
        self._manifest = _load_manifest()
        self._refresh_table()
        self._load_schedule_ui()
        self._load_log_file()

    def _load_schedule_ui(self) -> None:
        enabled, hh, mm = _get_schedule()
        self.query_one("#time-input", Input).value = f"{hh:02d}:{mm:02d}"
        self.query_one("#schedule-enable", Checkbox).value = enabled
        self.query_one("#schedule-panel").update(_next_run_text(enabled, hh, mm))

    def _save_schedule(self) -> None:
        log = self.query_one("#monitor-log", Log)
        time_str = self.query_one("#time-input", Input).value.strip()
        enabled  = self.query_one("#schedule-enable", Checkbox).value
        try:
            hh, mm = [int(x) for x in time_str.split(":")]
            assert 0 <= hh <= 23 and 0 <= mm <= 59
        except Exception:
            log.write_line("[x] Invalid time — use HH:MM format (e.g. 11:00)")
            return
        try:
            _set_schedule(enabled, hh, mm)
            status = _next_run_text(enabled, hh, mm)
            self.query_one("#schedule-panel").update(status)
            log.write_line(f"[ok] Schedule {'enabled' if enabled else 'disabled'}: {status}")
        except Exception as exc:
            log.write_line(f"[x] Could not update crontab: {exc}")

    # ------------------------------------------------------------------ #
    #  Table                                                               #
    # ------------------------------------------------------------------ #

    def _refresh_table(self) -> None:
        table = self.query_one("#watcher-table", DataTable)
        table.clear()
        for slug, entry in self._manifest.items():
            table.add_row(
                slug,
                str(len(entry.get("known_tasks", []))),
                self._fmt_dt(entry.get("last_checked")),
                self._fmt_dt(entry.get("last_pull")),
                entry.get("dataset_slug", "—"),
                "yes" if entry.get("publish") else "no",
                key=slug,
            )

    @staticmethod
    def _fmt_dt(iso: str | None) -> str:
        if not iso:
            return "never"
        try:
            return datetime.fromisoformat(iso).strftime("%Y-%m-%d %H:%M")
        except Exception:
            return iso[:16]

    def _selected_slug(self) -> str | None:
        table = self.query_one("#watcher-table", DataTable)
        if table.cursor_row < 0 or not self._manifest:
            return None
        keys = list(self._manifest.keys())
        idx  = table.cursor_row
        return keys[idx] if idx < len(keys) else None

    # ------------------------------------------------------------------ #
    #  Events                                                              #
    # ------------------------------------------------------------------ #

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """Populate the form with the selected watcher's settings."""
        slug = self._selected_slug()
        if not slug or slug not in self._manifest:
            return
        entry = self._manifest[slug]
        self.query_one("#slug-input", Input).value = slug
        self.query_one("#dataset-slug-input", Input).value = entry.get("dataset_slug", "")
        self.query_one("#dataset-title-input", Input).value = entry.get("dataset_title", "")
        self.query_one("#publish-check", Checkbox).value = bool(entry.get("publish", True))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "add-btn":
            self._add_watcher()
        elif bid == "check-btn":
            self._check_all()
        elif bid == "check-sel-btn":
            slug = self._selected_slug()
            if slug:
                self._check_one(slug)
            else:
                self.query_one("#monitor-log", Log).write_line("[x] No watcher selected.")
        elif bid == "remove-btn":
            self._remove_selected()
        elif bid == "republish-btn":
            slug = self._selected_slug()
            if slug:
                self._force_republish(slug)
            else:
                self.query_one("#monitor-log", Log).write_line("[x] Select a watcher row first.")
        elif bid == "save-schedule-btn":
            self._save_schedule()
        elif bid == "load-log-btn":
            self._load_log_file()
        elif bid == "push-github-btn":
            self._push_to_github()

    def action_check_all(self) -> None:
        self._check_all()

    # ------------------------------------------------------------------ #
    #  Add / Remove                                                        #
    # ------------------------------------------------------------------ #

    def _add_watcher(self) -> None:
        log   = self.query_one("#monitor-log", Log)
        slug  = self.query_one("#slug-input", Input).value.strip().strip("/")
        ds    = self.query_one("#dataset-slug-input", Input).value.strip()
        title = self.query_one("#dataset-title-input", Input).value.strip()
        pub   = self.query_one("#publish-check", Checkbox).value

        if not slug or "/" not in slug:
            log.write_line("[x] Benchmark slug is required (format: username/benchmark-name)")
            return

        is_update = slug in self._manifest
        entry = self._manifest.get(slug, {"known_tasks": []})

        # If dataset details are being filled in for the first time (or changed),
        # reset known_tasks so the next check re-pulls and republishes everything.
        dataset_changed = (ds and ds != entry.get("dataset_slug")) or \
                          (title and title != entry.get("dataset_title"))
        if is_update and dataset_changed:
            entry["known_tasks"] = []
            log.write_line(f"[!] Dataset details changed — resetting known tasks so next check re-pulls.")

        if ds:
            entry["dataset_slug"]  = ds
        if title:
            entry["dataset_title"] = title
        entry["publish"] = pub

        self._manifest[slug] = entry
        _save_manifest(self._manifest)
        self._refresh_table()

        self.query_one("#slug-input",         Input).value = ""
        self.query_one("#dataset-slug-input",  Input).value = ""
        self.query_one("#dataset-title-input", Input).value = ""
        action = "Updated" if is_update else "Watching"
        log.write_line(f"[ok] {action}: {slug}")

    def _remove_selected(self) -> None:
        log  = self.query_one("#monitor-log", Log)
        slug = self._selected_slug()
        if not slug:
            log.write_line("[x] No watcher selected.")
            return
        del self._manifest[slug]
        _save_manifest(self._manifest)
        self._refresh_table()
        log.write_line(f"[ok] Removed: {slug}")

    # ------------------------------------------------------------------ #
    #  Check workers                                                       #
    # ------------------------------------------------------------------ #

    def _check_all(self) -> None:
        if not self._manifest:
            self.query_one("#monitor-log", Log).write_line("[x] No watchers configured. Add one above.")
            return
        for slug in list(self._manifest.keys()):
            self._check_one(slug)

    def _check_one(self, slug: str) -> None:
        self.query_one("#monitor-log", Log).write_line(f"\n>> Checking {slug} …")
        self._run_check(slug)

    @work(thread=True, exclusive=False)
    def _run_check(self, slug: str) -> None:
        log = self.query_one("#monitor-log", Log)

        def write(msg: str) -> None:
            self.app.call_from_thread(log.write_line, msg)

        import os, shutil, requests
        from kaggle.api.kaggle_api_extended import KaggleApi
        from kagglesdk import KaggleClient
        from kagglesdk.kernels.types.kernels_api_service import ApiListKernelSessionOutputRequest
        from core.merger import discover_outputs, merge_outputs

        username = config.kaggle_username
        api_key  = config.kaggle_key
        if not username or not api_key:
            write("[x] Credentials not configured.")
            return

        if config.kaggle_username:
            os.environ["KAGGLE_USERNAME"] = config.kaggle_username
        if config.kaggle_key:
            os.environ["KAGGLE_KEY"] = config.kaggle_key

        try:
            api        = KaggleApi(); api.authenticate()
            kag_client = KaggleClient(username=username, api_token=api_key)
        except Exception as exc:
            write(f"[x] Auth failed: {exc}"); return

        # ── Discover current tasks ────────────────────────────────────
        current_tasks: list[str] = _discover_tasks(api, slug, kag_client=kag_client, log=write)

        entry     = self._manifest.get(slug, {"known_tasks": []})
        known     = set(entry.get("known_tasks", []))
        new_tasks = [t for t in current_tasks if t not in known]

        now = datetime.now().isoformat(timespec="seconds")

        if not new_tasks:
            write(f"   ✅ No new tasks. ({len(current_tasks)} known)")
            entry["last_checked"] = now
            self._manifest[slug]  = entry
            _save_manifest(self._manifest)
            self.app.call_from_thread(self._refresh_table)
            return

        write(f"   🆕 {len(new_tasks)} new task(s): {', '.join(new_tasks)}")

        # ── Pull new tasks ────────────────────────────────────────────
        out_dir = config.output_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        all_downloaded: list[Path] = []
        pulled_tasks: set[str] = set()   # tasks that had at least one file downloaded

        for task_slug in new_tasks:
            write(f"\n   Pulling: {task_slug}")
            owner, kernel_slug = task_slug.split("/", 1)
            page_token = None
            run_files  = []
            try:
                while True:
                    req = ApiListKernelSessionOutputRequest()
                    req.user_name   = owner
                    req.kernel_slug = kernel_slug
                    req.page_size   = 100
                    if page_token:
                        req.page_token = page_token
                    resp = kag_client.kernels.kernels_api_client.list_kernel_session_output(req)
                    run_files  += [f for f in (resp.files or []) if f.file_name.endswith(".run.json")]
                    page_token  = resp.next_page_token or ""
                    if not page_token:
                        break
            except Exception as exc:
                exc_str = str(exc)
                if "403" in exc_str:
                    write(f"   ⏳ {task_slug}: no accessible runs yet (403) — skipping.")
                else:
                    write(f"   [!] List failed: {exc_str}")
                continue

            for fi in run_files:
                dest = out_dir / fi.file_name
                try:
                    r = requests.get(fi.url, auth=(username, api_key), timeout=60)
                    r.raise_for_status()
                    dest.write_bytes(r.content)
                    all_downloaded.append(dest)
                    pulled_tasks.add(task_slug)
                    write(f"   + {fi.file_name}")
                except Exception as exc:
                    write(f"   [!] Download failed: {exc}")

        if not all_downloaded:
            write("   ⚠  No files downloaded.")
            entry["last_checked"] = now
            self._manifest[slug]  = entry
            _save_manifest(self._manifest)
            self.app.call_from_thread(self._refresh_table)
            return

        # ── Merge ─────────────────────────────────────────────────────
        write("\n   Merging …")
        try:
            run_files = discover_outputs(out_dir)
            sft_df, pref_df, stats = merge_outputs(run_files, out_dir)
            write(f"   evalflow_sft.csv         — {len(sft_df)} rows")
            write(f"   evalflow_preferences.csv — {len(pref_df)} preference pairs")
        except Exception as exc:
            write(f"   [!] Merge failed: {exc}")

        # ── Publish ───────────────────────────────────────────────────
        if entry.get("publish") and not entry.get("dataset_slug"):
            write("   ⚠  Auto-publish is on but no Dataset slug is set — skipping publish.")
            write("      Edit the watcher: remove it, re-add with Dataset slug + title filled in.")
        if entry.get("publish") and entry.get("dataset_slug") and entry.get("dataset_title"):
            from core.uploader import upload_dataset
            ds_slug  = entry["dataset_slug"]
            ds_title = entry["dataset_title"]
            staging  = out_dir / "staging" / ds_slug
            if staging.exists():
                shutil.rmtree(staging)
            staging.mkdir(parents=True, exist_ok=True)

            for csv_name in ("evalflow_sft.csv", "evalflow_preferences.csv"):
                src = out_dir / csv_name
                if src.exists():
                    shutil.copy2(src, staging / csv_name)

            (staging / "dataset-metadata.json").write_text(json.dumps({
                "title":    ds_title,
                "id":       f"{username}/{ds_slug}",
                "licenses": [{"name": "CC0-1.0"}],
            }, indent=2))

            write(f"\n   Publishing {username}/{ds_slug} …")
            result = upload_dataset(folder=staging, is_update=True, append=True, log_cb=write)
            if not result.success:
                write(f"   [x] {result.error}")

        # ── Save manifest ─────────────────────────────────────────────
        # Only mark tasks as known if we successfully pulled files from them.
        # Tasks that returned 403 (no runs yet) stay unknown so they are retried.
        entry["known_tasks"]  = list(known | pulled_tasks)
        entry["last_checked"] = now
        entry["last_pull"]    = now
        self._manifest[slug]  = entry
        _save_manifest(self._manifest)
        self.app.call_from_thread(self._refresh_table)

    # ------------------------------------------------------------------ #
    #  Force republish                                                     #
    # ------------------------------------------------------------------ #

    @work(thread=True, exclusive=False)
    def _force_republish(self, slug: str) -> None:
        log = self.query_one("#monitor-log", Log)

        def write(msg: str) -> None:
            self.app.call_from_thread(log.write_line, msg)

        entry = self._manifest.get(slug, {})
        if not entry.get("dataset_slug") or not entry.get("dataset_title"):
            write("[x] No dataset slug/title set for this watcher — fill them in and click Add/Update first.")
            return

        import os, shutil
        from config import config as _cfg

        username = _cfg.kaggle_username
        api_key  = _cfg.kaggle_key
        if not username or not api_key:
            write("[x] Credentials not configured."); return
        if _cfg.kaggle_username:
            os.environ["KAGGLE_USERNAME"] = _cfg.kaggle_username
        if _cfg.kaggle_key:
            os.environ["KAGGLE_KEY"] = _cfg.kaggle_key

        sft_src  = _cfg.output_dir / "evalflow_sft.csv"
        pref_src = _cfg.output_dir / "evalflow_preferences.csv"
        if not sft_src.exists():
            write("[x] evalflow_sft.csv not found — run a check/pull first."); return

        from core.uploader import upload_dataset
        ds_slug  = entry["dataset_slug"]
        ds_title = entry["dataset_title"]
        staging  = _cfg.output_dir / "staging" / ds_slug
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir(parents=True, exist_ok=True)
        for csv_name, src in [("evalflow_sft.csv", sft_src), ("evalflow_preferences.csv", pref_src)]:
            if src.exists():
                shutil.copy2(src, staging / csv_name)
        import json
        (staging / "dataset-metadata.json").write_text(json.dumps({
            "title":    ds_title,
            "id":       f"{username}/{ds_slug}",
            "licenses": [{"name": "CC0-1.0"}],
        }, indent=2))
        write(f"\n>> Force-publishing {username}/{ds_slug} …")
        result = upload_dataset(folder=staging, is_update=True, append=True, log_cb=write)
        if not result.success:
            write(f"   [x] {result.error}")

    # ------------------------------------------------------------------ #
    #  Push manifest to GitHub                                           #
    # ------------------------------------------------------------------ #

    @work(thread=True)
    def _push_to_github(self) -> None:
        log = self.query_one("#monitor-log", Log)

        def write(msg: str):
            self.app.call_from_thread(log.write_line, msg)

        write("\n>> Pushing manifest to GitHub …")
        manifest_path = str(Path(_WORKDIR) / ".evalflow_manifest.json")
        steps = [
            (["git", "-C", _WORKDIR, "add", manifest_path],        "Staging manifest …"),
            (["git", "-C", _WORKDIR, "commit", "-m", "update: monitor manifest [evalflow]"], "Committing …"),
            (["git", "-C", _WORKDIR, "push"],                       "Pushing …"),
        ]
        for cmd, label in steps:
            write(f"   {label}")
            r = subprocess.run(cmd, capture_output=True, text=True)
            if r.returncode != 0:
                if "nothing to commit" in r.stdout + r.stderr:
                    write("   (nothing to commit — manifest already up to date)")
                    continue
                write(f"   [x] {r.stderr.strip() or r.stdout.strip()}")
                return
        write("   ✅ Manifest pushed — GitHub Actions will use updated watchers on next run.")

    # ------------------------------------------------------------------ #
    #  Log file                                                            #
    # ------------------------------------------------------------------ #

    def _load_log_file(self) -> None:
        """Load (or reload) the full tail of monitor.log and reset the poll position."""
        log = self.query_one("#monitor-log", Log)
        log_path = Path(_WORKDIR) / "monitor.log"
        if not log_path.exists():
            log.write_line("[!] monitor.log not found — schedule may not have run yet.")
            self._log_file_pos = 0
            return
        text = log_path.read_text(errors="replace")
        lines = text.splitlines()
        log.clear()
        for line in lines[-200:]:
            log.write_line(line)
        log.write_line(f"── loaded {len(lines)} lines ── (auto-refreshes every 5 s) ──")
        self._log_file_pos = log_path.stat().st_size

    def _poll_log_file(self) -> None:
        """Append any new bytes written to monitor.log since the last read."""
        log_path = Path(_WORKDIR) / "monitor.log"
        if not log_path.exists():
            return
        current_size = log_path.stat().st_size
        if current_size <= self._log_file_pos:
            return
        try:
            with open(log_path, errors="replace") as fh:
                fh.seek(self._log_file_pos)
                new_text = fh.read()
            self._log_file_pos = current_size
            log = self.query_one("#monitor-log", Log)
            for line in new_text.splitlines():
                log.write_line(line)
        except Exception:
            pass