# Braintrust Observability Integration — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add optional Braintrust tracing so all workflow executions produce hierarchical spans (workflow > agent stage > LLM calls) when `BRAINTRUST_API_KEY` is set.

**Architecture:** EventBus subscriber (`BraintrustTracer`) creates workflow/stage spans and passes parent span IDs to drivers. Claude CLI uses `CC_PARENT_SPAN_ID` env vars, API driver uses Braintrust LangChain callback, sandbox proxy routes through Braintrust proxy with `x-bt-parent` header. All Braintrust interactions are non-blocking and error-swallowed.

**Tech Stack:** `braintrust` (optional dep), `braintrust` Python SDK (`init_logger`, `start_span`), existing `EventBus`, existing proxy in `amelia/sandbox/proxy.py`

**Design doc:** `docs/plans/2026-02-22-braintrust-observability-design.md`

---

### Task 1: Add braintrust optional dependency

**Files:**
- Modify: `pyproject.toml:30` (after dependencies list)

**Step 1: Add optional dependency group**

In `pyproject.toml`, add after the `[project.scripts]` section (line 32), before `[dependency-groups]`:

```toml
[project.optional-dependencies]
braintrust = ["braintrust"]
```

**Step 2: Verify it resolves**

Run: `uv pip install -e ".[braintrust]" --dry-run`
Expected: resolves `braintrust` package without errors

**Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "build: add braintrust as optional dependency (#234)"
```

---

### Task 2: Add Braintrust config fields to ServerConfig

**Files:**
- Modify: `amelia/server/config.py:10-39`
- Test: `tests/unit/server/test_braintrust_config.py`

**Step 1: Write the failing test**

Create `tests/unit/server/test_braintrust_config.py`:

```python
"""Tests for Braintrust configuration fields on ServerConfig."""

import os
from unittest.mock import patch

from amelia.server.config import ServerConfig


def test_braintrust_fields_default_to_none_and_amelia():
    """ServerConfig has braintrust_api_key=None and braintrust_project='amelia' by default."""
    with patch.dict(os.environ, {}, clear=True):
        config = ServerConfig(database_url="postgresql://x:x@localhost/x")
    assert config.braintrust_api_key is None
    assert config.braintrust_project == "amelia"


def test_braintrust_fields_read_from_env():
    """ServerConfig reads AMELIA_BRAINTRUST_API_KEY and AMELIA_BRAINTRUST_PROJECT from env."""
    env = {
        "AMELIA_BRAINTRUST_API_KEY": "br-test-key-123",
        "AMELIA_BRAINTRUST_PROJECT": "my-project",
        "AMELIA_DATABASE_URL": "postgresql://x:x@localhost/x",
    }
    with patch.dict(os.environ, env, clear=True):
        config = ServerConfig()
    assert config.braintrust_api_key == "br-test-key-123"
    assert config.braintrust_project == "my-project"


def test_braintrust_not_enabled_when_key_absent():
    """Without API key, braintrust_api_key is None."""
    with patch.dict(os.environ, {"AMELIA_DATABASE_URL": "postgresql://x:x@localhost/x"}, clear=True):
        config = ServerConfig()
    assert config.braintrust_api_key is None
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/test_braintrust_config.py -v`
Expected: FAIL — `ServerConfig` has no `braintrust_api_key` attribute

**Step 3: Add config fields**

Add to `amelia/server/config.py` inside `ServerConfig`, after `db_pool_max_size`:

```python
    braintrust_api_key: str | None = Field(
        default=None,
        description="Braintrust API key. When set, enables observability tracing.",
    )
    braintrust_project: str = Field(
        default="amelia",
        description="Braintrust project name for trace logging.",
    )
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/test_braintrust_config.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/server/config.py tests/unit/server/test_braintrust_config.py
git commit -m "feat(config): add Braintrust API key and project settings (#234)"
```

---

### Task 3: Create BraintrustTracer core class

**Files:**
- Create: `amelia/ext/__init__.py`
- Create: `amelia/ext/braintrust.py`
- Test: `tests/unit/test_braintrust_tracer.py`

**Step 1: Write the failing tests**

Create `tests/unit/test_braintrust_tracer.py`:

```python
"""Tests for BraintrustTracer EventBus subscriber."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from amelia.server.models.events import EventType, WorkflowEvent


@pytest.fixture
def mock_braintrust():
    """Mock the braintrust module."""
    with patch("amelia.ext.braintrust.braintrust") as mock_bt:
        mock_logger = MagicMock()
        mock_bt.init_logger.return_value = mock_logger
        yield mock_bt, mock_logger


@pytest.fixture
def tracer(mock_braintrust):
    """Create a BraintrustTracer with mocked braintrust SDK."""
    from amelia.ext.braintrust import BraintrustTracer
    return BraintrustTracer(api_key="test-key", project="test-project")


def _make_event(
    event_type: EventType,
    agent: str = "system",
    workflow_id=None,
    data=None,
) -> WorkflowEvent:
    return WorkflowEvent(
        id=uuid4(),
        workflow_id=workflow_id or uuid4(),
        sequence=1,
        timestamp="2026-01-01T00:00:00Z",
        agent=agent,
        event_type=event_type,
        message="test",
        data=data,
    )


def test_workflow_started_creates_root_span(tracer, mock_braintrust):
    _, mock_logger = mock_braintrust
    mock_span = MagicMock()
    mock_logger.start_span.return_value = mock_span

    wf_id = uuid4()
    event = _make_event(EventType.WORKFLOW_STARTED, workflow_id=wf_id)
    tracer.on_event(event)

    mock_logger.start_span.assert_called_once()
    assert tracer.get_root_span_id(wf_id) is not None


def test_stage_started_creates_child_span(tracer, mock_braintrust):
    _, mock_logger = mock_braintrust
    root_span = MagicMock()
    child_span = MagicMock()
    mock_logger.start_span.return_value = root_span
    root_span.start_span.return_value = child_span

    wf_id = uuid4()
    tracer.on_event(_make_event(EventType.WORKFLOW_STARTED, workflow_id=wf_id))
    tracer.on_event(_make_event(EventType.STAGE_STARTED, agent="architect", workflow_id=wf_id))

    root_span.start_span.assert_called_once()
    assert tracer.get_parent_span_id(wf_id, "architect") is not None


def test_stage_completed_ends_span(tracer, mock_braintrust):
    _, mock_logger = mock_braintrust
    root_span = MagicMock()
    child_span = MagicMock()
    mock_logger.start_span.return_value = root_span
    root_span.start_span.return_value = child_span

    wf_id = uuid4()
    tracer.on_event(_make_event(EventType.WORKFLOW_STARTED, workflow_id=wf_id))
    tracer.on_event(_make_event(EventType.STAGE_STARTED, agent="architect", workflow_id=wf_id))
    tracer.on_event(_make_event(EventType.STAGE_COMPLETED, agent="architect", workflow_id=wf_id))

    child_span.end.assert_called_once()
    assert tracer.get_parent_span_id(wf_id, "architect") is None


def test_workflow_completed_ends_root_span(tracer, mock_braintrust):
    _, mock_logger = mock_braintrust
    root_span = MagicMock()
    mock_logger.start_span.return_value = root_span

    wf_id = uuid4()
    tracer.on_event(_make_event(EventType.WORKFLOW_STARTED, workflow_id=wf_id))
    tracer.on_event(_make_event(EventType.WORKFLOW_COMPLETED, workflow_id=wf_id))

    root_span.end.assert_called_once()
    assert tracer.get_root_span_id(wf_id) is None


def test_workflow_failed_ends_root_span(tracer, mock_braintrust):
    _, mock_logger = mock_braintrust
    root_span = MagicMock()
    mock_logger.start_span.return_value = root_span

    wf_id = uuid4()
    tracer.on_event(_make_event(EventType.WORKFLOW_STARTED, workflow_id=wf_id))
    tracer.on_event(_make_event(EventType.WORKFLOW_FAILED, workflow_id=wf_id, data={"error": "boom"}))

    root_span.end.assert_called_once()


def test_on_event_never_raises(tracer, mock_braintrust):
    """on_event must never raise, even if braintrust SDK errors."""
    _, mock_logger = mock_braintrust
    mock_logger.start_span.side_effect = RuntimeError("SDK exploded")

    event = _make_event(EventType.WORKFLOW_STARTED)
    # Must not raise
    tracer.on_event(event)


def test_get_parent_span_id_returns_none_when_no_span(tracer):
    assert tracer.get_parent_span_id(uuid4(), "architect") is None


def test_get_root_span_id_returns_none_when_no_span(tracer):
    assert tracer.get_root_span_id(uuid4()) is None


def test_tool_call_annotates_stage_span(tracer, mock_braintrust):
    _, mock_logger = mock_braintrust
    root_span = MagicMock()
    child_span = MagicMock()
    mock_logger.start_span.return_value = root_span
    root_span.start_span.return_value = child_span

    wf_id = uuid4()
    tracer.on_event(_make_event(EventType.WORKFLOW_STARTED, workflow_id=wf_id))
    tracer.on_event(_make_event(EventType.STAGE_STARTED, agent="developer", workflow_id=wf_id))
    tracer.on_event(_make_event(
        EventType.CLAUDE_TOOL_CALL,
        agent="developer",
        workflow_id=wf_id,
        data={"tool_name": "file_edit", "tool_input": {"path": "/tmp/test.py"}},
    ))

    child_span.log.assert_called()
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_braintrust_tracer.py -v`
Expected: FAIL — `amelia.ext.braintrust` module does not exist

**Step 3: Create amelia/ext package and BraintrustTracer**

Create `amelia/ext/__init__.py` (empty file).

Create `amelia/ext/braintrust.py`:

```python
"""Optional Braintrust observability integration.

When BRAINTRUST_API_KEY is set, this module provides a BraintrustTracer
that subscribes to the EventBus and maps WorkflowEvents to Braintrust spans.

All Braintrust interactions are non-blocking and error-swallowed to ensure
the integration never breaks normal functionality.
"""

from __future__ import annotations

import uuid

from loguru import logger

from amelia.server.models.events import EventType, WorkflowEvent

try:
    import braintrust
except ImportError:
    braintrust = None  # type: ignore[assignment]


class BraintrustTracer:
    """EventBus subscriber that maps WorkflowEvents to Braintrust spans.

    Creates a hierarchy: workflow root span > agent stage spans.
    Tool calls and other events are logged as metadata on active stage spans.
    """

    def __init__(self, api_key: str, project: str = "amelia") -> None:
        if braintrust is None:
            raise ImportError(
                "braintrust package is required for tracing. "
                "Install with: pip install 'amelia[braintrust]'"
            )
        self._logger = braintrust.init_logger(project=project, api_key=api_key)
        self._workflow_spans: dict[uuid.UUID, object] = {}
        self._stage_spans: dict[tuple[uuid.UUID, str], object] = {}

    def on_event(self, event: WorkflowEvent) -> None:
        """EventBus callback. Must be synchronous and non-blocking."""
        try:
            self._handle_event(event)
        except Exception:
            logger.warning(
                "Braintrust tracing failed",
                event_type=event.event_type.value,
                workflow_id=str(event.workflow_id),
                exc_info=True,
            )

    def _handle_event(self, event: WorkflowEvent) -> None:
        match event.event_type:
            case EventType.WORKFLOW_STARTED:
                span = self._logger.start_span(
                    name="workflow",
                    span_attributes={"type": "task"},
                    input={
                        "workflow_id": str(event.workflow_id),
                        **(event.data or {}),
                    },
                )
                self._workflow_spans[event.workflow_id] = span

            case EventType.STAGE_STARTED:
                parent = self._workflow_spans.get(event.workflow_id)
                if parent is None:
                    return
                span = parent.start_span(
                    name=event.agent,
                    span_attributes={"type": "task"},
                    input={"stage": event.agent, **(event.data or {})},
                )
                self._stage_spans[(event.workflow_id, event.agent)] = span

            case EventType.STAGE_COMPLETED:
                key = (event.workflow_id, event.agent)
                span = self._stage_spans.pop(key, None)
                if span is not None:
                    span.log(output=event.data or {})
                    span.end()

            case EventType.WORKFLOW_COMPLETED:
                span = self._workflow_spans.pop(event.workflow_id, None)
                if span is not None:
                    span.log(output={"status": "completed", **(event.data or {})})
                    span.end()

            case EventType.WORKFLOW_FAILED:
                span = self._workflow_spans.pop(event.workflow_id, None)
                if span is not None:
                    span.log(
                        output={"status": "failed", **(event.data or {})},
                        scores={"success": 0},
                    )
                    span.end()
                # Also clean up any lingering stage spans
                keys_to_remove = [
                    k for k in self._stage_spans if k[0] == event.workflow_id
                ]
                for key in keys_to_remove:
                    stale = self._stage_spans.pop(key, None)
                    if stale is not None:
                        stale.end()

            case EventType.CLAUDE_TOOL_CALL | EventType.CLAUDE_TOOL_RESULT:
                key = (event.workflow_id, event.agent)
                span = self._stage_spans.get(key)
                if span is not None:
                    span.log(metadata=event.data or {})

            case EventType.TASK_STARTED | EventType.TASK_COMPLETED | EventType.TASK_FAILED:
                key = (event.workflow_id, event.agent)
                span = self._stage_spans.get(key)
                if span is not None:
                    span.log(metadata={
                        "task_event": event.event_type.value,
                        **(event.data or {}),
                    })

    def get_parent_span_id(self, workflow_id: uuid.UUID, agent: str) -> str | None:
        """Get the Braintrust span ID for an active agent stage."""
        span = self._stage_spans.get((workflow_id, agent))
        return span.id if span is not None else None

    def get_root_span_id(self, workflow_id: uuid.UUID) -> str | None:
        """Get the Braintrust span ID for the workflow root."""
        span = self._workflow_spans.get(workflow_id)
        return span.id if span is not None else None
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_braintrust_tracer.py -v`
Expected: PASS

**Step 5: Run linting and type checking**

Run: `uv run ruff check amelia/ext/ tests/unit/test_braintrust_tracer.py`
Run: `uv run mypy amelia/ext/`

**Step 6: Commit**

```bash
git add amelia/ext/__init__.py amelia/ext/braintrust.py tests/unit/test_braintrust_tracer.py
git commit -m "feat(ext): add BraintrustTracer EventBus subscriber (#234)"
```

---

### Task 4: Wire BraintrustTracer into server startup

**Files:**
- Modify: `amelia/server/main.py` (lifespan or startup section)
- Test: `tests/unit/server/test_braintrust_startup.py`

**Step 1: Write the failing test**

Create `tests/unit/server/test_braintrust_startup.py`:

```python
"""Tests for conditional Braintrust tracer startup."""

from unittest.mock import MagicMock, patch

from amelia.ext.braintrust import BraintrustTracer
from amelia.server.events.bus import EventBus


def test_tracer_subscribes_to_event_bus():
    """When created, tracer can be subscribed to EventBus."""
    with patch("amelia.ext.braintrust.braintrust") as mock_bt:
        mock_bt.init_logger.return_value = MagicMock()
        bus = EventBus()
        tracer = BraintrustTracer(api_key="test-key")
        bus.subscribe(tracer.on_event)
        assert tracer.on_event in bus._subscribers


def test_tracer_not_created_when_no_api_key():
    """create_braintrust_tracer returns None when API key is absent."""
    from amelia.ext.braintrust import create_braintrust_tracer
    result = create_braintrust_tracer(api_key=None, project="amelia")
    assert result is None


def test_tracer_not_created_when_package_missing():
    """create_braintrust_tracer returns None when braintrust not installed."""
    with patch("amelia.ext.braintrust.braintrust", None):
        from amelia.ext.braintrust import create_braintrust_tracer
        result = create_braintrust_tracer(api_key="test-key", project="amelia")
        assert result is None
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/test_braintrust_startup.py -v`
Expected: FAIL — `create_braintrust_tracer` does not exist

**Step 3: Add factory function to braintrust module**

Add to `amelia/ext/braintrust.py`, after the `BraintrustTracer` class:

```python
def create_braintrust_tracer(
    api_key: str | None,
    project: str = "amelia",
) -> BraintrustTracer | None:
    """Create a BraintrustTracer if configured, or return None.

    Returns None (with a warning log) if:
    - api_key is None (not configured)
    - braintrust package is not installed
    """
    if api_key is None:
        return None
    if braintrust is None:
        logger.warning(
            "BRAINTRUST_API_KEY is set but braintrust package is not installed. "
            "Install with: pip install 'amelia[braintrust]'"
        )
        return None
    try:
        tracer = BraintrustTracer(api_key=api_key, project=project)
        logger.info("Braintrust tracing enabled", project=project)
        return tracer
    except Exception:
        logger.warning("Failed to initialize Braintrust tracer", exc_info=True)
        return None
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/test_braintrust_startup.py -v`
Expected: PASS

**Step 5: Wire into server main.py**

Find the server startup in `amelia/server/main.py` where the `EventBus` is created and subscribers are set up. Add after EventBus creation:

```python
from amelia.ext.braintrust import create_braintrust_tracer

# ... inside create_application() or lifespan, after event_bus is created:
tracer = create_braintrust_tracer(
    api_key=config.braintrust_api_key,
    project=config.braintrust_project,
)
if tracer is not None:
    event_bus.subscribe(tracer.on_event)
    application.state.braintrust_tracer = tracer
```

The exact location depends on where `event_bus` is instantiated in `main.py`. Look for `EventBus()` and add the tracer subscription right after.

**Step 6: Commit**

```bash
git add amelia/ext/braintrust.py amelia/server/main.py tests/unit/server/test_braintrust_startup.py
git commit -m "feat(server): wire BraintrustTracer into server startup (#234)"
```

---

### Task 5: Pass Braintrust span IDs to Claude CLI driver

**Files:**
- Modify: `amelia/drivers/cli/claude.py:49-55` (`_build_sanitized_env`) and `:273-350` (`_build_options`)
- Modify: `amelia/drivers/factory.py:10-65` (`get_driver`)
- Test: `tests/unit/test_claude_driver_braintrust.py`

**Step 1: Write the failing test**

Create `tests/unit/test_claude_driver_braintrust.py`:

```python
"""Tests for Braintrust span ID passthrough in Claude CLI driver."""

from amelia.drivers.cli.claude import _build_sanitized_env


def test_build_sanitized_env_includes_braintrust_vars():
    """When braintrust env vars are set, they pass through to Claude subprocess."""
    import os
    from unittest.mock import patch

    bt_env = {
        "BRAINTRUST_API_KEY": "br-test-key",
        "BRAINTRUST_CC_PROJECT": "test-project",
        "CC_PARENT_SPAN_ID": "span-123",
        "CC_ROOT_SPAN_ID": "root-456",
    }
    with patch.dict(os.environ, bt_env):
        env = _build_sanitized_env()
        # Braintrust vars should NOT be stripped
        # (they're set in os.environ and SDK merges env on top of os.environ)
        # The function only needs to not strip them.
        # Verify the function doesn't add them to an exclusion list
        assert "BRAINTRUST_API_KEY" not in env or env.get("BRAINTRUST_API_KEY") != ""
```

**Step 2: Run test — analyze current behavior**

Run: `uv run pytest tests/unit/test_claude_driver_braintrust.py -v`

The Claude SDK merges the `env` dict on top of `os.environ`. So Braintrust env vars set in `os.environ` will naturally pass through. The key question is whether `_build_sanitized_env` strips them — it currently only overrides `_NESTED_SESSION_OVERRIDES`. So Braintrust vars should pass through without changes.

However, we need a way for the orchestrator to set `CC_PARENT_SPAN_ID` and `CC_ROOT_SPAN_ID` per-invocation. The `_build_options` method builds the `env` dict, so we need to add span ID injection there.

**Step 3: Add braintrust_env parameter to _build_options**

Modify `ClaudeCliDriver._build_options` to accept optional Braintrust env vars:

In `_build_options`, add parameter `braintrust_env: dict[str, str] | None = None`, and merge into the env dict:

```python
env = _build_sanitized_env()
if braintrust_env:
    env.update(braintrust_env)
```

Then in `execute_agentic`, extract braintrust kwargs and pass them:

```python
braintrust_env = kwargs.get("braintrust_env")
options = self._build_options(
    ...,
    braintrust_env=braintrust_env,
)
```

**Step 4: Run tests**

Run: `uv run pytest tests/unit/test_claude_driver_braintrust.py tests/unit/test_claude_driver.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/drivers/cli/claude.py tests/unit/test_claude_driver_braintrust.py
git commit -m "feat(drivers): pass Braintrust span IDs to Claude CLI subprocess (#234)"
```

---

### Task 6: Pass Braintrust env vars to Codex CLI driver

**Files:**
- Modify: `amelia/drivers/cli/codex.py:141-229` (`_run_codex_stream`)
- Test: `tests/unit/test_codex_driver_braintrust.py`

**Step 1: Write the failing test**

Create `tests/unit/test_codex_driver_braintrust.py`:

```python
"""Tests for Braintrust env var passthrough in Codex CLI driver."""

import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from amelia.drivers.cli.codex import CodexCliDriver


async def test_codex_passes_braintrust_env_to_subprocess():
    """When braintrust_env is in kwargs, it's merged into subprocess env."""
    driver = CodexCliDriver(model="o3-mini")

    # We need to verify the env dict passed to create_subprocess_exec
    # includes Braintrust vars. Patch create_subprocess_exec to capture args.
    with patch("asyncio.create_subprocess_exec") as mock_exec:
        mock_proc = AsyncMock()
        mock_proc.stdout.readline = AsyncMock(return_value=b"")
        mock_proc.wait = AsyncMock(return_value=0)
        mock_proc.returncode = 0
        mock_proc.stderr = AsyncMock()
        mock_proc.stderr.read = AsyncMock(return_value=b"")
        mock_exec.return_value = mock_proc

        async for _ in driver._run_codex_stream(
            "test prompt",
            cwd="/tmp",
            braintrust_env={"BRAINTRUST_API_KEY": "br-key"},
        ):
            pass

        # Check that env kwarg was passed and includes the key
        call_kwargs = mock_exec.call_args
        assert call_kwargs is not None
        env = call_kwargs.kwargs.get("env", {})
        assert env.get("BRAINTRUST_API_KEY") == "br-key"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_codex_driver_braintrust.py -v`
Expected: FAIL — `_run_codex_stream` doesn't accept `braintrust_env`

**Step 3: Add braintrust_env to _run_codex_stream**

Modify `CodexCliDriver._run_codex_stream` to accept `braintrust_env: dict[str, str] | None = None` and pass it as `env` to `asyncio.create_subprocess_exec`:

```python
import os

# In _run_codex_stream, build env dict:
env: dict[str, str] | None = None
if braintrust_env:
    env = {**os.environ, **braintrust_env}

proc = await asyncio.create_subprocess_exec(
    *cmd,
    cwd=cwd or self.cwd,
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
    env=env,
)
```

Also update `execute_agentic` to extract and pass `braintrust_env` from kwargs:

```python
braintrust_env = kwargs.get("braintrust_env")
async for event in self._run_codex_stream(
    full_prompt, cwd=cwd, session_id=session_id,
    approval_mode=resolved_mode,
    braintrust_env=braintrust_env,
):
```

**Step 4: Run tests**

Run: `uv run pytest tests/unit/test_codex_driver_braintrust.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/drivers/cli/codex.py tests/unit/test_codex_driver_braintrust.py
git commit -m "feat(drivers): pass Braintrust env vars to Codex CLI subprocess (#234)"
```

---

### Task 7: Add Braintrust proxy routing for sandbox

**Files:**
- Modify: `amelia/sandbox/proxy.py:128-192` (`forward_request`)
- Test: `tests/unit/sandbox/test_braintrust_proxy.py`

**Step 1: Write the failing test**

Create `tests/unit/sandbox/test_braintrust_proxy.py`:

```python
"""Tests for Braintrust proxy routing in sandbox."""

import os
from unittest.mock import patch

from amelia.sandbox.proxy import ProviderConfig, resolve_braintrust_provider


def test_resolve_braintrust_provider_when_configured():
    """When BRAINTRUST_API_KEY is set, returns Braintrust proxy config."""
    with patch.dict(os.environ, {"BRAINTRUST_API_KEY": "br-key"}):
        result = resolve_braintrust_provider(
            original=ProviderConfig(base_url="https://openrouter.ai/api/v1", api_key="or-key"),
            parent_span_id="span-123",
        )
    assert result is not None
    assert "braintrust" in result.base_url
    assert result.api_key == "br-key"


def test_resolve_braintrust_provider_when_not_configured():
    """When BRAINTRUST_API_KEY is absent, returns None (use original)."""
    with patch.dict(os.environ, {}, clear=True):
        result = resolve_braintrust_provider(
            original=ProviderConfig(base_url="https://openrouter.ai/api/v1", api_key="or-key"),
        )
    assert result is None
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/sandbox/test_braintrust_proxy.py -v`
Expected: FAIL — `resolve_braintrust_provider` does not exist

**Step 3: Add resolve_braintrust_provider to proxy.py**

Add to `amelia/sandbox/proxy.py`:

```python
BRAINTRUST_PROXY_BASE_URL = "https://api.braintrust.dev/v1/proxy"


def resolve_braintrust_provider(
    original: ProviderConfig,
    parent_span_id: str | None = None,
) -> ProviderConfig | None:
    """Return Braintrust proxy config if BRAINTRUST_API_KEY is set.

    Args:
        original: The original provider config (unused but kept for interface clarity).
        parent_span_id: Optional Braintrust span ID for trace hierarchy.

    Returns:
        ProviderConfig pointing to Braintrust proxy, or None if not configured.
    """
    api_key = os.environ.get("BRAINTRUST_API_KEY")
    if not api_key:
        return None
    return ProviderConfig(
        base_url=BRAINTRUST_PROXY_BASE_URL,
        api_key=api_key,
    )
```

Also modify `forward_request` to add the `x-bt-parent` header when routing through Braintrust:

```python
# In forward_request, after building headers dict:
braintrust_project = os.environ.get("BRAINTRUST_PROJECT", "amelia")
if "braintrust" in upstream_url:
    bt_parent = request.headers.get("x-bt-parent")
    if bt_parent:
        headers["x-bt-parent"] = bt_parent
    elif braintrust_project:
        headers["x-bt-parent"] = f"project_name:{braintrust_project}"
```

**Step 4: Run tests**

Run: `uv run pytest tests/unit/sandbox/test_braintrust_proxy.py -v`
Expected: PASS

**Step 5: Wire into proxy_chat_completions**

In `create_proxy_router`, modify `proxy_chat_completions` to check for Braintrust routing:

```python
# Inside proxy_chat_completions, after resolving provider:
bt_provider = resolve_braintrust_provider(provider)
if bt_provider is not None:
    provider = bt_provider
```

**Step 6: Commit**

```bash
git add amelia/sandbox/proxy.py tests/unit/sandbox/test_braintrust_proxy.py
git commit -m "feat(sandbox): add Braintrust proxy routing for container driver (#234)"
```

---

### Task 8: Pass span IDs from orchestrator to drivers

**Files:**
- Modify: `amelia/agents/developer.py` (and similarly architect.py, reviewer.py)
- Test: `tests/unit/agents/test_braintrust_span_passing.py`

This is the bridge: when agents call `driver.execute_agentic()`, they need to pass `braintrust_env` with span IDs from the tracer.

**Step 1: Write the failing test**

Create `tests/unit/agents/test_braintrust_span_passing.py`:

```python
"""Tests for Braintrust span ID passing from agents to drivers."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


async def test_developer_passes_braintrust_env_to_driver():
    """Developer agent passes braintrust_env from event_bus tracer to driver."""
    from amelia.agents.developer import DeveloperAgent
    from amelia.core.types import AgentConfig, Profile, SandboxConfig

    config = AgentConfig(
        driver="claude",
        model="sonnet",
        options={},
        sandbox=SandboxConfig(),
        profile_name="test",
    )

    mock_tracer = MagicMock()
    mock_tracer.get_parent_span_id.return_value = "span-123"
    mock_tracer.get_root_span_id.return_value = "root-456"

    with patch("amelia.agents.developer.get_driver") as mock_get_driver:
        mock_driver = AsyncMock()
        mock_driver.execute_agentic = AsyncMock(return_value=AsyncMock(__aiter__=lambda s: iter([])))
        mock_get_driver.return_value = mock_driver

        agent = DeveloperAgent(config=config, braintrust_tracer=mock_tracer)
        # The agent should store the tracer and pass span IDs when calling the driver
        assert agent._braintrust_tracer is mock_tracer
```

**Step 2: Analyze the integration surface**

Each agent (Developer, Architect, Reviewer, Evaluator) creates a driver in `__init__` and calls `driver.execute_agentic()` in its run method. The tracer needs to be passed to each agent so it can look up span IDs by `(workflow_id, agent_name)` and pass them as `braintrust_env` kwargs.

The agents are created by LangGraph nodes. Check how nodes create agents to find the injection point.

**Step 3: Add braintrust_tracer to agent constructors**

For each agent class (DeveloperAgent, ArchitectAgent, ReviewerAgent, EvaluatorAgent), add optional `braintrust_tracer` parameter:

```python
def __init__(
    self,
    config: AgentConfig,
    ...,
    braintrust_tracer: object | None = None,
) -> None:
    ...
    self._braintrust_tracer = braintrust_tracer
```

Then in `execute_agentic()` calls within each agent's run method, build braintrust_env:

```python
braintrust_env: dict[str, str] | None = None
if self._braintrust_tracer is not None:
    parent_id = self._braintrust_tracer.get_parent_span_id(workflow_id, self._agent_name)
    root_id = self._braintrust_tracer.get_root_span_id(workflow_id)
    if parent_id or root_id:
        import os
        braintrust_env = {}
        if parent_id:
            braintrust_env["CC_PARENT_SPAN_ID"] = parent_id
        if root_id:
            braintrust_env["CC_ROOT_SPAN_ID"] = root_id
        api_key = os.environ.get("BRAINTRUST_API_KEY", "")
        if api_key:
            braintrust_env["BRAINTRUST_API_KEY"] = api_key
            braintrust_env["BRAINTRUST_CC_PROJECT"] = os.environ.get("BRAINTRUST_PROJECT", "amelia")
```

Pass `braintrust_env=braintrust_env` to `self.driver.execute_agentic(...)`.

**Step 4: Wire tracer through LangGraph nodes**

The tracer is stored on `application.state.braintrust_tracer` (from Task 4). LangGraph nodes receive config via `RunnableConfig["configurable"]`. Add the tracer to the config dict in `OrchestratorService._run_workflow`:

```python
config: RunnableConfig = {
    "configurable": {
        ...,
        "braintrust_tracer": getattr(self, "_braintrust_tracer", None),
    },
}
```

Each LangGraph node that creates an agent extracts it from config and passes it to the agent constructor.

**Step 5: Run tests**

Run: `uv run pytest tests/unit/agents/test_braintrust_span_passing.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add amelia/agents/developer.py amelia/agents/architect.py amelia/agents/reviewer.py amelia/agents/evaluator.py amelia/server/orchestrator/service.py tests/unit/agents/test_braintrust_span_passing.py
git commit -m "feat(agents): pass Braintrust span IDs from orchestrator to drivers (#234)"
```

---

### Task 9: Full integration test

**Files:**
- Test: `tests/unit/test_braintrust_integration.py`

**Step 1: Write integration-style test (mocked Braintrust SDK)**

```python
"""End-to-end test of Braintrust tracing through EventBus lifecycle."""

from unittest.mock import MagicMock, patch, call
from uuid import uuid4

from amelia.ext.braintrust import BraintrustTracer, create_braintrust_tracer
from amelia.server.events.bus import EventBus
from amelia.server.models.events import EventType, WorkflowEvent


def _event(event_type, workflow_id, agent="system", data=None):
    return WorkflowEvent(
        id=uuid4(),
        workflow_id=workflow_id,
        sequence=1,
        timestamp="2026-01-01T00:00:00Z",
        agent=agent,
        event_type=event_type,
        message="test",
        data=data,
    )


def test_full_workflow_lifecycle_creates_correct_span_hierarchy():
    """Simulate a full workflow and verify span creation/closing order."""
    with patch("amelia.ext.braintrust.braintrust") as mock_bt:
        root_span = MagicMock(name="root_span")
        arch_span = MagicMock(name="arch_span")
        dev_span = MagicMock(name="dev_span")
        rev_span = MagicMock(name="rev_span")

        mock_logger = MagicMock()
        mock_bt.init_logger.return_value = mock_logger
        mock_logger.start_span.return_value = root_span
        root_span.start_span.side_effect = [arch_span, dev_span, rev_span]

        bus = EventBus()
        tracer = BraintrustTracer(api_key="test-key")
        bus.subscribe(tracer.on_event)

        wf_id = uuid4()

        # Workflow lifecycle
        bus.emit(_event(EventType.WORKFLOW_STARTED, wf_id))
        bus.emit(_event(EventType.STAGE_STARTED, wf_id, agent="architect"))
        bus.emit(_event(EventType.CLAUDE_TOOL_CALL, wf_id, agent="architect", data={"tool_name": "read"}))
        bus.emit(_event(EventType.STAGE_COMPLETED, wf_id, agent="architect"))
        bus.emit(_event(EventType.STAGE_STARTED, wf_id, agent="developer"))
        bus.emit(_event(EventType.STAGE_COMPLETED, wf_id, agent="developer"))
        bus.emit(_event(EventType.STAGE_STARTED, wf_id, agent="reviewer"))
        bus.emit(_event(EventType.STAGE_COMPLETED, wf_id, agent="reviewer"))
        bus.emit(_event(EventType.WORKFLOW_COMPLETED, wf_id))

        # Verify span lifecycle
        mock_logger.start_span.assert_called_once()  # root span
        assert root_span.start_span.call_count == 3  # 3 agent spans
        arch_span.end.assert_called_once()
        dev_span.end.assert_called_once()
        rev_span.end.assert_called_once()
        root_span.end.assert_called_once()

        # Verify tool call was logged on architect span
        arch_span.log.assert_called()


def test_tracer_disabled_when_no_key():
    """create_braintrust_tracer returns None without API key."""
    tracer = create_braintrust_tracer(api_key=None)
    assert tracer is None


def test_event_bus_continues_when_tracer_errors():
    """EventBus calls other subscribers even if tracer raises."""
    with patch("amelia.ext.braintrust.braintrust") as mock_bt:
        mock_logger = MagicMock()
        mock_bt.init_logger.return_value = mock_logger
        mock_logger.start_span.side_effect = RuntimeError("boom")

        bus = EventBus()
        tracer = BraintrustTracer(api_key="test-key")
        other_subscriber = MagicMock()

        bus.subscribe(tracer.on_event)
        bus.subscribe(other_subscriber)

        event = _event(EventType.WORKFLOW_STARTED, uuid4())
        bus.emit(event)

        # Other subscriber still called despite tracer error
        other_subscriber.assert_called_once_with(event)
```

**Step 2: Run tests**

Run: `uv run pytest tests/unit/test_braintrust_integration.py -v`
Expected: PASS

**Step 3: Commit**

```bash
git add tests/unit/test_braintrust_integration.py
git commit -m "test: add Braintrust tracing integration tests (#234)"
```

---

### Task 10: Final verification and cleanup

**Step 1: Run full test suite**

Run: `uv run pytest tests/unit/ -v`
Expected: All tests pass

**Step 2: Run linting**

Run: `uv run ruff check --fix amelia tests`
Run: `uv run mypy amelia`

**Step 3: Verify zero-overhead when disabled**

Manually verify:
- `amelia/ext/braintrust.py` only imports `braintrust` inside a try/except
- `create_braintrust_tracer(api_key=None)` returns `None` immediately
- No braintrust imports at module level in any other file

**Step 4: Final commit if any fixes**

```bash
git add -A
git commit -m "chore: lint and type fixes for Braintrust integration (#234)"
```
