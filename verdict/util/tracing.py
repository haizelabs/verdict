import time
import threading
import uuid
from abc import ABC, abstractmethod
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, List


@dataclass
class Call:
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

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_time = time.time()
        if exc_val is not None:
            self.exception = exc_val
        return False  # Don't suppress exceptions

    @property
    def duration(self):
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return None

    def set_outputs(self, outputs: Any):
        with self._lock:
            self.outputs = outputs

    def add_child(self, child: "Call"):
        with self._lock:
            self.children.append(child)


class Tracer(ABC):
    @abstractmethod
    @contextmanager
    def start_call(
        self,
        name: str,
        inputs: Dict[str, Any],
        trace_id: Optional[str] = None,
        parent_id: Optional[str] = None,
    ):
        pass


class NoOpTracer(Tracer):
    @contextmanager
    def start_call(
        self,
        name: str,
        inputs: Dict[str, Any],
        trace_id: Optional[str] = None,
        parent_id: Optional[str] = None,
    ):
        yield None


class ConsoleTracer(Tracer):
    def __init__(self):
        self._local = threading.local()

    @contextmanager
    def start_call(
        self,
        name: str,
        inputs: Dict[str, Any],
        trace_id: Optional[str] = None,
        parent_id: Optional[str] = None,
    ):
        call = Call(name, inputs, trace_id=trace_id, parent_id=parent_id)
        indent = self._get_indent(call)
        print(
            f"{indent}>> Call: {name} | trace_id={call.trace_id} | call_id={call.call_id} | parent_id={call.parent_id} | Inputs: {self._shorten(inputs)}"
        )
        if not hasattr(self._local, "stack"):
            self._local.stack = []
        self._local.stack.append(call)
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
            self._local.stack.pop()

    def _get_indent(self, call: Call) -> str:
        if not hasattr(self._local, "stack"):
            return ""
        stack = getattr(self._local, "stack", [])
        depth = 0
        parent_id = call.parent_id
        for c in reversed(stack):
            if c.call_id == parent_id:
                depth += 1
                parent_id = c.parent_id
        return "  " * depth

    def _shorten(self, obj: Any, maxlen: int = 120) -> str:
        s = str(obj)
        if len(s) > maxlen:
            return s[:maxlen] + "..."
        return s
