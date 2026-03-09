# Reviewer Skills Internalization Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Internalize beagle review skills into the Amelia repo, inject them into reviewer prompts server-side for driver-agnostic code review, add configurable review types, and add on-demand review from the dashboard.

**Architecture:** Review skills are plain markdown files stored in `amelia/skills/review/`. A Python registry maps technology tags to skill files. At review time, `detect_stack()` inspects the git diff to identify technologies, `load_skills()` resolves and concatenates the relevant markdown, and the result is injected into the reviewer prompt before it reaches the LLM. Multiple review types (general, security) trigger separate reviewer runs. An API endpoint enables on-demand review from the dashboard.

**Tech Stack:** Python 3.12, Pydantic, FastAPI, React/TypeScript, Vitest

---

### Task 1: Create skill files directory and copy beagle skills

**Files:**
- Create: `amelia/skills/__init__.py`
- Create: `amelia/skills/review/__init__.py`
- Create: `amelia/skills/review/general.md`
- Create: `amelia/skills/review/verification.md`
- Create: `amelia/skills/review/python/python.md`
- Create: `amelia/skills/review/python/pytest.md`
- Create: `amelia/skills/review/python/fastapi.md`
- Create: `amelia/skills/review/python/sqlalchemy.md`
- Create: `amelia/skills/review/python/postgres.md`
- Create: `amelia/skills/review/react/shadcn.md`
- Create: `amelia/skills/review/react/vitest.md`
- Create: `amelia/skills/review/react/react-router.md`
- Create: `amelia/skills/review/react/react-flow.md`
- Create: `amelia/skills/review/go/go.md`
- Create: `amelia/skills/review/go/go-testing.md`
- Create: `amelia/skills/review/go/go-concurrency.md`
- Create: `amelia/skills/review/go/go-middleware.md`
- Create: `amelia/skills/review/elixir/elixir.md`
- Create: `amelia/skills/review/elixir/phoenix.md`
- Create: `amelia/skills/review/elixir/liveview.md`
- Create: `amelia/skills/review/elixir/exunit.md`
- Create: `amelia/skills/review/elixir/elixir-security.md`
- Create: `amelia/skills/review/elixir/elixir-performance.md`
- Create: `amelia/skills/review/swift/swift.md`
- Create: `amelia/skills/review/swift/swiftui.md`
- Create: `amelia/skills/review/swift/combine.md`
- Create: `amelia/skills/review/security/general.md`
- Modify: `pyproject.toml:50-52` (add `amelia/skills/**/*.md` to artifacts)

**Step 1: Create directory structure and empty `__init__.py` files**

```bash
mkdir -p amelia/skills/review/{python,react,go,elixir,swift,security}
touch amelia/skills/__init__.py
```

**Step 2: Copy skill SKILL.md files from beagle**

Copy each beagle skill's `SKILL.md` content (stripping the YAML frontmatter) to the corresponding Amelia path. The source files are at `../beagle/plugins/beagle-{lang}/skills/{skill-name}/SKILL.md`.

Mapping:
- `beagle-python/skills/python-code-review/SKILL.md` → `amelia/skills/review/python/python.md`
- `beagle-python/skills/pytest-code-review/SKILL.md` → `amelia/skills/review/python/pytest.md`
- `beagle-python/skills/fastapi-code-review/SKILL.md` → `amelia/skills/review/python/fastapi.md`
- `beagle-python/skills/sqlalchemy-code-review/SKILL.md` → `amelia/skills/review/python/sqlalchemy.md`
- `beagle-python/skills/postgres-code-review/SKILL.md` → `amelia/skills/review/python/postgres.md`
- `beagle-python/skills/review-verification-protocol/SKILL.md` → `amelia/skills/review/verification.md`
- `beagle-react/skills/shadcn-code-review/SKILL.md` → `amelia/skills/review/react/shadcn.md`
- `beagle-react/skills/vitest-testing/SKILL.md` → `amelia/skills/review/react/vitest.md`
- `beagle-react/skills/react-router-code-review/SKILL.md` → `amelia/skills/review/react/react-router.md`
- `beagle-react/skills/react-flow-code-review/SKILL.md` → `amelia/skills/review/react/react-flow.md`
- `beagle-go/skills/go-code-review/SKILL.md` → `amelia/skills/review/go/go.md`
- `beagle-go/skills/go-testing-code-review/SKILL.md` → `amelia/skills/review/go/go-testing.md`
- `beagle-go/skills/go-concurrency-web/SKILL.md` → `amelia/skills/review/go/go-concurrency.md`
- `beagle-go/skills/go-middleware/SKILL.md` → `amelia/skills/review/go/go-middleware.md`
- `beagle-elixir/skills/elixir-code-review/SKILL.md` → `amelia/skills/review/elixir/elixir.md`
- `beagle-elixir/skills/phoenix-code-review/SKILL.md` → `amelia/skills/review/elixir/phoenix.md`
- `beagle-elixir/skills/liveview-code-review/SKILL.md` → `amelia/skills/review/elixir/liveview.md`
- `beagle-elixir/skills/exunit-code-review/SKILL.md` → `amelia/skills/review/elixir/exunit.md`
- `beagle-elixir/skills/elixir-security-review/SKILL.md` → `amelia/skills/review/elixir/elixir-security.md`
- `beagle-elixir/skills/elixir-performance-review/SKILL.md` → `amelia/skills/review/elixir/elixir-performance.md`
- `beagle-ios/skills/swift-code-review/SKILL.md` → `amelia/skills/review/swift/swift.md`
- `beagle-ios/skills/swiftui-code-review/SKILL.md` → `amelia/skills/review/swift/swiftui.md`
- `beagle-ios/skills/combine-code-review/SKILL.md` → `amelia/skills/review/swift/combine.md`

For `general.md` and `security/general.md`, these are new files we write (not copied from beagle). Content TBD in Step 3.

When stripping frontmatter: remove the `---` delimited YAML block at the top of each file. Keep everything after.

Also remove references to external files that no longer exist. Replace lines like:
- `Load and follow [review-verification-protocol](../review-verification-protocol/SKILL.md)` → `Refer to the verification protocol guidelines provided separately.`
- `[references/foo.md](references/foo.md)` → just the text label (e.g., `references/foo.md` as plain text, since we're not including reference docs)

**Step 3: Write general.md and security/general.md**

`amelia/skills/review/general.md`:
```markdown
# General Code Review Guidelines

## Review Priorities (in order)
1. Correctness — Does the code do what it claims?
2. Security — Are there vulnerabilities (injection, auth bypass, data exposure)?
3. Reliability — Error handling, edge cases, resource cleanup
4. Maintainability — Readability, naming, separation of concerns
5. Performance — Only flag measurable issues, not premature optimization

## What NOT to Flag
- Style preferences already enforced by linters (formatting, import order)
- Hypothetical future issues with no current evidence
- "I would have done it differently" without a concrete problem
- Test code not meeting production-level standards (test helpers can be pragmatic)

## Issue Format
For each issue found, use this format:
1. [FILE:LINE] ISSUE_TITLE
   - Issue: What's wrong
   - Why: Why it matters (bug, security, reliability)
   - Fix: Specific recommended fix
```

`amelia/skills/review/security/general.md`:
```markdown
# Security Code Review

Focus exclusively on security vulnerabilities and risks.

## Checklist
- [ ] No SQL injection (parameterized queries only)
- [ ] No command injection (no shell=True with user input, no string interpolation in commands)
- [ ] No XSS (user input escaped in HTML output)
- [ ] No hardcoded secrets (API keys, passwords, tokens)
- [ ] Authentication checks on all protected endpoints
- [ ] Authorization checks (users can only access their own resources)
- [ ] No path traversal (user input not used in file paths without validation)
- [ ] Sensitive data not logged or exposed in error messages
- [ ] CORS configured restrictively (not wildcard for authenticated endpoints)
- [ ] Dependencies don't have known CVEs
- [ ] Cryptographic operations use standard libraries (no custom crypto)
- [ ] Session management follows best practices (secure cookies, token rotation)

## Severity Guide
- **Critical**: Exploitable vulnerability (injection, auth bypass, data exposure)
- **Major**: Weak security control that could be exploited with effort
- **Minor**: Defense-in-depth improvement, hardening suggestion
```

**Step 4: Update pyproject.toml to include skill markdown files in wheel**

In `pyproject.toml:50-52`, add `amelia/skills/**/*.md` to artifacts:

```toml
[tool.hatch.build.targets.wheel]
packages = ["amelia"]
artifacts = ["amelia/server/static/*", "amelia/skills/**/*.md"]
```

**Step 5: Verify files exist**

Run: `find amelia/skills -name '*.md' | sort | wc -l`
Expected: 27 files (5 python + 4 react + 4 go + 6 elixir + 3 swift + general + verification + security/general + 2 more for subdirectory count variations — verify exact count matches step 2 list)

Run: `python -c "from amelia.skills import review; print('import ok')"`
Expected: `import ok`

**Step 6: Commit**

```bash
git add amelia/skills/ pyproject.toml
git commit -m "feat: internalize beagle review skills into amelia/skills/review/"
```

**Behavioral verification:** `ls amelia/skills/review/python/python.md` should exist and contain the Python code review checklist content.

---

### Task 2: Implement stack detection and skill loader

**Files:**
- Create: `tests/unit/skills/test_review.py`
- Create: `amelia/skills/review/__init__.py` (replace empty file from Task 1)

**Step 1: Write failing tests for detect_stack**

```python
# tests/unit/skills/test_review.py
"""Tests for review skill detection and loading."""
from amelia.skills.review import detect_stack, load_skills


class TestDetectStack:
    """Tests for detect_stack()."""

    def test_python_files(self) -> None:
        tags = detect_stack(["src/app.py", "src/utils.py"], "")
        assert "python" in tags

    def test_pytest_from_test_files(self) -> None:
        tags = detect_stack(["tests/test_app.py", "conftest.py"], "")
        assert "pytest" in tags
        assert "python" in tags

    def test_react_tsx(self) -> None:
        tags = detect_stack(["src/App.tsx", "src/Component.tsx"], "")
        assert "react" in tags

    def test_typescript_ts(self) -> None:
        tags = detect_stack(["src/utils.ts"], "")
        assert "typescript" in tags

    def test_go_files(self) -> None:
        tags = detect_stack(["main.go", "handler.go"], "")
        assert "go" in tags

    def test_elixir_files(self) -> None:
        tags = detect_stack(["lib/app.ex", "test/app_test.exs"], "")
        assert "elixir" in tags

    def test_swift_files(self) -> None:
        tags = detect_stack(["Sources/App.swift"], "")
        assert "swift" in tags

    def test_fastapi_from_imports(self) -> None:
        diff = "+from fastapi import APIRouter"
        tags = detect_stack(["src/routes.py"], diff)
        assert "fastapi" in tags
        assert "python" in tags

    def test_sqlalchemy_from_imports(self) -> None:
        diff = "+from sqlalchemy import Column"
        tags = detect_stack(["src/models.py"], diff)
        assert "sqlalchemy" in tags

    def test_shadcn_from_imports(self) -> None:
        diff = "+import { Button } from '@/components/ui/button'"
        tags = detect_stack(["src/App.tsx"], diff)
        assert "shadcn" in tags

    def test_react_router_from_imports(self) -> None:
        diff = "+import { useLoaderData } from 'react-router-dom'"
        tags = detect_stack(["src/Page.tsx"], diff)
        assert "react-router" in tags

    def test_react_flow_from_imports(self) -> None:
        diff = "+import { ReactFlow } from '@xyflow/react'"
        tags = detect_stack(["src/Flow.tsx"], diff)
        assert "react-flow" in tags

    def test_phoenix_from_imports(self) -> None:
        diff = "+use Phoenix.Router"
        tags = detect_stack(["lib/router.ex"], diff)
        assert "phoenix" in tags

    def test_empty_input(self) -> None:
        tags = detect_stack([], "")
        assert tags == set()

    def test_mixed_stack(self) -> None:
        tags = detect_stack(
            ["backend/app.py", "frontend/App.tsx"],
            "+from fastapi import FastAPI",
        )
        assert "python" in tags
        assert "fastapi" in tags
        assert "react" in tags


class TestLoadSkills:
    """Tests for load_skills()."""

    def test_load_general_skills(self) -> None:
        content = load_skills(set(), ["general"])
        assert "General Code Review" in content
        assert "verification" in content.lower()

    def test_load_python_skills(self) -> None:
        content = load_skills({"python"}, ["general"])
        assert "Python Code Review" in content

    def test_load_multiple_tags(self) -> None:
        content = load_skills({"python", "fastapi"}, ["general"])
        assert "Python Code Review" in content
        assert "FastAPI" in content

    def test_load_security_type(self) -> None:
        content = load_skills(set(), ["security"])
        assert "Security" in content

    def test_load_unknown_tag_ignored(self) -> None:
        content = load_skills({"nonexistent_lang"}, ["general"])
        # Should still include general skills, just no language-specific ones
        assert "General Code Review" in content

    def test_deduplication(self) -> None:
        """Loading same skills twice should not duplicate content."""
        content = load_skills({"python"}, ["general"])
        # Count occurrences of a unique header
        assert content.count("# Python Code Review") == 1
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/skills/test_review.py -v`
Expected: FAIL (detect_stack and load_skills not implemented)

**Step 3: Implement detect_stack and load_skills in `amelia/skills/review/__init__.py`**

```python
"""Review skill registry, stack detection, and skill loading."""
from __future__ import annotations

import re
from pathlib import Path

_SKILLS_DIR = Path(__file__).parent

# Maps technology tags to skill file paths (relative to _SKILLS_DIR)
REVIEW_SKILLS: dict[str, list[str]] = {
    # Python
    "python": ["python/python.md"],
    "pytest": ["python/pytest.md"],
    "fastapi": ["python/fastapi.md"],
    "sqlalchemy": ["python/sqlalchemy.md"],
    "postgres": ["python/postgres.md"],
    # React / Frontend
    "react": ["react/shadcn.md"],
    "shadcn": ["react/shadcn.md"],
    "vitest": ["react/vitest.md"],
    "react-router": ["react/react-router.md"],
    "react-flow": ["react/react-flow.md"],
    # Go
    "go": ["go/go.md"],
    "go-testing": ["go/go-testing.md"],
    "go-concurrency": ["go/go-concurrency.md"],
    "go-middleware": ["go/go-middleware.md"],
    # Elixir
    "elixir": ["elixir/elixir.md"],
    "phoenix": ["elixir/phoenix.md"],
    "liveview": ["elixir/liveview.md"],
    "exunit": ["elixir/exunit.md"],
    "elixir-security": ["elixir/elixir-security.md"],
    "elixir-performance": ["elixir/elixir-performance.md"],
    # Swift
    "swift": ["swift/swift.md"],
    "swiftui": ["swift/swiftui.md"],
    "combine": ["swift/combine.md"],
}

# Maps review types to always-included skill files
REVIEW_TYPE_SKILLS: dict[str, list[str]] = {
    "general": ["general.md", "verification.md"],
    "security": ["security/general.md"],
}

# File extension -> tag mapping
_EXTENSION_TAGS: dict[str, str] = {
    ".py": "python",
    ".tsx": "react",
    ".jsx": "react",
    ".ts": "typescript",
    ".js": "typescript",
    ".go": "go",
    ".ex": "elixir",
    ".exs": "elixir",
    ".swift": "swift",
}

# Path patterns -> additional tags (checked after extension matching)
_PATH_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(^|/)test_[^/]*\.py$"), "pytest"),
    (re.compile(r"(^|/)conftest\.py$"), "pytest"),
    (re.compile(r"_test\.go$"), "go-testing"),
    (re.compile(r"(^|/)test/.*_test\.exs$"), "exunit"),
    (re.compile(r"\.test\.(ts|tsx|js|jsx)$"), "vitest"),
    (re.compile(r"\.spec\.(ts|tsx|js|jsx)$"), "vitest"),
]

# Import patterns in diff content -> additional tags
_IMPORT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"from fastapi\b|import fastapi\b"), "fastapi"),
    (re.compile(r"from sqlalchemy\b|import sqlalchemy\b"), "sqlalchemy"),
    (re.compile(r"from asyncpg\b|import asyncpg\b|psycopg"), "postgres"),
    (re.compile(r"@/components/ui/|from ['\"]@/components/ui"), "shadcn"),
    (re.compile(r"react-router-dom|@react-router"), "react-router"),
    (re.compile(r"@xyflow/react"), "react-flow"),
    (re.compile(r"use Phoenix\.|Phoenix\.Router|Phoenix\.LiveView"), "phoenix"),
    (re.compile(r"Phoenix\.LiveView|live_render|live_component"), "liveview"),
    (re.compile(r"use SwiftUI\b|import SwiftUI\b"), "swiftui"),
    (re.compile(r"import Combine\b"), "combine"),
]


def detect_stack(file_paths: list[str], diff_content: str) -> set[str]:
    """Detect technology stack from changed file paths and diff content.

    Two-pass detection:
    1. File extensions and path patterns
    2. Import patterns in diff content

    Args:
        file_paths: List of changed file paths from git diff --name-only.
        diff_content: Raw diff content for import scanning.

    Returns:
        Set of technology tags (e.g., {"python", "fastapi", "pytest"}).
    """
    tags: set[str] = set()

    # Pass 1: File extensions and path patterns
    for path in file_paths:
        suffix = Path(path).suffix.lower()
        if suffix in _EXTENSION_TAGS:
            tags.add(_EXTENSION_TAGS[suffix])

        for pattern, tag in _PATH_PATTERNS:
            if pattern.search(path):
                tags.add(tag)

    # Pass 2: Import patterns in diff content (only added lines)
    for pattern, tag in _IMPORT_PATTERNS:
        if pattern.search(diff_content):
            tags.add(tag)

    return tags


def load_skills(tags: set[str], review_types: list[str]) -> str:
    """Load and concatenate review skill files for the given tags and types.

    Args:
        tags: Technology tags from detect_stack().
        review_types: Review types to include (e.g., ["general"], ["security"]).

    Returns:
        Concatenated markdown content from all matched skill files.
    """
    seen_paths: set[str] = set()
    sections: list[str] = []

    # Collect file paths from review types
    for review_type in review_types:
        for rel_path in REVIEW_TYPE_SKILLS.get(review_type, []):
            if rel_path not in seen_paths:
                seen_paths.add(rel_path)

    # Collect file paths from technology tags
    for tag in sorted(tags):
        for rel_path in REVIEW_SKILLS.get(tag, []):
            if rel_path not in seen_paths:
                seen_paths.add(rel_path)

    # Read and concatenate
    for rel_path in sorted(seen_paths):
        full_path = _SKILLS_DIR / rel_path
        if full_path.exists():
            sections.append(full_path.read_text(encoding="utf-8").strip())

    return "\n\n---\n\n".join(sections)
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/skills/test_review.py -v`
Expected: All PASS

**Step 5: Run linting and type checking**

Run: `uv run ruff check amelia/skills/ tests/unit/skills/`
Run: `uv run mypy amelia/skills/`
Expected: No errors

**Step 6: Commit**

```bash
git add amelia/skills/review/__init__.py tests/unit/skills/ tests/unit/skills/test_review.py
git commit -m "feat: add stack detection and skill loading for reviewer"
```

**Behavioral verification:** `uv run python -c "from amelia.skills.review import detect_stack, load_skills; tags = detect_stack(['app.py'], '+from fastapi import FastAPI'); print(tags); content = load_skills(tags, ['general']); print(f'{len(content)} chars loaded, has FastAPI: {\"FastAPI\" in content}')"` — should print tags including `python` and `fastapi`, and confirm FastAPI content is loaded.

---

### Task 3: Update reviewer prompt to use injected skills

**Files:**
- Modify: `amelia/agents/reviewer.py:82-117` (replace `AGENTIC_REVIEW_PROMPT` class variable)
- Modify: `amelia/agents/prompts/defaults.py:136-176` (update `reviewer.agentic` prompt)
- Modify: `tests/unit/agents/test_reviewer.py` (update tests that reference old prompt)

**Step 1: Update the AGENTIC_REVIEW_PROMPT in reviewer.py**

Replace the class variable at `reviewer.py:82-117` with a new prompt template that uses `{review_guidelines}` placeholder instead of Skill tool instructions:

```python
    AGENTIC_REVIEW_PROMPT = f"""You are an expert code reviewer.

## Review Guidelines

{{review_guidelines}}

## Process

1. **Identify Changed Files**: Run `git diff --name-only {{base_commit}}` to see what files changed
2. **Get the Diff**: Run `git diff {{base_commit}}` to get the full diff
3. **Review**: Evaluate the code against the review guidelines above
4. **Output**: Provide your review in the following markdown format:

```markdown
{REVIEW_OUTPUT_FORMAT}
```

## Rules

- Number every issue sequentially (1, 2, 3...)
- Include FILE:LINE for each issue
- Separate Issue/Why/Fix clearly
- Categorize by actual severity (Critical/Major/Minor)
- Only flag real issues - check linters first before flagging style issues
- "Ready: Yes" means approved to merge as-is"""
```

Note: The prompt now has two format placeholders: `{review_guidelines}` and `{base_commit}`. The `review_guidelines` is filled before passing to the reviewer; `base_commit` is filled at review time (already done at `reviewer.py:283`).

**Step 2: Update the `agentic_review` method to accept review_guidelines**

At `reviewer.py:283`, change:
```python
system_prompt = self.agentic_prompt.format(base_commit=base_commit)
```
to:
```python
system_prompt = self.agentic_prompt.format(
    base_commit=base_commit,
    review_guidelines=self._review_guidelines,
)
```

Add `review_guidelines` parameter to `__init__`:
```python
def __init__(
    self,
    config: AgentConfig,
    event_bus: EventBus | None = None,
    prompts: dict[str, str] | None = None,
    agent_name: str = "reviewer",
    sandbox_provider: SandboxProvider | None = None,
    review_guidelines: str = "",
):
```
Store it: `self._review_guidelines = review_guidelines`

**Step 3: Update the prompt default in defaults.py**

Update `defaults.py:136-176` to match the new prompt (same content as the class variable, just without the f-string/REVIEW_OUTPUT_FORMAT substitution since that's handled at import time). Remove the import of `REVIEW_OUTPUT_FORMAT` from defaults.py if it's now redundant (the class variable already does the f-string substitution).

**Step 4: Update tests in test_reviewer.py**

Any tests that assert on the old prompt content (checking for "Load Review Skills", "beagle-python", "Skill tool") need updating to reflect the new prompt structure. Search for these strings and update assertions.

**Step 5: Run tests**

Run: `uv run pytest tests/unit/agents/test_reviewer.py -v`
Expected: All PASS

**Step 6: Run full test suite**

Run: `uv run pytest tests/unit/ -v`
Expected: All PASS

**Step 7: Commit**

```bash
git add amelia/agents/reviewer.py amelia/agents/prompts/defaults.py tests/unit/agents/test_reviewer.py
git commit -m "feat: replace Skill tool references with injected review guidelines"
```

**Behavioral verification:** `uv run python -c "from amelia.agents.reviewer import Reviewer; print('Skill' not in Reviewer.AGENTIC_REVIEW_PROMPT and 'review_guidelines' in Reviewer.AGENTIC_REVIEW_PROMPT)"` — should print `True`.

---

### Task 4: Wire skill loading into call_reviewer_node

**Files:**
- Modify: `amelia/pipelines/nodes.py:191-296` (update `call_reviewer_node`)
- Create: `tests/unit/core/test_skill_injection.py`

**Step 1: Write failing test for skill injection**

```python
# tests/unit/core/test_skill_injection.py
"""Tests for skill injection into the reviewer via call_reviewer_node."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from amelia.core.types import ReviewResult, Severity
from amelia.pipelines.nodes import call_reviewer_node


class TestSkillInjection:
    """Tests for review skill injection in call_reviewer_node."""

    @pytest.fixture
    def mock_state(self, mock_execution_state_factory):
        state = mock_execution_state_factory()
        state.base_commit = "abc123"
        state.current_task_index = 0
        state.total_tasks = 1
        return state

    @pytest.fixture
    def mock_config(self, mock_profile_factory):
        profile = mock_profile_factory()
        return {
            "configurable": {
                "event_bus": MagicMock(),
                "workflow_id": "test-wf-id",
                "profile": profile,
                "prompts": {},
                "repository": None,
                "sandbox_provider": None,
            }
        }

    @patch("amelia.pipelines.nodes.Reviewer")
    @patch("amelia.pipelines.nodes.detect_stack")
    @patch("amelia.pipelines.nodes.load_skills")
    async def test_skills_injected_into_reviewer(
        self,
        mock_load: MagicMock,
        mock_detect: MagicMock,
        mock_reviewer_cls: MagicMock,
        mock_state,
        mock_config,
    ) -> None:
        mock_detect.return_value = {"python", "fastapi"}
        mock_load.return_value = "# Python Review Guidelines\n..."

        mock_reviewer = MagicMock()
        mock_reviewer.agentic_review = AsyncMock(
            return_value=(
                ReviewResult(
                    reviewer_persona="general",
                    approved=True,
                    comments=[],
                    severity=Severity.NONE,
                ),
                "session-123",
            )
        )
        mock_reviewer.driver = MagicMock()
        mock_reviewer_cls.return_value = mock_reviewer

        await call_reviewer_node(mock_state, mock_config)

        # Verify Reviewer was constructed with review_guidelines
        mock_reviewer_cls.assert_called_once()
        call_kwargs = mock_reviewer_cls.call_args
        assert "review_guidelines" in call_kwargs.kwargs
        assert "Python Review Guidelines" in call_kwargs.kwargs["review_guidelines"]
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/core/test_skill_injection.py -v`
Expected: FAIL (detect_stack/load_skills not imported in nodes.py)

**Step 3: Update call_reviewer_node to inject skills**

In `amelia/pipelines/nodes.py`, add imports and modify `call_reviewer_node()`:

Add at top of file:
```python
from amelia.skills.review import detect_stack, load_skills
```

In `call_reviewer_node`, after `base_commit` is resolved (after line 253), add skill detection:

```python
    # Detect stack and load review skills
    review_types = agent_config.options.get("review_types", ["general"])
    # Get changed file paths for stack detection
    changed_files = await _get_changed_files(base_commit, profile.repo_root, sandbox_provider)
    diff_content = await _get_diff_content(base_commit, profile.repo_root, sandbox_provider)
    tags = detect_stack(changed_files, diff_content)
    review_guidelines = load_skills(tags, review_types)

    logger.info(
        "Loaded review skills",
        agent=agent_name,
        tags=sorted(tags),
        review_types=review_types,
        guidelines_length=len(review_guidelines),
    )
```

Pass `review_guidelines` to Reviewer constructor (update line 228):
```python
    reviewer = Reviewer(
        agent_config,
        event_bus=event_bus,
        prompts=prompts,
        agent_name=agent_name,
        sandbox_provider=sandbox_provider,
        review_guidelines=review_guidelines,
    )
```

Add helper functions `_get_changed_files` and `_get_diff_content` that run git commands via the sandbox or subprocess. These are lightweight wrappers — check if similar helpers already exist in the codebase (the reviewer currently tells the LLM to run these commands, but we need them in Python now).

NOTE: If running git directly is complex due to sandbox considerations, an alternative is to use `asyncio.create_subprocess_exec` with `cwd=profile.repo_root`. Check existing patterns in the codebase for running git commands from Python (search for `git diff` or `subprocess` in `amelia/`).

**Step 4: Run tests**

Run: `uv run pytest tests/unit/core/test_skill_injection.py tests/unit/core/test_orchestrator_review.py -v`
Expected: All PASS

**Step 5: Run full unit test suite**

Run: `uv run pytest tests/unit/ -v`
Expected: All PASS

**Step 6: Commit**

```bash
git add amelia/pipelines/nodes.py tests/unit/core/test_skill_injection.py
git commit -m "feat: inject review skills into reviewer prompt via call_reviewer_node"
```

**Behavioral verification:** `uv run pytest tests/unit/core/test_skill_injection.py::TestSkillInjection::test_skills_injected_into_reviewer -v` — should PASS, confirming the full injection pipeline works.

---

### Task 5: Update state model for multiple review types

**Files:**
- Modify: `amelia/core/types.py:235-243` (ReviewResult — add review_type field if not using reviewer_persona)
- Modify: `amelia/pipelines/implementation/state.py:72` (last_review → last_reviews)
- Modify: `amelia/pipelines/implementation/routing.py:43-114` (update route_after_task_review)
- Modify: `amelia/pipelines/nodes.py` (update call_reviewer_node return)
- Modify: `amelia/pipelines/review/routing.py` (update route_after_fixes/evaluation)
- Modify: `tests/unit/core/test_orchestrator_review.py` (update for last_reviews)
- Modify: any other files referencing `state.last_review`

**Step 1: Search for all references to `last_review`**

Run: `grep -rn 'last_review' amelia/ tests/` and catalog every file that needs updating.

**Step 2: Write failing tests for the new state shape**

Update `tests/unit/core/test_orchestrator_review.py` to expect `last_reviews: list[ReviewResult]` instead of `last_review: ReviewResult | None`.

**Step 3: Update ImplementationState**

In `state.py:72`, change:
```python
last_review: ReviewResult | None = None
```
to:
```python
last_reviews: list[ReviewResult] = Field(default_factory=list)
```

**Step 4: Update routing logic**

In `routing.py:61`, change:
```python
approved = state.last_review.approved if state.last_review else False
```
to:
```python
approved = all(r.approved for r in state.last_reviews) if state.last_reviews else False
```

In `review/routing.py`, update `route_after_evaluation` and `route_after_fixes` if they reference `last_review`.

**Step 5: Update call_reviewer_node return**

In `nodes.py`, the reviewer now may run multiple times (once per review_type). Loop over review_types, run the reviewer for each, collect results into a list:

```python
    reviews: list[ReviewResult] = []
    for review_type in review_types:
        guidelines = load_skills(tags, [review_type])
        reviewer = Reviewer(
            agent_config, event_bus=event_bus, prompts=prompts,
            agent_name=agent_name, sandbox_provider=sandbox_provider,
            review_guidelines=guidelines,
        )
        result, session_id = await reviewer.agentic_review(
            state, base_commit, profile, workflow_id=workflow_id
        )
        # Set reviewer_persona to the review type
        result = result.model_copy(update={"reviewer_persona": review_type})
        reviews.append(result)
        new_session_id = session_id

    result_dict = {
        "last_reviews": reviews,
        "driver_session_id": new_session_id,
        "review_iteration": next_iteration,
        "task_review_iteration": state.task_review_iteration + 1,
    }
```

**Step 6: Update all other references to `last_review`**

Based on the grep from Step 1, update every reference. Common patterns:
- `state.last_review` → `state.last_reviews`
- `state.last_review.approved` → `all(r.approved for r in state.last_reviews)`
- `state.last_review.comments` → aggregate from all reviews
- Event emissions that reference last_review

**Step 7: Run tests**

Run: `uv run pytest tests/unit/ -v`
Expected: All PASS

**Step 8: Run type checking**

Run: `uv run mypy amelia/`
Expected: No errors

**Step 9: Commit**

```bash
git add amelia/core/types.py amelia/pipelines/ amelia/agents/ tests/
git commit -m "feat: support multiple review types with last_reviews list"
```

**Behavioral verification:** `uv run python -c "from amelia.pipelines.implementation.state import ImplementationState; s = ImplementationState(workflow_id='test', profile_id='p'); print(type(s.last_reviews), len(s.last_reviews))"` — should print `<class 'list'> 0`.

---

### Task 6: Add on-demand review API endpoint

**Files:**
- Create: `tests/unit/server/routes/test_review_endpoint.py`
- Modify: `amelia/server/models/requests.py` (add `RequestReviewRequest`)
- Modify: `amelia/server/routes/workflows.py` (add `POST /{workflow_id}/review` endpoint)
- Modify: `amelia/server/orchestrator/service.py` (add `request_review` method)

**Step 1: Write failing test for the endpoint**

```python
# tests/unit/server/routes/test_review_endpoint.py
"""Tests for on-demand review endpoint."""
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from amelia.server.dependencies import get_orchestrator
from amelia.server.routes.workflows import configure_exception_handlers, router


class TestRequestReviewEndpoint:

    @pytest.fixture
    def mock_orchestrator(self) -> MagicMock:
        orch = MagicMock()
        orch.request_review = AsyncMock(return_value=None)
        return orch

    @pytest.fixture
    def client(self, mock_orchestrator: MagicMock) -> TestClient:
        app = FastAPI()
        app.include_router(router, prefix="/api")
        app.dependency_overrides[get_orchestrator] = lambda: mock_orchestrator
        configure_exception_handlers(app)
        return TestClient(app)

    def test_request_review_only(
        self, client: TestClient, mock_orchestrator: MagicMock
    ) -> None:
        response = client.post(
            "/api/workflows/550e8400-e29b-41d4-a716-446655440000/review",
            json={"mode": "review_only"},
        )
        assert response.status_code == 202
        mock_orchestrator.request_review.assert_called_once()

    def test_request_review_with_types(
        self, client: TestClient, mock_orchestrator: MagicMock
    ) -> None:
        response = client.post(
            "/api/workflows/550e8400-e29b-41d4-a716-446655440000/review",
            json={"mode": "review_only", "review_types": ["general", "security"]},
        )
        assert response.status_code == 202

    def test_request_review_fix(
        self, client: TestClient, mock_orchestrator: MagicMock
    ) -> None:
        response = client.post(
            "/api/workflows/550e8400-e29b-41d4-a716-446655440000/review",
            json={"mode": "review_fix"},
        )
        assert response.status_code == 202
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/server/routes/test_review_endpoint.py -v`
Expected: FAIL

**Step 3: Add RequestReviewRequest model**

In `amelia/server/models/requests.py`, add:

```python
class RequestReviewRequest(BaseModel):
    """Request for on-demand code review."""

    mode: Literal["review_only", "review_fix"] = "review_only"
    review_types: list[str] = Field(default_factory=lambda: ["general"])
    base_commit: str | None = None
```

**Step 4: Add endpoint in workflows.py**

After the existing `/{workflow_id}/replan` endpoint (line 565), add:

```python
@router.post(
    "/{workflow_id}/review",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ActionResponse,
)
async def request_review(
    workflow_id: uuid.UUID,
    request: RequestReviewRequest,
    orchestrator: OrchestratorService = Depends(get_orchestrator),
) -> ActionResponse:
    """Request an on-demand code review for a workflow.

    Args:
        workflow_id: Unique workflow identifier.
        request: Review request with mode and optional review types.
        orchestrator: Orchestrator service dependency.

    Returns:
        202 Accepted with workflow_id and status.
    """
    await orchestrator.request_review(
        workflow_id=workflow_id,
        mode=request.mode,
        review_types=request.review_types,
        base_commit=request.base_commit,
    )
    logger.info("Review requested", workflow_id=workflow_id, mode=request.mode)
    return ActionResponse(status="review_requested", workflow_id=workflow_id)
```

**Step 5: Add orchestrator method stub**

In `amelia/server/orchestrator/service.py`, add a `request_review` method. For now, implement `review_only` mode (runs reviewer node directly). `review_fix` mode invokes the existing review pipeline.

This step requires understanding the orchestrator's pattern for spawning tasks. The method should:
1. Look up the workflow
2. Get the profile
3. For `review_only`: run the reviewer node directly and emit results via event bus
4. For `review_fix`: invoke the existing review pipeline

**Step 6: Run tests**

Run: `uv run pytest tests/unit/server/routes/test_review_endpoint.py -v`
Expected: All PASS

**Step 7: Run full test suite**

Run: `uv run pytest tests/unit/ -v`
Expected: All PASS

**Step 8: Commit**

```bash
git add amelia/server/models/requests.py amelia/server/routes/workflows.py amelia/server/orchestrator/service.py tests/unit/server/routes/test_review_endpoint.py
git commit -m "feat: add on-demand review API endpoint POST /{workflow_id}/review"
```

**Behavioral verification:** Start the dev server with `uv run amelia dev` and test the endpoint:
```bash
curl -X POST http://localhost:8420/api/workflows/550e8400-e29b-41d4-a716-446655440000/review \
  -H 'Content-Type: application/json' \
  -d '{"mode": "review_only", "review_types": ["general"]}'
```
Expected: 202 response (or 404 if workflow doesn't exist — either confirms the endpoint is registered and routing correctly).

---

### Task 7: Add "Request Review" button to dashboard

**Files:**
- Create: `dashboard/src/components/RequestReviewDialog.tsx`
- Modify: `dashboard/src/api/client.ts` (add `requestReview` method)
- Modify: `dashboard/src/types/index.ts` (add `RequestReviewRequest` type)
- Modify: `dashboard/src/pages/WorkflowDetailPage.tsx` (add button)
- Create: `dashboard/src/components/__tests__/RequestReviewDialog.test.tsx`

**Step 1: Add TypeScript types**

In `dashboard/src/types/index.ts`, add:

```typescript
export interface RequestReviewRequest {
  mode: 'review_only' | 'review_fix';
  review_types?: string[];
  base_commit?: string;
}
```

**Step 2: Add API client method**

In `dashboard/src/api/client.ts`, add to the `api` object:

```typescript
  async requestReview(
    workflowId: string,
    request: RequestReviewRequest
  ): Promise<void> {
    const response = await fetchWithTimeout(
      `${API_BASE_URL}/workflows/${workflowId}/review`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(request),
      }
    );
    await handleResponse(response);
  },
```

**Step 3: Create RequestReviewDialog component**

```tsx
// dashboard/src/components/RequestReviewDialog.tsx
import { useState, useCallback } from 'react';
import { Search } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { api } from '@/api/client';
import type { RequestReviewRequest } from '@/types';

const REVIEW_TYPES = [
  { id: 'general', label: 'General' },
  { id: 'security', label: 'Security' },
] as const;

interface RequestReviewDialogProps {
  workflowId: string;
}

export function RequestReviewDialog({ workflowId }: RequestReviewDialogProps) {
  const [open, setOpen] = useState(false);
  const [selectedTypes, setSelectedTypes] = useState<string[]>(['general']);
  const [mode, setMode] = useState<'review_only' | 'review_fix'>('review_only');
  const [submitting, setSubmitting] = useState(false);

  const toggleType = useCallback((typeId: string) => {
    setSelectedTypes((prev) =>
      prev.includes(typeId)
        ? prev.filter((t) => t !== typeId)
        : [...prev, typeId]
    );
  }, []);

  const handleSubmit = useCallback(async () => {
    if (selectedTypes.length === 0) return;
    setSubmitting(true);
    try {
      const request: RequestReviewRequest = {
        mode,
        review_types: selectedTypes,
      };
      await api.requestReview(workflowId, request);
      setOpen(false);
    } finally {
      setSubmitting(false);
    }
  }, [workflowId, mode, selectedTypes]);

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm">
          <Search className="w-4 h-4 mr-2" />
          Request Review
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Request Code Review</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 pt-2">
          <div>
            <label className="text-sm font-medium text-muted-foreground">Review Types</label>
            <div className="flex gap-2 mt-1">
              {REVIEW_TYPES.map((type) => (
                <button
                  key={type.id}
                  onClick={() => toggleType(type.id)}
                  className={`px-3 py-1.5 text-sm rounded-md border transition-colors ${
                    selectedTypes.includes(type.id)
                      ? 'border-primary bg-primary/10 text-primary'
                      : 'border-border text-muted-foreground hover:border-primary/50'
                  }`}
                >
                  {type.label}
                </button>
              ))}
            </div>
          </div>
          <div>
            <label className="text-sm font-medium text-muted-foreground">Mode</label>
            <div className="flex gap-2 mt-1">
              <button
                onClick={() => setMode('review_only')}
                className={`px-3 py-1.5 text-sm rounded-md border transition-colors ${
                  mode === 'review_only'
                    ? 'border-primary bg-primary/10 text-primary'
                    : 'border-border text-muted-foreground hover:border-primary/50'
                }`}
              >
                Review Only
              </button>
              <button
                onClick={() => setMode('review_fix')}
                className={`px-3 py-1.5 text-sm rounded-md border transition-colors ${
                  mode === 'review_fix'
                    ? 'border-primary bg-primary/10 text-primary'
                    : 'border-border text-muted-foreground hover:border-primary/50'
                }`}
              >
                Review & Fix
              </button>
            </div>
          </div>
          <Button
            onClick={handleSubmit}
            disabled={submitting || selectedTypes.length === 0}
            className="w-full"
          >
            {submitting ? 'Requesting...' : 'Request Review'}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
```

**Step 4: Add button to WorkflowDetailPage**

In `dashboard/src/pages/WorkflowDetailPage.tsx`, import and add the dialog button in the header area. Add it next to the status badge (around line 113-115):

```tsx
import { RequestReviewDialog } from '@/components/RequestReviewDialog';

// In the PageHeader.Right section:
<PageHeader.Right>
  <RequestReviewDialog workflowId={workflow.id} />
  <StatusBadge status={workflow.status} />
</PageHeader.Right>
```

**Step 5: Write component test**

```tsx
// dashboard/src/components/__tests__/RequestReviewDialog.test.tsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { RequestReviewDialog } from '../RequestReviewDialog';

describe('RequestReviewDialog', () => {
  it('renders the trigger button', () => {
    render(<RequestReviewDialog workflowId="test-id" />);
    expect(screen.getByText('Request Review')).toBeInTheDocument();
  });
});
```

**Step 6: Run frontend tests and build**

Run (from dashboard/): `pnpm test:run`
Run (from dashboard/): `pnpm build`
Expected: All pass, build succeeds

**Step 7: Commit**

```bash
git add dashboard/src/
git commit -m "feat: add Request Review dialog to workflow detail page"
```

**Behavioral verification:** `cd dashboard && pnpm build` — should succeed. The "Request Review" button will be visible on the workflow detail page when the dev server is running.

---

### Task 8: Final verification and cleanup

**Files:**
- Verify: all files from Tasks 1-7
- Modify: `amelia/agents/reviewer.py` (update docstring referencing beagle skills at line 73-75)

**Step 1: Run full backend test suite**

Run: `uv run pytest tests/unit/ -v`
Expected: All PASS (100% pass rate)

**Step 2: Run linting and type checking**

Run: `uv run ruff check amelia/ tests/`
Run: `uv run mypy amelia/`
Expected: No errors

**Step 3: Run dashboard build**

Run (from dashboard/): `pnpm build`
Run (from dashboard/): `pnpm test:run`
Run (from dashboard/): `pnpm type-check`
Expected: All pass

**Step 4: Search for any remaining beagle/Skill tool references**

Run: `grep -rn 'beagle\|Load Review Skills\|Skill tool' amelia/ dashboard/src/`
Expected: No results (all references removed)

**Step 5: Verify all files from the plan were created/modified**

Run: `git diff --name-only HEAD~8` (or appropriate number of commits)
Verify against the file lists from all tasks above.

**Step 6: Update reviewer docstring**

In `reviewer.py:73-75`, change:
```python
        agentic_review(): Agentic review that auto-detects technologies, loads review
            skills, and fetches diff via git.
```
to:
```python
        agentic_review(): Agentic review using injected review guidelines.
            Fetches diff via git and reviews against provided skill content.
```

**Step 7: Final commit**

```bash
git add -A
git commit -m "chore: remove beagle references and update reviewer docstrings"
```

**Behavioral verification:**
1. `grep -rn 'beagle' amelia/` — should return no results
2. `uv run pytest tests/unit/ -v` — 100% pass rate
3. `cd dashboard && pnpm build` — succeeds
4. `uv run ruff check amelia/ tests/ && uv run mypy amelia/` — clean
