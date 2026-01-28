# pnp/tui.py
from __future__ import annotations

# ======================= STANDARDS =======================
from contextlib import contextmanager
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
    DONE = "done"
    FAIL = "fail"
    ABORT = "abort"


class TUIRunner:
    def __init__(self, labels: list[str], enabled: bool
        ) -> None:
        self.enabled   = enabled
        self.labels    = labels
        self.statuses  = [StepStatus.PENDING] * len(labels)
        self.console   = Console(stderr=True)
        self._messages = [[] for _ in labels]
        self._spinners = [None] * len(labels)
        self._live: Live | None = None

    # Safe add_message
    def add_message(self, idx: int | None, msg: str) -> None:
        if not self.enabled or idx is None:
            # fallback: print directly if step index unknown
            print(msg)
            return
        self._messages[idx].append(msg)
        self._refresh()

    def __enter__(self) -> "TUIRunner":
        if not self.enabled: return self
        utils.bind_console(self.console)
        self._live = Live(self._render(),
                     console=self.console,
                     refresh_per_second=10, transient=False)
        self._live.__enter__()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        utils.bind_console(None)
        if self._live:
            self._live.__exit__(exc_type, exc, tb)

    def start(self, idx: int) -> None:
        if not self.enabled: return
        self.statuses[idx] = StepStatus.RUNNING
        # Create a real Spinner for this step
        self._spinners[idx] = Spinner("dots", text=self.labels[idx])
        self._refresh()

    def finish(self, idx: int, result) -> None:
        if not self.enabled: return
        status_name = getattr(result, "name", "").lower()
        if status_name == "ok":
            self.statuses[idx] = StepStatus.DONE
        elif status_name == "abort":
            self.statuses[idx] = StepStatus.ABORT
        else:
            self.statuses[idx] = StepStatus.FAIL
        # Remove spinner after finish
        self._spinners[idx] = None
        self._refresh()

    def _refresh(self) -> None:
        if self._live:
            self._live.update(self._render())

    def _render(self) -> Table:
        table = Table(show_header=False, box=None, pad_edge=False)
        table.add_column(justify="left")
    
        for i, (label, status) in enumerate(zip(self.labels, self.statuses)):
            step_render = self._row(label, status)
    
            if self._messages[i]:
                raw_msgs   = "\n".join(self._messages[i])
                msgs_text  = Text.from_ansi(raw_msgs)
                msgs_panel = Panel(msgs_text, box=MINIMAL,
                             padding=(0, 2))
                renderable = Group(step_render, msgs_panel)
            else: renderable = step_render
    
            table.add_row(renderable)
    
        return table
    
    
    def _row(self, label: str, status: StepStatus) -> Text | Spinner:
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
def tui_runner(labels: list[str], enabled: bool):
    runner = TUIRunner(labels, enabled)
    with runner: yield runner
