from __future__ import annotations

import concurrent.futures
import copy
import itertools
import resource
import threading
from abc import ABC, abstractmethod
from contextlib import ExitStack, contextmanager
from enum import Enum
from pathlib import Path
from typing import (
    Any,
    Callable,
    Collection,
    ContextManager,
    Dict,
    Generic,
    List,
    Optional,
    Set,
    Tuple,
    Type,
    TypeVar,
    Union,
)

import dill  # type: ignore[import-untyped]
import networkx as nx  # type: ignore[import-untyped]
from PIL import Image
from typing_extensions import Self

from verdict import config
from verdict.extractor import Extractor, StructuredOutputExtractor
from verdict.schema import Schema
from verdict.util.exceptions import (
    ConfigurationError,
    VerdictExecutionTimeError,
    VerdictSystemError,
)
from verdict.util.log import logger as base_logger
from verdict.util.tracing import ExecutionContext


class CascadingProperty:
    def __init__(
        self,
        name: str,
        nodes_fn: Callable[[Any], Collection["Node"]] = lambda graph: graph.nodes,
        obj_fn: Callable[[Any], Any] = lambda unit: unit,
        default_factory: Callable[[], Any] = lambda: None,
    ):
        self.name = name
        self.nodes_fn = nodes_fn
        self.obj_fn = obj_fn
        self.default_factory = default_factory

    def __get__(self, obj: Any, objtype=None) -> Any:
        if obj is None:
            return self
        return getattr(self.obj_fn(obj), self.name, self.default_factory())

    def __set__(self, obj: Any, value: Any) -> None:
        setattr(self.obj_fn(obj), self.name, value)
        if isinstance(obj, Graph):
            for node in self.nodes_fn(obj):
                setattr(node, self.name, value)


def CascadingSetter(
    attr_name: str, attr_type: Optional[Type] = Any
) -> Callable[[Any], Self]:
    def setter(self, value: attr_type = None) -> Self:
        # Utilize CascadingProperty's __set__ via setattr
        setattr(self, attr_name, value or True)
        return self

    setter.__name__ = f"set_{attr_name}"
    return setter


class Node(ABC):
    dependencies: Set[Self]
    dependents: Set[Self]

    graph = CascadingProperty("_graph")
    source_input = CascadingProperty("_source_input")
    executor = CascadingProperty("_executor")

    extractor = CascadingProperty(
        "_extractor", default_factory=lambda: StructuredOutputExtractor()
    )
    extract = CascadingSetter("extractor", attr_type=Extractor)

    should_pin_output = CascadingProperty("_should_pin_output")
    pin = CascadingSetter("should_pin_output")

    should_stream_output = CascadingProperty(
        "_should_stream_output", default_factory=lambda: False
    )
    stream = CascadingSetter("should_stream_output")

    propagator = CascadingProperty("_propagator", lambda graph: graph.leaf_nodes)
    propagate = CascadingSetter("propagator")

    __idx = CascadingProperty("_idx", default_factory=lambda: None)
    idx = CascadingSetter("__idx")

    _ordering_timestamp: float
    parent: Optional[Graph[Node]]

    def __init__(self, name: Optional[str] = None, **kwargs) -> None:
        self.name = name

        self.dependencies = set()
        self.dependents = set()

    def set(self, attr, value) -> None:
        if getattr(self, attr) is None:
            setattr(self, attr, value)

    def clear_dependencies(self) -> Self:
        self.dependencies = set()
        self.dependents = set()

        return self

    @abstractmethod
    def copy(self) -> Self:
        """
        Returns a completely independent deep copy of the node.

        Used in .from_sequence, etc.
        """

    @abstractmethod
    def clone(self) -> Self:
        """
        Returns an associated deep copy of the node.

        Used to create a new execution instance of a node.
        """

    @abstractmethod
    def __rshift__(self, other: Union["Node", "Graph[Node]"]) -> None:
        pass

    @abstractmethod
    def link(self, other: Union["Node", "Graph[Node]"]) -> None:
        pass

    @abstractmethod
    def _materialize(self, context) -> Tuple[Self, Any]:
        pass

    @contextmanager
    def freeze(self) -> ContextManager[None]:  # type: ignore
        try:
            yield
        finally:
            pass

    @contextmanager
    def freeze_root_nodes(self) -> ContextManager[None]:  # type: ignore
        try:
            yield
        finally:
            pass

    @contextmanager
    def freeze_leaf_nodes(self) -> ContextManager[None]:  # type: ignore
        try:
            yield
        finally:
            pass

    @contextmanager
    def freeze_all_nodes(self) -> ContextManager[None]:  # type: ignore
        try:
            yield
        finally:
            pass


class Task(ABC):
    leader: bool = False
    thread_id: int = 0

    def __init__(self) -> None:
        self.completed = False
        self.output = None  # NOTE: populated by implementation

    def is_ready(self) -> bool:
        return all(dep.completed for dep in self.dependencies)

    @abstractmethod
    def execute(self, input_data: Any) -> Any:
        raise VerdictSystemError("Subclasses must implement the execute method.")


class ExecutionState(Enum):
    UNSCHEDULED = 0
    WAITING_FOR_DEPENDENCIES = 1
    WAITING_FOR_RESOURCES = 2
    RUNNING = 3
    COMPLETE = 4
    FAILED = 5


thread_counter = itertools.count()


class GraphExecutor:
    class State(Enum):
        SUCCESS = 1
        FAILURE = 2
        TERMINATED = 3

    def __init__(
        self,
        max_workers: Optional[int] = None,
        execution_context: Optional["ExecutionContext"] = None,
    ) -> None:
        soft_fd_limit, hard_fd_limit = resource.getrlimit(resource.RLIMIT_NOFILE)
        requested_soft_fd_limit = min(
            hard_fd_limit, max(soft_fd_limit, 5_000_000)
        )  # TODO: make this a function of max_workers
        if requested_soft_fd_limit <= hard_fd_limit:
            base_logger.debug(
                f"Setting file descriptor limit to {requested_soft_fd_limit}"
            )
            resource.setrlimit(
                resource.RLIMIT_NOFILE, (requested_soft_fd_limit, hard_fd_limit)
            )
        else:
            raise VerdictSystemError(
                f"Number of requested worker threads ({max_workers}) exceeds the current system file descriptor limit ({hard_fd_limit})."
            )

        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)
        # NOTE: map tasks should be very lightweight; this prevents the executor from becoming deadlocked due to fragmented dependency status
        self.lightweight_executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=config.LIGHTWEIGHT_EXECUTOR_WORKER_COUNT
        )

        self.lock = threading.RLock()

        self.is_complete = threading.Event()
        self.execution_state = GraphExecutor.State.SUCCESS
        self.execution_state_lock = threading.Lock()

        self.execution_pool: Set[Task] = set()

        self.outputs: Dict[Task, Schema] = {}
        self.input_data_map: Dict[Task, Schema] = {}
        self.task_to_call_id: Dict[Task, str] = {}  # Track call_id for each task
        self.task_to_trace_id: Dict[Task, str] = {}  # Track trace_id for each task

        from verdict.util.tracing import ExecutionContext

        self.execution_context: ExecutionContext = (
            execution_context or ExecutionContext()
        )

        self.pending_tasks: Set[Task] = set()
        self.active_task_count = 0

    def graceful_shutdown(self) -> None:
        self.execution_state = GraphExecutor.State.TERMINATED
        self.is_complete.set()

    def submit(
        self,
        tasks: List["Unit"],  # noqa: F821 # type: ignore
        input_data: Schema,
        leader: bool = False,
        execution_context: Optional["ExecutionContext"] = None,
        trace_id: str = None,
        parent_id: str = None,
    ) -> None:  # noqa: F821 # type: ignore[name-defined]
        execution_context = execution_context or self.execution_context
        with self.lock:
            for task in tasks:
                if getattr(task, "accumulate", False):
                    self.input_data_map[task] = Schema.of(values=[(input_data,)])
                else:
                    self.input_data_map[task] = input_data

                # If trace_id or parent_id are provided, create a new ExecutionContext for this task
                task_execution_context = execution_context
                if trace_id is not None or parent_id is not None:
                    task_execution_context = ExecutionContext(
                        tracer=execution_context.tracer,
                        trace_id=trace_id or execution_context.trace_id,
                        parent_id=parent_id
                        if parent_id is not None
                        else execution_context.parent_id,
                    )

                self.task_to_trace_id[task] = task_execution_context.trace_id

                base_logger.debug(
                    f"Submitting task with input: {input_data.escape()}",
                    unit=".".join(task.prefix),
                )
                self._try_execute(
                    task, leader, execution_context=task_execution_context
                )

    def _try_execute(
        self,
        task: "Unit",  # noqa: F821 # type: ignore
        leader: bool,
        execution_context: Optional["ExecutionContext"] = None,
    ) -> None:  # noqa: F821 # type: ignore[name-defined]
        execution_context = execution_context or self.execution_context
        logger = base_logger.bind(unit=".".join(task.prefix))
        with self.lock:
            if self.is_complete.is_set():
                logger.error("Exiting early since executor has been marked is_complete")
                return

            task.leader = leader
            task.shared.branch.update(ExecutionState.WAITING_FOR_RESOURCES, task)

            if task.is_ready() and task not in self.execution_pool:
                self.execution_pool.add(task)
                self.active_task_count += 1

                input_data = self.input_data_map.get(task, Schema.empty())
                if getattr(task, "accumulate", False):
                    input_data = Schema.of(values=[x[0] for x in input_data.values])  # type: ignore
                    logger.debug(f"Accumulated {len(input_data.values)} values")

                task.thread_id = next(thread_counter)

                if getattr(task, "lightweight", False):
                    future = self.lightweight_executor.submit(
                        self._execute_task, task, input_data, leader, execution_context
                    )
                    logger.debug("Submitted to lightweight ThreadPoolExecutor")
                else:
                    future = self.executor.submit(
                        self._execute_task, task, input_data, leader, execution_context
                    )
                    logger.debug("Submitted to I/O ThreadPoolExecutor")

                future.add_done_callback(lambda _: self._on_task_complete(task))
            else:
                self.pending_tasks.add(task)

    @base_logger.catch()
    def _execute_task(
        self,
        task: "Unit",  # noqa: F821 # type: ignore
        input_data: Schema,
        leader: bool,
        execution_context: Optional["ExecutionContext"] = None,
    ) -> None:  # noqa: F821 # type: ignore[name-defined]
        execution_context = execution_context or self.execution_context
        logger = base_logger.bind(unit=".".join(task.prefix), thread_id=task.thread_id)
        if self.is_complete.is_set():
            logger.error("Exiting early since executor has been marked is_complete")
            return

        logger.debug("Started executor thread")
        task.shared.branch.update(ExecutionState.RUNNING, task)

        try:
            # don't allow pinning if the prompt references the source sample
            if task.should_pin_output and "source" in task._prompt.get_all_keys():
                raise ConfigurationError(
                    "Prompt references source input. Cannot pin result across all samples."
                )

            if not task.should_pin_output or leader:
                if task.should_pin_output:
                    logger.debug("Elected as leader.")
                # Start the trace for this unit execution and store the call_id
                call_name = (
                    getattr(task, "_char", None)
                    or getattr(task, "char", None)
                    or task.__class__.__name__
                )
                with execution_context.trace_call(
                    name=call_name,
                    inputs={"input": input_data, "unit": task},
                ) as call:
                    if call is not None:
                        self.task_to_call_id[task] = call.call_id
                    output = task.execute(
                        input_data, execution_context=execution_context
                    )
                    with task.shared.shared_output:
                        task.shared.output = output
                        task.shared.shared_output.notify_all()
            else:
                logger.debug("Waiting for leader to complete.")
                with task.shared.shared_output:
                    while task.shared.output is None:
                        task.shared.shared_output.wait()  # timeout=0.1)

                output = task.shared.output
                logger.debug("Gathered output from leader.")

            with self.lock:
                self.outputs[task] = task.output = output
        except Exception as e:
            task.shared.branch.update(ExecutionState.FAILED, task)

            with self.execution_state_lock:
                self.execution_state = GraphExecutor.State.FAILURE
            self.is_complete.set()

            raise VerdictExecutionTimeError() from e

    def _on_task_complete(self, task: "Unit") -> None:  # noqa: F821 # type: ignore[name-defined]
        logger = base_logger.bind(unit=".".join(task.prefix), thread_id=task.thread_id)
        if self.is_complete.is_set():
            logger.error("Exiting early since executor has been marked is_complete")
            return

        with self.lock:
            output = self.outputs[task]
            task.shared.branch.update(ExecutionState.COMPLETE, task)

            for dependent in task.dependents:
                if getattr(dependent, "accumulate", False):
                    if dependent not in self.input_data_map:
                        self.input_data_map[dependent] = Schema.of(values=[])
                    self.input_data_map[dependent].values.append(
                        (output, getattr(task, "_ordering_timestamp", 0))
                    )  # type: ignore
                    self.input_data_map[dependent].values.sort(key=lambda x: x[1])  # type: ignore
                else:
                    self.input_data_map[dependent] = output

            task.completed = True

            trace_id = self.task_to_trace_id.get(task, None)

            for dependent in task.dependents:
                if all(dep.completed for dep in dependent.dependencies):
                    logger.debug(
                        f"Submitting dependent {'.'.join(dependent.prefix)} since all dependencies are complete."
                    )
                    parent_call_id = self.task_to_call_id.get(task, None)
                    dependent_execution_context = ExecutionContext(
                        tracer=self.execution_context.tracer,
                        trace_id=self.task_to_trace_id.get(
                            task, self.execution_context.trace_id
                        ),
                        parent_id=parent_call_id,
                    )
                    self._try_execute(
                        dependent,
                        task.leader,
                        execution_context=dependent_execution_context,
                    )
                else:
                    logger.debug(
                        f"Skipping dependent {'.'.join(dependent.prefix)} since not all dependencies are complete."
                    )

            ready_tasks = [
                pending for pending in list(self.pending_tasks) if pending.is_ready()
            ]
            for ready_task in ready_tasks:
                self.pending_tasks.remove(ready_task)
                logger.debug(
                    f"Submitting unrelated ready task {'.'.join(ready_task.prefix)}",
                    unit="",
                )
                self._try_execute(
                    ready_task,
                    ready_task.leader,
                    execution_context=self.execution_context,
                )

            self.execution_pool.remove(task)
            self.active_task_count -= 1

            if self.active_task_count == 0:
                with self.execution_state_lock:
                    self.execution_state = GraphExecutor.State.SUCCESS
                self.is_complete.set()

    def wait_for_completion(self, graceful: bool = False) -> None:
        self.is_complete.wait()

        base_logger.info(f"GraphExecutor completed in state {self.execution_state}")

        self.executor.shutdown(wait=False, cancel_futures=True)
        self.lightweight_executor.shutdown(wait=False, cancel_futures=True)

        if self.execution_state == GraphExecutor.State.FAILURE:
            base_logger.critical("GraphExecutor failed.")
            if graceful:
                return

            file_name = None
            for handler in base_logger._core.handlers.values():
                if hasattr(handler._sink, "_file"):
                    file_name = handler._sink._file.name

            raise VerdictSystemError(
                "Executor failed. See logs for context"
                + (f": {file_name}" if file_name else ".")
            )

        if self.execution_state == GraphExecutor.State.TERMINATED:
            base_logger.critical("GraphExecutor terminated.")
            if graceful:
                return
            raise VerdictSystemError("Executor terminated.")

    def save(self, path: Path) -> None:
        with open(path, "wb") as f:
            dill.dump(self, f)

    @staticmethod
    def load(path: Path) -> "GraphExecutor":
        with open(path, "rb") as f:
            return dill.load(f)


T = TypeVar("T", bound="Node")


class Graph(Generic[T], Node, ABC):
    def __init__(self, node_type: Type[T]) -> None:
        self.nodes: Set[T] = set()
        self.node_type = node_type

    def add(self, node: Union[T, List[T]]) -> None:
        assert isinstance(node, self.node_type)
        node.graph = self
        self.nodes.add(node)

    def setup_link(self, from_node: T, to_node: T) -> None:
        assert isinstance(from_node, self.node_type) and isinstance(
            to_node, self.node_type
        )

        if from_node not in self.nodes:
            self.add(from_node)

        if to_node not in self.nodes:
            self.add(to_node)

        from_node.dependents.add(to_node)
        to_node.dependencies.add(from_node)

    def replace(self, old: T, new: T) -> None:
        assert isinstance(old, self.node_type) and isinstance(new, self.node_type)

        for node in self.nodes:
            if old in node.dependencies:
                node.dependencies.remove(old)
                node.dependencies.add(new)

            if old in node.dependents:
                node.dependents.remove(old)
                node.dependents.add(new)

        self.nodes.remove(old)

        new.graph = self
        self.nodes.add(new)

    def remove(self, node: T) -> None:
        assert isinstance(node, self.node_type)

        self.nodes.discard(node)
        for dep in node.dependencies:
            dep.dependents.discard(node)
        for dep in node.dependents:
            dep.dependencies.discard(node)

    def set(self, attr, value) -> None:
        setattr(self, attr, value)
        for node in self.nodes:
            node.set(attr, value)

    @property
    def root_nodes(self) -> List[T]:
        if hasattr(self, "_root_nodes"):
            return self._root_nodes
        else:
            return list(filter(lambda node: len(node.dependencies) == 0, self.nodes))

    @property
    def leaf_nodes(self) -> List[T]:
        if hasattr(self, "_leaf_nodes"):
            return self._leaf_nodes
        else:
            return list(filter(lambda node: len(node.dependents) == 0, self.nodes))

    @contextmanager
    def freeze(self) -> ContextManager[None]:  # type: ignore
        """
        Freeze the root_nodes and leaf_nodes properties so that they can be iterated over
        without triggering a recomputation of the properties.
        """
        reentrant = hasattr(self, "_root_nodes") or hasattr(self, "_leaf_nodes")
        try:
            if not reentrant:
                self._root_nodes = self.root_nodes
                self._leaf_nodes = self.leaf_nodes
            yield
        finally:
            if not reentrant:
                del self._root_nodes
                del self._leaf_nodes

    @contextmanager
    def freeze_leaf_nodes(self) -> ContextManager[None]:  # type: ignore
        """Freeze all leaf nodes within a single `with` block."""
        with ExitStack() as stack:
            # Enter `freeze` for all leaf nodes
            for node in list(self.leaf_nodes):
                stack.enter_context(node.freeze())
            yield

    @contextmanager
    def freeze_root_nodes(self) -> ContextManager[None]:  # type: ignore
        """Freeze all leaf nodes within a single `with` block."""
        with ExitStack() as stack:
            # Enter `freeze` for all root nodes
            for node in list(self.root_nodes):
                stack.enter_context(node.freeze())
            yield

    @contextmanager
    def freeze_all_nodes(self) -> ContextManager[None]:  # type: ignore
        """Freeze all nodes within a single `with` block."""
        with ExitStack() as stack:
            for node in self.nodes:
                stack.enter_context(node.freeze())
            yield

    def copy(self) -> "Graph[T]":
        return self.apply(lambda node: node.copy())

    def clone(self) -> "Graph[T]":
        return self.apply(lambda node: node.clone())

    def view(self) -> "Graph[T]":
        return copy.copy(self)

    # avoid disturbing the relative ordering of nodes
    def sort_by_timestamp(self, nodes: Collection[Node]) -> Collection[Node]:
        return sorted(nodes, key=lambda node: getattr(node, "_ordering_timestamp", 0))

    def apply(self, fn: Callable[[T], T]) -> "Graph[T]":
        # NOTE: only call apply on materialized graphs
        other = type(self)()  # type: ignore

        old_to_new: Dict[T, T] = {}

        def map_old_to_new(node: T) -> T:
            if node in old_to_new:
                return old_to_new[node]

            old_to_new[node] = fn(node).clear_dependencies()
            return old_to_new[node]

        for node, dependents in list(
            map(lambda node: (node, list(node.dependents)), self.sort())
        ):
            if len(dependents) == 0:
                other.add(map_old_to_new(node))
            else:
                for dep in self.sort_by_timestamp(dependents):
                    other.setup_link(map_old_to_new(node), map_old_to_new(dep))  # type: ignore

        return other

    # topological sort the nodes
    def sort(self) -> List[T]:
        def traverse(nodes: Collection[T]) -> List[T]:
            visited = set()
            sorted_nodes = []

            def visit(node: T) -> None:
                if node in visited:
                    return
                visited.add(node)
                for dependent in node.dependents:
                    visit(dependent)
                sorted_nodes.append(node)

            for root in nodes:
                visit(root)

            return sorted_nodes[::-1]

        return traverse(self.root_nodes)

    def plot(self, display=False) -> Image.Image:
        from io import BytesIO

        from graphviz import Digraph  # type: ignore[import-untyped]

        def build_graphviz(
            nodes: Collection[T], dot: Digraph, visited: Optional[Set[T]] = None
        ) -> None:
            if visited is None:
                visited = set()
            for node in self.sort_by_timestamp(nodes):
                if node in visited:
                    continue

                dot.node(
                    str(id(node)), label=node.char, shape="box"
                )  # , style='filled', fillcolor=node.color)

                visited.add(node)
                for dep in self.sort_by_timestamp(node.dependencies):
                    if dep in self.nodes:
                        dot.edge(str(id(dep)), str(id(node)))
                        build_graphviz([dep], dot, visited)

        # Initialize Graphviz Digraph
        dot = Digraph()
        build_graphviz(self.nodes, dot)

        # Render and view the graph
        image = Image.open(BytesIO(dot.pipe(format="png")))
        if display:
            image.show()

        return image

    def to_networkx(self) -> nx.DiGraph:
        g = nx.DiGraph()
        for node in self.nodes:
            g.add_node(node)
            for dep in node.dependents:
                g.add_edge(node, dep)
        return g
