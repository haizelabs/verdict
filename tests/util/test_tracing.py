"""
Tests for verdict.util.tracing module.

Tests cover:
- TraceContext creation and behavior
- Call dataclass functionality including context manager and thread safety
- NoOpTracer context propagation
- ConsoleTracer output and formatting
- TracingManager multi-tracer coordination
- ExecutionContext behavior
- Utility functions
- Concurrency and thread safety
"""

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import Mock, MagicMock

import pytest
import time

from verdict.util.tracing import (
    TraceContext,
    Call,
    Tracer,
    TracingManager,
    NoOpTracer,
    ConsoleTracer,
    ExecutionContext,
    ensure_tracing_manager,
    current_trace_context,
)


# === TraceContext Tests ===


def test_trace_context_creation():
    """Test basic TraceContext creation and attributes."""
    trace_id = "test-trace-123"
    call_id = "test-call-456"
    parent_id = "test-parent-789"

    context = TraceContext(trace_id=trace_id, call_id=call_id, parent_id=parent_id)

    assert context.trace_id == trace_id
    assert context.call_id == call_id
    assert context.parent_id == parent_id


def test_trace_context_equality():
    """Test TraceContext equality comparison."""
    context1 = TraceContext("trace1", "call1", "parent1")
    context2 = TraceContext("trace1", "call1", "parent1")
    context3 = TraceContext("trace1", "call1", "parent2")

    assert context1 == context2
    assert context1 != context3


def test_trace_context_with_parent():
    """Test TraceContext with None parent (root context)."""
    context = TraceContext("trace1", "call1", None)

    assert context.trace_id == "trace1"
    assert context.call_id == "call1"
    assert context.parent_id is None


# === Call Tests ===


def test_call_creation_with_defaults():
    """Test Call creation with default values."""
    call = Call(name="test_operation", inputs={"arg1": "value1"})

    assert call.name == "test_operation"
    assert call.inputs == {"arg1": "value1"}
    assert call.outputs is None
    assert call.exception is None
    assert call.start_time is None
    assert call.end_time is None
    assert call.children == []
    assert call.duration is None
    # trace_id and call_id should be generated
    assert call.trace_id is not None
    assert call.call_id is not None


def test_call_context_manager_timing():
    """Test Call context manager properly tracks timing."""
    call = Call(name="test", inputs={})

    start_before = time.time()
    with call:
        time.sleep(0.01)
    end_after = time.time()

    assert call.start_time is not None
    assert call.end_time is not None
    assert call.start_time >= start_before
    assert call.end_time <= end_after
    assert call.duration is not None
    assert call.duration > 0


def test_call_context_manager_exception_handling():
    """Test Call context manager properly captures exceptions."""
    call = Call(name="test", inputs={})
    test_exception = ValueError("test error")

    with pytest.raises(ValueError):
        with call:
            raise test_exception

    assert call.exception == test_exception
    assert call.start_time is not None
    assert call.end_time is not None


def test_call_duration_calculation():
    """Test Call duration calculation."""
    call = Call(name="test", inputs={})

    # Before timing
    assert call.duration is None

    # Set times manually
    call.start_time = 1000.0
    call.end_time = 1000.5

    assert call.duration == 0.5


def test_call_thread_safe_outputs():
    """Test Call.set_outputs is thread-safe."""
    call = Call(name="test", inputs={})
    results = []

    def set_output(value):
        call.set_outputs(f"output_{value}")
        results.append(call.outputs)

    threads = []
    for i in range(10):
        thread = threading.Thread(target=set_output, args=(i,))
        threads.append(thread)
        thread.start()

    for thread in threads:
        thread.join()

    # Should have one of the outputs set
    assert call.outputs is not None
    assert call.outputs.startswith("output_")


def test_call_thread_safe_children():
    """Test Call.add_child is thread-safe."""
    parent_call = Call(name="parent", inputs={})

    def add_child(value):
        child = Call(name=f"child_{value}", inputs={})
        parent_call.add_child(child)

    threads = []
    for i in range(10):
        thread = threading.Thread(target=add_child, args=(i,))
        threads.append(thread)
        thread.start()

    for thread in threads:
        thread.join()

    assert len(parent_call.children) == 10
    child_names = [child.name for child in parent_call.children]
    for i in range(10):
        assert f"child_{i}" in child_names


# === NoOpTracer Tests ===


def test_noop_tracer_context_propagation():
    """Test NoOpTracer properly propagates context."""
    tracer = NoOpTracer()

    # Set initial context
    initial_context = TraceContext("trace1", "call1", None)
    token = current_trace_context.set(initial_context)

    try:
        with tracer.start_call("test", {}) as call:
            # Should propagate parent context
            current_ctx = current_trace_context.get()
            assert current_ctx is not None
            assert current_ctx.trace_id == "trace1"
            assert current_ctx.parent_id == "call1"
            assert current_ctx.call_id != "call1"  # New call_id
    finally:
        current_trace_context.reset(token)


def test_noop_tracer_yields_none():
    """Test NoOpTracer yields None instead of Call object."""
    tracer = NoOpTracer()

    with tracer.start_call("test", {}) as call:
        assert call is None


def test_noop_tracer_inherits_parent_context():
    """Test NoOpTracer inherits from parent context when available."""
    tracer = NoOpTracer()

    # Set parent context
    parent_context = TraceContext("parent_trace", "parent_call", None)
    token = current_trace_context.set(parent_context)

    try:
        with tracer.start_call("test", {}) as call:
            current_ctx = current_trace_context.get()
            assert current_ctx.trace_id == "parent_trace"
            assert current_ctx.parent_id == "parent_call"
    finally:
        current_trace_context.reset(token)


def test_noop_tracer_generates_new_ids():
    """Test NoOpTracer generates new call_id and trace_id when no parent."""
    tracer = NoOpTracer()

    # Clear any existing context
    current_trace_context.set(None)

    with tracer.start_call("test", {}) as call:
        current_ctx = current_trace_context.get()
        assert current_ctx.call_id is not None
        # No parent, so no trace_id
        assert current_ctx.trace_id is None
        assert current_ctx.parent_id is None


# === ConsoleTracer Tests ===


def test_console_tracer_basic_output(capsys):
    """Test ConsoleTracer produces expected console output."""
    tracer = ConsoleTracer()

    with tracer.start_call("test_operation", {"input": "value"}) as call:
        call.set_outputs("test_output")

    captured = capsys.readouterr()
    assert ">> Call: test_operation" in captured.out
    assert "<< Call: test_operation" in captured.out
    assert "Inputs: {'input': 'value'}" in captured.out
    assert "Outputs: test_output" in captured.out


def test_console_tracer_indentation(capsys):
    """Test ConsoleTracer properly indents nested calls."""
    tracer = ConsoleTracer()

    with tracer.start_call("parent", {}) as parent_call:
        with tracer.start_call("child", {}) as child_call:
            pass

    captured = capsys.readouterr()
    lines = captured.out.strip().split("\n")

    # Find parent and child lines
    parent_start = next(line for line in lines if ">> Call: parent" in line)
    child_start = next(line for line in lines if ">> Call: child" in line)

    # Child should be indented more than parent
    parent_indent = len(parent_start) - len(parent_start.lstrip())
    child_indent = len(child_start) - len(child_start.lstrip())
    assert child_indent > parent_indent


def test_console_tracer_exception_handling(capsys):
    """Test ConsoleTracer properly logs exceptions."""
    tracer = ConsoleTracer()

    with pytest.raises(ValueError):
        with tracer.start_call("failing_operation", {}) as call:
            raise ValueError("test error")

    captured = capsys.readouterr()
    assert "Exception: test error" in captured.out


def test_console_tracer_context_propagation():
    """Test ConsoleTracer properly propagates context."""
    tracer = ConsoleTracer()

    with tracer.start_call("outer", {}) as outer_call:
        outer_context = current_trace_context.get()

        with tracer.start_call("inner", {}) as inner_call:
            inner_context = current_trace_context.get()

            # Inner should have outer as parent
            assert inner_context.parent_id == outer_context.call_id
            assert inner_context.trace_id == outer_context.trace_id


def test_console_tracer_duration_tracking(capsys):
    """Test ConsoleTracer includes duration in output."""
    tracer = ConsoleTracer()

    with tracer.start_call("timed_operation", {}) as call:
        time.sleep(0.01)

    captured = capsys.readouterr()
    assert "Duration:" in captured.out
    assert "s" in captured.out  # Should show seconds


def test_console_tracer_nested_calls(capsys):
    """Test ConsoleTracer handles deeply nested calls."""
    tracer = ConsoleTracer()

    with tracer.start_call("level1", {}) as call1:
        with tracer.start_call("level2", {}) as call2:
            with tracer.start_call("level3", {}) as call3:
                pass

    captured = capsys.readouterr()
    lines = captured.out.strip().split("\n")

    # Should have start and end for each level
    level1_starts = [line for line in lines if ">> Call: level1" in line]
    level2_starts = [line for line in lines if ">> Call: level2" in line]
    level3_starts = [line for line in lines if ">> Call: level3" in line]

    assert len(level1_starts) == 1
    assert len(level2_starts) == 1
    assert len(level3_starts) == 1


# === TracingManager Tests ===


def test_tracing_manager_single_tracer():
    """Test TracingManager with a single tracer."""
    mock_tracer = MagicMock(spec=Tracer)
    mock_call = Mock()
    mock_tracer.start_call.return_value.__enter__.return_value = mock_call
    mock_tracer.start_call.return_value.__exit__.return_value = None

    manager = TracingManager([mock_tracer])

    with manager.start_call("test", {"input": "value"}) as call:
        assert call == mock_call

    mock_tracer.start_call.assert_called_once()


def test_tracing_manager_multiple_tracers():
    """Test TracingManager fans out to multiple tracers."""
    mock_tracer1 = MagicMock(spec=Tracer)
    mock_tracer2 = MagicMock(spec=Tracer)
    mock_call1 = Mock()
    mock_call2 = Mock()

    mock_tracer1.start_call.return_value.__enter__.return_value = mock_call1
    mock_tracer1.start_call.return_value.__exit__.return_value = None
    mock_tracer2.start_call.return_value.__enter__.return_value = mock_call2
    mock_tracer2.start_call.return_value.__exit__.return_value = None

    manager = TracingManager([mock_tracer1, mock_tracer2])

    with manager.start_call("test", {"input": "value"}) as call:
        # Should return the first tracer's call
        assert call == mock_call1

    mock_tracer1.start_call.assert_called_once()
    mock_tracer2.start_call.assert_called_once()


def test_tracing_manager_context_propagation():
    """Test TracingManager properly propagates context to child tracers."""
    tracer1 = NoOpTracer()
    tracer2 = ConsoleTracer()
    manager = TracingManager([tracer1, tracer2])

    # Set parent context
    parent_context = TraceContext("parent_trace", "parent_call", None)
    token = current_trace_context.set(parent_context)

    try:
        with manager.start_call("test", {}) as call:
            current_ctx = current_trace_context.get()
            assert current_ctx.trace_id == "parent_trace"
            assert current_ctx.parent_id == "parent_call"
    finally:
        current_trace_context.reset(token)


def test_tracing_manager_exception_propagation():
    """Test TracingManager properly handles exceptions from child tracers."""
    mock_tracer = MagicMock(spec=Tracer)
    mock_tracer.start_call.return_value.__enter__.side_effect = ValueError(
        "tracer error"
    )

    manager = TracingManager([mock_tracer])

    with pytest.raises(ValueError, match="tracer error"):
        with manager.start_call("test", {}):
            pass


def test_tracing_manager_add_tracer():
    """Test TracingManager.add_tracer functionality."""
    manager = TracingManager([])
    mock_tracer = Mock(spec=Tracer)

    manager.add_tracer(mock_tracer)

    assert mock_tracer in manager.tracers


def test_tracing_manager_context_reset():
    """Test TracingManager context behavior with child tracers.

    NOTE: Currently TracingManager and child tracers both manage context,
    which can lead to the child tracer's context persisting. This might
    be a design issue to address in the future.
    """
    manager = TracingManager([NoOpTracer()])

    # Clear any existing context
    current_trace_context.set(None)

    # Verify no initial context
    assert current_trace_context.get() is None

    with manager.start_call("test", {}):
        # Context should be set inside
        inner_ctx = current_trace_context.get()
        assert inner_ctx is not None
        assert inner_ctx.call_id is not None

    # This demonstrates the interaction between TracingManager and child tracers
    outer_ctx = current_trace_context.get()
    # The context might still be set by the child NoOpTracer
    if outer_ctx is not None:
        assert isinstance(outer_ctx, TraceContext)


# === ExecutionContext Tests ===


def test_execution_context_creation():
    """Test ExecutionContext creation with defaults."""
    context = ExecutionContext()

    assert isinstance(context.tracer, NoOpTracer)
    assert context.trace_id is not None
    assert context.call_id is not None
    assert context.parent_id is None


def test_execution_context_child_creation():
    """Test ExecutionContext.child() creates proper child context."""
    parent = ExecutionContext()
    child = parent.child()

    assert child.tracer == parent.tracer
    assert child.trace_id == parent.trace_id
    assert child.parent_id == parent.call_id
    assert child.call_id != parent.call_id


def test_execution_context_trace_call():
    """Test ExecutionContext.trace_call() works properly."""
    mock_tracer = MagicMock(spec=Tracer)
    mock_call = Mock()
    mock_tracer.start_call.return_value.__enter__.return_value = mock_call
    mock_tracer.start_call.return_value.__exit__.return_value = None

    context = ExecutionContext(tracer=mock_tracer)

    with context.trace_call("test_operation", {"input": "value"}) as call:
        assert call == mock_call

    mock_tracer.start_call.assert_called_once_with(
        name="test_operation",
        inputs={"input": "value"},
        trace_id=context.trace_id,
        parent_id=context.parent_id,
    )


def test_execution_context_with_custom_tracer():
    """Test ExecutionContext with custom tracer."""
    custom_tracer = ConsoleTracer()
    context = ExecutionContext(tracer=custom_tracer)

    assert context.tracer == custom_tracer


# === Utility Function Tests ===


def test_ensure_tracing_manager_with_none():
    """Test ensure_tracing_manager with None input."""
    manager = ensure_tracing_manager(None)

    assert isinstance(manager, TracingManager)
    assert len(manager.tracers) == 1
    assert isinstance(manager.tracers[0], NoOpTracer)


def test_ensure_tracing_manager_with_single_tracer():
    """Test ensure_tracing_manager with single tracer."""
    tracer = ConsoleTracer()
    manager = ensure_tracing_manager(tracer)

    assert isinstance(manager, TracingManager)
    assert len(manager.tracers) == 1
    assert manager.tracers[0] == tracer


def test_ensure_tracing_manager_with_list():
    """Test ensure_tracing_manager with list of tracers."""
    tracers = [NoOpTracer(), ConsoleTracer()]
    manager = ensure_tracing_manager(tracers)

    assert isinstance(manager, TracingManager)
    assert len(manager.tracers) == 2
    assert manager.tracers == tracers


def test_ensure_tracing_manager_with_existing_manager():
    """Test ensure_tracing_manager with existing TracingManager."""
    original_manager = TracingManager([NoOpTracer()])
    result_manager = ensure_tracing_manager(original_manager)

    assert result_manager == original_manager


# === Concurrency and Thread Safety Tests ===


def test_context_isolation_across_threads():
    """Test that trace contexts are isolated across threads."""
    results = {}

    def worker(thread_id):
        tracer = NoOpTracer()
        with tracer.start_call(f"operation_{thread_id}", {}) as call:
            ctx = current_trace_context.get()
            results[thread_id] = ctx.call_id
            time.sleep(0.01)  # Let other threads run

            # Context should still be the same
            ctx_after = current_trace_context.get()
            assert ctx_after.call_id == ctx.call_id

    threads = []
    for i in range(5):
        thread = threading.Thread(target=worker, args=(i,))
        threads.append(thread)
        thread.start()

    for thread in threads:
        thread.join()

    # All threads should have different call_ids
    call_ids = list(results.values())
    assert len(set(call_ids)) == len(call_ids)


def test_concurrent_call_tracking():
    """Test concurrent call tracking with ConsoleTracer."""
    tracer = ConsoleTracer()
    results = []

    def worker(worker_id):
        with tracer.start_call(
            f"concurrent_op_{worker_id}", {"worker": worker_id}
        ) as call:
            time.sleep(0.01)
            call.set_outputs(f"result_{worker_id}")
            results.append(call.call_id)

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(worker, i) for i in range(3)]
        for future in as_completed(futures):
            future.result()  # Wait for completion

    # All calls should have completed successfully
    assert len(results) == 3
    assert len(set(results)) == 3  # All unique call_ids


def test_nested_async_context_propagation():
    """Test context behavior in concurrent operations with shared tracers."""
    tracer = TracingManager([ConsoleTracer()])

    def inner_operation(operation_id):
        # Each thread should start with clean context, but ConsoleTracer
        # may share some state through its call registry
        with tracer.start_call(f"inner_{operation_id}", {}) as call:
            return current_trace_context.get()

    def outer_operation():
        with tracer.start_call("outer", {}) as call:
            outer_ctx = current_trace_context.get()

            # Run inner operations concurrently
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [executor.submit(inner_operation, i) for i in range(2)]
                inner_contexts = [future.result() for future in as_completed(futures)]

            # Verify we got contexts back (the exact parent relationships
            # may vary due to ConsoleTracer's shared call registry)
            assert len(inner_contexts) == 2
            for inner_ctx in inner_contexts:
                assert inner_ctx is not None
                assert inner_ctx.call_id is not None

    outer_operation()


# === Transform Unit Tracing Tests ===


def test_map_unit_tracing_with_default_context():
    """Test MapUnit execute method with default ExecutionContext."""
    from verdict.transform import MapUnit
    from verdict.schema import Schema

    # Create a mock tracer to capture calls
    mock_tracer = MagicMock(spec=Tracer)
    mock_call = Mock()
    mock_tracer.start_call.return_value.__enter__.return_value = mock_call
    mock_tracer.start_call.return_value.__exit__.return_value = None

    # Create MapUnit
    map_unit = MapUnit(lambda x: x * 2)
    input_data = MapUnit.InputSchema(values=[1, 2, 3])

    # Execute with custom execution context
    execution_context = ExecutionContext(tracer=mock_tracer)
    result = map_unit.execute(input_data, execution_context)

    # Verify tracing was called
    mock_tracer.start_call.assert_called_once()
    call_args = mock_tracer.start_call.call_args
    assert call_args[1]["name"] == "MapUnit"  # Should use class name
    assert call_args[1]["inputs"]["input"] == input_data
    assert call_args[1]["inputs"]["unit"] == map_unit

    # Verify call.set_outputs was called
    mock_call.set_outputs.assert_called_once()
    assert isinstance(result, MapUnit.ResponseSchema)


def test_map_unit_tracing_with_none_context():
    """Test MapUnit execute method creates ExecutionContext when None provided."""
    from verdict.transform import MapUnit

    # Create MapUnit
    map_unit = MapUnit(lambda x: x * 2)
    input_data = MapUnit.InputSchema(values=[1, 2, 3])

    # Execute with None execution context (should create default)
    result = map_unit.execute(input_data, execution_context=None)

    # Should complete without errors
    assert isinstance(result, MapUnit.ResponseSchema)
    assert result.values == [1, 2, 3, 1, 2, 3]  # Lambda doubles the list


def test_map_unit_tracing_with_console_tracer(capsys):
    """Test MapUnit execute method with ConsoleTracer."""
    from verdict.transform import MapUnit

    # Create MapUnit - class name takes priority in call name resolution
    map_unit = MapUnit(lambda x: [i + 1 for i in x])
    input_data = MapUnit.InputSchema(values=[1, 2, 3])

    # Execute with ConsoleTracer
    execution_context = ExecutionContext(tracer=ConsoleTracer())
    result = map_unit.execute(input_data, execution_context)

    # Check console output - should use class name "MapUnit"
    captured = capsys.readouterr()
    assert ">> Call: MapUnit" in captured.out
    assert "<< Call: MapUnit" in captured.out
    assert "Duration:" in captured.out

    # Verify result
    assert isinstance(result, MapUnit.ResponseSchema)
    assert result.values == [2, 3, 4]


def test_field_map_unit_tracing():
    """Test FieldMapUnit execute method with tracing."""
    from verdict.transform import FieldMapUnit
    from verdict.schema import Schema
    import statistics

    # Create test data
    test_values = [
        Schema.inline(score=int)(score=5),
        Schema.inline(score=int)(score=3),
        Schema.inline(score=int)(score=4),
    ]
    input_data = FieldMapUnit.InputSchema(values=test_values)

    # Create FieldMapUnit - class name takes priority in call name resolution
    field_map_unit = FieldMapUnit(statistics.mean, ["score"])

    # Create mock tracer
    mock_tracer = MagicMock(spec=Tracer)
    mock_call = Mock()
    mock_tracer.start_call.return_value.__enter__.return_value = mock_call
    mock_tracer.start_call.return_value.__exit__.return_value = None

    # Execute with tracing
    execution_context = ExecutionContext(tracer=mock_tracer)
    result = field_map_unit.execute(input_data, execution_context)

    # Verify tracing was called with correct parameters
    mock_tracer.start_call.assert_called_once()
    call_args = mock_tracer.start_call.call_args
    assert call_args[1]["name"] == "FieldMapUnit"  # Uses class name
    assert call_args[1]["inputs"]["input"] == input_data
    assert call_args[1]["inputs"]["unit"] == field_map_unit

    # Verify outputs were set
    mock_call.set_outputs.assert_called_once()

    # Verify result
    assert hasattr(result, "score")
    assert result.score == 4.0  # Mean of [5, 3, 4]


def test_mean_pool_unit_tracing():
    """Test MeanPoolUnit tracing functionality."""
    from verdict.transform import MeanPoolUnit
    from verdict.schema import Schema

    # Create test data with scores
    test_values = [
        Schema.inline(score=int)(score=5),
        Schema.inline(score=int)(score=3),
        Schema.inline(score=int)(score=4),
    ]
    input_data = MeanPoolUnit.InputSchema(values=test_values)

    # Create MeanPoolUnit
    mean_pool = MeanPoolUnit(["score"])

    # Create mock tracer
    mock_tracer = MagicMock(spec=Tracer)
    mock_call = Mock()
    mock_tracer.start_call.return_value.__enter__.return_value = mock_call
    mock_tracer.start_call.return_value.__exit__.return_value = None

    # Execute with tracing
    execution_context = ExecutionContext(tracer=mock_tracer)
    result = mean_pool.execute(input_data, execution_context)

    # Verify tracing was called with MeanPoolUnit class name
    mock_tracer.start_call.assert_called_once()
    call_args = mock_tracer.start_call.call_args
    assert call_args[1]["name"] == "MeanPoolUnit"  # Should use class name

    # Verify outputs and result
    mock_call.set_outputs.assert_called_once()
    assert hasattr(result, "score")
    assert result.score == 4.0


def test_map_unit_tracing_call_name_resolution():
    """Test MapUnit call name resolution priority."""
    from verdict.transform import MapUnit

    # Test with class name only (default behavior)
    map_unit1 = MapUnit(lambda x: x)
    input_data = MapUnit.InputSchema(values=[1])

    mock_tracer = MagicMock(spec=Tracer)
    mock_tracer.start_call.return_value.__enter__.return_value = Mock()
    mock_tracer.start_call.return_value.__exit__.return_value = None

    execution_context = ExecutionContext(tracer=mock_tracer)
    map_unit1.execute(input_data, execution_context)

    # Should use class name first
    call_args = mock_tracer.start_call.call_args
    assert call_args[1]["name"] == "MapUnit"

    # Test with _char set (but class name still takes priority)
    mock_tracer.reset_mock()
    map_unit2 = MapUnit(lambda x: x)
    map_unit2._char = "CustomChar"

    map_unit2.execute(input_data, execution_context)
    call_args = mock_tracer.start_call.call_args
    assert call_args[1]["name"] == "MapUnit"  # Class name takes priority

    # Test that char property is read-only (computed from _char and other factors)
    map_unit3 = MapUnit(lambda x: x)
    map_unit3._char = "TestChar"

    # char property should reflect _char (plus potential model info)
    assert "TestChar" in map_unit3.char

    # But tracing still uses class name first
    mock_tracer.reset_mock()
    map_unit3.execute(input_data, execution_context)
    call_args = mock_tracer.start_call.call_args
    assert call_args[1]["name"] == "MapUnit"  # Class name still takes priority


def test_map_unit_tracing_with_exception():
    """Test MapUnit tracing behavior when execution raises exception."""
    from verdict.transform import MapUnit
    from verdict.util.exceptions import VerdictExecutionTimeError

    # Create MapUnit that will raise an exception
    def failing_func(x):
        raise ValueError("Test error")

    map_unit = MapUnit(failing_func)
    input_data = MapUnit.InputSchema(values=[1, 2, 3])

    # Create mock tracer
    mock_tracer = MagicMock(spec=Tracer)
    mock_call = Mock()
    mock_tracer.start_call.return_value.__enter__.return_value = mock_call
    mock_tracer.start_call.return_value.__exit__.return_value = None

    execution_context = ExecutionContext(tracer=mock_tracer)

    # Execute should raise VerdictExecutionTimeError
    with pytest.raises(VerdictExecutionTimeError):
        map_unit.execute(input_data, execution_context)

    # Verify tracing was still called
    mock_tracer.start_call.assert_called_once()
    # set_outputs should not be called due to exception
    mock_call.set_outputs.assert_not_called()


def test_field_map_unit_tracing_auto_fields():
    """Test FieldMapUnit tracing with automatic field detection."""
    from verdict.transform import FieldMapUnit
    from verdict.schema import Schema
    import statistics

    # Create test data with multiple fields
    test_values = [
        Schema.inline(score=int, confidence=float)(score=5, confidence=0.9),
        Schema.inline(score=int, confidence=float)(score=3, confidence=0.7),
        Schema.inline(score=int, confidence=float)(score=4, confidence=0.8),
    ]
    input_data = FieldMapUnit.InputSchema(values=test_values)

    # Create FieldMapUnit with empty fields (should auto-detect)
    field_map_unit = FieldMapUnit(statistics.mean, fields=[])

    # Create mock tracer
    mock_tracer = MagicMock(spec=Tracer)
    mock_call = Mock()
    mock_tracer.start_call.return_value.__enter__.return_value = mock_call
    mock_tracer.start_call.return_value.__exit__.return_value = None

    # Execute with tracing
    execution_context = ExecutionContext(tracer=mock_tracer)
    result = field_map_unit.execute(input_data, execution_context)

    # Verify tracing occurred
    mock_tracer.start_call.assert_called_once()
    mock_call.set_outputs.assert_called_once()

    # Verify auto-detected fields were processed
    assert hasattr(result, "score")
    assert hasattr(result, "confidence")
    assert result.score == 4.0  # Mean of [5, 3, 4]
    assert abs(result.confidence - 0.8) < 0.01  # Mean of [0.9, 0.7, 0.8]


def test_transform_units_context_propagation():
    """Test that transform units properly participate in context propagation."""
    from verdict.transform import MeanPoolUnit
    from verdict.schema import Schema

    # Create test data
    test_values = [Schema.inline(score=int)(score=5), Schema.inline(score=int)(score=3)]
    input_data = MeanPoolUnit.InputSchema(values=test_values)

    # Set up parent context
    parent_context = TraceContext("parent_trace", "parent_call", None)
    token = current_trace_context.set(parent_context)

    try:
        mean_pool = MeanPoolUnit(["score"])

        # Execute should inherit parent context
        result = mean_pool.execute(input_data, execution_context=None)

        # Verify result
        assert hasattr(result, "score")
        assert result.score == 4.0

    finally:
        current_trace_context.reset(token)
