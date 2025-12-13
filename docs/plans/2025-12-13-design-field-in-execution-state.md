# Design Field in ExecutionState Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add design field to ExecutionState so architect can include design context when generating task DAGs.

**Architecture:** Design is stored on ExecutionState and conditionally compiled into context by ArchitectContextStrategy. Other agents (Developer) don't include it. Design can be populated by a brainstorm node or externally provided.

**Tech Stack:** Pydantic, pytest

---

### Task 1: Add design field to ExecutionState

**Files:**
- Modify: `amelia/core/state.py:173-197`

**Step 1: Write the failing test**

Add to `tests/unit/test_state.py`:

```python
def test_execution_state_accepts_design_field():
    """ExecutionState should accept optional design field."""
    from amelia.core.types import Design, Profile

    profile = Profile(name="test", driver="cli:claude")
    design = Design(
        title="Test Design",
        goal="Test goal",
        architecture="Test architecture",
        tech_stack=["Python"],
        components=["Component A"],
        raw_content="# Test Design\n\nRaw content here",
    )
    state = ExecutionState(profile=profile, design=design)

    assert state.design is not None
    assert state.design.title == "Test Design"


def test_execution_state_design_defaults_to_none():
    """ExecutionState design should default to None."""
    from amelia.core.types import Profile

    profile = Profile(name="test", driver="cli:claude")
    state = ExecutionState(profile=profile)

    assert state.design is None
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_state.py::test_execution_state_accepts_design_field tests/unit/test_state.py::test_execution_state_design_defaults_to_none -v`

Expected: FAIL with "unexpected keyword argument 'design'"

**Step 3: Add Design import and field to ExecutionState**

In `amelia/core/state.py`, update import on line 8:

```python
from amelia.core.types import Design, Issue, Profile
```

Add field to `ExecutionState` class (after line 189, the `issue` field):

```python
    design: Design | None = None
```

Update docstring (after line 180, add to Attributes):

```python
        design: Optional design context from brainstorming or external upload.
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_state.py::test_execution_state_accepts_design_field tests/unit/test_state.py::test_execution_state_design_defaults_to_none -v`

Expected: PASS

**Step 5: Commit**

```bash
git add amelia/core/state.py tests/unit/test_state.py
git commit -m "feat(state): add optional design field to ExecutionState"
```

---

### Task 2: Update mock_execution_state_factory to support design

**Files:**
- Modify: `tests/conftest.py:159-180`

**Step 1: Write the failing test**

Add to `tests/unit/test_state.py`:

```python
def test_mock_execution_state_factory_accepts_design(
    mock_execution_state_factory, mock_design_factory
):
    """mock_execution_state_factory should accept design parameter."""
    design = mock_design_factory(title="Factory Design")
    state = mock_execution_state_factory(design=design)

    assert state.design is not None
    assert state.design.title == "Factory Design"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_state.py::test_mock_execution_state_factory_accepts_design -v`

Expected: FAIL (design not passed through or test fails)

**Step 3: Update mock_execution_state_factory**

In `tests/conftest.py`, update the factory function signature (around line 161):

```python
def _create(
    profile: Profile | None = None,
    profile_preset: str = "cli_single",
    issue: Issue | None = None,
    design: Design | None = None,
    plan: TaskDAG | None = None,
    code_changes_for_review: str | None = None,
    **kwargs
) -> ExecutionState:
```

Add Design import at top of file if not present:

```python
from amelia.core.types import Design, Issue, Profile
```

Pass design to ExecutionState construction (around line 175):

```python
return ExecutionState(
    profile=profile,
    issue=issue,
    design=design,
    plan=plan,
    code_changes_for_review=code_changes_for_review,
    **kwargs
)
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_state.py::test_mock_execution_state_factory_accepts_design -v`

Expected: PASS

**Step 5: Commit**

```bash
git add tests/conftest.py tests/unit/test_state.py
git commit -m "test(conftest): add design parameter to mock_execution_state_factory"
```

---

### Task 3: Add _format_design_section helper method

**Files:**
- Modify: `amelia/agents/architect.py:52-108`
- Test: `tests/unit/agents/test_architect_context.py`

**Step 1: Write the failing test**

Add to `tests/unit/agents/test_architect_context.py`:

```python
def test_format_design_section_structures_design_fields(
    strategy, mock_design_factory
):
    """Test _format_design_section formats design as structured markdown."""
    design = mock_design_factory(
        title="Authentication System",
        goal="Build secure JWT-based authentication",
        architecture="Layered architecture with service and repository patterns",
        tech_stack=["FastAPI", "PostgreSQL", "Redis"],
        components=["AuthService", "TokenManager", "UserRepository"],
        data_flow="Request -> AuthService -> TokenManager -> Response",
        testing_strategy="Unit tests for services, integration for API",
    )

    result = strategy._format_design_section(design)

    assert "## Goal" in result
    assert "Build secure JWT-based authentication" in result
    assert "## Architecture" in result
    assert "Layered architecture" in result
    assert "## Tech Stack" in result
    assert "- FastAPI" in result
    assert "- PostgreSQL" in result
    assert "## Components" in result
    assert "- AuthService" in result
    assert "## Data Flow" in result
    assert "Request -> AuthService" in result
    assert "## Testing Strategy" in result
    assert "Unit tests for services" in result
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/agents/test_architect_context.py::TestArchitectContextStrategy::test_format_design_section_structures_design_fields -v`

Expected: FAIL with "has no attribute '_format_design_section'"

**Step 3: Add _format_design_section method**

Add to `ArchitectContextStrategy` class in `amelia/agents/architect.py` (after line 108, before `compile`):

```python
    def _format_design_section(self, design: Design) -> str:
        """Format Design into structured markdown for context.

        Args:
            design: The design to format.

        Returns:
            Formatted markdown string with design fields.
        """
        parts = []

        parts.append(f"## Goal\n\n{design.goal}")
        parts.append(f"## Architecture\n\n{design.architecture}")

        if design.tech_stack:
            tech_list = "\n".join(f"- {tech}" for tech in design.tech_stack)
            parts.append(f"## Tech Stack\n\n{tech_list}")

        if design.components:
            comp_list = "\n".join(f"- {comp}" for comp in design.components)
            parts.append(f"## Components\n\n{comp_list}")

        if design.data_flow:
            parts.append(f"## Data Flow\n\n{design.data_flow}")

        if design.error_handling:
            parts.append(f"## Error Handling\n\n{design.error_handling}")

        if design.testing_strategy:
            parts.append(f"## Testing Strategy\n\n{design.testing_strategy}")

        if design.conventions:
            parts.append(f"## Conventions\n\n{design.conventions}")

        if design.relevant_files:
            files_list = "\n".join(f"- `{f}`" for f in design.relevant_files)
            parts.append(f"## Relevant Files\n\n{files_list}")

        return "\n\n".join(parts)
```

Add Design import at top of file if not present (around line 12):

```python
from amelia.core.types import Design, Issue
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/agents/test_architect_context.py::TestArchitectContextStrategy::test_format_design_section_structures_design_fields -v`

Expected: PASS

**Step 5: Commit**

```bash
git add amelia/agents/architect.py tests/unit/agents/test_architect_context.py
git commit -m "feat(architect): add _format_design_section helper method"
```

---

### Task 4: Update compile() to include design section

**Files:**
- Modify: `amelia/agents/architect.py:109-145`
- Test: `tests/unit/agents/test_architect_context.py`

**Step 1: Write the failing test**

Add to `tests/unit/agents/test_architect_context.py`:

```python
def test_compile_includes_design_section_when_present(
    strategy, mock_execution_state_factory, mock_issue_factory, mock_design_factory
):
    """Test compile includes design section when state.design is set."""
    issue = mock_issue_factory(title="Build auth", description="Auth system")
    design = mock_design_factory(
        title="Auth Design",
        goal="Secure authentication",
        architecture="JWT-based",
    )
    state = mock_execution_state_factory(issue=issue, design=design)

    context = strategy.compile(state)

    # Should have two sections: issue and design
    assert len(context.sections) == 2
    section_names = [s.name for s in context.sections]
    assert "issue" in section_names
    assert "design" in section_names

    # Find design section
    design_section = next(s for s in context.sections if s.name == "design")
    assert "Secure authentication" in design_section.content
    assert "JWT-based" in design_section.content
    assert design_section.source == "state.design"


def test_compile_excludes_design_section_when_none(
    strategy, mock_execution_state_factory, mock_issue_factory
):
    """Test compile excludes design section when state.design is None."""
    issue = mock_issue_factory(title="Build feature", description="Feature desc")
    state = mock_execution_state_factory(issue=issue, design=None)

    context = strategy.compile(state)

    # Should have only issue section
    assert len(context.sections) == 1
    assert context.sections[0].name == "issue"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/agents/test_architect_context.py::TestArchitectContextStrategy::test_compile_includes_design_section_when_present tests/unit/agents/test_architect_context.py::TestArchitectContextStrategy::test_compile_excludes_design_section_when_none -v`

Expected: FAIL - first test fails (only 1 section, no design)

**Step 3: Update compile() to include design section**

Replace the `compile` method body in `amelia/agents/architect.py` (lines 109-145):

```python
    def compile(self, state: ExecutionState) -> CompiledContext:
        """Compile ExecutionState into context for planning.

        Args:
            state: The current execution state.

        Returns:
            CompiledContext with system prompt and relevant sections.

        Raises:
            ValueError: If required sections are missing.
        """
        sections: list[ContextSection] = []

        # Issue section (required)
        issue_summary = self.get_issue_summary(state)
        if not issue_summary:
            raise ValueError("Issue context is required for planning")

        sections.append(
            ContextSection(
                name="issue",
                content=issue_summary,
                source="state.issue",
            )
        )

        # Design section (optional)
        if state.design:
            design_content = self._format_design_section(state.design)
            sections.append(
                ContextSection(
                    name="design",
                    content=design_content,
                    source="state.design",
                )
            )

        # Validate all sections before returning
        self.validate_sections(sections)

        return CompiledContext(
            system_prompt=self.SYSTEM_PROMPT,
            sections=sections,
        )
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/agents/test_architect_context.py::TestArchitectContextStrategy::test_compile_includes_design_section_when_present tests/unit/agents/test_architect_context.py::TestArchitectContextStrategy::test_compile_excludes_design_section_when_none -v`

Expected: PASS

**Step 5: Commit**

```bash
git add amelia/agents/architect.py tests/unit/agents/test_architect_context.py
git commit -m "feat(architect): include design section in compile() when present"
```

---

### Task 5: Remove design parameter from Architect.plan()

**Files:**
- Modify: `amelia/agents/architect.py:166-212`
- Modify: `amelia/agents/architect.py:214-247`
- Test: `tests/unit/agents/test_architect.py`

**Step 1: Check existing tests for plan() signature**

Run: `uv run pytest tests/unit/agents/test_architect.py -v --collect-only`

Review which tests call `plan()` with design parameter.

**Step 2: Write the failing test**

Add to `tests/unit/agents/test_architect.py` (or update existing):

```python
async def test_plan_reads_design_from_state(
    mock_driver, mock_execution_state_factory, mock_issue_factory, mock_design_factory
):
    """Test plan() reads design from state, not from parameter."""
    issue = mock_issue_factory(title="Build feature", description="Feature desc")
    design = mock_design_factory(title="Feature Design", goal="Build it well")
    state = mock_execution_state_factory(issue=issue, design=design)

    architect = Architect(driver=mock_driver)
    result = await architect.plan(state)

    # Verify plan was generated (driver was called)
    assert result.task_dag is not None
```

**Step 3: Run test to verify current behavior**

Run: `uv run pytest tests/unit/agents/test_architect.py::test_plan_reads_design_from_state -v`

**Step 4: Update plan() to remove design parameter**

Update `Architect.plan()` signature and docstring in `amelia/agents/architect.py` (lines 166-212):

```python
    async def plan(
        self,
        state: ExecutionState,
        output_dir: str | None = None
    ) -> PlanOutput:
        """Generate a development plan from an issue and optional design.

        Creates a structured TaskDAG and saves a markdown version for human review.
        Design context is read from state.design when available.

        Args:
            state: The execution state containing the issue and optional design.
            output_dir: Directory path where the markdown plan will be saved.
                If None, uses profile's plan_output_dir from state.

        Returns:
            PlanOutput containing the task DAG and path to the saved markdown file.

        Raises:
            ValueError: If no issue is present in the state.
        """
        if not state.issue:
            raise ValueError("Cannot generate plan: no issue in ExecutionState")

        # Use profile's output directory if not specified
        if output_dir is None:
            output_dir = state.profile.plan_output_dir

        # Compile context using strategy
        strategy = self.context_strategy()
        compiled_context = strategy.compile(state)

        logger.debug(
            "Compiled context",
            agent="architect",
            sections=[s.name for s in compiled_context.sections],
            system_prompt_length=len(compiled_context.system_prompt) if compiled_context.system_prompt else 0
        )

        # Generate task DAG using compiled context
        task_dag = await self._generate_task_dag(compiled_context, state.issue, strategy)

        # Save markdown (design now comes from state)
        markdown_path = self._save_markdown(task_dag, state.issue, state.design, output_dir)

        return PlanOutput(task_dag=task_dag, markdown_path=markdown_path)
```

**Step 5: Update _generate_task_dag() to remove design parameter**

Update `_generate_task_dag()` signature in `amelia/agents/architect.py` (lines 214-247):

```python
    async def _generate_task_dag(
        self,
        compiled_context: CompiledContext,
        issue: Issue,
        strategy: ArchitectContextStrategy,
    ) -> TaskDAG:
        """Generate TaskDAG using LLM.

        Args:
            compiled_context: Compiled context from the strategy.
            issue: Original issue being planned.
            strategy: The context strategy instance for prompt generation.

        Returns:
            TaskDAG containing structured tasks with TDD steps.
        """
        task_system_prompt = strategy.get_task_generation_system_prompt()
        task_user_prompt = strategy.get_task_generation_user_prompt()

        # Convert compiled context to messages (user messages only)
        base_messages = strategy.to_messages(compiled_context)

        # Prepend task-specific system prompt and append user prompt
        messages = [
            AgentMessage(role="system", content=task_system_prompt),
            *base_messages,
            AgentMessage(role="user", content=task_user_prompt),
        ]

        response = await self.driver.generate(messages=messages, schema=TaskListResponse)

        return TaskDAG(tasks=response.tasks, original_issue=issue.id)
```

**Step 6: Run tests to verify**

Run: `uv run pytest tests/unit/agents/test_architect.py -v`

Expected: PASS (may need to update other tests that pass design parameter)

**Step 7: Commit**

```bash
git add amelia/agents/architect.py tests/unit/agents/test_architect.py
git commit -m "refactor(architect): remove design parameter from plan(), read from state"
```

---

### Task 6: Update callers of Architect.plan()

**Files:**
- Search and update any callers passing design parameter

**Step 1: Find all callers**

Run: `uv run ruff check amelia tests --select=E --ignore=E501` to check for errors after signature change.

Or search:
```bash
grep -r "\.plan(" amelia/ --include="*.py" | grep -v "__pycache__"
```

**Step 2: Update callers to set state.design instead**

If any caller was:
```python
await architect.plan(state, design=design)
```

Change to:
```python
state.design = design
await architect.plan(state)
```

**Step 3: Run full test suite**

Run: `uv run pytest tests/unit/ -v`

Expected: PASS

**Step 4: Commit**

```bash
git add -A
git commit -m "refactor: update Architect.plan() callers to use state.design"
```

---

### Task 7: Run type checking and linting

**Files:**
- All modified files

**Step 1: Run mypy**

Run: `uv run mypy amelia`

Expected: No errors

**Step 2: Run ruff**

Run: `uv run ruff check amelia tests`

Expected: No errors (or fix any that appear)

**Step 3: Run full test suite**

Run: `uv run pytest`

Expected: All tests pass

**Step 4: Final commit if any fixes needed**

```bash
git add -A
git commit -m "chore: fix type and lint issues"
```

---

Plan complete and saved to `docs/plans/2025-12-13-design-field-in-execution-state.md`. Two execution options:

**1. Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

Which approach?
