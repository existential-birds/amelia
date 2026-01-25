# Distributed Tracing Design

**Issue:** #232
**Date:** 2026-01-25
**Status:** Draft

## Overview

Amelia lacks end-to-end tracing across agent interactions, making it hard to debug failures, identify bottlenecks, and understand workflow execution.

This design adds an optional, pluggable tracing layer that captures LangGraph node transitions and LLM calls, with Braintrust as the initial implementation.

## Goals

1. **Debugging failures** - Trace back through the full chain of events when something fails
2. **Performance optimization** - Identify which agent/tool is the bottleneck via latency breakdown
3. **Visibility** - Link from Amelia dashboard to external trace visualization

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Optional | Yes | Zero overhead when disabled; open-source users may not want/need tracing |
| Pluggable | `TracingProvider` protocol | Allows multiple backends without vendor lock-in |
| Initial implementation | Braintrust only | YAGNI - add others when needed |
| Configuration scope | Server-level | Tracing is infrastructure config, not workflow-specific |
| Trace depth | Nodes + LLM calls | Good debugging power without over-instrumenting |
| Dashboard integration | Link to external | Avoid building duplicate visualization |
| Context propagation | `contextvars` | No manual span threading through call stack |

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Amelia Server                        │
│  ┌───────────────────────────────────────────────────┐  │
│  │              OrchestratorService                  │  │
│  │  ┌─────────────────────────────────────────────┐  │  │
│  │  │           LangGraph Pipeline                │  │  │
│  │  │   architect → validator → developer → ...   │  │  │
│  │  └──────────────────┬──────────────────────────┘  │  │
│  │                     │                             │  │
│  │  ┌──────────────────▼──────────────────────────┐  │  │
│  │  │       TracingProvider Protocol              │  │  │
│  │  │                                             │  │  │
│  │  │   None (disabled)  │  BraintrustTracing     │  │  │
│  │  └─────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

## Configuration

Two environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `AMELIA_TRACING_PROVIDER` | `None` | Tracing backend: `braintrust`; use `none` or unset to disable |
| `AMELIA_TRACING_API_KEY` | `None` | API key for the tracing provider |

Example:

```bash
export AMELIA_TRACING_PROVIDER=braintrust
export AMELIA_TRACING_API_KEY=sk-xxx
uv run amelia serve
```

## Implementation Details

### TracingProvider Protocol

Located at `amelia/ext/tracing/__init__.py`:

```python
from typing import Protocol, Any, runtime_checkable
from contextlib import contextmanager
from dataclasses import dataclass

@dataclass
class SpanContext:
    """Opaque context returned by start_span, passed to end_span."""
    trace_id: str
    span_id: str
    provider_data: Any = None

@runtime_checkable
class TracingProvider(Protocol):
    """Protocol for distributed tracing backends."""

    def configure(self, api_key: str) -> None:
        """Initialize the provider with credentials."""
        ...

    def start_trace(self, workflow_id: str, metadata: dict[str, Any]) -> SpanContext:
        """Start a new trace for a workflow. Returns root span context."""
        ...

    def start_span(
        self,
        name: str,
        parent: SpanContext | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SpanContext:
        """Start a child span within a trace."""
        ...

    def end_span(self, ctx: SpanContext, output: Any = None, error: str | None = None) -> None:
        """End a span, recording output or error."""
        ...

    def get_trace_url(self, ctx: SpanContext) -> str | None:
        """Return URL to view this trace in the provider's dashboard."""
        ...

    def get_langchain_callback(self) -> Any | None:
        """Return a LangChain callback handler for automatic instrumentation."""
        ...

    @contextmanager
    def span(self, name: str, metadata: dict[str, Any] | None = None):
        """Context manager that auto-parents to current span and sets context."""
        ...
```

### Context Propagation

Located at `amelia/ext/tracing/context.py`:

```python
from contextvars import ContextVar
from amelia.ext.tracing import SpanContext

_current_span: ContextVar[SpanContext | None] = ContextVar("current_span", default=None)

def get_current_span() -> SpanContext | None:
    return _current_span.get()

def set_current_span(ctx: SpanContext | None) -> None:
    _current_span.set(ctx)
```

### Factory

Located at `amelia/ext/tracing/factory.py`:

```python
from amelia.ext.tracing import TracingProvider

def create_tracing_provider(provider: str | None, api_key: str | None) -> TracingProvider | None:
    """Create tracing provider based on configuration. Returns None if disabled."""
    if not provider or provider == "none" or not api_key:
        return None

    if provider == "braintrust":
        from amelia.ext.tracing.braintrust import BraintrustTracingProvider
        p = BraintrustTracingProvider()
        p.configure(api_key=api_key)
        return p

    raise ValueError(f"Unknown tracing provider: {provider}")
```

### Braintrust Implementation

Located at `amelia/ext/tracing/braintrust.py`:

```python
from typing import Any
from contextlib import contextmanager

from braintrust import init_logger
from braintrust_langchain import BraintrustCallbackHandler

from amelia.ext.tracing import SpanContext
from amelia.ext.tracing.context import get_current_span, set_current_span


class BraintrustTracingProvider:
    """Braintrust implementation of TracingProvider."""

    def __init__(self) -> None:
        self._logger: Any = None
        self._callback_handler: BraintrustCallbackHandler | None = None

    def configure(self, api_key: str) -> None:
        self._logger = init_logger(
            project="amelia",
            api_key=api_key,
        )
        self._callback_handler = BraintrustCallbackHandler()

    def start_trace(self, workflow_id: str, metadata: dict[str, Any]) -> SpanContext:
        span = self._logger.start_span(
            name=f"workflow:{workflow_id}",
            **metadata,
        )
        ctx = SpanContext(trace_id=span.id, span_id=span.id, provider_data=span)
        set_current_span(ctx)
        return ctx

    def start_span(
        self,
        name: str,
        parent: SpanContext | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SpanContext:
        resolved_parent = parent or get_current_span()
        if resolved_parent is not None:
            parent_provider = resolved_parent.provider_data
            span = parent_provider.start_span(name=name, **(metadata or {}))
        else:
            # No parent context available - start a new root span
            span = self._logger.start_span(name=name, **(metadata or {}))
        return SpanContext(
            trace_id=resolved_parent.trace_id if resolved_parent else span.id,
            span_id=span.id,
            provider_data=span,
        )

    def end_span(self, ctx: SpanContext, output: Any = None, error: str | None = None) -> None:
        if output is not None:
            ctx.provider_data.log(output=output)
        if error is not None:
            ctx.provider_data.log(error=error)
        ctx.provider_data.end()

    def get_trace_url(self, ctx: SpanContext) -> str | None:
        return f"https://www.braintrust.dev/app/project/traces/{ctx.trace_id}"

    def get_langchain_callback(self) -> BraintrustCallbackHandler | None:
        return self._callback_handler

    @contextmanager
    def span(self, name: str, metadata: dict[str, Any] | None = None):
        """Context manager that auto-parents to current span and sets context."""
        parent = get_current_span()
        ctx = self.start_span(name, parent=parent, metadata=metadata)
        set_current_span(ctx)
        try:
            yield ctx
        except Exception as e:
            self.end_span(ctx, error=str(e))
            raise
        else:
            self.end_span(ctx)
        finally:
            set_current_span(parent)
```

### Server Configuration

In `amelia/server/config.py`:

```python
class ServerSettings(BaseSettings):
    # ... existing fields ...

    # Tracing (optional)
    tracing_provider: str | None = None
    tracing_api_key: str | None = None
```

### Orchestrator Integration

In `amelia/server/orchestrator/service.py`:

```python
from amelia.ext.tracing.factory import create_tracing_provider

class OrchestratorService:
    def __init__(self, ...):
        # ... existing init ...
        self._tracing = create_tracing_provider(
            settings.tracing_provider,
            settings.tracing_api_key,
        )

    async def _run_workflow(self, workflow_id: str, state: ImplementationState, ...):
        trace_ctx = None
        if self._tracing:
            trace_ctx = self._tracing.start_trace(workflow_id, {
                "issue_key": state.issue.key,
                "profile": state.profile.name,
            })
            await self._update_workflow(workflow_id, trace_url=self._tracing.get_trace_url(trace_ctx))

        callbacks = []
        if self._tracing and (cb := self._tracing.get_langchain_callback()):
            callbacks.append(cb)

        config = RunnableConfig(
            configurable={"workflow_id": workflow_id, ...},
            callbacks=callbacks,
        )

        try:
            async for event in graph.astream(state, config=config):
                await self._handle_graph_event(event, workflow_id)
        finally:
            if self._tracing and trace_ctx:
                self._tracing.end_span(trace_ctx)
```

### Driver Instrumentation

In `amelia/drivers/api/deepagents.py`:

```python
class ApiDriver:
    async def generate(self, prompt: str, **kwargs) -> GenerateResult:
        if not self._tracing:
            return await self._agent.run(prompt, **kwargs)

        with self._tracing.span(f"llm:{self._model}", {"prompt_len": len(prompt)}):
            return await self._agent.run(prompt, **kwargs)
```

### Dashboard Link

Add `trace_url` field to `amelia/server/models/state.py`:

```python
class WorkflowState:
    # ... existing fields ...
    trace_url: str | None = None
```

In `dashboard/src/components/WorkflowDetail.tsx`:

```tsx
{workflow.trace_url && (
  <a
    href={workflow.trace_url}
    target="_blank"
    rel="noopener noreferrer"
    className="text-sm text-blue-500 hover:underline flex items-center gap-1"
  >
    <ExternalLinkIcon className="w-4 h-4" />
    View trace
  </a>
)}
```

### Dependencies

In `pyproject.toml`:

```toml
[project.optional-dependencies]
tracing-braintrust = [
    "braintrust>=0.5.0",
    "braintrust-langchain>=0.2.1",
]
```

## Files Changed

| File | Change |
|------|--------|
| `amelia/ext/tracing/__init__.py` | New: `TracingProvider` protocol, `SpanContext` dataclass |
| `amelia/ext/tracing/context.py` | New: `contextvars` for current span |
| `amelia/ext/tracing/factory.py` | New: `create_tracing_provider()` |
| `amelia/ext/tracing/braintrust.py` | New: Braintrust implementation |
| `amelia/server/config.py` | Add `tracing_provider`, `tracing_api_key` |
| `amelia/server/orchestrator/service.py` | Initialize tracing, pass callbacks |
| `amelia/drivers/api/deepagents.py` | LLM call spans |
| `amelia/server/models/state.py` | Add `trace_url` field |
| `dashboard/src/components/WorkflowDetail.tsx` | "View trace" link |
| `pyproject.toml` | Optional `tracing-braintrust` dependency |

## Testing

1. **Unit tests** for `TracingProvider` protocol compliance
2. **Unit tests** for factory with valid/invalid/missing config
3. **Integration test** with mock Braintrust API
4. **Manual test** with real Braintrust account

## Future Considerations

- Additional providers (Langfuse, OpenTelemetry) when requested
- Per-profile tracing configuration if needed
- Tool-level tracing (Phase 2)
- Configurable project name if users need it
