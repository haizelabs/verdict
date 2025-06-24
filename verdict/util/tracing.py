"""
tracing.py

This module provides a flexible, thread- and async-safe tracing infrastructure for
pipelines, units, and other components. It supports multi-tracer fan-out, context
propagation using contextvars, and extensibility for custom tracers.

Key classes:
    - TraceContext: Stores the current trace context (trace_id, call_id, parent_id).
    - Call: Represents a single traced call (span).
    - Tracer: Abstract base class for all tracers.
    - TracingManager: Fans out to multiple tracers, manages context propagation.
    - NoOpTracer: A tracer that does nothing, but propagates context.
    - ConsoleTracer: Prints trace events to the console, with indentation.

Usage examples are provided at the end of the file.
"""

import contextvars
import threading
import time
import uuid
from abc import ABC, abstractmethod
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass, field
from typing import (
    Any,
    Dict,
    Iterator,
    List,
    Optional,
    Union,
)

# --- Context Management ---


@dataclass
class TraceContext:
    """Stores the current trace context for a logical execution flow.

    Attributes:
        trace_id: The unique identifier for the trace (spans/calls tree).
        call_id: The unique identifier for this call/span.
        parent_id: The call_id of the parent call, if any.
    """

    trace_id: str
    call_id: str
    parent_id: Optional[str]


#: The current trace context for the thread or async task.
current_trace_context: contextvars.ContextVar[Optional[TraceContext]] = (
    contextvars.ContextVar("current_trace_context", default=None)
)


# --- Call Data Structure ---


@dataclass
class Call:
    """Represents a single traced call/span.

    Attributes:
        name: The name of the call (operation).
        inputs: The input arguments for the call.
        trace_id: The trace ID for the call tree.
        call_id: The unique ID for this call.
        parent_id: The parent call's ID, if any.
        outputs: The outputs of the call.
        exception: Any exception raised during the call.
        start_time: The time the call started.
        end_time: The time the call ended.
        children: List of child Call objects.
    """

    name: str
    inputs: Dict[str, Any]
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    call_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    parent_id: Optional[str] = None
    outputs: Any = None
    exception: Any = None
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    children: List["Call"] = field(default_factory=list)
    _lock: threading.Lock = field(
        default_factory=threading.Lock, repr=False, compare=False
    )

    def __enter__(self) -> "Call":
        """Start timing the call."""
        self.start_time = time.time()
        return self

    def __exit__(
        self,
        exc_type: Optional[type],
        exc_val: Optional[BaseException],
        exc_tb: Optional[Any],
    ) -> bool:
        """End timing the call and record any exception."""
        self.end_time = time.time()
        if exc_val is not None:
            self.exception = exc_val
        return False  # Don't suppress exceptions

    @property
    def duration(self) -> Optional[float]:
        """Returns the duration of the call in seconds, or None if not finished."""
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return None

    def set_outputs(self, outputs: Any) -> None:
        """Thread-safe setter for outputs."""
        with self._lock:
            self.outputs = outputs

    def add_child(self, child: "Call") -> None:
        """Thread-safe adder for child calls."""
        with self._lock:
            self.children.append(child)


# --- Tracer Interface ---


class Tracer(ABC):
    """Abstract base class for all tracers.

    Subclasses must implement the start_call context manager.
    """

    @abstractmethod
    @contextmanager
    def start_call(
        self,
        name: str,
        inputs: Dict[str, Any],
        trace_id: Optional[str] = None,
        parent_id: Optional[str] = None,
    ) -> Iterator[Optional[Call]]:
        """Context manager for tracing a call/span.

        Args:
            name: The name of the operation.
            inputs: The input arguments.
            trace_id: The trace ID (optional).
            parent_id: The parent call ID (optional).

        Yields:
            A Call object (or None for NoOpTracer).
        """
        pass


# --- TracingManager ---


class TracingManager(Tracer):
    """A tracer that fans out to multiple tracers and manages context propagation.

    Args:
        tracers: A list of Tracer instances to fan out to.
    """

    def __init__(self, tracers: List[Tracer]) -> None:
        self.tracers = tracers

    @contextmanager
    def start_call(
        self,
        name: str,
        inputs: Dict[str, Any],
        trace_id: Optional[str] = None,
        parent_id: Optional[str] = None,
    ) -> Iterator[Optional[Call]]:
        """Starts a call on all child tracers, manages context propagation."""
        parent_ctx = current_trace_context.get()
        if parent_id is None and parent_ctx is not None:
            parent_id = parent_ctx.call_id
        if trace_id is None and parent_ctx is not None:
            trace_id = parent_ctx.trace_id

        contexts: List[AbstractContextManager[Optional[Call]]] = [
            t.start_call(name, inputs, trace_id, parent_id) for t in self.tracers
        ]
        calls: List[Optional[Call]] = []
        token: Optional[contextvars.Token] = None
        try:
            for ctx in contexts:
                calls.append(ctx.__enter__())
            call_id: str = (
                calls[0].call_id
                if calls and hasattr(calls[0], "call_id") and calls[0] is not None
                else str(uuid.uuid4())
            )
            token = current_trace_context.set(
                TraceContext(trace_id, call_id, parent_id)
            )
            yield calls[0] if calls else None
        except Exception as e:
            for ctx in contexts:
                ctx.__exit__(type(e), e, e.__traceback__)
            raise
        else:
            for ctx in contexts:
                ctx.__exit__(None, None, None)
        finally:
            if token is not None:
                current_trace_context.reset(token)

    def add_tracer(self, tracer: Tracer) -> None:
        self.tracers.append(tracer)


# --- NoOpTracer ---


class NoOpTracer(Tracer):
    """A tracer that does nothing, but propagates context for downstream code."""

    @contextmanager
    def start_call(
        self,
        name: str,
        inputs: Dict[str, Any],
        trace_id: Optional[str] = None,
        parent_id: Optional[str] = None,
    ) -> Iterator[None]:
        parent_ctx = current_trace_context.get()
        if parent_id is None and parent_ctx is not None:
            parent_id = parent_ctx.call_id
        if trace_id is None and parent_ctx is not None:
            trace_id = parent_ctx.trace_id
        call_id: str = str(uuid.uuid4())
        token: contextvars.Token = current_trace_context.set(
            TraceContext(trace_id, call_id, parent_id)
        )
        try:
            yield None
        finally:
            current_trace_context.reset(token)


# --- ConsoleTracer ---


class ConsoleTracer(Tracer):
    """A tracer that prints trace events to the console, with indentation."""

    def __init__(self) -> None:
        self._call_registry: Dict[str, Call] = {}  # call_id -> Call

    @contextmanager
    def start_call(
        self,
        name: str,
        inputs: Dict[str, Any],
        trace_id: Optional[str] = None,
        parent_id: Optional[str] = None,
    ) -> Iterator[Call]:
        parent_ctx = current_trace_context.get()
        if parent_id is None and parent_ctx is not None:
            parent_id = parent_ctx.call_id
        if trace_id is None and parent_ctx is not None:
            trace_id = parent_ctx.trace_id

        call = Call(name, inputs, trace_id=trace_id, parent_id=parent_id)
        self._call_registry[call.call_id] = call
        indent = self._get_indent(call)
        print(
            f"{indent}>> Call: {name} | trace_id={call.trace_id} | call_id={call.call_id} | parent_id={call.parent_id} | Inputs: {self._shorten(inputs)}"
        )
        token: contextvars.Token = current_trace_context.set(
            TraceContext(trace_id, call.call_id, parent_id)
        )
        try:
            yield call
        except Exception as e:
            call.exception = e
            raise
        finally:
            call.end_time = time.time()
            duration_str = (
                f"{call.duration:.3f}s" if call.duration is not None else "N/A"
            )
            print(
                f"{indent}<< Call: {name} | trace_id={call.trace_id} | call_id={call.call_id} | parent_id={call.parent_id} | Outputs: {self._shorten(call.outputs)} | Exception: {call.exception} | Duration: {duration_str}"
            )
            current_trace_context.reset(token)

    def _get_indent(self, call: Call) -> str:
        """Compute indentation for pretty-printing based on call depth."""
        depth: int = 0
        parent_id: Optional[str] = call.parent_id
        while parent_id:
            parent_call = self._call_registry.get(parent_id)
            if parent_call is None:
                break
            depth += 1
            parent_id = parent_call.parent_id
        return "  " * depth

    def _shorten(self, obj: Any, maxlen: int = 120) -> str:
        """Shorten a string representation for console output."""
        s: str = str(obj)
        if len(s) > maxlen:
            return s[:maxlen] + "..."
        return s


def ensure_tracing_manager(
    tracer: Optional[Union[Tracer, List[Tracer]]],
) -> TracingManager:
    if tracer is None:
        return TracingManager([NoOpTracer()])
    if isinstance(tracer, TracingManager):
        return tracer
    if isinstance(tracer, list):
        return TracingManager(tracer)
    return TracingManager([tracer])


@dataclass
class ExecutionContext:
    """Stores the current execution context, including tracing information and the tracer instance.

    Attributes:
        tracer: The tracer instance to use for this execution.
        trace_id: The unique identifier for the trace (spans/calls tree).
        call_id: The unique identifier for this call/span.
        parent_id: The call_id of the parent call, if any.
    """

    tracer: Tracer = field(default_factory=NoOpTracer)
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    call_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    parent_id: Optional[str] = None

    def child(self, call_id: Optional[str] = None) -> "ExecutionContext":
        """Create a new context for a child call/span."""
        return ExecutionContext(
            tracer=self.tracer,
            trace_id=self.trace_id,
            call_id=call_id or str(uuid.uuid4()),
            parent_id=self.call_id,
        )

    @contextmanager
    def trace_call(self, name: str, inputs: dict):
        with self.tracer.start_call(
            name=name,
            inputs=inputs,
            trace_id=self.trace_id,
            parent_id=self.parent_id,
        ) as call:
            yield call
