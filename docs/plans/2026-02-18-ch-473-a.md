# Codex and Explicit CLI Drivers — Continuation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Context:** A prior agent began executing `docs/plans/2026-02-18-gh-473.md` on branch `feat/codex-driver` but failed after partially completing Task 1. This plan picks up where it left off.

**Current state:** `amelia/core/types.py` and `tests/unit/core/test_types.py` have **uncommitted** changes. `DriverType` now has `CLAUDE/CODEX/API` (correct), but three old tests in `test_types.py` still construct `AgentConfig(driver="cli", ...)` and will fail. No other tasks were started. No commits exist on this branch beyond `main`.

**Execution Rules:** Use @test-driven-development for each task, run @verification-before-completion before claiming success, and request final review with @requesting-code-review.

---

### Task 1: Fix and Commit DriverType Contract (resume prior work)

**Files:**
- Already modified (unstaged): `amelia/core/types.py`, `tests/unit/core/test_types.py`
- Test: `tests/unit/core/test_types.py`

**Step 1: Fix broken tests in `tests/unit/core/test_types.py`**

Three tests still use `driver="cli"` which will fail with the new enum. Fix them:
- Line 135: `AgentConfig(driver="cli", ...)` → `AgentConfig(driver="claude", ...)`
- Line 144: `AgentConfig(driver="cli", ...)` → `AgentConfig(driver="claude", ...)`
- Line 189: `AgentConfig(driver="cli", ...)` → `AgentConfig(driver="claude", ...)`

**Step 2: Run tests to verify**

Run: `uv run pytest tests/unit/core/test_types.py -v`
Expected: ALL PASS (both new driver tests and fixed old tests).

**Step 3: Commit**

```bash
git add amelia/core/types.py tests/unit/core/test_types.py
git commit -m "refactor(types): replace cli driver enum with claude and codex"
```

---

### Task 2: Update Driver Factory Routing and Session Cleanup

**Files:**
- Modify: `amelia/drivers/factory.py`
- Modify: `tests/unit/test_driver_factory.py`
- Modify: `tests/unit/drivers/test_factory.py`

**Step 1: Write the failing test**

In both factory test files, replace `"cli"` expectations with explicit `"claude"` and add codex coverage:

```python
@pytest.mark.parametrize(
    "driver_key,expected_class",
    [
        ("claude", "ClaudeCliDriver"),
        ("codex", "CodexCliDriver"),
        ("api", "ApiDriver"),
    ],
)
def test_get_driver_routes_explicit_driver_keys(driver_key: str, expected_class: str) -> None:
    ...


def test_get_driver_rejects_legacy_cli() -> None:
    with pytest.raises(ValueError, match="Valid options: 'claude', 'codex', 'api'"):
        get_driver("cli")


@pytest.mark.asyncio
async def test_cleanup_driver_session_codex_returns_false() -> None:
    assert await cleanup_driver_session("codex", "any") is False
```

Also update container-mode test to ensure both `claude` and `codex` are rejected:

```python
@pytest.mark.parametrize("driver_key", ["claude", "codex"])
def test_container_mode_rejects_cli_wrappers(driver_key: str) -> None:
    sandbox = SandboxConfig(mode="container")
    with pytest.raises(ValueError, match="Container sandbox requires API driver"):
        get_driver(driver_key, sandbox_config=sandbox)
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_driver_factory.py tests/unit/drivers/test_factory.py -v`
Expected: FAIL because factory only supports `cli|api`.

**Step 3: Write minimal implementation**

In `amelia/drivers/factory.py`:

```python
from amelia.drivers.cli.codex import CodexCliDriver

...
if sandbox_config and sandbox_config.mode == "container":
    if driver_key in {"claude", "codex"}:
        raise ValueError(
            "Container sandbox requires API driver. "
            "CLI driver containerization is not yet supported."
        )
    if driver_key != "api":
        raise ValueError(f"Unknown driver key: {driver_key}")

if driver_key == "claude":
    return ClaudeCliDriver(model=model, cwd=cwd)
elif driver_key == "codex":
    return CodexCliDriver(model=model, cwd=cwd)
elif driver_key == "api":
    return ApiDriver(provider="openrouter", model=model)
else:
    raise ValueError(
        f"Unknown driver key: {driver_key!r}. "
        "Valid options: 'claude', 'codex', 'api'. "
        "(Legacy forms 'cli', 'cli:claude', and 'api:openrouter' are no longer supported.)"
    )

...
if driver_key in {"claude", "codex"}:
    return False
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_driver_factory.py tests/unit/drivers/test_factory.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/drivers/factory.py tests/unit/test_driver_factory.py tests/unit/drivers/test_factory.py
git commit -m "refactor(factory): route claude codex api and reject legacy cli"
```

---

### Task 3: Add CodexCliDriver Contract Tests (Before Implementation)

**Files:**
- Create: `tests/unit/drivers/test_codex_driver.py`
- Create: `amelia/drivers/cli/codex.py` (scaffold only)

**Step 1: Write the failing test**

Create `tests/unit/drivers/test_codex_driver.py`:

```python
import json
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import BaseModel

from amelia.drivers.base import AgenticMessageType
from amelia.drivers.cli.codex import CodexCliDriver


class _Schema(BaseModel):
    answer: str


@pytest.mark.asyncio
async def test_generate_returns_text() -> None:
    driver = CodexCliDriver(model="gpt-5-codex", cwd="/tmp")
    with patch.object(driver, "_run_codex", new=AsyncMock(return_value='{"result":"ok"}')):
        text, session_id = await driver.generate("ping")
    assert text == "ok"
    assert session_id is None


@pytest.mark.asyncio
async def test_generate_parses_schema() -> None:
    driver = CodexCliDriver(model="gpt-5-codex", cwd="/tmp")
    payload = json.dumps({"answer": "42"})
    with patch.object(driver, "_run_codex", new=AsyncMock(return_value=payload)):
        result, _ = await driver.generate("question", schema=_Schema)
    assert isinstance(result, _Schema)
    assert result.answer == "42"


@pytest.mark.asyncio
async def test_execute_agentic_maps_stream_events() -> None:
    driver = CodexCliDriver(model="gpt-5-codex", cwd="/tmp")
    with patch.object(
        driver,
        "_run_codex_stream",
        return_value=iter([
            {"type": "reasoning", "content": "thinking"},
            {"type": "tool_call", "name": "read_file", "input": {"path": "a.py"}, "id": "1"},
            {"type": "tool_result", "name": "read_file", "output": "ok", "id": "1"},
            {"type": "final", "content": "done"},
        ]),
    ):
        msgs = [m async for m in driver.execute_agentic("task", cwd="/tmp")]

    assert [m.type for m in msgs] == [
        AgenticMessageType.THINKING,
        AgenticMessageType.TOOL_CALL,
        AgenticMessageType.TOOL_RESULT,
        AgenticMessageType.RESULT,
    ]


@pytest.mark.asyncio
async def test_cleanup_session_is_false() -> None:
    driver = CodexCliDriver(model="gpt-5-codex")
    assert await driver.cleanup_session("any") is False
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/drivers/test_codex_driver.py -v`
Expected: FAIL with `ModuleNotFoundError` for `amelia.drivers.cli.codex`.

**Step 3: Write minimal implementation scaffold**

Create `amelia/drivers/cli/codex.py` with class and method signatures only raising `NotImplementedError`:

```python
class CodexCliDriver:
    async def generate(self, *args, **kwargs):
        raise NotImplementedError

    def _run_codex_stream(self, *args, **kwargs):
        raise NotImplementedError

    async def cleanup_session(self, session_id):
        raise NotImplementedError
```

**Step 4: Run test to verify failure shape is now implementation-level**

Run: `uv run pytest tests/unit/drivers/test_codex_driver.py -v`
Expected: FAIL with `NotImplementedError` (import resolved).

**Step 5: Commit**

```bash
git add tests/unit/drivers/test_codex_driver.py amelia/drivers/cli/codex.py
git commit -m "test(drivers): add failing codex cli driver contract tests"
```

---

### Task 4: Implement CodexCliDriver

**Files:**
- Modify: `amelia/drivers/cli/codex.py`
- Modify: `amelia/drivers/cli/__init__.py`
- Modify: `tests/unit/drivers/test_codex_driver.py`

**Step 1: Write final failing edge-case tests**

Append tests for error handling and usage:

```python
@pytest.mark.asyncio
async def test_generate_wraps_process_error() -> None:
    driver = CodexCliDriver(model="gpt-5-codex")
    with patch.object(driver, "_run_codex", new=AsyncMock(side_effect=RuntimeError("boom"))):
        with pytest.raises(Exception, match="Codex CLI generate failed"):
            await driver.generate("x")


def test_get_usage_defaults_model() -> None:
    driver = CodexCliDriver(model="gpt-5-codex")
    usage = driver.get_usage()
    assert usage is None
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/drivers/test_codex_driver.py -v`
Expected: FAIL until implementation is complete.

**Step 3: Write full implementation**

Implement `CodexCliDriver` in `amelia/drivers/cli/codex.py`. Refer to the original plan (`docs/plans/2026-02-18-gh-473.md` Task 4 Step 3) for the complete implementation code. Key points:
- `__init__` takes `model` and optional `cwd`
- `_run_codex` shells out via `asyncio.create_subprocess_exec` to `codex exec --model ... --json`
- `_run_codex_stream` raises `NotImplementedError` (streaming adapter TBD)
- `generate` parses JSON output, supports schema validation
- `execute_agentic` maps stream events to `AgenticMessage` types
- `get_usage` returns `None`
- `cleanup_session` returns `False`
- Wraps errors in `ModelProviderError` with `provider_name="codex-cli"`

Export in `amelia/drivers/cli/__init__.py`:

```python
from amelia.drivers.cli.codex import CodexCliDriver

__all__ = ["CodexCliDriver"]
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/drivers/test_codex_driver.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/drivers/cli/codex.py amelia/drivers/cli/__init__.py tests/unit/drivers/test_codex_driver.py
git commit -m "feat(drivers): implement codex cli driver"
```

---

### Task 5: Update CLI Config Validation and Profile Defaults

**Files:**
- Modify: `amelia/cli/config.py`
- Modify: `tests/unit/cli/test_config_cli.py`

**Step 1: Write the failing test**

In `tests/unit/cli/test_config_cli.py`, update and add assertions:

```python
def test_profile_create_accepts_codex_driver(runner, mock_db):
    result = runner.invoke(app, [
        "config", "profile", "create", "new-profile",
        "--driver", "codex",
        "--model", "gpt-5-codex",
        "--tracker", "noop",
        "--working-dir", "/tmp",
    ])
    assert result.exit_code == 0


def test_profile_create_rejects_legacy_cli_driver(runner, mock_db):
    result = runner.invoke(app, [
        "config", "profile", "create", "new-profile",
        "--driver", "cli",
        "--model", "sonnet",
    ])
    assert result.exit_code != 0
    assert "Invalid driver 'cli'" in result.stdout
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/cli/test_config_cli.py -k "driver or profile_create" -v`
Expected: FAIL because CLI currently only accepts `cli|api`.

**Step 3: Write minimal implementation**

In `amelia/cli/config.py`:
- Replace `VALID_DRIVERS` set: `{DriverType.CLAUDE, DriverType.CODEX, DriverType.API}`
- Update help text: `"Driver (claude, codex, or api)"`
- Update default prompts: `default="claude"`
- Update validation messages

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/cli/test_config_cli.py -k "driver or profile_create" -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/cli/config.py tests/unit/cli/test_config_cli.py
git commit -m "feat(cli): accept claude codex api drivers in profile config"
```

---

### Task 6: Migrate Fixtures and Integration Driver References

**Files:**
- Modify: `tests/conftest.py`
- Modify: `tests/integration/conftest.py`
- Modify: `tests/integration/test_multi_driver_agents.py`
- Modify: `tests/integration/test_extraction_driver_instantiation.py`
- Modify: `tests/integration/test_reviewer_prompt_parser.py`
- Modify: `tests/integration/test_queue_workflow_flow.py`
- Modify: `tests/unit/test_orchestrator_profile.py`
- Modify: `tests/unit/test_orchestrator_graph.py`
- Modify: `tests/unit/client/test_cli_start.py`
- Any other files found by: `rg -l '"cli"|DriverType\.CLI|driver: cli|--driver cli' tests/`

**Step 1: Find all remaining `"cli"` references in tests**

Run: `rg -n '"cli"|DriverType\.CLI' tests/`
This produces the migration hit list.

**Step 2: Apply global test migration**

Replace all `"cli"` → `"claude"` and `DriverType.CLI` → `DriverType.CLAUDE` across test files. Then manually verify the few spots that should exercise `codex` paths (factory tests, multi-driver integration) to ensure they parametrize over `codex` too.

**Step 3: Update integration test driver matrix**

In `tests/integration/test_multi_driver_agents.py`:

```python
DRIVER_CONFIGS = [
    pytest.param("api", "anthropic/claude-sonnet-4-20250514", id="api-openrouter"),
    pytest.param("claude", "sonnet", id="claude-cli"),
    pytest.param("codex", "gpt-5-codex", id="codex-cli"),
]
```

Update patch selection logic:

```python
if driver_key == "api":
    patch_target = "amelia.drivers.api.deepagents.ApiDriver.execute_agentic"
elif driver_key == "claude":
    patch_target = "amelia.drivers.cli.claude.ClaudeCliDriver.execute_agentic"
else:
    patch_target = "amelia.drivers.cli.codex.CodexCliDriver.execute_agentic"
```

**Step 4: Run tests to verify**

Run: `uv run pytest tests/integration/test_multi_driver_agents.py tests/unit/test_orchestrator_profile.py tests/unit/test_orchestrator_graph.py -v`
Expected: PASS

**Step 5: Verify no legacy references remain**

Run: `rg -n '"cli"|DriverType\.CLI' tests/`
Expected: Zero matches (or only in the "rejects legacy cli" test assertions).

**Step 6: Commit**

```bash
git add tests/
git commit -m "test: migrate fixtures from cli to explicit claude and codex drivers"
```

---

### Task 7: Update User/Architecture Docs and Migration Guidance

**Files:**
- Modify: `README.md`
- Modify: `docs/site/guide/configuration.md` (if exists)
- Modify: `docs/site/guide/index.md`
- Modify: `docs/site/guide/usage.md`
- Modify: `docs/site/guide/troubleshooting.md`
- Modify: `docs/site/architecture/data-model.md` (if exists)
- Modify: `CHANGELOG.md`

**Step 1: Find all legacy doc references**

Run: `rg -n '--driver cli|driver: cli|driver=cli|\bcli\b driver' README.md docs/site/ CLAUDE.md`

**Step 2: Update all references**

- `--driver cli` → `--driver claude`
- `cli|api` tables → `claude|codex|api`
- Add codex examples alongside claude examples
- Update CLAUDE.md driver description if it mentions `cli`

**Step 3: Add changelog migration note**

Prepend to CHANGELOG.md:

```markdown
### Breaking Changes
- Removed legacy `driver: "cli"`.
- New explicit driver keys: `claude`, `codex`, `api`.
- Existing profiles must be migrated before running this version.
```

**Step 4: Verify no legacy references remain**

Run: `rg -n '--driver cli|driver: cli' README.md docs/site/`
Expected: Zero matches.

**Step 5: Commit**

```bash
git add README.md docs/site/ CHANGELOG.md CLAUDE.md
git commit -m "docs: document explicit claude codex api driver model and migration"
```

---

### Task 8: Full Verification Gate

**Step 1: Run targeted driver/unit tests**

Run: `uv run pytest tests/unit/test_driver_factory.py tests/unit/drivers/test_factory.py tests/unit/drivers/test_codex_driver.py tests/unit/test_claude_driver.py tests/unit/test_api_driver.py -v`
Expected: PASS

**Step 2: Run config and orchestration regression tests**

Run: `uv run pytest tests/unit/cli/test_config_cli.py tests/unit/test_orchestrator_profile.py tests/unit/test_orchestrator_graph.py tests/integration/test_multi_driver_agents.py -v`
Expected: PASS

**Step 3: Run full test suite**

Run: `uv run pytest tests/unit/ tests/integration/ -v`
Expected: PASS

**Step 4: Run static checks**

Run: `uv run ruff check .` and `uv run mypy amelia`
Expected: PASS

**Step 5: Verify no legacy driver key remains**

Run: `rg -n '"cli"|DriverType\.CLI|--driver cli|driver: cli' amelia tests README.md docs/site`
Expected: Zero matches (except intentional changelog migration notes).

**Step 6: Review commit history**

```bash
git log --oneline -n 10
```

Expected: Clean linear sequence of task commits.
