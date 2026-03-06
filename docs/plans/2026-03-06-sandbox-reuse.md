# Sandbox Reuse Across Workflow Stages — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Share a single Daytona `SandboxProvider` across all agents within a workflow, with guaranteed teardown.

**Architecture:** Provider is created once in the orchestrator's `_run_workflow()`, passed via LangGraph `configurable` dict to graph nodes, which inject it into agents. Teardown happens in a `finally` block. `get_driver()` gets an optional `sandbox_provider` parameter that bypasses provider creation when set.

**Tech Stack:** Python 3.12+, LangGraph, Pydantic, pytest-asyncio

**Design Doc:** `docs/plans/2026-03-06-sandbox-reuse-design.md`

---

### Task 1: Add `worker_env` property to `DaytonaSandboxProvider`

The provider needs to expose its LLM environment variables so `ContainerDriver` can read them without the factory having to thread them through separately.

**Files:**
- Modify: `amelia/sandbox/daytona.py` (add property after `worker_cmd` property, ~line 116)
- Modify: `amelia/sandbox/provider.py` (add default `worker_env` to protocol, after `worker_cmd`)
- Test: `tests/unit/sandbox/test_daytona_provider.py`

**Step 1: Write the failing test**

Add to `tests/unit/sandbox/test_daytona_provider.py`:

```python
class TestWorkerEnv:
    """Tests for the worker_env property."""

    def test_worker_env_returns_empty_when_no_env_set(self) -> None:
        """Provider with no LLM env returns empty dict."""
        provider = DaytonaSandboxProvider(api_key="test-key")
        assert provider.worker_env == {}

    def test_worker_env_returns_configured_env(self) -> None:
        """Provider with LLM env returns the configured variables."""
        provider = DaytonaSandboxProvider(api_key="test-key")
        provider._worker_env = {"LLM_PROXY_URL": "https://example.com", "OPENAI_API_KEY": "sk-test"}
        assert provider.worker_env == {
            "LLM_PROXY_URL": "https://example.com",
            "OPENAI_API_KEY": "sk-test",
        }
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/sandbox/test_daytona_provider.py::TestWorkerEnv -v`
Expected: FAIL — `worker_env` property doesn't exist yet.

**Step 3: Implement `worker_env` on `DaytonaSandboxProvider`**

In `amelia/sandbox/daytona.py`, add a `_worker_env` field to `__init__` and a property:

```python
# In __init__, add after self._workflow_branch:
self._worker_env: dict[str, str] = {}

# Add property after worker_cmd property:
@property
def worker_env(self) -> dict[str, str]:
    """Environment variables needed by the worker inside the sandbox."""
    return dict(self._worker_env)
```

In `amelia/sandbox/provider.py`, add default `worker_env` to the protocol after `worker_cmd`:

```python
@property
def worker_env(self) -> dict[str, str]:
    """Environment variables for the worker process.

    Returns additional env vars the worker needs (e.g., LLM API keys
    for remote sandboxes). Default is empty.
    """
    return {}
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/sandbox/test_daytona_provider.py::TestWorkerEnv -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/sandbox/daytona.py amelia/sandbox/provider.py tests/unit/sandbox/test_daytona_provider.py
git commit -m "feat(sandbox): add worker_env property to DaytonaSandboxProvider"
```

---

### Task 2: Add `sandbox_provider` parameter to `get_driver()`

When a pre-created provider is passed in, `get_driver()` should skip provider creation and wrap it directly in `ContainerDriver`.

**Files:**
- Modify: `amelia/drivers/factory.py:9-65` (the `get_driver` function)
- Test: `tests/unit/drivers/test_factory.py`

**Step 1: Write the failing test**

Add a new test class in `tests/unit/drivers/test_factory.py`:

```python
class TestGetDriverWithSharedProvider:
    """Tests for sandbox_provider parameter (sandbox reuse)."""

    def test_shared_provider_skips_creation(self) -> None:
        """When sandbox_provider is passed, get_driver wraps it directly."""
        mock_provider = MagicMock()
        mock_provider.worker_env = {"LLM_PROXY_URL": "https://example.com", "OPENAI_API_KEY": "sk-test"}
        with patch("amelia.sandbox.driver.ContainerDriver") as mock_driver_cls:
            mock_driver_cls.return_value = MagicMock()
            get_driver(
                "api",
                model="test-model",
                sandbox_provider=mock_provider,
            )
            mock_driver_cls.assert_called_once_with(
                model="test-model",
                provider=mock_provider,
                env={"LLM_PROXY_URL": "https://example.com", "OPENAI_API_KEY": "sk-test"},
            )

    def test_shared_provider_ignores_sandbox_config(self) -> None:
        """sandbox_provider takes precedence over sandbox_config."""
        mock_provider = MagicMock()
        mock_provider.worker_env = {}
        sandbox = SandboxConfig(mode="container", image="test:latest")
        with patch("amelia.sandbox.driver.ContainerDriver") as mock_driver_cls:
            mock_driver_cls.return_value = MagicMock()
            get_driver(
                "api",
                model="test-model",
                sandbox_config=sandbox,
                sandbox_provider=mock_provider,
            )
            # Should use the shared provider, not create a new Docker one
            mock_driver_cls.assert_called_once_with(
                model="test-model",
                provider=mock_provider,
                env={},
            )

    def test_none_provider_preserves_existing_behavior(self) -> None:
        """sandbox_provider=None (default) doesn't change behavior."""
        with patch("amelia.drivers.factory.ApiDriver") as mock_cls:
            mock_cls.return_value = MagicMock()
            get_driver("api", model="test-model", sandbox_provider=None)
            mock_cls.assert_called_once_with(provider="openrouter", model="test-model")
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/drivers/test_factory.py::TestGetDriverWithSharedProvider -v`
Expected: FAIL — `sandbox_provider` parameter not recognized.

**Step 3: Implement the `sandbox_provider` parameter**

In `amelia/drivers/factory.py`, modify `get_driver()`:

```python
def get_driver(
    driver_key: str,
    *,
    model: str = "",
    cwd: str | None = None,
    sandbox_config: SandboxConfig | None = None,
    sandbox_provider: "SandboxProvider | None" = None,   # NEW
    profile_name: str = "default",
    options: dict[str, Any] | None = None,
    retry_config: RetryConfig | None = None,
) -> DriverInterface:
```

Add early return at the top of the function body, before any sandbox_config checks:

```python
    # Shared provider path: reuse an existing provider instance.
    if sandbox_provider is not None:
        from amelia.sandbox.driver import ContainerDriver  # noqa: PLC0415

        return ContainerDriver(
            model=model,
            provider=sandbox_provider,
            env=sandbox_provider.worker_env,
        )
```

Also need to update `ContainerDriver.__init__` to accept `env`:

In `amelia/sandbox/driver.py`, modify `__init__`:

```python
def __init__(self, model: str, provider: SandboxProvider, env: dict[str, str] | None = None) -> None:
    self.model = model
    self._provider = provider
    self._env = env or {}
    self._last_usage: DriverUsage | None = None
```

And pass `self._env` to `exec_stream` calls in `execute_agentic` and `generate` (as the `env` kwarg).

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/drivers/test_factory.py::TestGetDriverWithSharedProvider -v`
Expected: PASS

**Step 5: Run full factory and container driver tests**

Run: `uv run pytest tests/unit/drivers/test_factory.py tests/unit/sandbox/test_container_driver.py -v`
Expected: ALL PASS (existing tests should not break since `env` and `sandbox_provider` default to None).

**Step 6: Commit**

```bash
git add amelia/drivers/factory.py amelia/sandbox/driver.py tests/unit/drivers/test_factory.py
git commit -m "feat(sandbox): add sandbox_provider param to get_driver for reuse"
```

---

### Task 3: Add `sandbox_provider` parameter to agent constructors

All four agents (Architect, Developer, Reviewer, Evaluator) need to accept and forward a shared provider.

**Files:**
- Modify: `amelia/agents/architect.py:64-85` (`__init__`)
- Modify: `amelia/agents/developer.py:38-54` (`__init__`)
- Modify: `amelia/agents/reviewer.py:116-144` (`__init__`)
- Modify: `amelia/agents/evaluator.py:73-97` (`__init__`)

**Step 1: Update all four agent constructors**

The change is identical for each agent. Add `sandbox_provider` parameter and forward it:

```python
# Architect.__init__ — add param after prompts:
def __init__(
    self,
    config: AgentConfig,
    prompts: dict[str, str] | None = None,
    sandbox_provider: "SandboxProvider | None" = None,
):
    self.driver = get_driver(
        config.driver,
        model=config.model,
        sandbox_config=config.sandbox,
        sandbox_provider=sandbox_provider,
        profile_name=config.profile_name,
        options=config.options,
    )
```

```python
# Developer.__init__ — add param after prompts:
def __init__(self, config: AgentConfig, prompts: dict[str, str] | None = None,
             sandbox_provider: "SandboxProvider | None" = None):
    self.driver = get_driver(
        config.driver,
        model=config.model,
        sandbox_config=config.sandbox,
        sandbox_provider=sandbox_provider,
        profile_name=config.profile_name,
        options=config.options,
    )
```

```python
# Reviewer.__init__ — add param after agent_name:
def __init__(
    self,
    config: AgentConfig,
    event_bus: "EventBus | None" = None,
    prompts: dict[str, str] | None = None,
    agent_name: str = "reviewer",
    sandbox_provider: "SandboxProvider | None" = None,
):
    self.driver = get_driver(
        config.driver,
        model=config.model,
        sandbox_config=config.sandbox,
        sandbox_provider=sandbox_provider,
        profile_name=config.profile_name,
        options=config.options,
    )
```

```python
# Evaluator.__init__ — add param after prompts:
def __init__(
    self,
    config: AgentConfig,
    event_bus: "EventBus | None" = None,
    prompts: dict[str, str] | None = None,
    sandbox_provider: "SandboxProvider | None" = None,
):
    self.driver = get_driver(
        config.driver,
        model=config.model,
        sandbox_config=config.sandbox,
        sandbox_provider=sandbox_provider,
        profile_name=config.profile_name,
        options=config.options,
    )
```

Note: Evaluator currently doesn't pass `sandbox_config` — fix this too.

Add the import to each file: `from amelia.sandbox.provider import SandboxProvider` (use `TYPE_CHECKING` guard).

**Step 2: Run existing agent tests to verify no regressions**

Run: `uv run pytest tests/unit/agents/ -v`
Expected: ALL PASS — the new parameter defaults to `None`, so existing call sites are unaffected.

**Step 3: Commit**

```bash
git add amelia/agents/architect.py amelia/agents/developer.py amelia/agents/reviewer.py amelia/agents/evaluator.py
git commit -m "feat(agents): accept sandbox_provider for sandbox reuse"
```

---

### Task 4: Extract and pass `sandbox_provider` in graph nodes

Graph nodes need to read the provider from LangGraph `configurable` and pass it to agent constructors.

**Files:**
- Modify: `amelia/pipelines/nodes.py:83-165` (`call_developer_node`)
- Modify: `amelia/pipelines/nodes.py:168-272` (`call_reviewer_node`)
- Modify: `amelia/pipelines/implementation/nodes.py:115-280` (`call_architect_node`)
- Modify: `amelia/pipelines/review/nodes.py:17-63` (`call_evaluation_node`)

**Step 1: Update `call_developer_node` in `amelia/pipelines/nodes.py`**

After the existing `prompts = configurable.get("prompts", {})` line, add:

```python
sandbox_provider = configurable.get("sandbox_provider")
```

Then pass it to the Developer constructor:

```python
developer = Developer(agent_config, prompts=prompts, sandbox_provider=sandbox_provider)
```

**Step 2: Update `call_reviewer_node` in `amelia/pipelines/nodes.py`**

Same pattern — add after prompts extraction:

```python
sandbox_provider = configurable.get("sandbox_provider")
```

Pass to Reviewer constructor:

```python
reviewer = Reviewer(agent_config, event_bus=event_bus, prompts=prompts, agent_name=agent_name, sandbox_provider=sandbox_provider)
```

**Step 3: Update `call_architect_node` in `amelia/pipelines/implementation/nodes.py`**

Same pattern:

```python
sandbox_provider = configurable.get("sandbox_provider")
architect = Architect(agent_config, prompts=prompts, sandbox_provider=sandbox_provider)
```

**Step 4: Update `call_evaluation_node` in `amelia/pipelines/review/nodes.py`**

Same pattern:

```python
sandbox_provider = configurable.get("sandbox_provider")
evaluator = Evaluator(config=agent_config, event_bus=event_bus, prompts=prompts, sandbox_provider=sandbox_provider)
```

**Step 5: Run existing pipeline tests**

Run: `uv run pytest tests/unit/pipelines/ -v`
Expected: ALL PASS — `sandbox_provider` defaults to `None` in configurable.

**Step 6: Commit**

```bash
git add amelia/pipelines/nodes.py amelia/pipelines/implementation/nodes.py amelia/pipelines/review/nodes.py
git commit -m "feat(pipelines): pass sandbox_provider from configurable to agents"
```

---

### Task 5: Extract `create_daytona_provider()` from factory

Move the Daytona provider creation logic out of `get_driver()` into a standalone function that both the factory and orchestrator can call.

**Files:**
- Modify: `amelia/drivers/factory.py` (extract function, update Daytona branch to call it)
- Test: `tests/unit/drivers/test_factory.py`

**Step 1: Write test for `create_daytona_provider()`**

Add to `tests/unit/drivers/test_factory.py`:

```python
from amelia.drivers.factory import create_daytona_provider

class TestCreateDaytonaProvider:
    """Tests for the standalone create_daytona_provider function."""

    def test_creates_provider_with_required_fields(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DAYTONA_API_KEY", "test-key")
        monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
        sandbox = SandboxConfig(mode="daytona", repo_url="https://github.com/test/repo")
        with patch("amelia.drivers.factory.DaytonaSandboxProvider") as mock_cls:
            mock_cls.return_value = MagicMock()
            provider, worker_env = create_daytona_provider(sandbox)
            mock_cls.assert_called_once()
            assert "LLM_PROXY_URL" in worker_env
            assert "OPENAI_API_KEY" in worker_env

    def test_raises_without_api_key(self) -> None:
        sandbox = SandboxConfig(mode="daytona", repo_url="https://github.com/test/repo")
        with pytest.raises(ValueError, match="DAYTONA_API_KEY"):
            create_daytona_provider(sandbox)

    def test_raises_without_repo_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DAYTONA_API_KEY", "test-key")
        sandbox = SandboxConfig(mode="daytona")
        with pytest.raises(ValueError, match="repo_url"):
            create_daytona_provider(sandbox)
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/drivers/test_factory.py::TestCreateDaytonaProvider -v`
Expected: FAIL — `create_daytona_provider` doesn't exist.

**Step 3: Extract `create_daytona_provider()` function**

In `amelia/drivers/factory.py`, create a new function that contains the Daytona-specific logic currently in the `SandboxMode.DAYTONA` branch of `get_driver()`. It should return `(provider, worker_env)` tuple.

```python
def create_daytona_provider(
    sandbox_config: SandboxConfig,
    *,
    options: dict[str, Any] | None = None,
    retry_config: RetryConfig | None = None,
) -> tuple["SandboxProvider", dict[str, str]]:
    """Create a DaytonaSandboxProvider and resolve worker environment.

    Args:
        sandbox_config: Sandbox configuration with Daytona fields.
        options: Driver options (used to resolve LLM provider).
        retry_config: Retry configuration for transient failures.

    Returns:
        Tuple of (provider, worker_env dict).

    Raises:
        ValueError: If required env vars or config fields are missing.
    """
    import os  # noqa: PLC0415
    from amelia.sandbox.daytona import DaytonaSandboxProvider  # noqa: PLC0415

    if sandbox_config.network_allowlist_enabled:
        raise ValueError(
            "Network allowlist is not supported with Daytona cloud sandboxes."
        )

    api_key = os.environ.get("DAYTONA_API_KEY")
    if not api_key:
        raise ValueError("DAYTONA_API_KEY environment variable is required")

    if not sandbox_config.repo_url:
        raise ValueError("repo_url is required when sandbox mode is 'daytona'")

    git_token = os.environ.get("AMELIA_GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN")

    provider = DaytonaSandboxProvider(
        api_key=api_key,
        api_url=sandbox_config.daytona_api_url,
        target=sandbox_config.daytona_target,
        repo_url=sandbox_config.repo_url,
        resources=sandbox_config.daytona_resources,
        image=sandbox_config.daytona_image,
        snapshot=sandbox_config.daytona_snapshot,
        timeout=sandbox_config.daytona_timeout,
        retry_config=retry_config,
        git_token=git_token,
    )

    # Resolve worker env for remote sandbox
    llm_provider = (options or {}).get("provider", "openrouter")
    provider_registry = {
        "openrouter": "https://openrouter.ai/api/v1",
        "openai": "https://api.openai.com/v1",
    }
    api_key_env_vars = {
        "openrouter": "OPENROUTER_API_KEY",
        "openai": "OPENAI_API_KEY",
    }

    llm_base_url = provider_registry.get(llm_provider)
    llm_env_var = api_key_env_vars.get(llm_provider)
    if llm_base_url is None or llm_env_var is None:
        raise ValueError(f"Unsupported LLM provider: {llm_provider!r}")

    llm_api_key = os.environ.get(llm_env_var, "")
    if not llm_api_key:
        raise ValueError(f"{llm_env_var} is required for Daytona sandbox")

    worker_env = {"LLM_PROXY_URL": llm_base_url, "OPENAI_API_KEY": llm_api_key}

    # Store worker_env on the provider for ContainerDriver to read
    provider._worker_env = worker_env

    return provider, worker_env
```

Update the existing `SandboxMode.DAYTONA` branch in `get_driver()` to call `create_daytona_provider()`:

```python
    if sandbox_config and sandbox_config.mode == SandboxMode.DAYTONA:
        if driver_key in {"claude", "codex"}:
            raise ValueError("Daytona sandbox requires API driver.")
        if driver_key != "api":
            raise ValueError(f"Unknown driver key: {driver_key!r}")

        from amelia.sandbox.driver import ContainerDriver  # noqa: PLC0415

        provider, worker_env = create_daytona_provider(
            sandbox_config, options=options, retry_config=retry_config,
        )
        return ContainerDriver(model=model, provider=provider, env=worker_env)
```

**Step 4: Run all factory tests**

Run: `uv run pytest tests/unit/drivers/test_factory.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add amelia/drivers/factory.py tests/unit/drivers/test_factory.py
git commit -m "refactor(factory): extract create_daytona_provider for reuse"
```

---

### Task 6: Create and teardown provider in orchestrator workflow runners

This is the core change — create the provider once before graph execution, pass it via configurable, and tear it down in a `finally` block.

**Files:**
- Modify: `amelia/server/orchestrator/service.py:1077-1217` (`_run_workflow`)
- Modify: `amelia/server/orchestrator/service.py:1219-1296` (`_run_workflow_with_retry`)
- Modify: `amelia/server/orchestrator/service.py:1298-1400` (`_run_review_workflow`)

**Step 1: Update `_run_workflow` to accept and pass `sandbox_provider`**

Add `sandbox_provider` parameter:

```python
async def _run_workflow(
    self,
    workflow_id: uuid.UUID,
    state: ServerExecutionState,
    sandbox_provider: "SandboxProvider | None" = None,
) -> None:
```

In the config dict construction, add:

```python
config: RunnableConfig = {
    "recursion_limit": 100,
    "configurable": {
        "thread_id": str(workflow_id),
        "execution_mode": "server",
        "event_bus": self._event_bus,
        "profile": profile,
        "repository": self._repository,
        "prompts": prompts,
        "sandbox_provider": sandbox_provider,   # NEW
    },
}
```

**Step 2: Update `_run_workflow_with_retry` to create and teardown provider**

Wrap the retry loop in a try/finally that manages the provider lifecycle:

```python
async def _run_workflow_with_retry(
    self,
    workflow_id: uuid.UUID,
    state: ServerExecutionState,
) -> None:
    # ... existing profile resolution ...

    # Create shared sandbox provider if Daytona mode
    sandbox_provider = None
    try:
        if profile.sandbox.mode == SandboxMode.DAYTONA:
            from amelia.drivers.factory import create_daytona_provider  # noqa: PLC0415

            agent_options = None
            # Use developer agent options for LLM provider resolution
            try:
                dev_config = profile.get_agent_config("developer")
                agent_options = dev_config.options
            except ValueError:
                pass
            provider, _worker_env = create_daytona_provider(
                profile.sandbox, options=agent_options, retry_config=profile.retry,
            )
            await provider.ensure_running()
            sandbox_provider = provider

        # Existing retry loop
        attempt = 0
        while attempt <= retry_config.max_retries:
            try:
                await self._run_workflow(workflow_id, state, sandbox_provider=sandbox_provider)
                return
            except TRANSIENT_EXCEPTIONS as e:
                # ... existing retry logic ...
            except Exception as e:
                # ... existing non-transient handling ...
    finally:
        if sandbox_provider is not None:
            await sandbox_provider.teardown()
```

**Step 3: Update `_run_review_workflow` similarly**

Add sandbox provider creation and teardown. Same pattern as `_run_workflow_with_retry` but simpler (no retry loop):

```python
async def _run_review_workflow(
    self,
    workflow_id: uuid.UUID,
    state: ServerExecutionState,
    execution_state: ImplementationState,
) -> None:
    # ... existing profile resolution ...

    sandbox_provider = None
    try:
        if profile.sandbox.mode == SandboxMode.DAYTONA:
            from amelia.drivers.factory import create_daytona_provider
            provider, _worker_env = create_daytona_provider(profile.sandbox)
            await provider.ensure_running()
            sandbox_provider = provider

        config: RunnableConfig = {
            "configurable": {
                # ... existing fields ...
                "sandbox_provider": sandbox_provider,
            },
        }
        # ... existing graph execution ...
    finally:
        if sandbox_provider is not None:
            await sandbox_provider.teardown()
```

**Step 4: Add imports**

Add at top of `amelia/server/orchestrator/service.py`:

```python
from amelia.core.types import SandboxMode
```

**Step 5: Run full test suite**

Run: `uv run pytest tests/ -v --timeout=30`
Expected: ALL PASS

**Step 6: Commit**

```bash
git add amelia/server/orchestrator/service.py
git commit -m "feat(orchestrator): create shared sandbox provider with guaranteed teardown"
```

---

### Task 7: Update existing tests for new constructor signatures

Some existing tests may directly instantiate agents or call `get_driver` — update them for the new optional parameters.

**Files:**
- Scan and modify: `tests/unit/agents/`, `tests/unit/drivers/`, `tests/unit/sandbox/`, `tests/unit/pipelines/`

**Step 1: Run the full test suite to find breakages**

Run: `uv run pytest tests/unit/ -v --timeout=30`
Expected: Identify any tests that break due to the new parameters.

**Step 2: Fix any failures**

Most tests should pass since all new parameters are optional with `None` defaults. If any tests mock `get_driver` or agent constructors with strict signature checks, update the mock expectations to include the new parameter.

**Step 3: Run full test suite again**

Run: `uv run pytest tests/unit/ -v --timeout=30`
Expected: ALL PASS

**Step 4: Run mypy**

Run: `uv run mypy amelia`
Expected: No new errors. Fix any type errors from the new parameters.

**Step 5: Run linter**

Run: `uv run ruff check amelia tests`
Expected: Clean

**Step 6: Commit**

```bash
git add -u
git commit -m "fix(tests): update tests for sandbox_provider constructor params"
```

---

### Task 8: End-to-end verification

**Step 1: Run the complete pre-push check**

Run: `uv run ruff check amelia tests && uv run mypy amelia && uv run pytest tests/`
Expected: ALL PASS

**Step 2: Verify the integration test still works**

Check `tests/integration/test_daytona_sandbox.py` — it may need the `create_daytona_provider` import updated if it used the old factory path.

Run: `uv run pytest tests/integration/test_daytona_sandbox.py -v --timeout=60` (if Daytona env vars are set)
Expected: PASS or skip (if no DAYTONA_API_KEY)

**Step 3: Final commit with all changes**

If any fixes were needed:
```bash
git add -u
git commit -m "fix: final cleanup for sandbox reuse implementation"
```
