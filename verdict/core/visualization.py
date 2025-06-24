from __future__ import annotations

import threading
from collections import defaultdict
from types import SimpleNamespace
from typing import Any, Collection, Dict, List, Optional

import rich.layout
import rich.panel
import rich.text

from verdict.core.executor import ExecutionState
from verdict.schema import Schema


class StreamingLayoutManager:
    lock: threading.Lock

    streaming_panel: rich.panel.Panel
    layouts: Collection[rich.layout.Layout]

    class StreamingLayout:
        manager: "StreamingLayoutManager"
        unit: "Unit"  # noqa: F821 # type: ignore[name-defined]
        order: int

        text: rich.text.Text
        panel: rich.panel.Panel
        layout: rich.layout.Layout

        def __init__(
            self,
            manager: "StreamingLayoutManager",
            title: str,
            unit: "Unit",
            order: int,
        ):  # noqa: F821 # type: ignore[name-defined]
            self.manager = manager
            self.unit = unit
            self.order = order

            self.text = rich.text.Text("...")
            self.panel = rich.panel.Panel(
                rich.align.Align.left(
                    self.text,
                    vertical="top",
                ),
                title=title,
            )
            self.layout = rich.layout.Layout(self.panel)

        def update(self, response: Schema) -> None:
            self.panel = rich.panel.Panel(
                text := rich.text.Text(),
                title=self.panel.title,
                subtitle=self.panel.subtitle,
                border_style=self.panel.border_style,
                padding=self.panel.padding,
            )

            text.plain = ""
            for k, v in response.model_dump().items():
                text.append(f"{k}:", style="bold underline")
                text.append(f" {v}\n")

            self.text.plain = ""
            self.text.append(text)

            # detect overflow
            try:
                console = rich.console.Console()
                console = rich.console.Console(
                    width=(console.size.width // 2) - 6,
                )
                with console.capture() as capture:
                    console.print(self.panel)

                rendered_output = capture.get()
                height_requested = len(rendered_output.split("\n"))

                with self.manager.lock:
                    height_capacity = console.height // len(self.manager.children)
                    if height_requested > height_capacity:
                        height_overflow = height_requested - height_capacity
                        self.text.plain = ""
                        self.text.append(
                            "...\n"
                            + "\n".join(
                                map(
                                    lambda line: line.strip(" │"),
                                    rendered_output.split("\n")[
                                        2 + height_overflow : -3
                                    ],
                                )
                            )
                        )
            except Exception:
                self.text.plain = ""
                self.text.append(text)

    def __init__(self, layout: rich.layout.Layout, capacity: int = 5) -> None:
        self.lock = threading.Lock()

        self.layout = layout
        self.children: List[StreamingLayoutManager.StreamingLayout] = []

        self.capacity = capacity
        self.total = 0

    def add(self, unit: "Unit") -> StreamingLayout:  # noqa: F821 # type: ignore[name-defined]
        title = f"[{unit.char}]" + (
            f" [orange_red1]{unit.name}[/orange_red1]" if unit.name else ""
        )
        with self.lock:
            layout = StreamingLayoutManager.StreamingLayout(
                manager=self, title=title, unit=unit, order=self.total
            )

            # TODO: queue up running streamers, display as possible
            while len(self.children) >= self.capacity:
                # remove completed tasks first, then oldest tasks
                if not any(child.unit.completed for child in self.children):
                    return layout
                self.children.sort(
                    key=lambda child: (-int(child.unit.completed), child.order)
                )
                self.layout._children.remove(self.children.pop(0).layout)

            self.children.append(layout)
            self.layout.add_split(layout.layout)
            self.total += 1

            return layout


class BranchManager:
    spinner = {
        ExecutionState.WAITING_FOR_DEPENDENCIES: "bounce",
        ExecutionState.WAITING_FOR_RESOURCES: "dots11",
        ExecutionState.RUNNING: "dots3",
    }

    lock: threading._RLock
    branch: Optional[rich.tree.Tree]
    n_peers: int
    should_pin_output: bool

    visited_states: Dict[ExecutionState, int]

    def __init__(
        self,
        lock: threading.Lock,
        branch: Optional[rich.tree.Tree],
        n_peers: int,
        should_pin_output: bool,
    ) -> None:
        self.lock = threading.RLock()
        self.branch = branch
        self.n_peers = n_peers

        self.should_pin_output = should_pin_output
        self.length = 1 if self.should_pin_output else n_peers

        self.visited_states = defaultdict(int)

    def update(self, state: ExecutionState, unit: "Unit") -> None:  # noqa: F821 # type: ignore[name-defined]
        from verdict.core.primitive import Unit

        if not self.branch:
            return

        with self.lock:
            if self.visited_states[state] >= self.length:
                return
            self.visited_states[state] += 1

            text = f"[{unit.char}]" + (
                f" [orange_red1]{unit.name}[/orange_red1]" if unit.name else ""
            )
            if state == ExecutionState.WAITING_FOR_DEPENDENCIES:
                if self.n_peers <= 1:
                    table = rich.table.Table.grid(expand=True)
                    table.add_column(justify="left", ratio=3)  # status
                    table.add_column(
                        justify="right", ratio=1, no_wrap=True, overflow="ellipsis"
                    )  # result

                    groups = [
                        rich.spinner.Spinner(BranchManager.spinner[state], text=text)
                    ]
                    if type(unit).description is not Unit.description:
                        groups.append(f"\t{str(unit.description)}")  # type: ignore
                    table.add_row(rich.console.Group(*groups), "")
                    self.branch = self.branch.add(table)
                else:
                    # set progress bar
                    progress = rich.progress.Progress(
                        rich.progress.SpinnerColumn(
                            spinner_name=BranchManager.spinner[ExecutionState.RUNNING]
                        ),
                        rich.progress.BarColumn(bar_width=10),
                        rich.progress.MofNCompleteColumn(),  # TODO: running | completed/total
                        rich.progress.TextColumn(
                            "[progress.description]{task.description}"
                        ),
                        rich.progress.TimeElapsedColumn(),
                        rich.progress.TimeRemainingColumn(),
                    )
                    progress.add_task(text, total=self.length)
                    self.branch = self.branch.add(rich.console.Group(progress))
            elif state in [
                ExecutionState.WAITING_FOR_RESOURCES,
                ExecutionState.RUNNING,
            ]:
                if self.n_peers <= 1:
                    self.branch.label.columns[0]._cells[0].renderables[0] = (
                        rich.spinner.Spinner(  # type: ignore
                            BranchManager.spinner[state],
                            text=self.branch.label.columns[0]
                            ._cells[0]
                            .renderables[0]
                            .text,  # type: ignore
                        )
                    )
                # (pending_tasks): increment pending (just once!), use task.fields
            elif state == ExecutionState.COMPLETE:
                if self.n_peers <= 1:
                    self.branch.label.columns[0]._cells[0].renderables[0] = (
                        f"✔ {self.branch.label.columns[0]._cells[0].renderables[0].text}"  # type: ignore
                    )
                    if isinstance(unit.output, Schema):
                        unit_output = unit.output.model_dump()
                        if len(unit_output) == 1:
                            output: Any = unit_output[list(unit_output.keys())[0]]
                            if isinstance(output, float):
                                output = f"{output:.4f}"
                            output_str: str = str(output).split("\n")[0]
                        else:

                            def clean(output: Any) -> str:
                                if isinstance(output, float):
                                    return f"{output:.4f}"
                                elif isinstance(output, str) and len(output) > 4:
                                    return "…"
                                return str(output)

                            output_str = ", ".join(
                                [f"{k}: {clean(v)}" for k, v in unit_output.items()]
                            )

                        self.branch.label.columns[1]._cells[0] = rich.text.Text(
                            output_str, style="bright_black"
                        )  # type: ignore
                else:
                    self.branch.label.renderables[0].advance(task_id=0)  # type: ignore
                # (pending_tasks): decrement pending
            else:
                if self.n_peers <= 1:
                    self.branch.label.columns[0]._cells[0].renderables[0] = (
                        f"✘ {self.branch.label.columns[0]._cells[0].renderables[0].text}"  # type: ignore
                    )
                else:
                    column = next(
                        filter(
                            lambda c: isinstance(c, rich.progress.SpinnerColumn),
                            self.branch.label.renderables[0].columns,
                        )
                    )  # type: ignore
                    column.spinner = SimpleNamespace(render=lambda task: "✘")
