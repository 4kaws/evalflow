"""Publish view — upload SFT + preference CSVs to Kaggle Datasets."""

import json
import shutil
from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Checkbox, Input, Label, Log, Select, Static
from textual import work

from config import config
from core.uploader import upload_dataset

_LICENSE_OPTS = [
    ("CC0 1.0 (Public Domain)", "CC0-1.0"),
    ("CC BY 4.0",               "CC BY 4.0"),
    ("CC BY-SA 4.0",            "CC BY-SA 4.0"),
    ("Apache 2.0",              "Apache 2.0"),
]


class PublishView(Vertical):
    _BTN_IDS = ["publish-btn", "update-btn"]

    BINDINGS = [
        Binding("ctrl+u", "publish_new",    "Publish new",    show=True, key_display="Ctrl+U"),
        Binding("ctrl+e", "publish_update", "Update existing", show=True, key_display="Ctrl+E"),
        Binding("down",   "nav_down",   show=False),
        Binding("up",     "nav_up",     show=False),
        Binding("left",   "nav_left",   show=False),
        Binding("right",  "nav_right",  show=False),
        Binding("escape", "nav_esc",    show=False),
    ]

    def _fid(self) -> str | None:
        return self.app.focused.id if self.app.focused else None

    def _select_btn(self, btn_id: str) -> None:
        for bid in self._BTN_IDS:
            self.query_one(f"#{bid}", Button).variant = (
                "primary" if bid == btn_id else "default"
            )
        self.query_one(f"#{btn_id}", Button).focus()

    def _reset_btns(self) -> None:
        self._select_btn("publish-btn")

    def action_nav_down(self) -> None:
        if self._fid() in self._BTN_IDS:
            return
        self.app.action_focus_next()

    def action_nav_up(self) -> None:
        if self._fid() in self._BTN_IDS:
            self._reset_btns()
            self.query_one("#public-switch", Checkbox).focus()
        else:
            self.app.action_focus_previous()

    def action_nav_left(self) -> None:
        fid = self._fid()
        if fid in self._BTN_IDS:
            idx = self._BTN_IDS.index(fid)
            self._select_btn(self._BTN_IDS[(idx - 1) % 2])

    def action_nav_right(self) -> None:
        fid = self._fid()
        if fid in self._BTN_IDS:
            idx = self._BTN_IDS.index(fid)
            self._select_btn(self._BTN_IDS[(idx + 1) % 2])

    def action_nav_esc(self) -> None:
        if self._fid() in self._BTN_IDS:
            self._reset_btns()
        self.app.action_unfocus()

    DEFAULT_CSS = """
    PublishView { padding: 0 1; height: 1fr; }
    .section-title { color: $primary; text-style: bold; margin-top: 0; margin-bottom: 0; }
    .field-row { layout: horizontal; height: 3; align: left middle; margin-bottom: 0; }
    .field-label { width: 22; color: $text-muted; content-align: right middle; padding-right: 2; }
    .field-input { width: 50; }
#btn-row { layout: horizontal; height: 3; margin-top: 0; }
    #btn-row Button { margin-right: 1; }
    #publish-log {
        height: 1fr;
        min-height: 4;
        border: solid $primary 20%;
        background: $surface;
        margin-top: 0;
    }
    #url-panel {
        color: $success;
        margin-top: 0;
        height: 3;
        background: $surface;
        padding: 0 1;
        border: solid $success 20%;
    }
    #creds-note { color: $text-muted; margin-bottom: 0; }
    #files-panel {
        height: 4;
        border: solid $primary 20%;
        background: $surface;
        padding: 0 1;
        margin-bottom: 0;
        color: $text-muted;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._sft_path:  Path | None = None
        self._pref_path: Path | None = None

    def compose(self) -> ComposeResult:
        yield Static("Publish to Kaggle Datasets", classes="section-title")
        yield Static(
            "Reads KAGGLE_USERNAME + KAGGLE_KEY from .env or ~/.kaggle/kaggle.json",
            id="creds-note",
        )

        yield Static(self._files_text(), id="files-panel")

        with Horizontal(classes="field-row"):
            yield Label("Kaggle username:", classes="field-label")
            yield Input(
                value=config.kaggle_username or "",
                placeholder="your-kaggle-username",
                id="username-input",
                classes="field-input",
            )

        with Horizontal(classes="field-row"):
            yield Label("Dataset title:", classes="field-label")
            yield Input(
                placeholder="e.g. My Benchmark Results",
                id="title-input",
                classes="field-input",
            )

        with Horizontal(classes="field-row"):
            yield Label("Dataset slug:", classes="field-label")
            yield Input(
                placeholder="e.g. my-benchmark-results  (URL-safe, no spaces)",
                id="slug-input",
                classes="field-input",
            )

        with Horizontal(classes="field-row"):
            yield Label("Description:", classes="field-label")
            yield Input(
                placeholder="Describe your benchmark and what models were evaluated",
                id="description-input",
                classes="field-input",
            )

        with Horizontal(classes="field-row"):
            yield Label("License:", classes="field-label")
            yield Select(
                _LICENSE_OPTS,
                value="CC0-1.0",
                id="license-select",
                classes="field-input",
            )

        yield Checkbox("Public dataset", value=True, id="public-switch")

        with Horizontal(id="btn-row"):
            yield Button("Publish New",     id="publish-btn", variant="primary")
            yield Button("Update Existing", id="update-btn",  variant="default")

        yield Static("Publish Log", classes="section-title")
        yield Log(id="publish-log", highlight=True)
        yield Static("", id="url-panel")

    def set_merged_csvs(self, sft_path: Path, pref_path: Path) -> None:
        """Called by MergeView after a successful merge."""
        self._sft_path  = sft_path
        self._pref_path = pref_path
        self.query_one("#files-panel").update(self._files_text())

    def _files_text(self) -> str:
        if self._sft_path and self._pref_path:
            sft_info  = f"({self._row_count(self._sft_path)} rows)"
            pref_info = f"({self._row_count(self._pref_path)} pairs)"
            return (
                f"  Files to upload:\n"
                f"  + evalflow_sft.csv           {sft_info}\n"
                f"  + evalflow_preferences.csv   {pref_info}"
            )
        return "  No files ready. Go to Merge tab and run a merge first."

    # ------------------------------------------------------------------ #
    #  Events                                                              #
    # ------------------------------------------------------------------ #

    def on_activate(self) -> None:
        self.query_one("#username-input", Input).focus()

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "license-select":
            self.app.call_after_refresh(
                lambda: self.query_one("#public-switch", Checkbox).focus()
            )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "publish-btn":
            self._do_publish(is_update=False)
        elif event.button.id == "update-btn":
            self._do_publish(is_update=True)
        self._reset_btns()
        self.app.set_focus(None)

    def action_publish_new(self) -> None:
        self._do_publish(is_update=False)

    def action_publish_update(self) -> None:
        self._do_publish(is_update=True)

    def _log_from_thread(self, msg: str) -> None:
        self.app.call_from_thread(self.query_one("#publish-log", Log).write_line, msg)

    # ------------------------------------------------------------------ #
    #  Publish                                                             #
    # ------------------------------------------------------------------ #

    def _do_publish(self, is_update: bool) -> None:
        log = self.query_one("#publish-log", Log)
        log.clear()
        self.query_one("#url-panel").update("")

        sft_path  = self._sft_path  or config.output_dir / "evalflow_sft.csv"
        pref_path = self._pref_path or config.output_dir / "evalflow_preferences.csv"

        missing = [str(p) for p in [sft_path, pref_path] if not p.exists()]
        if missing:
            log.write_line("[x] Missing files — run Merge first:\n  " + "\n  ".join(missing))
            return

        username    = self.query_one("#username-input",    Input).value.strip()
        title       = self.query_one("#title-input",       Input).value.strip()
        slug        = self.query_one("#slug-input",        Input).value.strip()
        description = self.query_one("#description-input", Input).value.strip()
        license_val = str(self.query_one("#license-select", Select).value)

        if not username:
            log.write_line("[x] Kaggle username is required.")
            return
        if not title:
            log.write_line("[x] Dataset title is required.")
            return
        if not slug:
            log.write_line("[x] Dataset slug is required.")
            return
        if " " in slug:
            log.write_line("[x] Slug cannot contain spaces — use hyphens, e.g. my-benchmark-results")
            return

        # Build staging folder
        staging = config.output_dir / "staging" / slug
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir(parents=True)

        shutil.copy2(sft_path,  staging / sft_path.name)
        shutil.copy2(pref_path, staging / pref_path.name)

        metadata = {
            "title":       title,
            "id":          f"{username}/{slug}",
            "licenses":    [{"name": license_val}],
            "description": description,
        }
        with open(staging / "dataset-metadata.json", "w") as f:
            json.dump(metadata, f, indent=2)

        log.write_line(f">> Staging: {staging}")
        log.write_line(f"   + {sft_path.name}   ({self._row_count(sft_path)} rows)")
        log.write_line(f"   + {pref_path.name}   ({self._row_count(pref_path)} rows)\n")

        # Run the blocking upload in a background thread so the UI stays responsive
        self._run_upload(staging, is_update)

    @work(thread=True)
    def _run_upload(self, staging: Path, is_update: bool) -> None:
        result = upload_dataset(
            folder=staging,
            is_update=is_update,
            log_cb=self._log_from_thread,
        )

        def _apply():
            if result.success:
                self.query_one("#url-panel").update(f"  {result.url}")
            else:
                self.query_one("#publish-log", Log).write_line(f"\n[x] {result.error}")

        self.app.call_from_thread(_apply)

    @staticmethod
    def _row_count(path: Path) -> str:
        try:
            with open(path, "rb") as f:
                return str(sum(1 for _ in f) - 1)  # subtract header
        except Exception:
            return "?"
