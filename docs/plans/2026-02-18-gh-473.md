# Codex and Explicit CLI Drivers Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace generic `cli` driver with explicit `claude` and `codex` drivers, add `CodexCliDriver`, and keep `api` behavior unchanged.

**Architecture:** Promote driver identity into the type system (`claude|codex|api`), route instantiation through the factory, and keep all orchestrator/agent code consuming the existing `DriverInterface`. Implement Codex CLI integration as a separate driver module that emits the same `AgenticMessage` contract as existing drivers. Enforce hard-break validation: legacy `cli` values are invalid everywhere.

**Tech Stack:** Python 3.12, pydantic, typer, pytest, claude-agent-sdk, subprocess-based Codex CLI integration

**Execution Rules:** Use @test-driven-development for each task, run @verification-before-completion before claiming success, and request final review with @requesting-code-review.

---

### Task 1: Introduce Explicit DriverType Contract

**Files:**
- Modify: `amelia/core/types.py:29-33`
- Modify: `tests/unit/core/test_types.py`
- Test: `tests/unit/core/test_types.py`

**Step 1: Write the failing test**

In `tests/unit/core/test_types.py`, add/replace driver assertions to require explicit keys:

```python
from amelia.core.types import AgentConfig


def test_agent_config_accepts_claude_driver() -> None:
    config = AgentConfig(driver="claude", model="sonnet")
    assert config.driver == "claude"


def test_agent_config_accepts_codex_driver() -> None:
    config = AgentConfig(driver="codex", model="gpt-5-codex")
    assert config.driver == "codex"


def test_agent_config_rejects_legacy_cli_driver() -> None:
    import pytest

    with pytest.raises(ValueError, match="Input should be 'claude', 'codex' or 'api'"):
        AgentConfig(driver="cli", model="sonnet")
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/core/test_types.py -k driver -v`
Expected: FAIL because `DriverType` still defines `cli` and does not define `claude`/`codex`.

**Step 3: Write minimal implementation**

In `amelia/core/types.py`, replace `DriverType` values:

```python
class DriverType(StrEnum):
    """LLM driver type for agent configuration."""

    CLAUDE = "claude"
    CODEX = "codex"
    API = "api"
```

Update `AgentConfig` docstring text from `('api' or 'cli')` to `('claude', 'codex', or 'api')`.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/core/test_types.py -k driver -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/core/types.py tests/unit/core/test_types.py
git commit -m "refactor(types): replace cli driver enum with claude and codex"
```

---

### Task 2: Update Driver Factory Routing and Session Cleanup

**Files:**
- Modify: `amelia/drivers/factory.py:1-91`
- Modify: `tests/unit/test_driver_factory.py`
- Modify: `tests/unit/drivers/test_factory.py`
- Test: `tests/unit/test_driver_factory.py`
- Test: `tests/unit/drivers/test_factory.py`

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
from amelia.drivers.cli.claude import ClaudeCliDriver
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
- Test: `tests/unit/drivers/test_codex_driver.py`

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

Create `amelia/drivers/cli/codex.py` with class and method signatures only raising `NotImplementedError`.

```python
class CodexCliDriver:
    async def generate(...):
        raise NotImplementedError
```

**Step 4: Run test to verify failure shape is now implementation-level**

Run: `uv run pytest tests/unit/drivers/test_codex_driver.py -v`
Expected: FAIL with `NotImplementedError` (import issue resolved).

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
- Test: `tests/unit/drivers/test_codex_driver.py`

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
Expected: FAIL until parsing/mapping/error behavior is implemented.

**Step 3: Write minimal implementation**

Implement `CodexCliDriver` in `amelia/drivers/cli/codex.py`:

```python
import asyncio
import json
from collections.abc import AsyncIterator, Iterator
from typing import Any

from pydantic import BaseModel

from amelia.core.exceptions import ModelProviderError
from amelia.drivers.base import AgenticMessage, AgenticMessageType, DriverUsage, GenerateResult


class CodexCliDriver:
    def __init__(self, model: str = "gpt-5-codex", cwd: str | None = None) -> None:
        self.model = model
        self.cwd = cwd
        self._usage: DriverUsage | None = None

    async def _run_codex(self, prompt: str, cwd: str | None, instructions: str | None = None) -> str:
        cmd = ["codex", "exec", "--model", self.model, "--json", prompt]
        if instructions:
            cmd.extend(["--instructions", instructions])
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=cwd or self.cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            err = stderr.decode("utf-8", errors="replace").strip()[:1000]
            raise ModelProviderError("Codex CLI generate failed", provider_name="codex-cli", details=err)
        return stdout.decode("utf-8", errors="replace")

    def _run_codex_stream(self, prompt: str, cwd: str, instructions: str | None = None) -> Iterator[dict[str, Any]]:
        raise NotImplementedError("Streaming adapter should be implemented using codex --json output")

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        schema: type[BaseModel] | None = None,
        **kwargs: Any,
    ) -> GenerateResult:
        output = await self._run_codex(prompt=prompt, cwd=kwargs.get("cwd"), instructions=system_prompt)
        data = json.loads(output)
        if schema:
            if isinstance(data, dict):
                return schema.model_validate(data), None
            raise ValueError("Expected JSON object for schema validation")
        if isinstance(data, dict) and "result" in data:
            return str(data["result"]), None
        return output.strip(), None

    async def execute_agentic(
        self,
        prompt: str,
        cwd: str,
        session_id: str | None = None,
        instructions: str | None = None,
        schema: type[BaseModel] | None = None,
        allowed_tools: list[str] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[AgenticMessage]:
        del session_id, schema, allowed_tools, kwargs
        for event in self._run_codex_stream(prompt=prompt, cwd=cwd, instructions=instructions):
            kind = event.get("type")
            if kind == "reasoning":
                yield AgenticMessage(type=AgenticMessageType.THINKING, content=str(event.get("content", "")))
            elif kind == "tool_call":
                yield AgenticMessage(
                    type=AgenticMessageType.TOOL_CALL,
                    tool_name=event.get("name"),
                    tool_input=event.get("input") if isinstance(event.get("input"), dict) else {},
                    tool_call_id=event.get("id"),
                )
            elif kind == "tool_result":
                yield AgenticMessage(
                    type=AgenticMessageType.TOOL_RESULT,
                    tool_name=event.get("name"),
                    tool_output=str(event.get("output", "")),
                    tool_call_id=event.get("id"),
                    is_error=bool(event.get("is_error", False)),
                )
            elif kind == "final":
                yield AgenticMessage(type=AgenticMessageType.RESULT, content=str(event.get("content", "")))

    def get_usage(self) -> DriverUsage | None:
        return self._usage

    async def cleanup_session(self, session_id: str) -> bool:
        del session_id
        return False
```

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
- Modify: `amelia/cli/config.py:93-96`
- Modify: `amelia/cli/config.py:255-291`
- Modify: `amelia/cli/config.py:420-423`
- Modify: `tests/unit/cli/test_config_cli.py`
- Test: `tests/unit/cli/test_config_cli.py`

**Step 1: Write the failing test**

In `tests/unit/cli/test_config_cli.py`, update and add assertions:

```python
def test_profile_create_accepts_codex_driver(runner: CliRunner, mock_db: MagicMock) -> None:
    ...
    result = runner.invoke(app, [
        "config", "profile", "create", "new-profile",
        "--driver", "codex",
        "--model", "gpt-5-codex",
        "--tracker", "noop",
        "--working-dir", "/tmp",
    ])
    assert result.exit_code == 0


def test_profile_create_rejects_legacy_cli_driver(runner: CliRunner, mock_db: MagicMock) -> None:
    ...
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
Expected: FAIL because CLI currently only accepts `cli|api` and prompts default to `cli`.

**Step 3: Write minimal implementation**

In `amelia/cli/config.py`:

```python
VALID_DRIVERS: set[DriverType] = {
    DriverType.CLAUDE,
    DriverType.CODEX,
    DriverType.API,
}
```

Update user-facing text and defaults:

```python
typer.Option("--driver", "-d", help="Driver (claude, codex, or api)")
...
driver = typer.prompt("Driver", default="claude", show_default=True)
...
driver_input = typer.prompt("Driver (claude, codex, or api)", default="claude")
```

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
- Modify: `tests/unit/test_orchestrator_profile.py`
- Modify: `tests/unit/test_orchestrator_graph.py`
- Test: `tests/integration/test_multi_driver_agents.py`
- Test: `tests/unit/test_orchestrator_profile.py`

**Step 1: Write the failing test**

In `tests/integration/test_multi_driver_agents.py`, define explicit driver matrix:

```python
DRIVER_CONFIGS = [
    pytest.param("api", "anthropic/claude-sonnet-4-20250514", id="api-openrouter"),
    pytest.param("claude", "sonnet", id="claude-cli"),
    pytest.param("codex", "gpt-5-codex", id="codex-cli"),
]
```

Patch selection logic:

```python
if driver_key == "api":
    patch_target = "amelia.drivers.api.deepagents.ApiDriver.execute_agentic"
elif driver_key == "claude":
    patch_target = "amelia.drivers.cli.claude.ClaudeCliDriver.execute_agentic"
else:
    patch_target = "amelia.drivers.cli.codex.CodexCliDriver.execute_agentic"
```

Update fixtures in `tests/conftest.py` / `tests/integration/conftest.py` default driver to `"claude"` and remove `"cli"` assumptions.

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_multi_driver_agents.py tests/unit/test_orchestrator_profile.py -v`
Expected: FAIL until all hard-coded `cli` values are migrated.

**Step 3: Write minimal implementation**

Apply global test migration:

```bash
rg -l '"cli"|DriverType\.CLI|driver: cli|--driver cli' tests | xargs sed -i '' -e 's/"cli"/"claude"/g' -e 's/DriverType\.CLI/DriverType.CLAUDE/g'
```

Then manually fix the few tests that should explicitly exercise `codex` paths (factory and multi-driver integration) instead of blanket-replacing everything.

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/integration/test_multi_driver_agents.py tests/unit/test_orchestrator_profile.py tests/unit/test_orchestrator_graph.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/conftest.py tests/integration/conftest.py tests/integration/test_multi_driver_agents.py tests/integration/test_extraction_driver_instantiation.py tests/unit/test_orchestrator_profile.py tests/unit/test_orchestrator_graph.py
git commit -m "test: migrate fixtures from cli to explicit claude and codex drivers"
```

---

### Task 7: Update User/Architecture Docs and Migration Guidance

**Files:**
- Modify: `README.md`
- Modify: `docs/site/guide/configuration.md`
- Modify: `docs/site/guide/usage.md`
- Modify: `docs/site/guide/troubleshooting.md`
- Modify: `docs/site/architecture/data-model.md`
- Modify: `CHANGELOG.md`

**Step 1: Write failing doc validation check**

Run a grep-based guard to ensure no legacy `--driver cli` guidance remains in user docs:

Run: `rg -n "--driver cli|driver: cli|\bcli\b driver" README.md docs/site/guide docs/site/architecture`
Expected: Non-empty output (FAIL condition for this migration task).

**Step 2: Run check to verify it fails before edits**

Run the command above.
Expected: Finds legacy references.

**Step 3: Write minimal documentation implementation**

Update references:
- `cli` driver docs -> explicit `claude` and `codex` entries.
- Tables that say `cli|api` -> `claude|codex|api`.
- Troubleshooting examples:

```bash
amelia config profile create dev-claude --driver claude --tracker none
amelia config profile create dev-codex --driver codex --model gpt-5-codex --tracker none
```

Add changelog migration note:

```markdown
### Breaking Changes
- Removed legacy `driver: "cli"`.
- New explicit driver keys: `claude`, `codex`, `api`.
- Existing profiles must be migrated before running this version.
```

**Step 4: Run validation checks**

Run:
- `rg -n "--driver cli|driver: cli" README.md docs/site/guide docs/site/architecture`
- `uv run pytest tests/unit/cli/test_config_cli.py -v`

Expected:
- First command returns no matches.
- CLI tests remain PASS.

**Step 5: Commit**

```bash
git add README.md docs/site/guide/configuration.md docs/site/guide/usage.md docs/site/guide/troubleshooting.md docs/site/architecture/data-model.md CHANGELOG.md
git commit -m "docs: document explicit claude codex api driver model and migration"
```

---

### Task 8: Full Verification Gate

**Files:**
- Modify: none (verification only)

**Step 1: Run targeted driver/unit tests**

Run:
- `uv run pytest tests/unit/test_driver_factory.py tests/unit/drivers/test_factory.py tests/unit/drivers/test_codex_driver.py tests/unit/test_claude_driver.py tests/unit/test_api_driver.py -v`

Expected: PASS

**Step 2: Run config and orchestration regression tests**

Run:
- `uv run pytest tests/unit/cli/test_config_cli.py tests/unit/test_orchestrator_profile.py tests/unit/test_orchestrator_graph.py tests/integration/test_multi_driver_agents.py -v`

Expected: PASS

**Step 3: Run static checks**

Run:
- `uv run ruff check .`
- `uv run mypy .`

Expected: PASS

**Step 4: Verify no legacy driver key remains in code/tests/docs**

Run:
- `rg -n '"cli"|DriverType\.CLI|--driver cli|driver: cli' amelia tests README.md docs/site`

Expected: Either zero matches, or only intentional historical references called out in changelog migration section.

**Step 5: Commit verification note**

```bash
git status
git log --oneline -n 8
```

Expected: Clean working tree and a linear sequence of task commits ready for PR.

