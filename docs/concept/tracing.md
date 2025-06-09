---
label: "Tracing"
order: 15
---


<!-- TODO: Add Weave Tracing and cookbook docs here -->

Verdict provides a flexible tracing infrastructure for observing pipeline execution, debugging LLM calls, and measuring performance. Tracers are thread-safe and can be combined to send traces to multiple destinations simultaneously.

```python
from verdict import Pipeline, Layer
from verdict.common.judge import JudgeUnit
from verdict.util.tracing import ConsoleTracer
from verdict.schema import Schema

# Enable detailed execution tracing
pipeline = Pipeline(tracer=ConsoleTracer())
pipeline = pipeline >> JudgeUnit().prompt("Rate this: {source.text}")

# Execution traces will show hierarchical call structure
response = pipeline.run(Schema.of(text="Hello world"))
```

## Usage
### Basic Console Tracing
The simplest way to observe pipeline execution is with `ConsoleTracer`:

```python
from verdict import Pipeline, Layer
from verdict.common.judge import JudgeUnit
from verdict.transform import MeanPoolUnit
from verdict.util.tracing import ConsoleTracer
from verdict.schema import Schema

# Create pipeline with console tracing
tracer = ConsoleTracer()
pipeline = Pipeline(tracer=tracer)

# Traces show nested execution with timing
pipeline = pipeline \
    >> Layer([JudgeUnit(), JudgeUnit()], 2) \
    >> MeanPoolUnit()

# Create a simple dataset for demonstration
dataset_schema = Schema.of(text="Sample text for processing")
response = pipeline.run(dataset_schema)
```

Output shows hierarchical execution structure:
```
>> Call: Pipeline | trace_id=abc123 | Inputs: {...}
  >> Call: Layer | parent_id=abc123 | Inputs: {...}
    >> Call: JudgeUnit | Duration: 0.234s
    >> Call: JudgeUnit | Duration: 0.187s
  << Call: Layer | Duration: 0.456s
<< Call: Pipeline | Duration: 0.523s
```

### Multiple Tracers
Combine multiple tracers to send traces to different destinations:

```python
from verdict import Pipeline
from verdict.util.tracing import ConsoleTracer, NoOpTracer

console_tracer = ConsoleTracer()
custom_tracer = NoOpTracer()  # Replace with your custom implementation

pipeline = Pipeline(tracer=[console_tracer, custom_tracer])
```

### Performance Monitoring
Create custom tracers for specific monitoring needs:

```python
from verdict import Pipeline
from verdict.common.judge import JudgeUnit
from verdict.util.tracing import Tracer, Call
from verdict.schema import Schema
from contextlib import contextmanager

class PerformanceTracer(Tracer):
    @contextmanager
    def start_call(self, name, inputs, trace_id=None, parent_id=None):
        call = Call(name, inputs, trace_id=trace_id, parent_id=parent_id)
        
        with call:
            yield call
        
        # Log slow operations
        if call.duration and call.duration > 1.0:
            print(f"⚠️  Slow: {name} took {call.duration:.2f}s")

pipeline = Pipeline(tracer=PerformanceTracer())
pipeline = pipeline >> JudgeUnit().prompt("Evaluate: {source.text}")
response = pipeline.run(Schema.of(text="Sample input"))
```

## Anatomy of Tracing
### Core Components
Verdict's tracing system consists of three main components:

- **`TraceContext`**: Stores trace metadata (`trace_id`, `call_id`, `parent_id`)
- **`Call`**: Represents a single traced operation with timing and I/O
- **`Tracer`**: Context manager that handles trace collection and output

### Context Propagation
Trace context flows automatically through nested calls using Python's `contextvars`:

```python
# Each pipeline execution gets isolated trace context
# Child calls inherit parent context automatically
# Thread-safe for concurrent execution
```

### Built-in Tracers

{.compact}
|           Tracer | Description                                | Use Case                     |
| ---------------: | ------------------------------------------ | ---------------------------- |
|     `NoOpTracer` | Context propagation only, minimal overhead | Testing environments         |
|  `ConsoleTracer` | Detailed console output with indentation   | Development and debugging    |
| `TracingManager` | Coordinates multiple tracers               | Complex observability setups |

## Custom Tracer Implementation
Subclass `Tracer` to create custom tracing behavior:

```python
from verdict.util.tracing import Tracer, Call, current_trace_context, TraceContext
from contextlib import contextmanager

class MyCustomTracer(Tracer):
    @contextmanager
    def start_call(self, name, inputs, trace_id=None, parent_id=None):
        # Inherit context from parent
        parent_ctx = current_trace_context.get()
        if parent_id is None and parent_ctx:
            parent_id = parent_ctx.call_id
        if trace_id is None and parent_ctx:
            trace_id = parent_ctx.trace_id
        
        # Create and time the call
        call = Call(name, inputs, trace_id=trace_id, parent_id=parent_id)
        
        # Set trace context
        token = current_trace_context.set(
            TraceContext(trace_id, call.call_id, parent_id)
        )
        
        try:
            with call:  # Automatically times the operation
                yield call
        finally:
            current_trace_context.reset(token)
```

### Subclass Checklist

|            Component | Required? | Description                              |
| -------------------: | :-------: | ---------------------------------------- |
|       **start_call** |     ✅     | Context manager for tracing operations   |
| **Context handling** |     ✅     | Manage `current_trace_context` properly  |
|    **Thread safety** |     ✅     | Use appropriate locking for shared state |

## Runtime Configuration
Tracers can be added or modified at runtime:

```python
from verdict import Pipeline
from verdict.common.judge import JudgeUnit
from verdict.util.tracing import ConsoleTracer, Tracer, Call
from verdict.schema import Schema
from contextlib import contextmanager

# Define the PerformanceTracer class first
class PerformanceTracer(Tracer):
    @contextmanager
    def start_call(self, name, inputs, trace_id=None, parent_id=None):
        call = Call(name, inputs, trace_id=trace_id, parent_id=parent_id)
        
        with call:
            yield call
        
        # Log slow operations
        if call.duration and call.duration > 1.0:
            print(f"⚠️  Slow: {name} took {call.duration:.2f}s")

pipeline = Pipeline()  # Starts with NoOpTracer
pipeline = pipeline >> JudgeUnit().prompt("Evaluate: {source.text}")

# Override tracer for specific runs
response = pipeline.run(Schema.of(text="Sample data"), tracers=ConsoleTracer())

# Add permanent tracer
pipeline.add_tracer(PerformanceTracer())
``` 