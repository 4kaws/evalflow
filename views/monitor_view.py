"""Monitor view — watch benchmarks for new tasks and auto-pull/publish."""

import json
import re as _re
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Checkbox, DataTable, Input, Label, Log, Select, Static

from config import config
from core.discovery import discover_tasks as _discover_tasks_api
from core.merger import SFT_FILENAME, PREF_FILENAME, row_count as _row_count
from core.uploader import DEFAULT_LICENSE
from monitor import MANIFEST_FILE, load_manifest as _load_manifest, save_manifest as _save_manifest
from views.widgets import LogExpandIcon, PageHeader


_WORKDIR       = str(Path(__file__).parent.parent)
_WORKFLOW_FILE = Path(__file__).parent.parent / ".github" / "workflows" / "evalflow_ci.yml"

_WORKFLOW_TZ = "Europe/Bucharest"

TIMEZONES: list[tuple[str, str]] = [
    ("UTC",              "UTC"),
    ("US / Eastern",     "America/New_York"),
    ("US / Central",     "America/Chicago"),
    ("US / Mountain",    "America/Denver"),
    ("US / Pacific",     "America/Los_Angeles"),
    ("Brazil / Brasília","America/Sao_Paulo"),
    ("UK / London",      "Europe/London"),
    ("Europe / Paris",   "Europe/Paris"),
    ("Europe / Berlin",  "Europe/Berlin"),
    ("Europe / Bucharest","Europe/Bucharest"),
    ("Gulf / Dubai",     "Asia/Dubai"),
    ("India / Kolkata",  "Asia/Kolkata"),
    ("China / Shanghai", "Asia/Shanghai"),
    ("Japan / Tokyo",    "Asia/Tokyo"),
    ("Australia / Sydney","Australia/Sydney"),
]


def _get_schedule() -> tuple[bool, int, int, str]:
    """Read schedule from GitHub Actions workflow. Returns (found, hh, mm, tz)."""
    try:
        content = _WORKFLOW_FILE.read_text()
        m = _re.search(r'cron:\s*"(\d+)\s+(\d+)\s+\*\s+\*\s+\*"', content)
        if m:
            mm, hh = int(m.group(1)), int(m.group(2))
            tz_m = _re.search(r'timezone:\s*"([^"]+)"', content)
            tz = tz_m.group(1) if tz_m else _WORKFLOW_TZ
            return True, hh, mm, tz
    except Exception:
        pass
    return False, 0, 0, "UTC"


def _set_schedule_in_workflow(hh: int, mm: int, tz: str = _WORKFLOW_TZ) -> None:
    """Update (or add) the cron expression in the GitHub Actions workflow file."""
    _valid_tzs = {v for _, v in TIMEZONES}
    if tz not in _valid_tzs:
        raise ValueError(f"Unknown timezone: {tz!r}")
    content = _WORKFLOW_FILE.read_text()
    new_cron = f'    - cron: "{mm} {hh} * * *"\n      timezone: "{tz}"\n'
    if _re.search(r'[ \t]*- cron:\s*"', content):
        content = _re.sub(
            r'[ \t]*- cron: "[^"]*"[^\n]*\n([ \t]*timezone:[^\n]*)?\n?',
            new_cron,
            content,
        )
    else:
        # No schedule block yet — insert one before env: or jobs:
        schedule_block = f'\n  schedule:\n{new_cron}\n'
        for marker in ('\nenv:', '\njobs:'):
            if marker in content:
                content = content.replace(marker, schedule_block + marker, 1)
                break
    _WORKFLOW_FILE.write_text(content)


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


class MonitorView(Vertical):
    _BTN_IDS = ["check-btn", "add-btn", "remove-btn"]

    BINDINGS = [
        Binding("ctrl+l", "toggle_log_focus", "Expand log", show=True, key_display="Ctrl+L", priority=True),
        Binding("ctrl+r", "check_all", "Check All", show=True, key_display="Ctrl+R"),
    ]

    DEFAULT_CSS = """
    MonitorView { padding: 0; height: 1fr; }

    #schedule-section { padding: 1 3 0 3; height: auto; }
    #schedule-row { layout: horizontal; height: 3; align: left middle; margin-bottom: 0; }
    #sched-label { width: 13; height: 3; color: #636E7B; content-align: right middle; padding-right: 2; }
    #time-input { width: 12; }
    #tz-select { width: 32; margin-left: 1; }
    #save-schedule-btn { margin-left: 1; }
    #schedule-panel { height: 1; color: #636E7B; padding: 0 0 0 15; }

    #monitor-body { height: 1fr; layout: horizontal; }

    #monitor-left {
        width: 1fr;
        padding: 0 3 1 3;
        overflow-y: auto;
        height: 1fr;
        border-right: hkey #D0D7DE;
    }

    #monitor-right {
        width: 1fr;
        padding: 1 3;
        height: 1fr;
    }

    .section-title { color: #636E7B; text-style: bold; margin-top: 1; margin-bottom: 0; }
    .section-subtitle { color: #636E7B; height: 1; margin-bottom: 1; padding: 0 1; }

    #watcher-table {
        height: 6;
        min-height: 3;
        background: $surface;
        border: round #D0D7DE;
        margin-bottom: 0;
        margin-top: 1;
    }

    #empty-hint { display: none; color: #636E7B; padding: 1 2; height: 7; }

    #table-actions { layout: horizontal; height: 3; margin-top: 1; margin-bottom: 0; }
    #table-actions Button { margin-right: 1; }

    #danger-actions { layout: horizontal; height: 3; margin-top: 0; margin-bottom: 0; }
    #danger-actions Button { margin-right: 1; }

    #edit-indicator {
        color: #636E7B;
        text-style: italic;
        margin-top: 1;
        padding: 0 1;
        height: 1;
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
    .field-input { width: 1fr; }

    #form-actions { layout: horizontal; height: 3; margin-top: 1; margin-bottom: 0; }
    #form-actions Button { margin-right: 1; }

    #monitor-log {
        height: 1fr;
        background: $surface;
        border: round #D0D7DE;
        margin-top: 1;
        padding: 0 1;
    }

    #publish-check { margin-bottom: 0; }

    MonitorView.log-focused #schedule-section { display: none; }
    MonitorView.log-focused #monitor-left     { display: none; }
    MonitorView.log-focused #monitor-right    { width: 1fr; }
    """

    def action_toggle_log_focus(self) -> None:
        self.toggle_class("log-focused")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._manifest: dict = _load_manifest()
        self._log_file_pos: int = 0
        self._editing_slug: str | None = None  # None = new-watcher mode

    def compose(self) -> ComposeResult:
        yield PageHeader(
            "Monitor",
            "Watch benchmarks — pull, merge, publish on a daily schedule.",
        )
        # Schedule lives above the split so the Select dropdown isn't clipped
        with Vertical(id="schedule-section"):
            with Horizontal(id="schedule-row"):
                yield Static("Daily at:", id="sched-label")
                yield Input(placeholder="HH:MM", id="time-input")
                yield Select(TIMEZONES, id="tz-select")
                yield Button("Save", id="save-schedule-btn", variant="primary")
            yield Static("", id="schedule-panel")

        with Horizontal(id="monitor-body"):
            with Vertical(id="monitor-left"):
                yield DataTable(id="watcher-table", cursor_type="row", zebra_stripes=True)
                yield Static(
                    "  No watchers yet. To get started:\n"
                    "    1. Fill in the form below — benchmark slug + dataset slug/title\n"
                    "    2. Click Save Watcher\n"
                    "    3. Set a daily time at the top and click Save & Push\n"
                    "       (this commits the schedule to your repo and pushes to GitHub Actions)\n"
                    "  Press ? to read what each button does.",
                    id="empty-hint",
                )

                # Routine actions
                with Horizontal(id="table-actions"):
                    yield Button("Check All Now",  id="check-btn",     variant="primary")
                    yield Button("Check Selected", id="check-sel-btn", variant="default")
                    yield Button("Copy Log",       id="copy-log-btn",  variant="default")

                # Destructive / advanced actions grouped separately
                with Horizontal(id="danger-actions"):
                    yield Button("Remove Selected",        id="remove-btn",      variant="warning")
                    yield Button("Reset & Re-pull",        id="repull-btn",      variant="warning")
                    yield Button("Sync Watchers → Secret", id="sync-secret-btn", variant="default")

                # Form — editing an existing watcher populates these fields
                yield Static("New watcher", id="edit-indicator")
                yield Static("Watcher Settings", classes="section-title")

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

                with Horizontal(id="form-actions"):
                    yield Button("Save Watcher",    id="add-btn",       variant="primary")
                    yield Button("Force Republish", id="republish-btn", variant="default")
                    yield Button("View Dataset",    id="view-ds-btn",   variant="default")
                    yield Button("New Watcher",     id="new-btn",       variant="default")

            with Vertical(id="monitor-right"):
                with Horizontal(classes="log-header-row"):
                    yield Static("Activity Log", classes="section-title")
                    yield LogExpandIcon()
                yield Log(id="monitor-log", highlight=True)

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
        found, hh, mm, tz = _get_schedule()
        self.query_one("#time-input", Input).value = f"{hh:02d}:{mm:02d}" if found else ""
        tz_select = self.query_one("#tz-select", Select)
        if found:
            tz_select.value = tz
        else:
            tz_select.clear()
        self.query_one("#schedule-panel").update(_next_run_text(found, hh, mm))

    def _save_schedule(self) -> None:
        log = self.query_one("#monitor-log", Log)
        time_str = self.query_one("#time-input", Input).value.strip()
        tz = str(self.query_one("#tz-select", Select).value)
        try:
            hh, mm = [int(x) for x in time_str.split(":")]
            assert 0 <= hh <= 23 and 0 <= mm <= 59
        except Exception:
            log.write_line("[x] Invalid time — use HH:MM format (e.g. 14:00)")
            return
        self._push_schedule(hh, mm, tz)

    @work(thread=True)
    def _push_schedule(self, hh: int, mm: int, tz: str = _WORKFLOW_TZ) -> None:
        log = self.query_one("#monitor-log", Log)

        def write(msg: str) -> None:
            self.app.call_from_thread(log.write_line, msg)

        try:
            _set_schedule_in_workflow(hh, mm, tz)
            write(f"\n>> Schedule set to {hh:02d}:{mm:02d} {tz} — pushing to GitHub …")
        except Exception as exc:
            write(f"[x] Could not update workflow file: {exc}")
            return

        r = subprocess.run(
            ["git", "-C", _WORKDIR, "add", str(_WORKFLOW_FILE)],
            capture_output=True, text=True,
        )
        if r.returncode != 0:
            write(f"[x] git add failed: {r.stderr.strip()}")
            return

        r = subprocess.run(
            ["git", "-C", _WORKDIR, "commit", "-m", f"chore: set monitor schedule to {hh:02d}:{mm:02d} {tz}"],
            capture_output=True, text=True,
        )
        if r.returncode != 0:
            combined = (r.stdout + r.stderr).lower()
            no_change = ("nothing to commit" in combined
                         or "nothing added to commit" in combined
                         or "no changes added to commit" in combined)
            if no_change:
                write("   (schedule unchanged — nothing to push)")
            else:
                detail = (r.stderr.strip() or r.stdout.strip() or "no output from git")
                write(f"[x] git commit failed: {detail}")
            return

        try:
            r = subprocess.run(
                ["git", "-C", _WORKDIR, "push", "--set-upstream", "origin", "main"],
                capture_output=True, text=True, timeout=30,
            )
        except subprocess.TimeoutExpired:
            write("[x] Push timed out")
            return

        if r.returncode != 0:
            write(f"[x] git push failed: {r.stderr.strip()}")
            return

        write("[ok] Schedule pushed — GitHub Actions will run at the new time.")
        status = _next_run_text(True, hh, mm)
        self.app.call_from_thread(self.query_one("#schedule-panel").update, status)

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
        self.query_one("#empty-hint").display = not bool(self._manifest)

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
        self._editing_slug = slug
        entry = self._manifest[slug]
        self.query_one("#slug-input", Input).value = slug
        self.query_one("#dataset-slug-input", Input).value = entry.get("dataset_slug", "")
        self.query_one("#dataset-title-input", Input).value = entry.get("dataset_title", "")
        self.query_one("#publish-check", Checkbox).value = bool(entry.get("publish", True))
        self.query_one("#edit-indicator", Static).update(f"Editing: {slug}")

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "slug-input" and self._editing_slug is None:
            slug = event.value.strip()
            self.query_one("#edit-indicator", Static).update(
                f"New: {slug}" if slug else "New watcher"
            )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "copy-log-btn":
            self._copy_log()
            return
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
        elif bid == "repull-btn":
            slug = self._selected_slug()
            if slug:
                self._reset_and_repull(slug)
            else:
                self.query_one("#monitor-log", Log).write_line("[x] Select a watcher row first.")
        elif bid == "view-ds-btn":
            self._open_dataset()
        elif bid == "new-btn":
            self._clear_form()
        elif bid == "save-schedule-btn":
            self._save_schedule()
        elif bid == "sync-secret-btn":
            self._sync_to_github_secret()

    def action_check_all(self) -> None:
        self._check_all()

    # ------------------------------------------------------------------ #
    #  Add / Remove                                                        #
    # ------------------------------------------------------------------ #

    def _clear_form(self) -> None:
        self._editing_slug = None
        self.query_one("#slug-input",         Input).value = ""
        self.query_one("#dataset-slug-input",  Input).value = ""
        self.query_one("#dataset-title-input", Input).value = ""
        self.query_one("#publish-check", Checkbox).value = True
        self.query_one("#edit-indicator", Static).update("New watcher")
        self.query_one("#slug-input", Input).focus()

    def _open_dataset(self) -> None:
        log = self.query_one("#monitor-log", Log)
        ds_slug = self.query_one("#dataset-slug-input", Input).value.strip()
        username = config.kaggle_username
        if not ds_slug or not username:
            log.write_line("[x] No dataset slug set — save a watcher with a dataset slug first.")
            return
        url = f"https://www.kaggle.com/datasets/{username}/{ds_slug}"
        from views.widgets import open_url
        if not open_url(url):
            log.write_line(f">> {url}")

    def _copy_log(self) -> None:
        log = self.query_one("#monitor-log", Log)
        text = "\n".join(log.lines)
        copied = False
        import subprocess
        for cmd in (
            ["clip.exe"],
            ["/mnt/c/Windows/System32/clip.exe"],
            ["/mnt/c/WINDOWS/system32/clip.exe"],
        ):
            try:
                result = subprocess.run(
                    cmd,
                    input=text.encode("utf-8"),
                    capture_output=True,
                )
                if result.returncode == 0:
                    copied = True
                    break
            except FileNotFoundError:
                continue
            except Exception:
                continue
        if not copied:
            for cmd in (
                ["xclip", "-selection", "clipboard"],
                ["xsel", "--clipboard", "--input"],
                ["wl-copy"],
            ):
                try:
                    result = subprocess.run(cmd, input=text.encode("utf-8"), capture_output=True)
                    if result.returncode == 0:
                        copied = True
                        break
                except FileNotFoundError:
                    continue
                except Exception:
                    continue
        btn = self.query_one("#copy-log-btn", Button)
        if copied:
            btn.label = "Copied!"
            self.set_timer(1.5, lambda: setattr(btn, "label", "Copy Log"))
        else:
            log.write_line("[!] Copy failed — try: clip.exe, xclip, xsel, or wl-copy")

    def _add_watcher(self) -> None:
        log   = self.query_one("#monitor-log", Log)
        slug  = self.query_one("#slug-input", Input).value.strip().strip("/")
        ds    = self.query_one("#dataset-slug-input", Input).value.strip()
        # Strip username prefix if user entered "username/slug" instead of just "slug"
        if "/" in ds:
            ds = ds.split("/")[-1]
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

        self._editing_slug = None
        self.query_one("#slug-input",         Input).value = ""
        self.query_one("#dataset-slug-input",  Input).value = ""
        self.query_one("#dataset-title-input", Input).value = ""
        self.query_one("#edit-indicator", Static).update("New watcher")
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

        import os, shutil
        from kagglesdk import KaggleClient
        from core.merger import discover_outputs, merge_outputs

        username = config.kaggle_username
        api_key  = config.kaggle_key
        if not username or not api_key:
            write("[x] Credentials not configured.")
            return

        # kagglesdk reads basic-auth credentials from ~/.kaggle/kaggle.json only.
        # Ensure it exists before calling KaggleClient() so the right creds are used.
        config.ensure_kaggle_json()
        try:
            kag_client = KaggleClient()
        except Exception as exc:
            write(f"[x] Auth failed: {exc}"); return

        # ── Discover current tasks ────────────────────────────────────
        current_tasks: list[str] = _discover_tasks_api(kag_client, slug, log=write) or [slug]
        write(f"   Found {len(current_tasks)} task(s)")

        entry     = self._manifest.get(slug, {"known_tasks": []})
        known     = set(entry.get("known_tasks", []))
        new_tasks = [t for t in current_tasks if t not in known]

        now = datetime.now().isoformat(timespec="seconds")

        if not new_tasks:
            write(f"   [ok] No new tasks. ({len(current_tasks)} known)")
            entry["last_checked"] = now
            self._manifest[slug]  = entry
            _save_manifest(self._manifest)
            self.app.call_from_thread(self._refresh_table)
            return

        write(f"   [+] {len(new_tasks)} new task(s): {', '.join(new_tasks)}")

        # ── Pull new tasks ────────────────────────────────────────────
        out_dir = config.output_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        all_downloaded: list[Path] = []
        pulled_tasks: set[str] = set()   # tasks that had at least one file downloaded

        import io, zipfile
        from kagglesdk.benchmarks.types.benchmark_tasks_api_service import (
            ApiBenchmarkTaskSlug,
            ApiDownloadBenchmarkTaskRunOutputRequest,
            ApiListBenchmarkTaskRunsRequest,
            BenchmarkTaskRunState,
        )
        tasks_client = kag_client.benchmarks.benchmark_tasks_api_client

        for task_slug in new_tasks:
            write(f"\n   Pulling: {task_slug}")
            owner, slug_name = task_slug.split("/", 1)

            # Collect completed run IDs
            completed_ids: list[int] = []
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
                    resp = tasks_client.list_benchmark_task_runs(req)
                    for run in resp.runs or []:
                        if run.state == BenchmarkTaskRunState.BENCHMARK_TASK_RUN_STATE_COMPLETED:
                            completed_ids.append(run.id)
                    page_token = resp.next_page_token or ""
                    if not page_token:
                        break
            except Exception as exc:
                exc_str = str(exc)
                if "403" in exc_str or "404" in exc_str:
                    write(f"   [~] {task_slug}: no accessible runs yet ({exc_str[:60]}) — skipping.")
                else:
                    write(f"   [!] List runs failed: {exc_str}")
                continue

            if not completed_ids:
                write(f"   [~] {task_slug}: no completed runs yet.")
                continue

            for run_id in completed_ids:
                try:
                    dl_req = ApiDownloadBenchmarkTaskRunOutputRequest()
                    dl_req.run_id = run_id
                    r = tasks_client.download_benchmark_task_run_output(dl_req)
                    if not r.ok:
                        write(f"   [!] Run {run_id}: HTTP {r.status_code}")
                        continue
                    zf = zipfile.ZipFile(io.BytesIO(r.content))
                    for name in zf.namelist():
                        if not name.endswith(".run.json"):
                            continue
                        dest = out_dir / Path(name).name
                        all_downloaded.append(dest)
                        pulled_tasks.add(task_slug)
                        if dest.exists():
                            continue
                        dest.write_bytes(zf.read(name))
                        write(f"   + {name}")
                except Exception as exc:
                    write(f"   [!] Download run {run_id} failed: {exc}")

        if not all_downloaded:
            write("   [!] No files downloaded.")
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
        publish_ok = True
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

            sft_src  = out_dir / SFT_FILENAME
            pref_src = out_dir / PREF_FILENAME
            for src in [sft_src, pref_src,
                        sft_src.with_suffix(".parquet"),
                        pref_src.with_suffix(".parquet")]:
                if src.exists():
                    shutil.copy2(src, staging / src.name)

            from views.publish_view import build_dataset_card
            (staging / "README.md").write_text(build_dataset_card(
                title=ds_title,
                description="",
                sft_rows=_row_count(sft_src),
                pref_pairs=_row_count(pref_src),
            ), encoding="utf-8")

            (staging / "dataset-metadata.json").write_text(json.dumps({
                "title":    ds_title,
                "id":       f"{username}/{ds_slug}",
                "licenses": [{"name": DEFAULT_LICENSE}],
            }, indent=2))

            write(f"\n   Publishing {username}/{ds_slug} …")
            result = upload_dataset(folder=staging, is_update=True, append=True, log_cb=write)
            if not result.success:
                write(f"   [x] {result.error}")
                publish_ok = False

        # ── Save manifest ─────────────────────────────────────────────
        # Only mark tasks as known if files were pulled AND publish succeeded.
        # If publish failed, keep tasks unknown so the next run retries them.
        if publish_ok:
            entry["known_tasks"] = list(known | pulled_tasks)
        else:
            write("   [!] Publish failed — tasks will be retried on the next check.")
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

        sft_src  = _cfg.output_dir / SFT_FILENAME
        pref_src = _cfg.output_dir / PREF_FILENAME
        if not sft_src.exists():
            write(f"[x] {SFT_FILENAME} not found — run a check/pull first."); return

        from core.uploader import upload_dataset
        ds_slug  = entry["dataset_slug"]
        ds_title = entry["dataset_title"]
        staging  = _cfg.output_dir / "staging" / ds_slug
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir(parents=True, exist_ok=True)
        for src in [sft_src, pref_src,
                    sft_src.with_suffix(".parquet"),
                    pref_src.with_suffix(".parquet")]:
            if src.exists():
                shutil.copy2(src, staging / src.name)
        import json
        from views.publish_view import build_dataset_card
        (staging / "README.md").write_text(build_dataset_card(
            title=ds_title,
            description="",
            sft_rows=_row_count(sft_src),
            pref_pairs=_row_count(pref_src),
        ), encoding="utf-8")
        (staging / "dataset-metadata.json").write_text(json.dumps({
            "title":    ds_title,
            "id":       f"{username}/{ds_slug}",
            "licenses": [{"name": DEFAULT_LICENSE}],
        }, indent=2))
        write(f"\n>> Force-publishing {username}/{ds_slug} …")
        result = upload_dataset(folder=staging, is_update=True, append=True, log_cb=write)
        if not result.success:
            write(f"   [x] {result.error}")

    # ------------------------------------------------------------------ #
    #  Reset known tasks and re-pull everything                          #
    # ------------------------------------------------------------------ #

    def _reset_and_repull(self, slug: str) -> None:
        log = self.query_one("#monitor-log", Log)
        entry = self._manifest.get(slug, {})
        entry["known_tasks"] = []
        self._manifest[slug] = entry
        _save_manifest(self._manifest)
        log.write_line(f"[ok] Reset known tasks for {slug} — re-pulling all tasks now …")
        self._check_one(slug)

    # ------------------------------------------------------------------ #
    #  Sync watcher manifest to GitHub Actions secret                    #
    # ------------------------------------------------------------------ #

    @work(thread=True)
    def _sync_to_github_secret(self) -> None:
        log = self.query_one("#monitor-log", Log)

        def write(msg: str) -> None:
            self.app.call_from_thread(log.write_line, msg)

        import requests as _req
        from base64 import b64encode, b64decode

        token = config.github_token
        repo  = config.github_repo
        if not token or not repo:
            write("[x] GITHUB_TOKEN and GITHUB_REPO must be set in .env")
            write("    GITHUB_TOKEN : a PAT with 'secrets' scope")
            write("    GITHUB_REPO  : e.g. 4kaws/evalflow")
            return

        write("\n>> Syncing watcher manifest to GitHub secret …")
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
        }

        r = _req.get(f"https://api.github.com/repos/{repo}/actions/secrets/public-key", headers=headers)
        if r.status_code != 200:
            write(f"[x] Could not fetch repo public key: {r.status_code}")
            return
        pk_data = r.json()

        try:
            from nacl import encoding, public as nacl_public
            pk  = nacl_public.PublicKey(b64decode(pk_data["key"]), encoding.RawEncoder)
            box = nacl_public.SealedBox(pk)
            encrypted = b64encode(box.encrypt(json.dumps(self._manifest, indent=2).encode())).decode()
        except Exception as exc:
            write(f"[x] Encryption failed: {exc}")
            write("    Run: pip install PyNaCl")
            return

        r = _req.put(
            f"https://api.github.com/repos/{repo}/actions/secrets/EVALFLOW_MANIFEST",
            headers=headers,
            json={"encrypted_value": encrypted, "key_id": pk_data["key_id"]},
        )
        if r.status_code in (201, 204):
            write(f"[ok] EVALFLOW_MANIFEST secret updated ({len(self._manifest)} watcher(s))")
        else:
            write(f"[x] Failed to update secret: {r.status_code} {r.text}")

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