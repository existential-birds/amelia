# Architect Rich Plans Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Refactor the Architect agent to generate rich, actionable development plans with TDD steps, exact file paths, and complete code snippets.

**Architecture:** Add new Pydantic models (`Design`, `TaskStep`, `FileOperation`) and enhance `Task`. Create a design parser utility that uses LLM to extract structured data from brainstorming markdown. Update Architect to accept optional Design input and output both structured TaskDAG and markdown file.

**Tech Stack:** Pydantic, async Python, LLM driver abstraction, pathlib, slugify

---

### Task 1: Add TaskStep and FileOperation models to state.py

**Files:**
- Modify: `amelia/core/state.py:11-19`
- Test: `tests/unit/test_state_models.py`

**Step 1: Write the failing test**

```python
# Add to tests/unit/test_state_models.py

from amelia.core.state import FileOperation
from amelia.core.state import TaskStep


def test_task_step_minimal():
    step = TaskStep(description="Write the failing test")
    assert step.description == "Write the failing test"
    assert step.code is None
    assert step.command is None
    assert step.expected_output is None


def test_task_step_full():
    step = TaskStep(
        description="Run test to verify it fails",
        code="def test_foo(): assert False",
        command="pytest tests/test_foo.py -v",
        expected_output="FAILED"
    )
    assert step.command == "pytest tests/test_foo.py -v"


def test_file_operation_create():
    op = FileOperation(operation="create", path="src/new_file.py")
    assert op.operation == "create"
    assert op.line_range is None


def test_file_operation_modify_with_range():
    op = FileOperation(operation="modify", path="src/existing.py", line_range="10-25")
    assert op.line_range == "10-25"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_state_models.py::test_task_step_minimal -v`
Expected: FAILED with "cannot import name 'TaskStep'"

**Step 3: Write minimal implementation**

```python
# Add to amelia/core/state.py after line 12 (after Severity)

class TaskStep(BaseModel):
    """A single step within a task (2-5 minutes of work)."""
    description: str
    code: str | None = None
    command: str | None = None
    expected_output: str | None = None


class FileOperation(BaseModel):
    """A file to be created, modified, or tested."""
    operation: Literal["create", "modify", "test"]
    path: str
    line_range: str | None = None
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_state_models.py -v -k "task_step or file_operation"`
Expected: 4 passed

**Step 5: Commit**

```bash
git add amelia/core/state.py tests/unit/test_state_models.py
git commit -m "feat(state): add TaskStep and FileOperation models"
```

---

### Task 2: Enhance Task model with new fields

**Files:**
- Modify: `amelia/core/state.py:14-20`
- Test: `tests/unit/test_state_models.py`

**Step 1: Write the failing test**

```python
# Add to tests/unit/test_state_models.py

def test_task_with_steps_and_files():
    from amelia.core.state import Task, TaskStep, FileOperation

    step = TaskStep(description="Write test", code="def test(): pass")
    file_op = FileOperation(operation="create", path="src/foo.py")

    task = Task(
        id="1",
        description="Add foo feature",
        files=[file_op],
        steps=[step],
        commit_message="feat: add foo"
    )

    assert len(task.files) == 1
    assert len(task.steps) == 1
    assert task.commit_message == "feat: add foo"


def test_task_without_new_fields():
    """Ensure defaults work for minimal task creation."""
    from amelia.core.state import Task

    task = Task(id="1", description="Simple task")
    assert task.files == []
    assert task.steps == []
    assert task.commit_message is None
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_state_models.py::test_task_with_steps_and_files -v`
Expected: FAILED with "unexpected keyword argument 'files'"

**Step 3: Write minimal implementation**

```python
# Replace Task class in amelia/core/state.py

class Task(BaseModel):
    """Task with TDD structure."""
    id: str
    description: str
    status: TaskStatus = "pending"
    dependencies: list[str] = Field(default_factory=list)
    files: list[FileOperation] = Field(default_factory=list)
    steps: list[TaskStep] = Field(default_factory=list)
    commit_message: str | None = None
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_state_models.py -v`
Expected: All passed

**Step 5: Commit**

```bash
git add amelia/core/state.py tests/unit/test_state_models.py
git commit -m "feat(state): enhance Task model with files, steps, commit_message"
```

---

### Task 3: Add Design model to types.py

**Files:**
- Modify: `amelia/core/types.py`
- Test: `tests/unit/test_state_models.py`

**Step 1: Write the failing test**

```python
# Add to tests/unit/test_state_models.py

from amelia.core.types import Design


def test_design_minimal():
    design = Design(
        title="Auth Feature",
        goal="Add user authentication",
        architecture="JWT-based auth with middleware",
        tech_stack=["FastAPI", "PyJWT"],
        components=["AuthMiddleware", "TokenService"],
        raw_content="# Auth Feature Design\n..."
    )
    assert design.title == "Auth Feature"
    assert design.data_flow is None
    assert design.relevant_files == []


def test_design_full():
    design = Design(
        title="Auth Feature",
        goal="Add user authentication",
        architecture="JWT-based auth",
        tech_stack=["FastAPI"],
        components=["AuthMiddleware"],
        data_flow="Request -> Middleware -> Handler",
        error_handling="Return 401 on invalid token",
        testing_strategy="Unit test token validation",
        relevant_files=["src/auth.py", "src/middleware.py"],
        conventions="Use async/await throughout",
        raw_content="# Full design..."
    )
    assert design.data_flow == "Request -> Middleware -> Handler"
    assert len(design.relevant_files) == 2
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_state_models.py::test_design_minimal -v`
Expected: FAILED with "cannot import name 'Design'"

**Step 3: Write minimal implementation**

```python
# Add to amelia/core/types.py after Issue class

class Design(BaseModel):
    """Structured design from brainstorming output."""
    title: str
    goal: str
    architecture: str
    tech_stack: list[str]
    components: list[str]
    data_flow: str | None = None
    error_handling: str | None = None
    testing_strategy: str | None = None
    relevant_files: list[str] = Field(default_factory=list)
    conventions: str | None = None
    raw_content: str
```

Note: Add `from pydantic import Field` to imports in types.py.

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_state_models.py -v -k "design"`
Expected: 2 passed

**Step 5: Commit**

```bash
git add amelia/core/types.py tests/unit/test_state_models.py
git commit -m "feat(types): add Design model for structured brainstorming output"
```

---

### Task 4: Update Profile with plan_output_dir

**Files:**
- Modify: `amelia/core/types.py:10-15`
- Test: `tests/unit/test_state_models.py`

**Step 1: Write the failing test**

```python
# Add to tests/unit/test_state_models.py

def test_profile_plan_output_dir_default():
    from amelia.core.types import Profile

    profile = Profile(name="test", driver="api:openai")
    assert profile.plan_output_dir == "docs/plans"


def test_profile_plan_output_dir_custom():
    from amelia.core.types import Profile

    profile = Profile(name="test", driver="api:openai", plan_output_dir="output/my-plans")
    assert profile.plan_output_dir == "output/my-plans"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_state_models.py::test_profile_plan_output_dir_default -v`
Expected: FAILED with "unexpected keyword argument 'plan_output_dir'" or assertion error

**Step 3: Write minimal implementation**

```python
# Modify Profile class in amelia/core/types.py
# Replace plan_output_template with plan_output_dir

class Profile(BaseModel):
    name: str
    driver: DriverType
    tracker: TrackerType = "none"
    strategy: StrategyType = "single"
    plan_output_dir: str = "docs/plans"
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_state_models.py -v -k "profile_plan"`
Expected: 2 passed

**Step 5: Commit**

```bash
git add amelia/core/types.py tests/unit/test_state_models.py
git commit -m "feat(types): replace plan_output_template with plan_output_dir in Profile"
```

---

### Task 5: Create design parser utility

**Files:**
- Create: `amelia/utils/__init__.py`
- Create: `amelia/utils/design_parser.py`
- Test: `tests/unit/test_design_parser.py`

**Step 1: Write the failing test**

```python
# Create tests/unit/test_design_parser.py

import pytest
from unittest.mock import AsyncMock, MagicMock

from amelia.core.types import Design
from amelia.utils.design_parser import parse_design


@pytest.fixture
def mock_driver_for_parser():
    """Mock driver that returns a Design-like response."""
    mock = MagicMock()
    mock.generate = AsyncMock(return_value=Design(
        title="Test Feature",
        goal="Build test feature",
        architecture="Simple architecture",
        tech_stack=["Python"],
        components=["ComponentA"],
        raw_content=""
    ))
    return mock


async def test_parse_design_extracts_fields(mock_driver_for_parser, tmp_path):
    # Create a mock design markdown file
    design_file = tmp_path / "design.md"
    design_file.write_text("# Test Feature\n\nSome design content here.")

    result = await parse_design(design_file, mock_driver_for_parser)

    assert result.title == "Test Feature"
    assert result.raw_content == "# Test Feature\n\nSome design content here."
    mock_driver_for_parser.generate.assert_called_once()


async def test_parse_design_file_not_found(mock_driver_for_parser):
    with pytest.raises(FileNotFoundError):
        await parse_design("/nonexistent/path.md", mock_driver_for_parser)
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_design_parser.py::test_parse_design_extracts_fields -v`
Expected: FAILED with "No module named 'amelia.utils'"

**Step 3: Write minimal implementation**

```python
# Create amelia/utils/__init__.py
# (empty file)
```

```python
# Create amelia/utils/design_parser.py

from pathlib import Path

from amelia.core.state import AgentMessage
from amelia.core.types import Design
from amelia.drivers.base import DriverInterface


PARSER_SYSTEM_PROMPT = """You are a design document parser. Extract structured information from the given markdown design document.

Parse the document and return a Design object with these fields:
- title: The main title/feature name
- goal: A one-sentence description of what this builds
- architecture: 2-3 sentences about the approach
- tech_stack: List of key technologies/libraries mentioned
- components: List of major components to build
- data_flow: How data moves through the system (if mentioned)
- error_handling: Error handling approach (if mentioned)
- testing_strategy: Testing approach (if mentioned)
- relevant_files: Existing files mentioned that need modification
- conventions: Code style or conventions mentioned

Extract only what is explicitly stated or clearly implied. Use null for fields not covered in the document."""


async def parse_design(path: str | Path, driver: DriverInterface) -> Design:
    """
    Parse a brainstorming markdown file into a structured Design.

    Uses the LLM driver to extract structured fields from freeform markdown.

    Args:
        path: Path to the markdown design document
        driver: LLM driver for structured extraction

    Returns:
        Design object with extracted fields

    Raises:
        FileNotFoundError: If the design file does not exist
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Design file not found: {path}")

    content = path.read_text()

    messages = [
        AgentMessage(role="system", content=PARSER_SYSTEM_PROMPT),
        AgentMessage(role="user", content=content)
    ]

    result = await driver.generate(messages=messages, schema=Design)
    result.raw_content = content
    return result
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_design_parser.py -v`
Expected: 2 passed

**Step 5: Commit**

```bash
git add amelia/utils/__init__.py amelia/utils/design_parser.py tests/unit/test_design_parser.py
git commit -m "feat(utils): add design parser to extract structured Design from markdown"
```

---

### Task 6: Add PlanOutput model and update Architect signature

**Files:**
- Modify: `amelia/agents/architect.py`
- Test: `tests/unit/test_agents.py`

**Step 1: Write the failing test**

```python
# Add to tests/unit/test_agents.py (or create new section)

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from amelia.agents.architect import Architect, PlanOutput
from amelia.core.state import Task, TaskStep, FileOperation, TaskDAG
from amelia.core.types import Issue, Design


@pytest.fixture
def mock_driver_for_architect():
    """Mock driver that returns a TaskListResponse-like object."""
    mock = MagicMock()

    class MockResponse:
        tasks = [
            Task(
                id="1",
                description="Add auth middleware",
                files=[FileOperation(operation="create", path="src/auth.py")],
                steps=[
                    TaskStep(description="Write failing test", code="def test_auth(): pass"),
                    TaskStep(description="Run test", command="pytest", expected_output="FAILED"),
                ],
                commit_message="feat: add auth middleware"
            )
        ]

    mock.generate = AsyncMock(return_value=MockResponse())
    return mock


async def test_architect_plan_returns_plan_output(mock_driver_for_architect, tmp_path):
    architect = Architect(mock_driver_for_architect)
    issue = Issue(id="TEST-1", title="Add auth", description="Add authentication")

    result = await architect.plan(issue, output_dir=str(tmp_path))

    assert isinstance(result, PlanOutput)
    assert isinstance(result.task_dag, TaskDAG)
    assert isinstance(result.markdown_path, Path)
    assert result.markdown_path.exists()


async def test_architect_plan_with_design(mock_driver_for_architect, tmp_path):
    architect = Architect(mock_driver_for_architect)
    issue = Issue(id="TEST-1", title="Add auth", description="Add authentication")
    design = Design(
        title="Auth Feature",
        goal="Add JWT auth",
        architecture="Middleware-based",
        tech_stack=["PyJWT"],
        components=["AuthMiddleware"],
        raw_content="# Design"
    )

    result = await architect.plan(issue, design=design, output_dir=str(tmp_path))

    assert result.task_dag.tasks[0].description == "Add auth middleware"
    # Verify design context was used (check prompt in mock call)
    call_args = mock_driver_for_architect.generate.call_args
    messages = call_args.kwargs.get("messages") or call_args[0][0]
    prompt_content = " ".join(m.content for m in messages)
    assert "Auth Feature" in prompt_content or "JWT auth" in prompt_content
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_agents.py::test_architect_plan_returns_plan_output -v`
Expected: FAILED with "cannot import name 'PlanOutput'"

**Step 3: Write minimal implementation**

```python
# Replace amelia/agents/architect.py entirely

from pathlib import Path
from datetime import date

from pydantic import BaseModel
from pydantic import Field

from amelia.core.state import AgentMessage
from amelia.core.state import Task
from amelia.core.state import TaskDAG
from amelia.core.state import TaskStep
from amelia.core.state import FileOperation
from amelia.core.types import Design
from amelia.core.types import Issue
from amelia.drivers.base import DriverInterface


class TaskListResponse(BaseModel):
    """Schema for LLM-generated list of tasks."""
    tasks: list[Task] = Field(description="A list of actionable development tasks.")


class PlanOutput(BaseModel):
    """Output from architect planning."""
    task_dag: TaskDAG
    markdown_path: Path

    class Config:
        arbitrary_types_allowed = True


def _slugify(text: str) -> str:
    """Convert text to URL-friendly slug."""
    return text.lower().replace(" ", "-").replace("_", "-")[:50]


class Architect:
    def __init__(self, driver: DriverInterface):
        self.driver = driver

    async def plan(
        self,
        issue: Issue,
        design: Design | None = None,
        output_dir: str = "docs/plans"
    ) -> PlanOutput:
        """
        Generates a development plan from an issue and optional design.

        Returns both structured TaskDAG and saves markdown for human review.
        """
        context = self._build_context(issue, design)
        task_dag = await self._generate_task_dag(context, issue)
        markdown_path = self._save_markdown(task_dag, issue, design, output_dir)

        return PlanOutput(task_dag=task_dag, markdown_path=markdown_path)

    def _build_context(self, issue: Issue, design: Design | None) -> str:
        """Build context string from issue and optional design."""
        context = f"Issue: {issue.title}\nDescription: {issue.description}\n"

        if design:
            context += f"\nDesign Context:\n"
            context += f"Title: {design.title}\n"
            context += f"Goal: {design.goal}\n"
            context += f"Architecture: {design.architecture}\n"
            context += f"Tech Stack: {', '.join(design.tech_stack)}\n"
            context += f"Components: {', '.join(design.components)}\n"
            if design.data_flow:
                context += f"Data Flow: {design.data_flow}\n"
            if design.error_handling:
                context += f"Error Handling: {design.error_handling}\n"
            if design.testing_strategy:
                context += f"Testing Strategy: {design.testing_strategy}\n"
            if design.relevant_files:
                context += f"Relevant Files: {', '.join(design.relevant_files)}\n"
            if design.conventions:
                context += f"Conventions: {design.conventions}\n"

        return context

    async def _generate_task_dag(self, context: str, issue: Issue) -> TaskDAG:
        """Generate TaskDAG using LLM."""
        system_prompt = """You are an expert software architect creating implementation plans.

Your role is to break down the given context into a sequence of actionable development tasks.
Each task MUST follow TDD (Test-Driven Development) principles.

For each task, provide:
- id: Unique identifier (e.g., "1", "2", "3")
- description: Clear, concise description of what to build
- dependencies: List of task IDs this task depends on
- files: List of FileOperation objects with:
  - operation: "create", "modify", or "test"
  - path: Exact file path (e.g., "src/auth/middleware.py")
  - line_range: Optional, for modify operations (e.g., "10-25")
- steps: List of TaskStep objects following TDD:
  1. Write the failing test (include actual code)
  2. Run test to verify it fails (include command and expected output)
  3. Write minimal implementation (include actual code)
  4. Run test to verify it passes (include command and expected output)
  5. Commit (include commit message)
- commit_message: Conventional commit message (e.g., "feat: add auth middleware")

Each step should be 2-5 minutes of work. Include complete code, not placeholders.
Output valid JSON conforming to the TaskListResponse schema."""

        user_prompt = f"""Given the following context:

{context}

Create a detailed implementation plan with bite-sized TDD tasks.
Ensure exact file paths, complete code in steps, and commands with expected output."""

        prompt_messages = [
            AgentMessage(role="system", content=system_prompt),
            AgentMessage(role="user", content=user_prompt)
        ]

        response = await self.driver.generate(messages=prompt_messages, schema=TaskListResponse)

        return TaskDAG(tasks=response.tasks, original_issue=issue.id)

    def _save_markdown(
        self,
        task_dag: TaskDAG,
        issue: Issue,
        design: Design | None,
        output_dir: str
    ) -> Path:
        """Save plan as markdown file."""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        title = design.title if design else issue.title
        filename = f"{date.today().isoformat()}-{_slugify(title)}.md"
        file_path = output_path / filename

        md_content = self._render_markdown(task_dag, issue, design)
        file_path.write_text(md_content)

        return file_path

    def _render_markdown(
        self,
        task_dag: TaskDAG,
        issue: Issue,
        design: Design | None
    ) -> str:
        """Render TaskDAG as markdown following writing-plans format."""
        title = design.title if design else issue.title
        goal = design.goal if design else issue.description
        architecture = design.architecture if design else "See task descriptions below."
        tech_stack = ", ".join(design.tech_stack) if design else "See implementation details."

        lines = [
            f"# {title} Implementation Plan",
            "",
            "> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.",
            "",
            f"**Goal:** {goal}",
            "",
            f"**Architecture:** {architecture}",
            "",
            f"**Tech Stack:** {tech_stack}",
            "",
            "---",
            "",
        ]

        for i, task in enumerate(task_dag.tasks, 1):
            lines.append(f"### Task {i}: {task.description}")
            lines.append("")

            if task.files:
                lines.append("**Files:**")
                for f in task.files:
                    if f.line_range:
                        lines.append(f"- {f.operation.capitalize()}: `{f.path}:{f.line_range}`")
                    else:
                        lines.append(f"- {f.operation.capitalize()}: `{f.path}`")
                lines.append("")

            for j, step in enumerate(task.steps, 1):
                lines.append(f"**Step {j}: {step.description}**")
                lines.append("")
                if step.code:
                    lines.append("```python")
                    lines.append(step.code)
                    lines.append("```")
                    lines.append("")
                if step.command:
                    lines.append(f"Run: `{step.command}`")
                if step.expected_output:
                    lines.append(f"Expected: {step.expected_output}")
                lines.append("")

            if task.commit_message:
                lines.append("**Commit:**")
                lines.append("```bash")
                if task.files:
                    file_paths = " ".join(f.path for f in task.files)
                    lines.append(f"git add {file_paths}")
                lines.append(f'git commit -m "{task.commit_message}"')
                lines.append("```")
                lines.append("")

            lines.append("---")
            lines.append("")

        return "\n".join(lines)
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_agents.py -v -k "architect"`
Expected: All architect tests passed

**Step 5: Commit**

```bash
git add amelia/agents/architect.py tests/unit/test_agents.py
git commit -m "feat(architect): refactor to return PlanOutput with rich TaskDAG and markdown"
```

---

### Task 7: Update CLI to support --design flag

**Files:**
- Modify: `amelia/main.py:114-182`
- Test: `tests/unit/test_cli.py` (create if needed)

**Step 1: Write the failing test**

```python
# Create tests/unit/test_cli.py

import pytest
from typer.testing import CliRunner
from unittest.mock import patch, AsyncMock, MagicMock
from pathlib import Path

from amelia.main import app


runner = CliRunner()


def test_plan_only_accepts_design_flag():
    """Verify --design flag is accepted (even if file doesn't exist, it should parse the arg)."""
    result = runner.invoke(app, ["plan-only", "TEST-1", "--design", "/nonexistent/design.md"])
    # Should fail due to file not found or settings, not due to unknown flag
    assert "--design" not in result.output or "Unknown option" not in result.output
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_cli.py::test_plan_only_accepts_design_flag -v`
Expected: FAILED with "No such option: --design"

**Step 3: Write minimal implementation**

```python
# Modify plan_only_command in amelia/main.py

@app.command(name="plan-only")
def plan_only_command(
    ctx: typer.Context,
    issue_id: str = typer.Argument(..., help="The ID of the issue to generate a plan for."),
    profile_name: str | None = typer.Option(
        None, "--profile", "-p", help="Specify the profile to use from settings.amelia.yaml."
    ),
    design_path: str | None = typer.Option(
        None, "--design", "-d", help="Path to design markdown file from brainstorming."
    ),
) -> None:
    """
    Generates a plan for the specified issue using the Architect agent without execution.
    """
    async def _run() -> None:
        settings = _safe_load_settings()
        active_profile = _get_active_profile(settings, profile_name)

        try:
            validate_profile(active_profile)
        except ValueError as e:
            typer.echo(f"Profile validation failed: {e}", err=True)
            raise typer.Exit(code=1) from None

        typer.echo(f"Generating plan for issue {issue_id} with profile: {active_profile.name}")

        project_manager = create_project_manager(active_profile)
        try:
            issue = project_manager.get_issue(issue_id)
        except ValueError as e:
            typer.echo(f"Error fetching issue: {e}", err=True)
            raise typer.Exit(code=1) from None

        # Parse design if provided
        design = None
        if design_path:
            from amelia.utils.design_parser import parse_design
            try:
                driver = DriverFactory.get_driver(active_profile.driver)
                design = await parse_design(design_path, driver)
                typer.echo(f"Loaded design from: {design_path}")
            except FileNotFoundError:
                typer.echo(f"Error: Design file not found: {design_path}", err=True)
                raise typer.Exit(code=1) from None

        architect = Architect(DriverFactory.get_driver(active_profile.driver))
        result = await architect.plan(
            issue,
            design=design,
            output_dir=active_profile.plan_output_dir
        )

        typer.echo("\n--- GENERATED PLAN ---")
        if result.task_dag and result.task_dag.tasks:
            for task in result.task_dag.tasks:
                deps = f" (Dependencies: {', '.join(task.dependencies)})" if task.dependencies else ""
                typer.echo(f"  - [{task.id}] {task.description}{deps}")

            typer.echo(f"\nPlan saved to: {result.markdown_path}")
        else:
            typer.echo("No plan generated.")

    asyncio.run(_run())
```

Also add import at top of file:
```python
from amelia.agents.architect import Architect, PlanOutput
```

And remove the old `from amelia.agents.architect import Architect` if it exists.

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_cli.py -v`
Expected: PASSED

**Step 5: Commit**

```bash
git add amelia/main.py tests/unit/test_cli.py
git commit -m "feat(cli): add --design flag to plan-only command"
```

---

### Task 8: Fix existing tests that use files_changed

**Files:**
- Modify: `tests/unit/test_state_models.py`
- Modify: `tests/conftest.py` (if needed)
- Run: full test suite

**Step 1: Search for files_changed usage**

Run: `uv run ruff check amelia tests`
Run: `grep -r "files_changed" tests/`

**Step 2: Update any tests using files_changed**

Remove or update any tests that reference `task.files_changed`.

**Step 3: Run full test suite**

Run: `uv run pytest`
Expected: All tests pass

**Step 4: Run linting and type checking**

Run: `uv run ruff check amelia tests`
Run: `uv run mypy amelia`
Expected: No errors

**Step 5: Commit**

```bash
git add -A
git commit -m "fix(tests): remove files_changed references after Task model update"
```

---

### Task 9: Final verification and cleanup

**Step 1: Run full test suite**

Run: `uv run pytest -v`
Expected: All tests pass

**Step 2: Run linting**

Run: `uv run ruff check amelia tests`
Run: `uv run ruff check --fix amelia tests` (if needed)
Expected: No issues

**Step 3: Run type checking**

Run: `uv run mypy amelia`
Expected: No errors

**Step 4: Test manually**

Run: `uv run amelia plan-only TEST-123 --help`
Expected: Shows --design flag in help

**Step 5: Final commit**

```bash
git add -A
git commit -m "chore: final cleanup for architect rich plans feature"
```

---

## Summary

After completing all tasks, the Architect agent will:
1. Accept optional `Design` object from brainstorming
2. Generate rich `TaskDAG` with `TaskStep` and `FileOperation`
3. Output markdown following writing-plans format
4. Save to configurable `profile.plan_output_dir`

The Developer agent refactor (to consume this rich structure) is tracked separately in `future-developer-agent-refactor.md`.
