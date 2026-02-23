from __future__ import annotations

# ======================= STANDARDS =======================
from contextlib import contextmanager
from collections.abc import Iterator
from types import TracebackType
from enum import Enum
import sys

# ==================== THIRD-PARTIES ======================
from rich.console import Console, RenderableType, Group
from rich.spinner import Spinner
from rich.panel import Panel
from rich.table import Table
from rich.box import MINIMAL
from rich.live import Live
from rich.text import Text

# ======================== LOCALS =========================
from . import utils


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE    = "done"
    FAIL    = "fail"
    ABORT   = "abort"


class TUIRunner:
    def __init__(self, labels: list[str], enabled: bool
        ) -> None:
        self.enabled   = enabled
        self.labels    = labels
        self.statuses  = [StepStatus.PENDING] * len(labels)
        self.console   = Console(stderr=True)
        self._messages: list[list[tuple[str, str, bool]]] \
                       = [[] for _ in labels]
        self._spinners: list[Spinner | None] = [None] \
                                             * len(labels)
        self._live: Live | None = None

    # Safe add_message
    def add_message(self, idx: int | None, msg: str,
                    fg: str = "yellow", prfx: bool = True
                   ) -> None:
        if not self.enabled or idx is None:
            # fallback: print directly if step index unknown
            text = utils.wrap(msg) if prfx else msg
            styled = utils.color(text, fg)
            if prfx:
                print(f"{utils.const.PNP}{styled}")
            else:
                print(styled)
            return
        self._messages[idx].append((msg, fg, prfx))
        self._refresh()

    def __enter__(self) -> "TUIRunner":
        if not self.enabled: return self
        utils.bind_console(self)
        self._live = Live(self._render(),
                     console=self.console,
                     refresh_per_second=10,
                     transient=False)
        self._live.__enter__()
        return self

    def __exit__(self, exc_type: type[BaseException] | None,
                 exc: BaseException | None,
                 tb: TracebackType | None) -> None:
        utils.bind_console(None)
        if self._live:
            self._live.__exit__(exc_type, exc, tb)
            self._live = None

    def suspend(self) -> None:
        """Temporarily stop live rendering for external TTY apps."""
        if not self.enabled or not self._live: return
        utils.bind_console(None)
        self._live.__exit__(None, None, None)
        self._live = None

    def resume(self) -> None:
        """Resume live rendering after external TTY apps exit."""
        if not self.enabled or self._live is not None: return
        self._live = Live(
            self._render(),
            console=self.console,
            refresh_per_second=10,
            transient=False,
        )
        self._live.__enter__()
        utils.bind_console(self)

    def start(self, idx: int) -> None:
        if not self.enabled: return
        self.statuses[idx] = StepStatus.RUNNING
        self._spinners[idx] = Spinner("dots",
                              text=self.labels[idx])
        self._refresh()

    def finish(self, idx: int, result: object) -> None:
        if not self.enabled: return
        status_name = getattr(result, "name", "").lower()
        if status_name == "ok":
            self.statuses[idx] = StepStatus.DONE
        elif status_name == "abort":
            self.statuses[idx] = StepStatus.ABORT
        else: self.statuses[idx] = StepStatus.FAIL
        # Remove spinner after finish
        self._spinners[idx] = None
        self._refresh()

    def _refresh(self) -> None:
        if self._live: self._live.update(self._render())

    def _render(self) -> Table:
        table = Table(show_header=False, box=None,
                pad_edge=False)
        table.add_column(justify="left")
    
        for i, (label, status) in enumerate(zip(self.labels,
                                            self.statuses)):
            step_render = self._row(label, status)
    
            if self._messages[i]:
                msgs_text = Text()
                for j, (msg, fg, prfx) in enumerate(
                        self._messages[i]):
                    if j: msgs_text.append("\n")
                    if prfx:
                        msgs_text.append(
                            f"{utils.const.APP} ",
                            style="magenta"
                        )
                    msgs_text.append(msg, style=fg)
                msgs_panel = Panel(msgs_text, box=MINIMAL,
                             padding=(0, 2))
                renderable: RenderableType = Group(
                            step_render, msgs_panel)
            else: renderable = step_render
    
            table.add_row(renderable)
    
        return table
    
    
    def _row(self, label: str, status: StepStatus
            ) -> Text | Spinner:
        if status == StepStatus.RUNNING:
            return Spinner("dots", text=label)
        if status == StepStatus.DONE:
            return Text(f"✔ {label}", style="green")
        if status == StepStatus.FAIL:
            return Text(f"✖ {label}", style="red")
        if status == StepStatus.ABORT:
            return Text(f"✖ {label}", style="yellow")
        return Text(f"○ {label}", style="dim")


@contextmanager
def tui_runner(labels: list[str], enabled: bool
              ) -> Iterator[TUIRunner]:
    runner = TUIRunner(labels, enabled)
    with runner: yield runner
