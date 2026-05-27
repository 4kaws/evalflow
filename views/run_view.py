"""
Run view — list own benchmark tasks, schedule new runs, and poll run status.

Uses the Kaggle Benchmark Tasks API:
  list_benchmark_tasks              → owned tasks  (task Select dropdown)
  list_benchmark_models             → available models  (models SelectionList)
  batch_schedule_benchmark_task_runs → kick off model × task combinations
  list_benchmark_task_runs          → poll completion status
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import urllib.parse
import uuid
from datetime import datetime, timedelta, timezone

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, DataTable, Input, Log, Select, SelectionList, Static

from config import config
from views.widgets import PageHeader

_OAUTH_REDIRECT = "https://www.kaggle.com/account/api/oauth/token"
_OAUTH_SCOPE    = "resources.admin:*"
_OAUTH_CLIENT   = "kagglesdk"


_STATE_ICONS = {
    "BENCHMARK_TASK_RUN_STATE_COMPLETED":   "✓",
    "BENCHMARK_TASK_RUN_STATE_ERRORED":     "✗",
    "BENCHMARK_TASK_RUN_STATE_RUNNING":     "⟳",
    "BENCHMARK_TASK_RUN_STATE_QUEUED":      "…",
    "BENCHMARK_TASK_RUN_STATE_UNSPECIFIED": "?",
}


class RunView(Vertical):
    BINDINGS = [
        Binding("ctrl+r", "refresh", "Refresh", show=True, key_display="Ctrl+R"),
    ]

    DEFAULT_CSS = """
    RunView { padding: 0; height: 1fr; }

    #run-body { padding: 1 3; height: 1fr; }

    .section-title {
        color: #636E7B;
        text-style: bold;
        margin-top: 1;
        margin-bottom: 0;
    }

    #run-top {
        layout: horizontal;
        height: 16;
    }

    #tasks-panel {
        width: 1fr;
        height: 1fr;
        margin-right: 1;
    }

    #tasks-table {
        height: 10;
        background: $surface;
        border: round #D0D7DE;
    }

    #tasks-btn-row { layout: horizontal; height: 3; margin-top: 1; }
    #tasks-btn-row Button { margin-right: 1; }

    #manual-slug-row { layout: horizontal; height: 3; margin-top: 1; align: left middle; }
    #manual-slug-input { width: 1fr; margin-right: 1; }

    #oauth-row { layout: horizontal; height: 3; margin-top: 0; align: left middle; }
    #oauth-code-input { width: 1fr; margin-right: 1; }

    #schedule-panel {
        width: 1fr;
        height: 1fr;
    }

    .field-row {
        layout: horizontal;
        height: 3;
        align: left middle;
        margin-bottom: 0;
    }
    .field-label {
        width: 10;
        height: 3;
        color: #636E7B;
        content-align: right middle;
        padding-right: 2;
    }
    .field-select { width: 1fr; }

    #models-list {
        height: 8;
        background: $surface;
        border: round #D0D7DE;
        margin-top: 0;
    }

    #schedule-btn-row { layout: horizontal; height: 3; margin-top: 1; }
    #schedule-btn-row Button { margin-right: 1; }

    #runs-table {
        height: 5;
        min-height: 3;
        background: $surface;
        border: round #D0D7DE;
        margin-top: 0;
    }

    #run-controls { height: auto; }

    #run-results { height: 1fr; }

    #run-log {
        height: 1fr;
        min-height: 4;
        background: $surface;
        border: round #D0D7DE;
        margin-top: 0;
        padding: 0 1;
    }

    #status-bar {
        color: #636E7B;
        height: 1;
        margin-top: 0;
        padding: 0 1;
    }

    #hint-note {
        color: #636E7B;
        margin-bottom: 0;
        height: 2;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._tasks: list[dict] = []
        self._selected_task_slug: str = ""
        self._oauth_state: dict | None = None

    def compose(self) -> ComposeResult:
        yield PageHeader(
            "Run",
            "Re-run and monitor benchmark task runs for models already in your benchmark.",
        )
        with Vertical(id="run-body"):
            with Vertical(id="run-controls"):
                yield Static(
                    "To add a NEW model to a benchmark, open it on Kaggle and use the [dim]Add Models[/dim] button.\n"
                    "Once a model is added there, use [bold]Schedule Runs[/bold] here to re-trigger specific task runs.",
                    id="hint-note",
                    markup=True,
                )

                with Horizontal(id="run-top"):
                    # Left: My Tasks table
                    with Vertical(id="tasks-panel"):
                        yield Static("My Tasks", classes="section-title")
                        yield DataTable(id="tasks-table", cursor_type="row", zebra_stripes=True)
                        with Horizontal(id="tasks-btn-row"):
                            yield Button("List My Tasks",           id="list-tasks-btn",   variant="primary")
                            yield Button("Refresh Runs",            id="refresh-runs-btn", variant="default")
                            yield Button("Open Benchmark on Kaggle", id="open-benchmark-btn", variant="default")
                        with Horizontal(id="manual-slug-row"):
                            yield Input(
                                placeholder="owner/task-slug  (if List My Tasks fails)",
                                id="manual-slug-input",
                            )
                            yield Button("Add Task", id="add-task-btn", variant="default")
                        with Horizontal(id="oauth-row"):
                            yield Button("Kaggle Login", id="oauth-login-btn", variant="default")
                            yield Input(
                                id="oauth-code-input",
                                placeholder="Paste verification code from Kaggle…",
                                classes="hidden",
                            )
                            yield Button("Verify Code", id="oauth-verify-run-btn", variant="primary", classes="hidden")

                    # Right: Schedule form with dropdowns
                    with Vertical(id="schedule-panel"):
                        yield Static("Schedule New Runs", classes="section-title")

                        with Horizontal(classes="field-row"):
                            yield Static("Task:", classes="field-label")
                            yield Select(
                                [("— list tasks first —", "__placeholder__")],
                                id="task-select",
                                classes="field-select",
                                allow_blank=False,
                            )

                        yield Static("  Models  (check to include):", classes="field-label")
                        yield SelectionList(
                            ("— load models first —", "__placeholder__", False),
                            id="models-list",
                        )

                        with Horizontal(id="schedule-btn-row"):
                            yield Button("Load Models",   id="load-models-btn",  variant="default")
                            yield Button("Schedule Runs", id="schedule-btn",     variant="primary")

            with Vertical(id="run-results"):
                yield Static("Recent Runs", classes="section-title")
                yield DataTable(id="runs-table", cursor_type="row", zebra_stripes=True)

                yield Static("Log", classes="section-title")
                yield Log(id="run-log", highlight=True)
                yield Static("", id="status-bar")

    def on_mount(self) -> None:
        tt = self.query_one("#tasks-table", DataTable)
        tt.add_columns("Task slug", "Status", "Created")

        rt = self.query_one("#runs-table", DataTable)
        rt.add_columns("Run ID", "Task", "Model", "State", "Started", "Ended")

    def on_activate(self) -> None:
        if not self._tasks:
            self._load_my_tasks()

    # ------------------------------------------------------------------ #
    #  Events                                                              #
    # ------------------------------------------------------------------ #

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "list-tasks-btn":
            self._load_my_tasks()
        elif bid == "load-models-btn":
            self._load_models()
        elif bid == "refresh-runs-btn":
            if self._selected_task_slug:
                self._load_task_runs(self._selected_task_slug)
        elif bid == "schedule-btn":
            self._do_schedule()
        elif bid == "add-task-btn":
            inp = self.query_one("#manual-slug-input", Input)
            slug = inp.value.strip()
            if not slug or "/" not in slug:
                log = self.query_one("#run-log", Log)
                log.write_line("[x] Enter a slug in owner/task-slug format.")
            else:
                self._add_task_to_ui(slug)
                inp.value = ""
        elif bid == "open-benchmark-btn":
            log = self.query_one("#run-log", Log)
            slug = self._selected_task_slug
            if slug and "/" in slug:
                owner, task_name = slug.split("/", 1)
                url = f"https://www.kaggle.com/benchmarks/tasks/{owner}/{task_name}"
            else:
                owner = config.kaggle_username or ""
                url = f"https://www.kaggle.com/{owner}/benchmarks" if owner else "https://www.kaggle.com/benchmarks"
            try:
                import subprocess
                subprocess.Popen(
                    ["/mnt/c/Windows/explorer.exe", url],
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
            except Exception:
                pass
            log.write_line(f">> {url}")
        elif bid == "oauth-login-btn":
            self._start_oauth_login()
        elif bid == "oauth-verify-run-btn":
            code = self.query_one("#oauth-code-input", Input).value.strip()
            if code:
                self._do_oauth_exchange(code)
            else:
                self.query_one("#run-log", Log).write_line("[x] Paste the verification code first.")

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "task-select":
            value = event.value
            # Guard against BLANK sentinel, placeholder, and non-slug values
            if not value or value is Select.BLANK or "/" not in str(value):
                return
            slug = str(value)
            self._selected_task_slug = slug
            self._load_task_runs(slug)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.data_table.id != "tasks-table":
            return
        if event.cursor_row >= len(self._tasks):
            return
        slug = self._tasks[event.cursor_row].get("slug", "")
        if slug:
            self._selected_task_slug = slug
            # Update the task Select to match
            sel = self.query_one("#task-select", Select)
            try:
                sel.value = slug
            except Exception:
                pass
            self._load_task_runs(slug)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "manual-slug-input":
            slug = event.value.strip()
            if slug and "/" in slug:
                self._add_task_to_ui(slug)
                event.input.value = ""
            else:
                log = self.query_one("#run-log", Log)
                log.write_line("[x] Enter a slug in owner/task-slug format.")
        elif event.input.id == "oauth-code-input":
            code = event.value.strip()
            if code:
                self._do_oauth_exchange(code)
            else:
                self.query_one("#run-log", Log).write_line("[x] Paste the verification code first.")

    def _add_task_to_ui(self, slug: str) -> None:
        """Add a manually-entered task slug to the table and select without the API."""
        if any(t["slug"] == slug for t in self._tasks):
            # Already present — just select it
            self._selected_task_slug = slug
            sel = self.query_one("#task-select", Select)
            try:
                sel.value = slug
            except Exception:
                pass
            self._load_task_runs(slug)
            return

        task = {"slug": slug, "state": "MANUAL", "created": "—"}
        self._tasks.append(task)

        tt = self.query_one("#tasks-table", DataTable)
        tt.add_row(slug, "○", "—")

        sel = self.query_one("#task-select", Select)
        options = [(t["slug"], t["slug"]) for t in self._tasks
                   if t["slug"] and "/" in t["slug"]]
        if options:
            sel.set_options(options)
            sel.value = slug
        self._selected_task_slug = slug
        self._load_task_runs(slug)
        self.query_one("#status-bar").update(
            f"  Task added — select models and click Schedule Runs"
        )

    def action_refresh(self) -> None:
        self._load_my_tasks()

    # ------------------------------------------------------------------ #
    #  Workers                                                             #
    # ------------------------------------------------------------------ #

    @work(thread=True, exclusive=True)
    def _load_my_tasks(self) -> None:
        log = self.query_one("#run-log", Log)
        log.write_line(">> Listing your benchmark tasks…")

        kag_client = self._make_client(log)
        if kag_client is None:
            return

        try:
            from kagglesdk.benchmarks.types.benchmark_tasks_api_service import ApiListBenchmarkTasksRequest
            client = kag_client.benchmarks.benchmark_tasks_api_client

            tasks: list[dict] = []
            page_token = ""
            while True:
                req = ApiListBenchmarkTasksRequest()
                req.page_size = 100
                if page_token:
                    req.page_token = page_token
                resp = client.list_benchmark_tasks(req)
                for t in resp.tasks or []:
                    slug_obj = t.slug
                    if slug_obj and hasattr(slug_obj, "owner_slug"):
                        slug_str = f"{slug_obj.owner_slug}/{slug_obj.task_slug}"
                    else:
                        slug_str = str(slug_obj or "")
                    state_str = str(t.creation_state or "").upper()
                    tasks.append({
                        "slug":    slug_str,
                        "state":   state_str,
                        "created": str(t.create_time or ""),
                    })
                page_token = resp.next_page_token or ""
                if not page_token:
                    break

            def _apply(tasks=tasks):
                self._tasks = tasks
                tt = self.query_one("#tasks-table", DataTable)
                tt.clear()
                for t in tasks:
                    icon = "✓" if "COMPLETE" in t["state"] else ("✗" if "ERROR" in t["state"] else "○")
                    created = t["created"][:10] if len(t["created"]) >= 10 else t["created"]
                    tt.add_row(t["slug"], icon, created)

                # Populate the task Select dropdown
                sel = self.query_one("#task-select", Select)
                options = [(t["slug"], t["slug"]) for t in tasks]
                if options:
                    sel.set_options(options)
                    sel.value = options[0][1]
                    self._selected_task_slug = options[0][1]

                self.query_one("#status-bar").update(
                    f"  {len(tasks)} task(s) loaded — select one to see its runs"
                )
                if not tasks:
                    log.write_line("[!] No tasks found. Create tasks at kaggle.com/benchmarks.")
                else:
                    log.write_line(f"[ok] {len(tasks)} task(s) loaded.")

            self.app.call_from_thread(_apply)

        except Exception as exc:
            self.app.call_from_thread(
                lambda: log.write_line(
                    f"[x] Failed to list tasks: {exc}\n"
                    "    → Enter your task slug manually in the field below the table."
                )
            )

    @work(thread=True)
    def _load_models(self) -> None:
        log = self.query_one("#run-log", Log)
        log.write_line("\n>> Loading available benchmark models…")

        kag_client = self._make_client(log)
        if kag_client is None:
            return

        try:
            from kagglesdk.benchmarks.types.benchmarks_api_service import ApiListBenchmarkModelsRequest
            client = kag_client.benchmarks.benchmarks_api_client

            models: list[tuple[str, str]] = []  # (label, schedule_slug)
            page_token = ""
            while True:
                req = ApiListBenchmarkModelsRequest()
                req.page_size = 100
                if page_token:
                    req.page_token = page_token
                resp = client.list_benchmark_models(req)
                for m in resp.benchmark_models or []:
                    label = m.display_name or m.slug or ""
                    versions = getattr(m, "versions", None) or (
                        [m.version] if getattr(m, "version", None) else []
                    )
                    for v in versions:
                        proxy    = getattr(v, "model_proxy_slug", "") or ""
                        ver_slug = getattr(v, "slug", "") or ""
                        # API accepts just the short version slug (e.g. "gemini-2.5-flash")
                        if ver_slug:
                            models.append((f"{label}  [{proxy}]", ver_slug))
                page_token = resp.next_page_token or ""
                if not page_token:
                    break

            def _apply(models=models):
                sl = self.query_one("#models-list", SelectionList)
                sl.clear_options()
                for label, value in models:
                    sl.add_option((label, value, False))  # False = not pre-selected
                log.write_line(f"[ok] {len(models)} model(s) loaded — check the ones to schedule.")

            self.app.call_from_thread(_apply)

        except Exception as exc:
            self.app.call_from_thread(
                lambda: log.write_line(f"[x] Failed to load models: {exc}")
            )

    @work(thread=True)
    def _load_task_runs(self, task_slug: str) -> None:
        log = self.query_one("#run-log", Log)
        log.write_line(f"\n>> Loading runs for {task_slug}…")

        kag_client = self._make_client(log)
        if kag_client is None:
            return

        try:
            from kagglesdk.benchmarks.types.benchmark_tasks_api_service import (
                ApiBenchmarkTaskSlug,
                ApiListBenchmarkTaskRunsRequest,
            )
            client = kag_client.benchmarks.benchmark_tasks_api_client
            parts = task_slug.split("/", 1)
            owner, slug_name = parts[0], parts[1] if len(parts) > 1 else ""

            runs: list[dict] = []
            page_token = ""
            while True:
                req = ApiListBenchmarkTaskRunsRequest()
                slug_obj = ApiBenchmarkTaskSlug()
                slug_obj.owner_slug = owner
                slug_obj.task_slug  = slug_name
                req.task_slug  = slug_obj
                req.page_size  = 50
                if page_token:
                    req.page_token = page_token
                resp = client.list_benchmark_task_runs(req)
                for r in resp.runs or []:
                    state_str = str(r.state or "")
                    state_key = state_str.split(".")[-1] if "." in state_str else state_str
                    icon = _STATE_ICONS.get(state_key, "?")
                    runs.append({
                        "id":    str(r.id or ""),
                        "model": str(r.model_version_slug or "").split("/")[-1],
                        "state": icon,
                        "start": str(r.start_time or "")[:16],
                        "end":   str(r.end_time   or "")[:16],
                    })
                page_token = resp.next_page_token or ""
                if not page_token:
                    break

            def _apply(runs=runs):
                rt = self.query_one("#runs-table", DataTable)
                rt.clear()
                for r in runs[:100]:
                    rt.add_row(r["id"], task_slug.split("/")[-1], r["model"], r["state"], r["start"], r["end"])
                log.write_line(f"[ok] {len(runs)} run(s) for {task_slug}.")

            self.app.call_from_thread(_apply)

        except Exception as exc:
            self.app.call_from_thread(
                lambda: log.write_line(f"[x] Failed to load runs: {exc}")
            )

    @work(thread=True)
    def _do_schedule(self) -> None:
        log = self.query_one("#run-log", Log)

        task_slug = self._selected_task_slug
        if not task_slug:
            self.app.call_from_thread(lambda: log.write_line("[x] Select a task first."))
            return

        selected_models: list[str] = self.query_one("#models-list", SelectionList).selected
        if not selected_models:
            self.app.call_from_thread(lambda: log.write_line("[x] Check at least one model."))
            return

        log.write_line(f"\n>> Scheduling {len(selected_models)} model run(s) on {task_slug}…")

        kag_client = self._make_client(log)
        if kag_client is None:
            return

        try:
            from kagglesdk.benchmarks.types.benchmark_tasks_api_service import (
                ApiBatchScheduleBenchmarkTaskRunsRequest,
                ApiBenchmarkTaskSlug,
            )
            client = kag_client.benchmarks.benchmark_tasks_api_client
            parts = task_slug.split("/", 1)
            owner, slug_name = parts[0], parts[1] if len(parts) > 1 else ""

            task_slug_obj = ApiBenchmarkTaskSlug()
            task_slug_obj.owner_slug = owner
            task_slug_obj.task_slug  = slug_name

            req = ApiBatchScheduleBenchmarkTaskRunsRequest()
            req.task_slugs          = [task_slug_obj]
            req.model_version_slugs = list(selected_models)

            resp = client.batch_schedule_benchmark_task_runs(req)
            results = resp.results or []

            def _finish(results=results):
                for res in results:
                    log.write_line(f"   {res}")
                log.write_line(f"[ok] Scheduled {len(selected_models)} run(s). Use Refresh Runs to poll status.")
                self._load_task_runs(task_slug)

            self.app.call_from_thread(_finish)

        except Exception as exc:
            self.app.call_from_thread(
                lambda: log.write_line(f"[x] Schedule failed: {exc}")
            )

    # ------------------------------------------------------------------ #
    #  OAuth re-authentication                                             #
    # ------------------------------------------------------------------ #

    @work(thread=True)
    def _start_oauth_login(self) -> None:
        log = self.query_one("#run-log", Log)
        self.app.call_from_thread(lambda: log.write_line(">> Generating Kaggle OAuth login URL…"))

        if not config.kaggle_username or not config.kaggle_key:
            self.app.call_from_thread(
                lambda: log.write_line("[x] Credentials not configured. Run setup wizard (w).")
            )
            return

        code_verifier = secrets.token_urlsafe(64)
        digest = hashlib.sha256(code_verifier.encode()).digest()
        code_challenge = base64.urlsafe_b64encode(digest).decode()
        state = str(uuid.uuid4())

        self._oauth_state = {
            "code_verifier": code_verifier,
            "state": state,
        }

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

        def _show(url=oauth_url):
            log.write_line(f"\n  Open this URL in your browser:\n  {url}\n")
            inp = self.query_one("#oauth-code-input", Input)
            inp.remove_class("hidden")
            inp.focus()
            self.query_one("#oauth-verify-run-btn", Button).remove_class("hidden")

        self.app.call_from_thread(_show)

    @work(thread=True)
    def _do_oauth_exchange(self, code: str) -> None:
        log = self.query_one("#run-log", Log)
        self.app.call_from_thread(lambda: log.write_line(">> Exchanging code with Kaggle…"))

        if not self._oauth_state:
            self.app.call_from_thread(
                lambda: log.write_line("[x] Click Kaggle Login first to generate a URL.")
            )
            return

        try:
            from kagglesdk import KaggleClient
            from kagglesdk.kaggle_creds import KaggleCredentials
            from kagglesdk.security.types.oauth_service import ExchangeOAuthTokenRequest

            config.ensure_kaggle_json()
            base_client = KaggleClient(
                username=config.kaggle_username,
                password=config.kaggle_key,
            )

            req = ExchangeOAuthTokenRequest()
            req.code = code
            req.code_verifier = self._oauth_state["code_verifier"]
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
                log.write_line(f"Authenticated as {u} — reloading tasks…")
                self.query_one("#oauth-code-input", Input).add_class("hidden")
                self.query_one("#oauth-verify-run-btn", Button).add_class("hidden")
                self._load_my_tasks()

            self.app.call_from_thread(_on_success)

        except Exception as exc:
            self.app.call_from_thread(
                lambda e=exc: log.write_line(f"[x] OAuth exchange failed: {e}")
            )

    # ------------------------------------------------------------------ #
    #  Auth helper                                                         #
    # ------------------------------------------------------------------ #

    def _make_client(self, log: Log):
        try:
            from kagglesdk import KaggleClient
            from kagglesdk.kaggle_creds import KaggleCredentials
            if not config.kaggle_username or not config.kaggle_key:
                self.app.call_from_thread(
                    lambda: log.write_line("[x] Credentials not configured. Run setup wizard (w).")
                )
                return None
            # The Benchmark Tasks API requires OAuth Bearer auth, not Basic auth.
            # kagglesdk 0.1.24+ saves OAuth creds to ~/.kaggle/credentials.json.
            # Load that file, refresh the access token if expired, then pass it
            # as api_token so the SDK uses Bearer auth for all calls.
            config.ensure_kaggle_json()
            base_client = KaggleClient(
                username=config.kaggle_username,
                password=config.kaggle_key,
            )
            creds = KaggleCredentials.load(base_client)
            if creds:
                token = creds.get_access_token()
                kag_client = KaggleClient(api_token=token)
                self.app.call_from_thread(
                    lambda: log.write_line("   (using OAuth Bearer token)")
                )
            else:
                kag_client = base_client
                self.app.call_from_thread(
                    lambda: log.write_line(
                        "   [!] No OAuth token — run  ! kaggle auth login  to enable Run view.\n"
                        "       Falling back to Basic auth (List My Tasks may return 404)."
                    )
                )
            return kag_client
        except ImportError:
            self.app.call_from_thread(lambda: log.write_line("[x] kagglesdk not installed."))
            return None
        except Exception as exc:
            self.app.call_from_thread(lambda: log.write_line(f"[x] Auth failed: {exc}"))
            return None
