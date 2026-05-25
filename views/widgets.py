"""Shared design-system widgets for the Evalflow TUI."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widgets import Static


class PageHeader(Horizontal):
    """Title + subtitle on the left, optional meta text on the right."""

    DEFAULT_CSS = """
    PageHeader {
        width: 100%;
        height: auto;
        min-height: 5;
        padding: 1 3;
        background: $surface;
        border-bottom: hkey #21262D;
        align: left middle;
    }
    PageHeader #ph-text { width: 1fr; height: auto; }
    PageHeader #ph-title {
        color: $foreground;
        text-style: bold;
    }
    PageHeader #ph-subtitle { color: #6E7681; }
    PageHeader #ph-meta {
        width: auto;
        height: auto;
        content-align: right middle;
        color: #6E7681;
        padding: 0 0 0 2;
    }
    """

    def __init__(self, title: str, subtitle: str = "", meta: str = "", **kwargs):
        super().__init__(**kwargs)
        self._title    = title
        self._subtitle = subtitle
        self._meta     = meta

    def compose(self) -> ComposeResult:
        with Vertical(id="ph-text"):
            yield Static(self._title,    id="ph-title",    markup=True)
            if self._subtitle:
                yield Static(self._subtitle, id="ph-subtitle", markup=True)
        if self._meta:
            yield Static(self._meta, id="ph-meta", markup=True)


class Section(Vertical):
    """Labeled section container with an optional hairline header row."""

    DEFAULT_CSS = """
    Section {
        width: 100%;
        height: auto;
        padding: 0 3 1 3;
        margin-top: 1;
    }
    Section .section-head {
        height: 2;
        align: left middle;
        border-bottom: hkey #21262D;
    }
    Section .section-title {
        color: #6E7681;
        text-style: bold;
        width: auto;
    }
    Section .section-hint {
        color: #6E7681;
        width: auto;
        padding: 0 1;
    }
    """

    def __init__(self, title: str = "", hint: str = "", **kwargs):
        super().__init__(**kwargs)
        self._title = title
        self._hint  = hint

    def compose(self) -> ComposeResult:
        if self._title or self._hint:
            with Horizontal(classes="section-head"):
                if self._title:
                    yield Static(self._title, classes="section-title", markup=True)
                if self._hint:
                    yield Static(f"· {self._hint}", classes="section-hint", markup=True)


class SegOpt(Static):
    """A single option inside a Segmented control."""

    def __init__(self, value: str, label: str, **kwargs):
        super().__init__(label, **kwargs)
        self.seg_value = value


class Segmented(Horizontal):
    """iOS-style segmented control. Posts Segmented.Changed when selection changes."""

    class Changed(Message):
        def __init__(self, value: str) -> None:
            super().__init__()
            self.value = value

    DEFAULT_CSS = """
    Segmented {
        height: 3;
        width: auto;
        background: $boost;
        border: round #21262D;
        padding: 0 1;
        align: left middle;
    }
    SegOpt {
        width: auto;
        height: 1;
        padding: 0 2;
        background: transparent;
        color: #6E7681;
        margin: 1 0;
        content-align: center middle;
    }
    SegOpt:hover {
        color: $foreground;
    }
    SegOpt.active {
        background: $surface;
        color: $primary;
        text-style: bold;
        border: round #21262D;
    }
    """

    def __init__(
        self,
        options: list[tuple[str, str]],
        initial: str = "",
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._options = options  # [(value, label), ...]
        self._value   = initial or (options[0][0] if options else "")

    def compose(self) -> ComposeResult:
        for value, label in self._options:
            opt = SegOpt(value, label)
            if value == self._value:
                opt.add_class("active")
            yield opt

    def on_click(self, event) -> None:
        widget = event.widget
        if isinstance(widget, SegOpt):
            if widget.seg_value != self._value:
                self._value = widget.seg_value
                for opt in self.query(SegOpt):
                    opt.remove_class("active")
                widget.add_class("active")
                self.post_message(self.Changed(self._value))

    @property
    def value(self) -> str:
        return self._value

    def set_value(self, value: str) -> None:
        if value == self._value:
            return
        self._value = value
        for opt in self.query(SegOpt):
            opt.remove_class("active")
            if opt.seg_value == value:
                opt.add_class("active")
        self.post_message(self.Changed(value))
