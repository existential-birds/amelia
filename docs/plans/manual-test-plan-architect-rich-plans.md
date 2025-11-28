# Manual Test Plan: Architect Rich Plans Feature

## Overview

This test plan validates the architect rich plans implementation which enables the Architect agent to generate rich, actionable development plans with TDD steps, exact file paths, and complete code snippets.

---

## Prerequisites

- [ ] All automated tests pass: `uv run pytest`
- [ ] Linting passes: `uv run ruff check amelia tests`
- [ ] Type checking passes: `uv run mypy amelia`

---

## Test 1: CLI Help Verification

**Objective:** Verify the `--design` flag appears in CLI help.

**Steps:**
```bash
uv run amelia plan-only --help
```

**Expected:**
- `--design` / `-d` flag is listed
- Help text shows: "Path to design markdown file from brainstorming."

---

## Test 2: Plan-Only Without Design

**Objective:** Verify basic plan generation works without a design file.

**Steps:**
```bash
uv run amelia plan-only TEST-001 --profile <your-profile>
```

**Expected:**
- Plan is generated successfully
- Markdown file is saved to `docs/plans/` directory
- Output shows task list with IDs and descriptions
- Output shows path to saved markdown file

---

## Test 3: Plan-Only With Design File

**Objective:** Verify plan generation incorporates design context.

**Setup:**
Create a test design file at `/tmp/test-design.md`:
```markdown
# User Authentication Feature

## Goal
Add JWT-based user authentication to the API.

## Architecture
- Middleware-based token validation
- Stateless authentication using JWT
- Refresh token rotation

## Tech Stack
- PyJWT for token handling
- FastAPI middleware
- Redis for token blacklist

## Components
- AuthMiddleware
- TokenService
- UserRepository

## Data Flow
Request → AuthMiddleware → TokenService → Handler

## Testing Strategy
Unit tests for token validation, integration tests for auth flow.
```

**Steps:**
```bash
uv run amelia plan-only TEST-002 --profile <your-profile> --design /tmp/test-design.md
```

**Expected:**
- Output shows: "Loaded design from: /tmp/test-design.md"
- Generated plan includes design context (JWT, middleware, etc.)
- Tasks follow TDD structure with steps
- Markdown file is saved with design title in filename

---

## Test 4: Design File Not Found Error

**Objective:** Verify proper error handling for missing design files.

**Steps:**
```bash
uv run amelia plan-only TEST-003 --profile <your-profile> --design /nonexistent/design.md
```

**Expected:**
- Error message: "Error: Design file not found: /nonexistent/design.md"
- Exit code: 1

---

## Test 5: Generated Markdown Format

**Objective:** Verify the generated markdown follows the writing-plans format.

**Steps:**
1. Generate a plan using Test 2 or Test 3
2. Open the generated markdown file

**Expected markdown structure:**
```markdown
# <Title> Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans...

**Goal:** <goal description>

**Architecture:** <architecture description>

**Tech Stack:** <comma-separated list>

---

### Task 1: <description>

**Files:**
- Create: `path/to/file.py`
- Modify: `path/to/other.py:10-25`

**Step 1: <description>**

```python
<code snippet>
```

Run: `<command>`
Expected: <expected output>

**Commit:**
```bash
git add <files>
git commit -m "<conventional commit message>"
```

---
```

---

## Test 6: Task Model Structure

**Objective:** Verify Task objects have the new fields.

**Steps:**
```python
# In Python REPL or test script
from amelia.core.state import Task, TaskStep, FileOperation

task = Task(
    id="1",
    description="Test task",
    files=[FileOperation(operation="create", path="src/test.py")],
    steps=[TaskStep(description="Write test", code="def test(): pass")],
    commit_message="feat: add test"
)

print(f"Files: {task.files}")
print(f"Steps: {task.steps}")
print(f"Commit: {task.commit_message}")
```

**Expected:**
- Task has `files` as `list[FileOperation]`
- Task has `steps` as `list[TaskStep]`
- Task has `commit_message` as `str | None`

---

## Test 7: Design Model Structure

**Objective:** Verify Design model has all expected fields.

**Steps:**
```python
from amelia.core.types import Design

design = Design(
    title="Test Feature",
    goal="Test goal",
    architecture="Test arch",
    tech_stack=["Python", "FastAPI"],
    components=["ComponentA"],
    data_flow="A -> B -> C",
    error_handling="Return 500 on error",
    testing_strategy="Unit tests",
    relevant_files=["src/main.py"],
    conventions="Use async/await",
    raw_content="# Raw markdown"
)

print(f"Title: {design.title}")
print(f"Optional fields: {design.data_flow}, {design.conventions}")
```

**Expected:**
- All required fields present
- Optional fields default to `None` or empty list

---

## Test 8: Profile Configuration

**Objective:** Verify Profile uses `plan_output_dir` instead of `plan_output_template`.

**Steps:**
```python
from amelia.core.types import Profile

# Default
p1 = Profile(name="test", driver="api:openai")
print(f"Default output dir: {p1.plan_output_dir}")

# Custom
p2 = Profile(name="test", driver="api:openai", plan_output_dir="custom/plans")
print(f"Custom output dir: {p2.plan_output_dir}")
```

**Expected:**
- Default: `docs/plans`
- Custom: `custom/plans`
- No `plan_output_template` attribute

---

## Test 9: Orchestrator Integration

**Objective:** Verify orchestrator correctly handles PlanOutput from Architect.

**Steps:**
Run the full workflow (requires valid tracker configuration):
```bash
uv run amelia start TEST-001 --profile <your-profile>
```

**Expected:**
- Architect generates plan successfully
- Plan is stored in state as TaskDAG (not PlanOutput)
- Subsequent steps (Developer, Reviewer) can access `state.plan.tasks`

---

## Cleanup

After testing, clean up generated files:
```bash
rm -f docs/plans/*test*.md
rm -f /tmp/test-design.md
```

---

## Summary Checklist

- [ ] Test 1: CLI help shows --design flag
- [ ] Test 2: Plan-only works without design
- [ ] Test 3: Plan-only incorporates design context
- [ ] Test 4: Missing design file shows error
- [ ] Test 5: Generated markdown follows format
- [ ] Test 6: Task model has new fields
- [ ] Test 7: Design model structure correct
- [ ] Test 8: Profile uses plan_output_dir
- [ ] Test 9: Orchestrator handles PlanOutput correctly
