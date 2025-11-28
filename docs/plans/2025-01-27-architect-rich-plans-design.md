# Architect Rich Plans Design

## Goal

Refactor the Architect agent to generate rich, actionable development plans following the writing-plans skill pattern, producing both a structured `TaskDAG` for downstream agents and a markdown file for human review.

## Architecture

The Architect receives an optional `Design` object (parsed from brainstorming markdown) alongside the `Issue`. It uses the LLM to generate a rich `TaskDAG` with bite-sized TDD steps, exact file paths, complete code snippets, and commands with expected output. The plan is also rendered to markdown following the writing-plans skill format.

## Tech Stack

- Pydantic models for `Design`, `TaskStep`, `FileOperation`, enhanced `Task`
- LLM driver for design parsing and plan generation
- Markdown templating for human-readable output

---

## Data Models

### TaskStep

```python
class TaskStep(BaseModel):
    """A single step within a task (2-5 minutes of work)."""
    description: str
    code: str | None = None
    command: str | None = None
    expected_output: str | None = None
```

### FileOperation

```python
class FileOperation(BaseModel):
    """A file to be created, modified, or tested."""
    operation: Literal["create", "modify", "test"]
    path: str
    line_range: str | None = None
```

### Task (Enhanced)

```python
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

### Design

```python
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

---

## Components

### Design Parser (`amelia/utils/design_parser.py`)

```python
async def parse_design(path: str | Path, driver: DriverInterface) -> Design:
    """
    Parse a brainstorming markdown file into a structured Design.
    Uses the LLM driver to extract structured fields from freeform markdown.
    """
```

- Reads markdown file
- Uses LLM to extract structured fields
- Preserves original content in `raw_content`

### Profile Configuration

```python
class Profile(BaseModel):
    # ... existing fields ...
    plan_output_dir: str = "docs/plans"
```

### Architect Agent

```python
class PlanOutput(BaseModel):
    """Output from architect planning."""
    task_dag: TaskDAG
    markdown_path: Path

class Architect:
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
```

**Behavior:**
- If `design` provided: uses rich context for detailed planning
- If `design` is None: falls back to Issue-only planning (current behavior)
- Generates bite-sized steps (2-5 min each)
- Includes exact file paths, complete code, commands with expected output
- Follows TDD flow: test -> fail -> implement -> pass -> commit
- Saves markdown to `{output_dir}/{date}-{title}.md`

### Markdown Output Format

```markdown
# {title} Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** {goal}

**Architecture:** {architecture}

**Tech Stack:** {tech_stack}

---

### Task 1: {description}

**Files:**
- Create: `path/to/new.py`
- Modify: `path/to/existing.py:10-25`
- Test: `tests/path/to/test.py`

**Step 1: Write the failing test**
```python
{code}
```

**Step 2: Run test to verify it fails**
Run: `{command}`
Expected: {expected_output}

**Step 3: Write minimal implementation**
```python
{code}
```

**Step 4: Run test to verify it passes**
Run: `{command}`
Expected: {expected_output}

**Step 5: Commit**
```bash
git add {files}
git commit -m "{commit_message}"
```
```

---

## Files Changed

**Create:**
- `amelia/utils/design_parser.py`

**Modify:**
- `amelia/core/types.py` - add `Design`, add `plan_output_dir` to `Profile`
- `amelia/core/state.py` - add `TaskStep`, `FileOperation`, enhance `Task`
- `amelia/agents/architect.py` - refactor `plan()`, add `PlanOutput`, markdown generation
- `amelia/cli/main.py` - add `--design` flag support
- `tests/` - update fixtures and tests

---

## Out of Scope

- Developer agent refactor to consume rich task structure (see `future-developer-agent-refactor.md`)
- Orchestrator updates for task-by-task review loop
