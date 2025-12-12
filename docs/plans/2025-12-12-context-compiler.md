# Context Compiler Implementation Plan

> Implements the Context Compiler design from [brainstorming/2025-12-10-context-compiler-design.md](../brainstorming/2025-12-10-context-compiler-design.md)
>
> Also addresses:
> - [Gap 3: Prompt Prefix Stability](../analysis/context-engineering-gaps.md#gap-3-prompt-prefix-stability-for-cache-optimization)
> - [Gap 5: Agent Scope Isolation](../analysis/context-engineering-gaps.md#gap-5-agent-scope-isolation)

## Goals

1. **Context Compiler** (Gap 1): Replace ad-hoc context building with unified `ContextStrategy` pattern
2. **Prefix Stability** (Gap 3): Separate stable system prompts from variable context for cache optimization
3. **Scope Isolation** (Gap 5): Enforce minimal default context per agent type

## Prerequisites

- Design document reviewed and approved

## Tasks

### Phase 1: Core Types (Foundation)

#### Task 1.1: Create context.py with core types
**File**: `amelia/core/context.py` (new)

Create the core types:
- `ContextSection` - Named chunk of context for inspection
- `CompiledContext` - Result of context compilation (with prefix/suffix separation)
- `ContextStrategy` - ABC for agent-specific strategies
- `AgentScope` - Enum defining minimal context requirements per agent type

**Prefix Stability (Gap 3)**: System prompts are defined as class constants on each strategy, ensuring they never change across calls. This enables provider-side prompt caching.

**Scope Isolation (Gap 5)**: Each strategy defines its `ALLOWED_SECTIONS` - the minimal context it's permitted to compile. Attempting to add sections outside this allowlist raises an error.

Include shared helper methods:
- `get_current_task(state)` - Extract current task from plan
- `get_issue_summary(state)` - Format issue for context
- `to_messages(context)` - Convert to AgentMessage list

**Acceptance Criteria**:
- [ ] `ContextSection` Pydantic model with `name`, `content`, `source` fields
- [ ] `CompiledContext` Pydantic model with `system_prompt`, `sections`, `messages` fields
- [ ] `ContextStrategy` ABC with abstract `compile()` method
- [ ] `ContextStrategy.SYSTEM_PROMPT` class constant for stable prefix (Gap 3)
- [ ] `ContextStrategy.ALLOWED_SECTIONS` class constant for scope isolation (Gap 5)
- [ ] `validate_sections()` method that raises if section name not in allowlist
- [ ] Default `to_messages()` implementation handles both section-based and override modes
- [ ] Helper methods `get_current_task()` and `get_issue_summary()` implemented

#### Task 1.2: Unit tests for core types
**File**: `tests/unit/test_context.py` (new)

**Acceptance Criteria**:
- [ ] Test `ContextSection` serialization
- [ ] Test `CompiledContext` with sections converts to messages correctly
- [ ] Test `CompiledContext` with `messages` override bypasses sections
- [ ] Test `to_messages()` formats sections with `## {name}` headers
- [ ] Test helper methods return correct data from ExecutionState
- [ ] Test `SYSTEM_PROMPT` is immutable class constant (Gap 3)
- [ ] Test `validate_sections()` raises for disallowed sections (Gap 5)
- [ ] Test `validate_sections()` passes for allowed sections (Gap 5)

---

### Phase 2: Agent Strategies (Parallel)

> Tasks 2.1, 2.2, and 2.3 can be implemented in parallel.

#### Task 2.1: ArchitectContextStrategy
**File**: `amelia/agents/architect.py`

Create `ArchitectContextStrategy` that compiles minimal context for planning.

**Scope Isolation (Gap 5) - Allowed Sections**:
- `issue` - Issue title and description (required)
- `design` - Design document reference (optional)

**Prefix Stability (Gap 3) - System Prompt**:
```python
SYSTEM_PROMPT = """You are a senior software architect creating implementation plans.
You analyze issues and produce structured task DAGs with clear dependencies."""
```

**Changes**:
1. Add `ArchitectContextStrategy` class implementing `ContextStrategy`
2. Define `SYSTEM_PROMPT` class constant (stable prefix)
3. Define `ALLOWED_SECTIONS = {"issue", "design"}` (scope isolation)
4. Add `context_strategy` class attribute to `Architect`
5. Update `plan()` method to use strategy
6. Remove `_build_context()` method

**Acceptance Criteria**:
- [ ] `ArchitectContextStrategy.SYSTEM_PROMPT` is class constant (Gap 3)
- [ ] `ArchitectContextStrategy.ALLOWED_SECTIONS = {"issue", "design"}` (Gap 5)
- [ ] `compile()` returns `CompiledContext` with issue section
- [ ] Design context included only when available
- [ ] `Architect.plan()` uses strategy instead of `_build_context()`
- [ ] `_build_context()` method removed

#### Task 2.2: DeveloperContextStrategy
**File**: `amelia/agents/developer.py`

Create `DeveloperContextStrategy` that compiles minimal context for task execution.

**Scope Isolation (Gap 5) - Allowed Sections**:
- `task` - Current task description (required)
- `files` - File operations list (optional)
- `steps` - Step-by-step instructions (optional)

**Note**: Developer does NOT receive issue context or other agents' history. Only the current task from the TaskDAG.

**Prefix Stability (Gap 3) - System Prompt**:
```python
SYSTEM_PROMPT = """You are a senior developer executing tasks following TDD principles.
Run tests after each change. Follow the task steps exactly."""
```

**Changes**:
1. Add `DeveloperContextStrategy` class implementing `ContextStrategy`
2. Define `SYSTEM_PROMPT` class constant (stable prefix)
3. Define `ALLOWED_SECTIONS = {"task", "files", "steps"}` (scope isolation)
4. Add `context_strategy` class attribute to `Developer`
5. Update `_execute_agentic()` to use strategy
6. Remove `_build_task_prompt()` method

**Acceptance Criteria**:
- [ ] `DeveloperContextStrategy.SYSTEM_PROMPT` is class constant (Gap 3)
- [ ] `DeveloperContextStrategy.ALLOWED_SECTIONS = {"task", "files", "steps"}` (Gap 5)
- [ ] `compile()` returns `CompiledContext` with task sections
- [ ] Files section formatted as bullet list
- [ ] Steps section includes code blocks and commands
- [ ] `Developer._execute_agentic()` uses strategy
- [ ] `_build_task_prompt()` method removed

#### Task 2.3: ReviewerContextStrategy
**File**: `amelia/agents/reviewer.py`

Create `ReviewerContextStrategy` that compiles minimal context for code review.

**Scope Isolation (Gap 5) - Allowed Sections**:
- `task` - Task description being reviewed (required)
- `diff` - Code changes to review (required)
- `criteria` - Acceptance criteria (optional)

**Note**: Reviewer receives task description (what was supposed to be done) and the diff (what was done), NOT the full issue or developer's reasoning.

**Prefix Stability (Gap 3) - System Prompt Template**:
```python
SYSTEM_PROMPT_TEMPLATE = """You are an expert code reviewer with a focus on {persona} aspects.
Analyze the provided code changes and provide a comprehensive review."""
```

Note: The persona (e.g., "Security", "Performance") is the only variable in the system prompt. We use a template with minimal substitution to maximize cache hits across same-persona reviews.

**Changes**:
1. Add `ReviewerContextStrategy` class implementing `ContextStrategy`
2. Define `SYSTEM_PROMPT_TEMPLATE` class constant with `{persona}` placeholder
3. Define `ALLOWED_SECTIONS = {"task", "diff", "criteria"}` (scope isolation)
4. Add `context_strategy` class attribute to `Reviewer`
5. Update `_single_review()` to use strategy
6. Extract inline context building into strategy

**Acceptance Criteria**:
- [ ] `ReviewerContextStrategy.SYSTEM_PROMPT_TEMPLATE` is class constant (Gap 3)
- [ ] `ReviewerContextStrategy.ALLOWED_SECTIONS = {"task", "diff", "criteria"}` (Gap 5)
- [ ] `compile()` accepts persona and returns `CompiledContext`
- [ ] System prompt formatted with persona from template
- [ ] Task and diff sections properly formatted
- [ ] `Reviewer._single_review()` uses strategy
- [ ] Inline context building removed from `_single_review()`

---

### Phase 3: Strategy Tests (Parallel with Phase 2)

> Tasks 3.1, 3.2, and 3.3 can be implemented in parallel with each other and with Phase 2.

#### Task 3.1: Test ArchitectContextStrategy
**File**: `tests/unit/agents/test_architect_context.py` (new)

**Acceptance Criteria**:
- [ ] Test compile with issue only
- [ ] Test compile with issue + design
- [ ] Test sections have correct names and sources
- [ ] Test to_messages produces valid AgentMessage list
- [ ] Test `SYSTEM_PROMPT` is stable across multiple calls (Gap 3)
- [ ] Test only `issue` and `design` sections allowed (Gap 5)
- [ ] Test compile raises if attempting to add disallowed section (Gap 5)

#### Task 3.2: Test DeveloperContextStrategy
**File**: `tests/unit/agents/test_developer_context.py` (new)

**Acceptance Criteria**:
- [ ] Test compile with minimal task (description only)
- [ ] Test compile with task + files
- [ ] Test compile with task + files + steps
- [ ] Test steps include code blocks when present
- [ ] Test steps include commands when present
- [ ] Test raises ValueError when no current task
- [ ] Test `SYSTEM_PROMPT` is stable across multiple calls (Gap 3)
- [ ] Test only `task`, `files`, `steps` sections allowed (Gap 5)
- [ ] Test does NOT include issue or other agent history (Gap 5)

#### Task 3.3: Test ReviewerContextStrategy
**File**: `tests/unit/agents/test_reviewer_context.py` (new)

**Acceptance Criteria**:
- [ ] Test compile with code diff
- [ ] Test persona appears in system prompt
- [ ] Test task context included (not full issue)
- [ ] Test handles missing task description gracefully
- [ ] Test `SYSTEM_PROMPT_TEMPLATE` produces stable prefix per persona (Gap 3)
- [ ] Test only `task`, `diff`, `criteria` sections allowed (Gap 5)
- [ ] Test does NOT include issue or developer reasoning (Gap 5)

---

### Phase 4: Debug Logging

#### Task 4.1: Add context compilation logging
**Files**: All agent files

Add loguru debug logging when context is compiled:

```python
logger.debug(
    "Compiled context",
    agent="developer",
    sections=[s.name for s in context.sections],
    system_prompt_length=len(context.system_prompt) if context.system_prompt else 0
)
```

**Acceptance Criteria**:
- [ ] Each agent logs when `compile()` is called
- [ ] Log includes agent name
- [ ] Log includes section names (not content)
- [ ] Log includes system prompt length

---

### Phase 5: Integration Verification

#### Task 5.1: Verify existing tests pass
Run full test suite to ensure no regressions.

**Acceptance Criteria**:
- [ ] `uv run pytest` passes
- [ ] `uv run mypy amelia` passes
- [ ] `uv run ruff check amelia` passes

#### Task 5.2: Manual integration test
Run `amelia plan-only` on a test issue to verify the flow works end-to-end.

**Acceptance Criteria**:
- [ ] Architect generates plan successfully
- [ ] Debug logs show compiled context

---

## Execution Order

```
Phase 1 (Foundation)
    │
    ├─── Task 1.1: Create core types
    │         │
    │         └─── Task 1.2: Unit tests for core types
    │
    ▼
Phase 2 + 3 (Parallel)
    │
    ├─── Task 2.1: ArchitectContextStrategy ──┬── Task 3.1: Test Architect
    ├─── Task 2.2: DeveloperContextStrategy ──┼── Task 3.2: Test Developer
    └─── Task 2.3: ReviewerContextStrategy ───┴── Task 3.3: Test Reviewer
    │
    ▼
Phase 4 (Logging)
    │
    └─── Task 4.1: Add debug logging
    │
    ▼
Phase 5 (Verification)
    │
    ├─── Task 5.1: Run test suite
    └─── Task 5.2: Manual integration test
```

## Files Changed

| File | Change Type |
|------|-------------|
| `amelia/core/context.py` | **New** |
| `amelia/agents/architect.py` | Modified |
| `amelia/agents/developer.py` | Modified |
| `amelia/agents/reviewer.py` | Modified |
| `tests/unit/test_context.py` | **New** |
| `tests/unit/agents/test_architect_context.py` | **New** |
| `tests/unit/agents/test_developer_context.py` | **New** |
| `tests/unit/agents/test_reviewer_context.py` | **New** |

## Agent Scope Reference (Gap 5)

| Agent | Allowed Sections | Explicitly Excluded |
|-------|------------------|---------------------|
| **Architect** | `issue`, `design` | developer history, review history |
| **Developer** | `task`, `files`, `steps` | issue, other agents' reasoning, full plan |
| **Reviewer** | `task`, `diff`, `criteria` | issue, developer reasoning, architect output |

This enforces the principle: *"The default context for any agent should contain nearly nothing."*

## Risk Mitigation

1. **Breaking existing tests**: Run test suite after each strategy implementation
2. **State access patterns**: Strategies only access state through explicit methods
3. **Message format changes**: `to_messages()` default behavior matches current output format
4. **Scope too restrictive** (Gap 5): If an agent genuinely needs more context, add to `ALLOWED_SECTIONS` explicitly—this is intentional friction to prevent scope creep

## Success Criteria

**Gap 1 (Context Compiler)**:
- [ ] All three agents use `ContextStrategy` pattern
- [ ] Ad-hoc context methods (`_build_context`, `_build_task_prompt`) removed
- [ ] Debug logging enabled for context inspection

**Gap 3 (Prefix Stability)**:
- [ ] Each strategy has `SYSTEM_PROMPT` class constant
- [ ] System prompts never change across calls (same persona = same prefix)
- [ ] Variable content isolated to sections (suffix)

**Gap 5 (Scope Isolation)**:
- [ ] Each strategy has `ALLOWED_SECTIONS` defining minimal scope
- [ ] `validate_sections()` enforces allowlist
- [ ] Architect: only issue + design
- [ ] Developer: only task + files + steps (no issue, no history)
- [ ] Reviewer: only task + diff + criteria (no issue, no developer reasoning)

**Quality**:
- [ ] Unit test coverage for each strategy including Gap 3/5 behavior
- [ ] All existing tests pass
