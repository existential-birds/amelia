# Implementation Plan - Amelia Agentic Orchestrator Completion

**Goal:** Complete the implementation of the Agentic Orchestrator by replacing simulations with real functionality, ensuring driver parity, and finalizing integration points.
**Architecture:** Python 3.12+, LangGraph (Orchestration), PydanticAI (Agents), Typer (CLI), HTTPX (API).
**Test Framework:** `pytest` with `pytest-asyncio`.

## Phase 1: Core Driver Parity & Configuration

### Task 1.1: Fix Driver Factory Aliases
**Goal:** Ensure generic profile settings (`driver: cli`, `driver: api`) resolve to concrete implementations.
**Files:** `amelia/drivers/factory.py`, `tests/unit/test_driver_factory.py`

1.  **Red (Write Failing Test):**
    ```python
    # tests/unit/test_driver_factory.py
    import pytest
    from amelia.drivers.factory import DriverFactory
    from amelia.drivers.cli.claude import ClaudeCliDriver
    from amelia.drivers.api.openai import ApiDriver

    def test_driver_aliases():
        assert isinstance(DriverFactory.get_driver("cli"), ClaudeCliDriver)
        assert isinstance(DriverFactory.get_driver("api"), ApiDriver)
    ```
2.  **Verify Failure:** `pytest tests/unit/test_driver_factory.py`
3.  **Green (Implementation):**
    -   Update `get_driver` in `amelia/drivers/factory.py` to handle `cli` maps to `cli:claude` and `api` maps to `api:openai`.
4.  **Verify Pass:** `pytest tests/unit/test_driver_factory.py`
5.  **Commit:** `fix(drivers): resolve generic driver aliases in factory`

### Task 1.2: Implement API Driver Tool Execution
**Goal:** Enable `ApiDriver` to perform actual side effects (shell commands, file writing) to match `ClaudeCliDriver`.
**Files:** `amelia/drivers/api/openai.py`, `tests/unit/test_api_driver_tools.py`

1.  **Red (Write Failing Test):**
    ```python
    # tests/unit/test_api_driver_tools.py
    import pytest
    import os
    from amelia.drivers.api.openai import ApiDriver

    @pytest.mark.asyncio
    async def test_api_driver_write_file(tmp_path):
        driver = ApiDriver()
        test_file = tmp_path / "test.txt"
        await driver.execute_tool("write_file", file_path=str(test_file), content="Hello World")
        assert test_file.read_text() == "Hello World"

    @pytest.mark.asyncio
    async def test_api_driver_shell_command():
        driver = ApiDriver()
        result = await driver.execute_tool("run_shell_command", command="echo 'test'")
        assert "test" in result.strip()
    ```
2.  **Verify Failure:** `pytest tests/unit/test_api_driver_tools.py`
3.  **Green (Implementation):**
    -   Import `subprocess` and `pathlib`.
    -   Implement `execute_tool` in `amelia/drivers/api/openai.py`.
    -   Handle `write_file`: open file and write content.
    -   Handle `run_shell_command`: use `subprocess.run`.
4.  **Verify Pass:** `pytest tests/unit/test_api_driver_tools.py`
5.  **Commit:** `feat(drivers): implement tool execution in ApiDriver`

## Phase 2: Real Context & Data

### Task 2.1: Real Git Diff Integration
**Goal:** Allow the Orchestrator/Reviewer to read actual local changes.
**Files:** `amelia/core/orchestrator.py`, `tests/unit/test_orchestrator_diff.py`

1.  **Red (Write Failing Test):**
    ```python
    # tests/unit/test_orchestrator_diff.py
    import pytest
    from unittest.mock import patch
    from amelia.core.orchestrator import get_code_changes_for_review
    from amelia.core.state import ExecutionState
    # Mock other state requirements...

    @pytest.mark.asyncio
    async def test_get_real_git_diff():
        # Setup a dummy state
        state = ExecutionState(
            profile=..., issue=..., # Fill with minimal mocks
            code_changes_for_review=None 
        )
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = "diff --git a/file b/file..."
            mock_run.return_value.returncode = 0
            diff = await get_code_changes_for_review(state)
            assert "diff --git" in diff
            mock_run.assert_called_with(["git", "diff", "HEAD"], capture_output=True, text=True, check=False)
    ```
2.  **Verify Failure:** `pytest tests/unit/test_orchestrator_diff.py`
3.  **Green (Implementation):**
    -   Update `get_code_changes_for_review` in `amelia/core/orchestrator.py`.
    -   Remove placeholder string.
    -   Use `subprocess.run(["git", "diff", "HEAD"], ...)` to fetch diffs.
4.  **Verify Pass:** `pytest tests/unit/test_orchestrator_diff.py`
5.  **Commit:** `feat(orchestrator): enable reading local git diffs`

### Task 2.2: Jira Tracker Implementation
**Goal:** Replace stub with HTTP-based Jira fetcher.
**Files:** `amelia/trackers/jira.py`, `tests/unit/test_trackers.py`

1.  **Red (Write Failing Test):**
    ```python
    # tests/unit/test_jira_tracker.py
    import pytest
    from unittest.mock import patch, MagicMock
    from amelia.trackers.jira import JiraTracker

    def test_jira_get_issue():
        tracker = JiraTracker()
        with patch("httpx.get") as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.return_value = {
                "key": "PROJ-123",
                "fields": {"summary": "Test Issue", "description": "Desc"}
            }
            issue = tracker.get_issue("PROJ-123")
            assert issue.title == "Test Issue"
            assert issue.description == "Desc"
    ```
2.  **Verify Failure:** `pytest tests/unit/test_jira_tracker.py`
3.  **Green (Implementation):**
    -   Use `httpx`.
    -   Implement `get_issue` in `amelia/trackers/jira.py`.
    -   Assume environment variables `JIRA_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN` for auth.
4.  **Verify Pass:** `pytest tests/unit/test_jira_tracker.py`
5.  **Commit:** `feat(trackers): implement Jira integration via HTTPX`

## Phase 3: Developer Agent Realization

### Task 3.1: Remove Developer Simulation
**Goal:** Ensure the Developer agent actually executes tools instead of simulating them.
**Files:** `amelia/agents/developer.py`, `tests/unit/test_agents.py`

1.  **Red (Write Failing Test):**
    ```python
    # tests/unit/test_developer_real.py
    import pytest
    from unittest.mock import AsyncMock
    from amelia.agents.developer import Developer
    from amelia.core.state import Task

    @pytest.mark.asyncio
    async def test_developer_executes_tool_not_simulation():
        mock_driver = AsyncMock()
        mock_driver.execute_tool.return_value = "File created"
        
        dev = Developer(mock_driver)
        task = Task(id="1", description="write file: test.py with print('hi')", status="pending")
        
        result = await dev.execute_task(task)
        
        # Verify execute_tool was CALLED, not just printed
        mock_driver.execute_tool.assert_called_once()
        assert result["output"] == "File created"
    ```
2.  **Verify Failure:** `pytest tests/unit/test_developer_real.py` (Expected to fail if it relies on the hardcoded simulation block that returns string literals without calling driver).
3.  **Green (Implementation):**
    -   Refactor `amelia/agents/developer.py`.
    -   In `execute_task`, parse the command and **call** `self.driver.execute_tool`.
    -   Remove the `return {"status": "completed", "output": "File write simulated"}` line.
4.  **Verify Pass:** `pytest tests/unit/test_developer_real.py`
5.  **Commit:** `refactor(agents): enable real tool execution in Developer agent`
