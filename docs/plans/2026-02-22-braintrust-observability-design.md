# Braintrust Observability Integration

**Date**: 2026-02-22
**Issue**: #234 (Observability Metrics Foundation)
**Status**: Design approved

## Goal

Add optional Braintrust integration for tracing and observability across all Amelia drivers. When `BRAINTRUST_API_KEY` is set, all workflow executions produce hierarchical traces in Braintrust. When absent, everything functions as normal with zero overhead.

Scoring deferred to a follow-up.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Amelia Orchestrator                   │
│                                                         │
│  ┌───────────────────────────────────────────────────┐  │
│  │ BraintrustTracer                                  │  │
│  │  - Subscribes to EventBus                         │  │
│  │  - Creates workflow root span on WORKFLOW_STARTED  │  │
│  │  - Creates agent child spans on STAGE_STARTED     │  │
│  │  - Annotates spans with event metadata            │  │
│  │  - Closes spans on STAGE_COMPLETED/WORKFLOW_*     │  │
│  └──────────┬────────────────────────────────────────┘  │
│             │ passes span IDs to drivers                │
│  ┌──────────▼────────────────────────────────────────┐  │
│  │ Driver Layer                                      │  │
│  │                                                   │  │
│  │  Claude CLI → CC_PARENT_SPAN_ID env var           │  │
│  │    (trace-claude-code plugin handles LLM detail)  │  │
│  │                                                   │  │
│  │  API → Braintrust LangChain callback handler      │  │
│  │    (or proxy with x-bt-parent header)             │  │
│  │                                                   │  │
│  │  Codex CLI → env vars for Braintrust tracing      │  │
│  │                                                   │  │
│  │  Container → Amelia proxy adds x-bt-parent        │  │
│  │    (worker and sandbox image unchanged)            │  │
│  └───────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────┐
│  Braintrust.dev  │  Unified trace view:
│                  │  Workflow → Agent → LLM calls
└─────────────────┘
```

Amelia owns the workflow-level trace hierarchy (workflow, agent stages, tasks). Braintrust's native integrations own LLM-level detail within each agent stage. The `BraintrustTracer` bridges them by passing parent span IDs.

## Configuration

| Env Var | Required | Purpose |
|---------|----------|---------|
| `BRAINTRUST_API_KEY` | No | Enables integration when present |
| `BRAINTRUST_PROJECT` | No | Project name (defaults to `"amelia"`) |

Activation: on server startup, check `BRAINTRUST_API_KEY`. If set, instantiate `BraintrustTracer` and subscribe to EventBus. If absent, nothing is instantiated.

`braintrust` is an optional dependency:

```toml
[project.optional-dependencies]
braintrust = ["braintrust"]
```

Lazy import at runtime:

```python
try:
    import braintrust
except ImportError:
    braintrust = None
```

If `BRAINTRUST_API_KEY` is set but the package isn't installed, log a warning and continue without tracing.

## BraintrustTracer (EventBus Subscriber)

New file: `amelia/ext/braintrust.py`

Core class that subscribes to the EventBus and maps `WorkflowEvent`s to Braintrust spans:

```python
class BraintrustTracer:
    def __init__(self, api_key: str, project: str = "amelia"):
        self._logger = braintrust.init_logger(project=project, api_key=api_key)
        self._workflow_spans: dict[UUID, Span] = {}
        self._stage_spans: dict[tuple[UUID, str], Span] = {}

    def on_event(self, event: WorkflowEvent) -> None:
        """EventBus callback. Must be non-blocking."""
        match event.event_type:
            case EventType.WORKFLOW_STARTED:
                span = self._logger.start_span(name="workflow", ...)
                self._workflow_spans[event.workflow_id] = span
            case EventType.STAGE_STARTED:
                parent = self._workflow_spans.get(event.workflow_id)
                span = parent.start_span(name=event.agent, ...)
                self._stage_spans[(event.workflow_id, event.agent)] = span
            case EventType.STAGE_COMPLETED:
                span = self._stage_spans.pop(...)
                span.log(output=event.data); span.end()
            case EventType.WORKFLOW_COMPLETED | EventType.WORKFLOW_FAILED:
                span = self._workflow_spans.pop(...)
                span.log(output={"status": ...}); span.end()
            case EventType.CLAUDE_TOOL_CALL | EventType.CLAUDE_TOOL_RESULT:
                # Annotate active stage span with tool metadata
                ...
```

The `on_event` callback is synchronous and non-blocking, matching the `EventBus.emit()` contract. Braintrust SDK batches and flushes asynchronously.

### Span ID Access

The tracer exposes a method for drivers to retrieve the current stage span ID:

```python
def get_parent_span_id(self, workflow_id: UUID, agent: str) -> str | None:
    span = self._stage_spans.get((workflow_id, agent))
    return span.id if span else None

def get_root_span_id(self, workflow_id: UUID) -> str | None:
    span = self._workflow_spans.get(workflow_id)
    return span.id if span else None
```

## Driver Integration

### Claude CLI Driver

When Braintrust is enabled and the `trace-claude-code` plugin is installed, pass span context as env vars to the Claude Code subprocess:

- `CC_PARENT_SPAN_ID` = stage span ID
- `CC_ROOT_SPAN_ID` = workflow root span ID
- `BRAINTRUST_API_KEY` = from server config
- `BRAINTRUST_CC_PROJECT` = project name

The `trace-claude-code` plugin nests its session/turn/tool spans under these parents.

### API Driver (Direct)

Use the Braintrust LangChain callback handler for automatic tracing:

```python
from braintrust_langchain import BraintrustCallbackHandler
handler = BraintrustCallbackHandler(parent=stage_span)
# Pass to LangChain invoke calls
```

Alternative: route through Braintrust proxy (`api.braintrust.dev/v1/proxy`) with `x-bt-parent` header.

### Codex CLI Driver

Pass `BRAINTRUST_API_KEY` as env var to the Codex subprocess. Investigate Codex support for parent span mechanisms similar to Claude Code's `CC_PARENT_SPAN_ID`.

### Container Driver (Sandbox)

The sandbox worker routes LLM calls through Amelia's proxy (`http://host.docker.internal:{port}/proxy/v1`). When Braintrust is enabled:

1. The Amelia proxy replaces the provider `base_url` with `https://api.braintrust.dev/v1/proxy`
2. Uses `BRAINTRUST_API_KEY` for authentication (Braintrust resolves provider credentials)
3. Adds `x-bt-parent` header with the active stage span ID

The container image and worker code stay unchanged. Tracing happens at the proxy layer.

## Trace Hierarchy

| Event | Braintrust Span | Data Logged |
|-------|----------------|-------------|
| `WORKFLOW_STARTED` | Root span | issue_id, workflow_id, profile |
| `STAGE_STARTED` | Child of workflow | agent name, stage |
| `STAGE_COMPLETED` | End stage span | output summary, duration |
| `CLAUDE_TOOL_CALL` | Metadata on stage span | tool_name, tool_input |
| `CLAUDE_TOOL_RESULT` | Metadata on stage span | tool_output, is_error |
| `TASK_STARTED/COMPLETED` | Metadata on stage span | task_index, total_tasks |
| `WORKFLOW_COMPLETED` | End root span | status, token usage |
| `WORKFLOW_FAILED` | End root span | failure_reason, error |

Native driver integrations add LLM-level detail (request/response bodies, token counts, per-call latency) as child spans beneath the stage spans.

## Error Handling

Every Braintrust interaction is wrapped to swallow errors:

```python
try:
    span.log(...)
except Exception:
    logger.warning("Braintrust tracing failed", exc_info=True)
```

- **Import failure**: caught at startup, logged, integration disabled
- **Invalid API key**: first call fails, logged, tracer deactivates
- **Network errors**: Braintrust SDK retries internally; failures caught and ignored
- **EventBus contract**: `on_event` never raises, never blocks

## File Changes

| File | Change |
|------|--------|
| `pyproject.toml` | Add `braintrust` optional dependency |
| `amelia/ext/braintrust.py` | New — `BraintrustTracer` class |
| `amelia/server/main.py` | Conditionally instantiate tracer, subscribe to EventBus |
| `amelia/server/config.py` | Add `braintrust_api_key` and `braintrust_project` to `ServerConfig` |
| `amelia/drivers/cli/claude.py` | Pass `CC_PARENT_SPAN_ID`/`CC_ROOT_SPAN_ID` env vars |
| `amelia/drivers/cli/codex.py` | Pass Braintrust env vars |
| `amelia/drivers/api/deepagents.py` | Add Braintrust callback handler option |
| `amelia/server/main.py` (proxy) | Conditional Braintrust proxy routing |

## Future Work (Deferred)

- **Online scoring**: Add Braintrust scorers for task completion, cost efficiency, trajectory adherence
- **Evals integration**: Use Braintrust evals framework to benchmark agent quality
- **Dashboard integration**: Surface Braintrust trace links in Amelia's dashboard
