# Autonomous Execution After Plan Approval

**Date:** 2025-12-01
**Status:** Design Complete

## Overview

Enable fully autonomous code execution after human approves a plan. Claude executes each task independently with full tool access (YOLO mode), streaming progress to the terminal in real-time.

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Granularity | Task-by-task | Preserves DAG dependencies, easier recovery on failure |
| Invocation | Profile-based `execution_mode` | Clean separation (driver = how to talk to Claude, profile = how to orchestrate) |
| Task context | Full TDD instructions | Reuses Architect's plan, Claude has roadmap but freedom in execution |
| Streaming | Live to terminal | Transparency, user can Ctrl+C if needed |
| Error handling | Fail fast | Autonomous mode is high-trust, failures need investigation |
| Review timing | After all tasks | Plan already approved, final review catches issues before commit |

## Configuration

New profile field `execution_mode`:

```yaml
profiles:
  default:
    driver: cli:claude
    tracker: github
    execution_mode: structured  # Current behavior (default)

  autonomous:
    driver: cli:claude
    tracker: github
    execution_mode: agentic     # New autonomous mode
    working_dir: /path/to/repo  # Optional, defaults to cwd
```

Usage: `amelia start ISSUE-123 --profile autonomous`

## Implementation

### 1. Type Additions

```python
# amelia/core/types.py
ExecutionMode = Literal["structured", "agentic"]
```

### 2. State Changes

```python
# amelia/core/state.py
class Profile(BaseModel):
    driver: DriverType = "cli:claude"
    tracker: TrackerType = "noop"
    strategy: ReviewStrategy = "single"
    execution_mode: ExecutionMode = "structured"  # NEW
    plan_output_dir: str | None = None
    working_dir: str | None = None  # NEW

class ExecutionState(BaseModel):
    # ... existing fields ...
    workflow_status: Literal["running", "completed", "failed"] = "running"  # NEW
```

### 3. Exception Addition

```python
# amelia/core/exceptions.py
class AgenticExecutionError(AmeliaError):
    """Raised when agentic execution fails."""
    pass
```

### 4. Driver Changes

Merge `execute_agentic()` from `ClaudeAgenticCliDriver` into `ClaudeCliDriver`:

```python
# amelia/drivers/cli/claude.py
class ClaudeCliDriver(CliDriver):
    def __init__(self, ...):
        ...
        self.tool_call_history: list[ClaudeStreamEvent] = []

    async def execute_agentic(
        self,
        prompt: str,
        cwd: str,
        session_id: str | None = None
    ) -> AsyncIterator[ClaudeStreamEvent]:
        """Execute prompt with full autonomous tool access (YOLO mode)."""
        cmd_args = [
            "claude", "-p",
            "--model", self.model,
            "--output-format", "stream-json",
            "--verbose",
            "--dangerously-skip-permissions"
        ]
        # ... stream events, track tool calls ...
```

Delete `amelia/drivers/cli/agentic.py` and remove `cli:claude:agentic` from factory.

### 5. Developer Agent Changes

```python
# amelia/agents/developer.py
class Developer:
    def __init__(self, driver: DriverInterface, execution_mode: ExecutionMode = "structured"):
        self.driver = driver
        self.execution_mode = execution_mode

    async def execute_task(self, task: Task, cwd: str | None = None) -> dict:
        if self.execution_mode == "agentic":
            return await self._execute_agentic(task, cwd or os.getcwd())
        else:
            return await self._execute_structured(task)

    async def _execute_structured(self, task: Task) -> dict:
        # Current implementation (extracted to method)
        ...

    async def _execute_agentic(self, task: Task, cwd: str) -> dict:
        prompt = self._build_task_prompt(task)

        async for event in self.driver.execute_agentic(prompt, cwd):
            self._handle_stream_event(event)
            if event.type == "error":
                raise AgenticExecutionError(event.content)

        return {"status": "completed", "task_id": task.id}

    def _build_task_prompt(self, task: Task) -> str:
        """Convert task to prompt with full TDD instructions."""
        sections = [f"# Task: {task.description}", "", "## Files"]
        for file_op in task.files:
            sections.append(f"- {file_op.operation}: `{file_op.path}`")

        if task.steps:
            sections.append("\n## Steps")
            for i, step in enumerate(task.steps, 1):
                sections.append(f"### Step {i}: {step.description}")
                if step.code:
                    sections.append(f"```\n{step.code}\n```")
                if step.command:
                    sections.append(f"Run: `{step.command}`")

        sections.append("\nExecute this task following TDD principles.")
        return "\n".join(sections)

    def _handle_stream_event(self, event: ClaudeStreamEvent) -> None:
        """Display streaming event to terminal."""
        if event.type == "tool_use":
            typer.secho(f"  → {event.tool_name}", fg=typer.colors.CYAN)
        elif event.type == "tool_result":
            typer.secho(f"  ✓ Done", fg=typer.colors.GREEN, dim=True)
        elif event.type == "error":
            typer.secho(f"  ✗ Error: {event.content}", fg=typer.colors.RED)
```

### 6. Orchestrator Changes

```python
# amelia/core/orchestrator.py
async def call_developer_node(state: ExecutionState) -> ExecutionState:
    driver = DriverFactory.get_driver(state.profile.driver)
    developer = Developer(driver, execution_mode=state.profile.execution_mode)
    cwd = state.profile.working_dir or os.getcwd()

    for task in state.plan.get_ready_tasks():
        task.status = "in_progress"
        try:
            await developer.execute_task(task, cwd=cwd)
            task.status = "completed"
        except AgenticExecutionError as e:
            task.status = "failed"
            return ExecutionState(..., workflow_status="failed")

    # Continue to next tasks or reviewer...
```

## Files Changed

| File | Change |
|------|--------|
| `amelia/core/types.py` | Add `ExecutionMode` type |
| `amelia/core/state.py` | Add fields to Profile and ExecutionState |
| `amelia/core/exceptions.py` | Add `AgenticExecutionError` |
| `amelia/drivers/cli/claude.py` | Add `execute_agentic()`, `tool_call_history` |
| `amelia/agents/developer.py` | Add agentic execution path |
| `amelia/core/orchestrator.py` | Pass execution_mode, handle fail-fast |
| `amelia/drivers/cli/agentic.py` | DELETE |
| `amelia/drivers/factory.py` | Remove `cli:claude:agentic` |

## Not Changing

- **Architect**: Same plan works for both modes
- **Reviewer**: Same review after all tasks complete
- **Trackers**: Unaffected

## Flow Diagram

```
                    ┌─────────────────────────────────────────────┐
                    │              PLAN APPROVAL                  │
                    │         (Human reviews plan)                │
                    └─────────────────┬───────────────────────────┘
                                      │ approved
                    ┌─────────────────▼───────────────────────────┐
                    │           DEVELOPER NODE                    │
                    │                                             │
                    │  if execution_mode == "agentic":            │
                    │    for task in ready_tasks:                 │
                    │      prompt = build_task_prompt(task)       │
                    │      stream = driver.execute_agentic(prompt)│
                    │      for event in stream:                   │
                    │        display_event(event)  ← live output  │
                    │        if error: fail_fast()                │
                    │                                             │
                    └─────────────────┬───────────────────────────┘
                                      │ all tasks done
                    ┌─────────────────▼───────────────────────────┐
                    │              REVIEWER                       │
                    │      (Reviews final git diff)               │
                    └─────────────────────────────────────────────┘
```
