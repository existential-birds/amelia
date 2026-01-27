# Oracle Phase 1 — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the Oracle consultation system foundation: a standalone agent that accepts a problem + codebase context and returns expert advice using agentic LLM execution.

**Architecture:** Four components built bottom-up — FileBundler (file gathering utility), OracleConsultation model + event types (shared types), Oracle agent (agentic LLM consultation), and API endpoint (REST + WebSocket streaming). Each component is built TDD with tests first.

**Tech Stack:** Python 3.12+, Pydantic, FastAPI, tiktoken, asyncio, LangGraph (append-only state), existing driver abstraction (`execute_agentic`)

**Design Spec:** `docs/plans/2026-01-26-oracle-phase1-design.md`

---

### Task 1: Add tiktoken dependency

**Files:**
- Modify: `pyproject.toml` (add `tiktoken` to `[project] dependencies`)

tiktoken is already in `uv.lock` as a transitive dependency but not declared as a direct dependency. FileBundler needs it for token estimation.

**Step 1: Add tiktoken to pyproject.toml**

In the `dependencies` list in `pyproject.toml`, add:

```
"tiktoken>=0.7.0",
```

Add it after the `websockets` entry (alphabetical-ish, at the end).

**Step 2: Sync dependencies**

Run: `uv sync`
Expected: Clean install, no errors.

**Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: add tiktoken as direct dependency for FileBundler token estimation"
```

---

### Task 2: Add OracleConsultation model to core types

**Files:**
- Modify: `amelia/core/types.py` (add `OracleConsultation` class)
- Test: `tests/unit/core/test_oracle_types.py`

**Step 1: Write the failing test**

Create `tests/unit/core/test_oracle_types.py`:

```python
"""Tests for OracleConsultation model."""

from datetime import UTC, datetime

from amelia.core.types import OracleConsultation


class TestOracleConsultation:
    """Tests for OracleConsultation Pydantic model."""

    def test_minimal_construction(self):
        """OracleConsultation should construct with required fields only."""
        consultation = OracleConsultation(
            timestamp=datetime.now(tz=UTC),
            problem="How should I refactor the auth module?",
            model="claude-sonnet-4-20250514",
            session_id="abc-123",
        )
        assert consultation.problem == "How should I refactor the auth module?"
        assert consultation.model == "claude-sonnet-4-20250514"
        assert consultation.session_id == "abc-123"
        assert consultation.advice is None
        assert consultation.tokens == {}
        assert consultation.cost_usd is None
        assert consultation.files_consulted == []
        assert consultation.outcome == "success"
        assert consultation.error_message is None

    def test_full_construction(self):
        """OracleConsultation should accept all optional fields."""
        consultation = OracleConsultation(
            timestamp=datetime.now(tz=UTC),
            problem="Refactor auth",
            advice="Use dependency injection.",
            model="claude-sonnet-4-20250514",
            session_id="abc-123",
            tokens={"input": 1000, "output": 500},
            cost_usd=0.015,
            files_consulted=["src/auth.py", "src/middleware.py"],
            outcome="success",
        )
        assert consultation.advice == "Use dependency injection."
        assert consultation.tokens == {"input": 1000, "output": 500}
        assert consultation.cost_usd == 0.015
        assert consultation.files_consulted == ["src/auth.py", "src/middleware.py"]

    def test_error_outcome(self):
        """OracleConsultation should record error state."""
        consultation = OracleConsultation(
            timestamp=datetime.now(tz=UTC),
            problem="Analyze this",
            model="claude-sonnet-4-20250514",
            session_id="abc-123",
            outcome="error",
            error_message="Driver timeout",
        )
        assert consultation.outcome == "error"
        assert consultation.error_message == "Driver timeout"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/core/test_oracle_types.py -v`
Expected: FAIL with `ImportError: cannot import name 'OracleConsultation'`

**Step 3: Write the implementation**

Add to `amelia/core/types.py`, after the `ReviewResult` class:

```python
class OracleConsultation(BaseModel):
    """Record of an Oracle consultation for persistence and analytics.

    Attributes:
        timestamp: When the consultation occurred.
        problem: The problem statement submitted.
        advice: The Oracle's advice (None until complete).
        model: LLM model used.
        session_id: UUIDv4, generated per-consultation by Oracle.consult().
        tokens: Token counts (e.g., {"input": N, "output": M}).
        cost_usd: Estimated cost in USD.
        files_consulted: File paths included in context.
        outcome: Whether consultation succeeded or errored.
        error_message: Error details if outcome is "error".
    """

    timestamp: datetime
    problem: str
    advice: str | None = None
    model: str
    session_id: str
    tokens: dict[str, int] = Field(default_factory=dict)
    cost_usd: float | None = None
    files_consulted: list[str] = Field(default_factory=list)
    outcome: Literal["success", "error"] = "success"
    error_message: str | None = None
```

Ensure `datetime` and `Literal` are imported at the top of `amelia/core/types.py`. `datetime` is already imported. `Literal` — check if already imported; if not, add `from typing import Literal`. Also check `Field` is imported from pydantic.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/core/test_oracle_types.py -v`
Expected: 3 passed

**Step 5: Commit**

```bash
git add amelia/core/types.py tests/unit/core/test_oracle_types.py
git commit -m "feat(oracle): add OracleConsultation model to core types"
```

---

### Task 3: Add Oracle event types

**Files:**
- Modify: `amelia/server/models/events.py` (add 4 Oracle event types + ORACLE domain)
- Test: `tests/unit/server/test_oracle_events.py`

**Step 1: Write the failing test**

Create `tests/unit/server/test_oracle_events.py`:

```python
"""Tests for Oracle event types."""

from amelia.server.models.events import EventDomain, EventLevel, EventType, get_event_level


class TestOracleEventTypes:
    """Tests for Oracle-specific event types."""

    def test_oracle_event_types_exist(self):
        """Oracle event types should be defined in EventType enum."""
        assert EventType.ORACLE_CONSULTATION_STARTED == "oracle_consultation_started"
        assert EventType.ORACLE_CONSULTATION_THINKING == "oracle_consultation_thinking"
        assert EventType.ORACLE_CONSULTATION_COMPLETED == "oracle_consultation_completed"
        assert EventType.ORACLE_CONSULTATION_FAILED == "oracle_consultation_failed"

    def test_oracle_domain_exists(self):
        """ORACLE domain should be defined in EventDomain."""
        assert EventDomain.ORACLE == "oracle"

    def test_oracle_started_is_info_level(self):
        """ORACLE_CONSULTATION_STARTED should be info level."""
        assert get_event_level(EventType.ORACLE_CONSULTATION_STARTED) == EventLevel.INFO

    def test_oracle_completed_is_info_level(self):
        """ORACLE_CONSULTATION_COMPLETED should be info level."""
        assert get_event_level(EventType.ORACLE_CONSULTATION_COMPLETED) == EventLevel.INFO

    def test_oracle_failed_is_info_level(self):
        """ORACLE_CONSULTATION_FAILED should be info level."""
        assert get_event_level(EventType.ORACLE_CONSULTATION_FAILED) == EventLevel.INFO

    def test_oracle_thinking_is_trace_level(self):
        """ORACLE_CONSULTATION_THINKING should be trace level (streaming)."""
        assert get_event_level(EventType.ORACLE_CONSULTATION_THINKING) == EventLevel.TRACE
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/test_oracle_events.py -v`
Expected: FAIL with `AttributeError: 'ORACLE_CONSULTATION_STARTED' is not a member of 'EventType'`

**Step 3: Write the implementation**

In `amelia/server/models/events.py`:

1. Add to `EventDomain` enum, after `BRAINSTORM`:

```python
    ORACLE = "oracle"
```

2. Add to `EventType` enum, after the brainstorm events block:

```python
    # Oracle consultation events
    ORACLE_CONSULTATION_STARTED = "oracle_consultation_started"
    ORACLE_CONSULTATION_THINKING = "oracle_consultation_thinking"
    ORACLE_CONSULTATION_COMPLETED = "oracle_consultation_completed"
    ORACLE_CONSULTATION_FAILED = "oracle_consultation_failed"
```

3. Add to `_INFO_TYPES` frozenset:

```python
    EventType.ORACLE_CONSULTATION_STARTED,
    EventType.ORACLE_CONSULTATION_COMPLETED,
    EventType.ORACLE_CONSULTATION_FAILED,
```

4. Add to `_TRACE_TYPES` frozenset:

```python
    EventType.ORACLE_CONSULTATION_THINKING,
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/test_oracle_events.py -v`
Expected: 6 passed

**Step 5: Run full test suite to check for regressions**

Run: `uv run pytest tests/unit/server/ -v --tb=short`
Expected: All pass

**Step 6: Commit**

```bash
git add amelia/server/models/events.py tests/unit/server/test_oracle_events.py
git commit -m "feat(oracle): add Oracle event types and ORACLE domain"
```

---

### Task 4: Add oracle_consultations to BasePipelineState

**Files:**
- Modify: `amelia/pipelines/base.py` (add `oracle_consultations` field)
- Test: `tests/unit/pipelines/test_oracle_state.py`

**Step 1: Write the failing test**

Create `tests/unit/pipelines/test_oracle_state.py`:

```python
"""Tests for Oracle consultation state integration."""

from datetime import UTC, datetime

from amelia.core.types import OracleConsultation
from amelia.pipelines.implementation.state import (
    ImplementationState,
    rebuild_implementation_state,
)

# Resolve forward references
rebuild_implementation_state()


class TestOracleConsultationsState:
    """Tests for oracle_consultations field on pipeline state."""

    def test_default_empty(self):
        """oracle_consultations should default to empty list."""
        state = ImplementationState(
            workflow_id="wf-1",
            pipeline_type="implementation",
            profile_id="prof-1",
            created_at=datetime.now(tz=UTC),
            status="pending",
        )
        assert state.oracle_consultations == []

    def test_append_consultation(self):
        """oracle_consultations should support append via model_copy."""
        consultation = OracleConsultation(
            timestamp=datetime.now(tz=UTC),
            problem="How to refactor?",
            advice="Use DI.",
            model="claude-sonnet-4-20250514",
            session_id="sess-1",
        )
        state = ImplementationState(
            workflow_id="wf-1",
            pipeline_type="implementation",
            profile_id="prof-1",
            created_at=datetime.now(tz=UTC),
            status="running",
        )
        updated = state.model_copy(update={
            "oracle_consultations": [consultation],
        })
        assert len(updated.oracle_consultations) == 1
        assert updated.oracle_consultations[0].advice == "Use DI."
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/pipelines/test_oracle_state.py -v`
Expected: FAIL with `ValidationError` — `oracle_consultations` field not recognized.

**Step 3: Write the implementation**

In `amelia/pipelines/base.py`, add to `BasePipelineState` class, after the `error` field:

```python
    # Oracle consultations (append-only)
    oracle_consultations: Annotated[
        list[OracleConsultation], operator.add
    ] = Field(default_factory=list)
```

Add the import at the top of the file:

```python
from amelia.core.types import OracleConsultation
```

`Annotated`, `operator`, and `Field` should already be imported. Verify.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/pipelines/test_oracle_state.py -v`
Expected: 2 passed

**Step 5: Run full pipeline tests to check for regressions**

Run: `uv run pytest tests/unit/pipelines/ -v --tb=short`
Expected: All pass

**Step 6: Commit**

```bash
git add amelia/pipelines/base.py tests/unit/pipelines/test_oracle_state.py
git commit -m "feat(oracle): add oracle_consultations to BasePipelineState"
```

---

### Task 5: FileBundler — types and git-based file gathering

**Files:**
- Create: `amelia/tools/file_bundler.py`
- Test: `tests/unit/tools/test_file_bundler.py`

This is the largest component. We'll build it incrementally across tasks 5-6.

**Step 1: Write failing tests for BundledFile and FileBundle models, and basic bundle_files**

Create `tests/unit/tools/test_file_bundler.py`:

```python
"""Tests for FileBundler utility."""

import os
from pathlib import Path

import pytest

from amelia.tools.file_bundler import BundledFile, FileBundle, bundle_files
from tests.conftest import init_git_repo


class TestBundledFileModel:
    """Tests for BundledFile Pydantic model."""

    def test_construction(self):
        """BundledFile should hold path, content, and token estimate."""
        bf = BundledFile(path="src/main.py", content="print('hi')", token_estimate=3)
        assert bf.path == "src/main.py"
        assert bf.content == "print('hi')"
        assert bf.token_estimate == 3


class TestFileBundleModel:
    """Tests for FileBundle Pydantic model."""

    def test_construction(self):
        """FileBundle should aggregate files and total tokens."""
        files = [
            BundledFile(path="a.py", content="x=1", token_estimate=2),
            BundledFile(path="b.py", content="y=2", token_estimate=3),
        ]
        bundle = FileBundle(files=files, total_tokens=5, working_dir="/tmp/repo")
        assert len(bundle.files) == 2
        assert bundle.total_tokens == 5
        assert bundle.working_dir == "/tmp/repo"


class TestBundleFiles:
    """Tests for the bundle_files async function."""

    async def test_bundle_single_file(self, tmp_path: Path):
        """bundle_files should gather a single file matching a pattern."""
        repo = tmp_path / "repo"
        repo.mkdir()
        init_git_repo(repo)
        (repo / "hello.py").write_text("print('hello')")
        # Stage the file so git ls-files picks it up
        os.system(f"cd {repo} && git add hello.py")

        bundle = await bundle_files(
            working_dir=str(repo),
            patterns=["hello.py"],
        )
        assert len(bundle.files) == 1
        assert bundle.files[0].path == "hello.py"
        assert bundle.files[0].content == "print('hello')"
        assert bundle.files[0].token_estimate > 0
        assert bundle.total_tokens > 0

    async def test_bundle_glob_pattern(self, tmp_path: Path):
        """bundle_files should resolve glob patterns."""
        repo = tmp_path / "repo"
        repo.mkdir()
        init_git_repo(repo)
        src = repo / "src"
        src.mkdir()
        (src / "a.py").write_text("a = 1")
        (src / "b.py").write_text("b = 2")
        (repo / "readme.md").write_text("# Readme")
        os.system(f"cd {repo} && git add -A")

        bundle = await bundle_files(
            working_dir=str(repo),
            patterns=["src/*.py"],
        )
        paths = sorted(f.path for f in bundle.files)
        assert paths == ["src/a.py", "src/b.py"]

    async def test_bundle_respects_gitignore(self, tmp_path: Path):
        """bundle_files should exclude gitignored files."""
        repo = tmp_path / "repo"
        repo.mkdir()
        init_git_repo(repo)
        (repo / ".gitignore").write_text("ignored.py\n")
        (repo / "included.py").write_text("yes")
        (repo / "ignored.py").write_text("no")
        os.system(f"cd {repo} && git add -A")

        bundle = await bundle_files(
            working_dir=str(repo),
            patterns=["*.py"],
        )
        paths = [f.path for f in bundle.files]
        assert "included.py" in paths
        assert "ignored.py" not in paths

    async def test_bundle_skips_binary_files(self, tmp_path: Path):
        """bundle_files should skip binary files (null bytes detected)."""
        repo = tmp_path / "repo"
        repo.mkdir()
        init_git_repo(repo)
        (repo / "text.py").write_text("x = 1")
        (repo / "binary.bin").write_bytes(b"\x00\x01\x02\x03" * 128)
        os.system(f"cd {repo} && git add -A")

        bundle = await bundle_files(
            working_dir=str(repo),
            patterns=["*"],
        )
        paths = [f.path for f in bundle.files]
        assert "text.py" in paths
        assert "binary.bin" not in paths

    async def test_bundle_path_traversal_blocked(self, tmp_path: Path):
        """bundle_files should reject paths that escape working_dir."""
        repo = tmp_path / "repo"
        repo.mkdir()
        init_git_repo(repo)

        with pytest.raises(ValueError, match="outside working directory"):
            await bundle_files(
                working_dir=str(repo),
                patterns=["../../../etc/passwd"],
            )

    async def test_bundle_exclude_patterns(self, tmp_path: Path):
        """bundle_files should respect exclude_patterns."""
        repo = tmp_path / "repo"
        repo.mkdir()
        init_git_repo(repo)
        (repo / "keep.py").write_text("keep")
        (repo / "skip.py").write_text("skip")
        os.system(f"cd {repo} && git add -A")

        bundle = await bundle_files(
            working_dir=str(repo),
            patterns=["*.py"],
            exclude_patterns=["skip.py"],
        )
        paths = [f.path for f in bundle.files]
        assert "keep.py" in paths
        assert "skip.py" not in paths

    async def test_bundle_non_git_directory(self, tmp_path: Path):
        """bundle_files should work outside git repos with hardcoded exclusions."""
        work = tmp_path / "work"
        work.mkdir()
        (work / "main.py").write_text("main")
        node_modules = work / "node_modules"
        node_modules.mkdir()
        (node_modules / "dep.js").write_text("dep")

        bundle = await bundle_files(
            working_dir=str(work),
            patterns=["**/*.py", "**/*.js"],
        )
        paths = [f.path for f in bundle.files]
        assert "main.py" in paths
        assert "node_modules/dep.js" not in paths

    async def test_bundle_empty_patterns(self, tmp_path: Path):
        """bundle_files with no matching patterns should return empty bundle."""
        repo = tmp_path / "repo"
        repo.mkdir()
        init_git_repo(repo)

        bundle = await bundle_files(
            working_dir=str(repo),
            patterns=["*.nonexistent"],
        )
        assert bundle.files == []
        assert bundle.total_tokens == 0
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/tools/test_file_bundler.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'amelia.tools.file_bundler'`

**Step 3: Write the implementation**

Create `amelia/tools/file_bundler.py`:

```python
"""FileBundler — codebase file gathering utility.

Gathers files by glob patterns, estimates token counts, and returns structured
bundles for use as LLM context. Respects .gitignore when in a git repo.
"""

import asyncio
import fnmatch
import subprocess
from pathlib import Path

import tiktoken
from pydantic import BaseModel


class BundledFile(BaseModel):
    """A single file with its content and metadata.

    Attributes:
        path: File path relative to working_dir.
        content: File text content.
        token_estimate: Approximate token count (cl100k_base encoding).
    """

    path: str
    content: str
    token_estimate: int


class FileBundle(BaseModel):
    """Collection of gathered files with aggregate metrics.

    Attributes:
        files: List of bundled files.
        total_tokens: Sum of all file token estimates.
        working_dir: Root directory files were gathered from.
    """

    files: list[BundledFile]
    total_tokens: int
    working_dir: str


# Hardcoded exclusions for non-git directories
_DEFAULT_EXCLUSIONS = frozenset({
    "node_modules",
    "__pycache__",
    ".venv",
    ".git",
    "dist",
    "build",
})

# Lazy-loaded encoder
_encoder: tiktoken.Encoding | None = None


def _get_encoder() -> tiktoken.Encoding:
    """Get or create the tiktoken encoder (lazy singleton)."""
    global _encoder
    if _encoder is None:
        _encoder = tiktoken.get_encoding("cl100k_base")
    return _encoder


def _estimate_tokens(text: str) -> int:
    """Estimate token count using cl100k_base encoding.

    Args:
        text: Text to estimate tokens for.

    Returns:
        Approximate token count.
    """
    return len(_get_encoder().encode(text))


def _is_binary(data: bytes) -> bool:
    """Detect binary content by checking for null bytes in first 512 bytes.

    Args:
        data: Raw file bytes.

    Returns:
        True if file appears to be binary.
    """
    return b"\x00" in data[:512]


def _is_git_repo(working_dir: Path) -> bool:
    """Check if working_dir is inside a git repository.

    Args:
        working_dir: Directory to check.

    Returns:
        True if inside a git repo.
    """
    result = subprocess.run(
        ["git", "rev-parse", "--git-dir"],
        cwd=working_dir,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _get_git_tracked_files(working_dir: Path) -> set[str]:
    """Get all git-tracked files (respects .gitignore).

    Uses `git ls-files` which excludes gitignored files.

    Args:
        working_dir: Git repository root.

    Returns:
        Set of relative file paths tracked by git.
    """
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=working_dir,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return set()
    return {line for line in result.stdout.strip().split("\n") if line}


def _should_exclude_non_git(path: Path, working_dir: Path) -> bool:
    """Check if a path should be excluded in non-git mode.

    Excludes files under default exclusion directories.

    Args:
        path: Absolute path to check.
        working_dir: Working directory root.

    Returns:
        True if the file should be excluded.
    """
    rel = path.relative_to(working_dir)
    for part in rel.parts:
        if part in _DEFAULT_EXCLUSIONS:
            return True
    return False


def _resolve_globs(
    working_dir: Path,
    patterns: list[str],
    tracked_files: set[str] | None,
    exclude_patterns: list[str] | None,
) -> list[Path]:
    """Resolve glob patterns to file paths.

    In git mode, filters results against tracked files.
    In non-git mode, applies default directory exclusions.

    Args:
        working_dir: Root directory for glob resolution.
        patterns: Glob patterns to match.
        tracked_files: Git-tracked files (None if not in git repo).
        exclude_patterns: Additional patterns to exclude.

    Returns:
        List of resolved absolute file paths.

    Raises:
        ValueError: If any resolved path escapes working_dir.
    """
    resolved_dir = working_dir.resolve()
    matched: set[Path] = set()

    for pattern in patterns:
        for path in working_dir.glob(pattern):
            abs_path = path.resolve()

            # Path traversal check
            try:
                abs_path.relative_to(resolved_dir)
            except ValueError:
                raise ValueError(
                    f"Path '{pattern}' resolves outside working directory: {abs_path}"
                )

            if not abs_path.is_file():
                continue

            rel_path = str(abs_path.relative_to(resolved_dir))

            # Git mode: filter to tracked files
            if tracked_files is not None:
                if rel_path not in tracked_files:
                    continue
            else:
                # Non-git mode: apply default exclusions
                if _should_exclude_non_git(abs_path, resolved_dir):
                    continue

            # Apply exclude patterns
            if exclude_patterns:
                excluded = False
                for ep in exclude_patterns:
                    if fnmatch.fnmatch(rel_path, ep):
                        excluded = True
                        break
                if excluded:
                    continue

            matched.add(abs_path)

    return sorted(matched)


async def _read_file(path: Path) -> bytes | None:
    """Read file contents asynchronously.

    Args:
        path: Absolute path to read.

    Returns:
        File bytes, or None if read fails.
    """
    try:
        return await asyncio.to_thread(path.read_bytes)
    except (OSError, PermissionError):
        return None


async def bundle_files(
    working_dir: str,
    patterns: list[str],
    exclude_patterns: list[str] | None = None,
) -> FileBundle:
    """Gather codebase files by glob patterns with token estimation.

    Resolves globs relative to working_dir, reads file contents, estimates
    token counts, and returns a structured bundle. Respects .gitignore
    when inside a git repo.

    Args:
        working_dir: Root directory for file gathering.
        patterns: Glob patterns to match (e.g., ["src/**/*.py"]).
        exclude_patterns: Additional glob patterns to exclude.

    Returns:
        FileBundle with matched files and token counts.

    Raises:
        ValueError: If any resolved path escapes working_dir.
    """
    wd = Path(working_dir)
    is_git = _is_git_repo(wd)
    tracked = _get_git_tracked_files(wd) if is_git else None

    file_paths = _resolve_globs(wd, patterns, tracked, exclude_patterns)

    bundled: list[BundledFile] = []
    total_tokens = 0

    for abs_path in file_paths:
        raw = await _read_file(abs_path)
        if raw is None:
            continue

        if _is_binary(raw):
            continue

        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue

        tokens = _estimate_tokens(content)
        rel_path = str(abs_path.relative_to(Path(working_dir).resolve()))

        bundled.append(BundledFile(
            path=rel_path,
            content=content,
            token_estimate=tokens,
        ))
        total_tokens += tokens

    return FileBundle(
        files=bundled,
        total_tokens=total_tokens,
        working_dir=working_dir,
    )
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/tools/test_file_bundler.py -v`
Expected: All pass

**Step 5: Run linting and type checking**

Run: `uv run ruff check amelia/tools/file_bundler.py && uv run mypy amelia/tools/file_bundler.py`
Expected: Clean

**Step 6: Commit**

```bash
git add amelia/tools/file_bundler.py tests/unit/tools/test_file_bundler.py
git commit -m "feat(oracle): add FileBundler utility for codebase file gathering"
```

---

### Task 6: Oracle agent — consult method

**Files:**
- Create: `amelia/agents/oracle.py`
- Modify: `amelia/agents/__init__.py` (export Oracle)
- Test: `tests/unit/agents/test_oracle.py`

**Step 1: Write the failing tests**

Create `tests/unit/agents/test_oracle.py`:

```python
"""Tests for Oracle agent."""

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from amelia.agents.oracle import Oracle, OracleConsultResult
from amelia.core.types import AgentConfig, OracleConsultation
from amelia.drivers.base import AgenticMessage, AgenticMessageType
from amelia.server.events.bus import EventBus
from amelia.server.models.events import EventType
from tests.conftest import create_mock_execute_agentic


class TestOracleInit:
    """Tests for Oracle initialization."""

    def test_init_creates_driver(self):
        """Oracle should create a driver from AgentConfig."""
        config = AgentConfig(driver="cli", model="sonnet")

        with patch("amelia.agents.oracle.get_driver") as mock_get_driver:
            mock_driver = MagicMock()
            mock_get_driver.return_value = mock_driver

            oracle = Oracle(config)

            mock_get_driver.assert_called_once_with("cli", model="sonnet")
            assert oracle._driver is mock_driver

    def test_init_accepts_event_bus(self):
        """Oracle should accept an optional EventBus."""
        config = AgentConfig(driver="cli", model="sonnet")
        event_bus = EventBus()

        with patch("amelia.agents.oracle.get_driver"):
            oracle = Oracle(config, event_bus=event_bus)
            assert oracle._event_bus is event_bus


class TestOracleConsult:
    """Tests for Oracle.consult() method."""

    async def test_consult_returns_result(self, tmp_path):
        """consult() should return OracleConsultResult with advice."""
        config = AgentConfig(driver="cli", model="sonnet")

        with patch("amelia.agents.oracle.get_driver") as mock_get_driver:
            mock_driver = MagicMock()
            mock_driver.execute_agentic = create_mock_execute_agentic([
                AgenticMessage(type=AgenticMessageType.THINKING, content="Analyzing..."),
                AgenticMessage(type=AgenticMessageType.RESULT, content="Use dependency injection."),
            ])
            mock_get_driver.return_value = mock_driver

            with patch("amelia.agents.oracle.bundle_files", new_callable=AsyncMock) as mock_bundle:
                from amelia.tools.file_bundler import FileBundle

                mock_bundle.return_value = FileBundle(
                    files=[], total_tokens=0, working_dir=str(tmp_path),
                )

                oracle = Oracle(config)
                result = await oracle.consult(
                    problem="How to refactor auth?",
                    working_dir=str(tmp_path),
                )

        assert isinstance(result, OracleConsultResult)
        assert result.advice == "Use dependency injection."
        assert result.consultation.problem == "How to refactor auth?"
        assert result.consultation.outcome == "success"
        assert result.consultation.session_id  # Should be a UUID

    async def test_consult_passes_files_to_bundler(self, tmp_path):
        """consult() should pass file patterns to bundle_files."""
        config = AgentConfig(driver="cli", model="sonnet")

        with patch("amelia.agents.oracle.get_driver") as mock_get_driver:
            mock_driver = MagicMock()
            mock_driver.execute_agentic = create_mock_execute_agentic([
                AgenticMessage(type=AgenticMessageType.RESULT, content="Done"),
            ])
            mock_get_driver.return_value = mock_driver

            with patch("amelia.agents.oracle.bundle_files", new_callable=AsyncMock) as mock_bundle:
                from amelia.tools.file_bundler import FileBundle

                mock_bundle.return_value = FileBundle(
                    files=[], total_tokens=0, working_dir=str(tmp_path),
                )

                oracle = Oracle(config)
                await oracle.consult(
                    problem="Analyze",
                    working_dir=str(tmp_path),
                    files=["src/**/*.py"],
                )

                mock_bundle.assert_called_once_with(
                    working_dir=str(tmp_path),
                    patterns=["src/**/*.py"],
                )

    async def test_consult_emits_events(self, tmp_path):
        """consult() should emit start, thinking, and complete events."""
        config = AgentConfig(driver="cli", model="sonnet")
        event_bus = EventBus()
        emitted: list[Any] = []
        event_bus.subscribe(lambda e: emitted.append(e))

        with patch("amelia.agents.oracle.get_driver") as mock_get_driver:
            mock_driver = MagicMock()
            mock_driver.execute_agentic = create_mock_execute_agentic([
                AgenticMessage(type=AgenticMessageType.THINKING, content="Hmm"),
                AgenticMessage(type=AgenticMessageType.RESULT, content="Advice"),
            ])
            mock_get_driver.return_value = mock_driver

            with patch("amelia.agents.oracle.bundle_files", new_callable=AsyncMock) as mock_bundle:
                from amelia.tools.file_bundler import FileBundle

                mock_bundle.return_value = FileBundle(
                    files=[], total_tokens=0, working_dir=str(tmp_path),
                )

                oracle = Oracle(config, event_bus=event_bus)
                await oracle.consult(
                    problem="Test",
                    working_dir=str(tmp_path),
                )

        event_types = [e.event_type for e in emitted]
        assert EventType.ORACLE_CONSULTATION_STARTED in event_types
        assert EventType.ORACLE_CONSULTATION_COMPLETED in event_types

    async def test_consult_handles_driver_error(self, tmp_path):
        """consult() should return error outcome on driver failure."""
        config = AgentConfig(driver="cli", model="sonnet")

        with patch("amelia.agents.oracle.get_driver") as mock_get_driver:
            mock_driver = MagicMock()

            async def _failing_agentic(*args, **kwargs):
                raise RuntimeError("Driver crashed")
                yield  # noqa: unreachable — makes this an async generator

            mock_driver.execute_agentic = _failing_agentic
            mock_get_driver.return_value = mock_driver

            with patch("amelia.agents.oracle.bundle_files", new_callable=AsyncMock) as mock_bundle:
                from amelia.tools.file_bundler import FileBundle

                mock_bundle.return_value = FileBundle(
                    files=[], total_tokens=0, working_dir=str(tmp_path),
                )

                oracle = Oracle(config)
                result = await oracle.consult(
                    problem="Test",
                    working_dir=str(tmp_path),
                )

        assert result.consultation.outcome == "error"
        assert "Driver crashed" in (result.consultation.error_message or "")
        assert result.advice == ""
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/agents/test_oracle.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'amelia.agents.oracle'`

**Step 3: Write the implementation**

Create `amelia/agents/oracle.py`:

```python
"""Oracle agent — expert consultation using agentic LLM execution.

Accepts a problem statement and codebase context, reasons about it using
an agentic LLM session with tool access, and returns structured advice.
"""

from datetime import UTC, datetime
from uuid import uuid4

from loguru import logger
from pydantic import BaseModel

from amelia.core.types import AgentConfig, OracleConsultation
from amelia.drivers.base import AgenticMessageType
from amelia.drivers.factory import get_driver
from amelia.server.events.bus import EventBus
from amelia.server.models.events import EventDomain, EventType, WorkflowEvent
from amelia.tools.file_bundler import bundle_files


class OracleConsultResult(BaseModel):
    """Result from an Oracle consultation.

    Attributes:
        advice: The Oracle's advice text.
        consultation: Full consultation record for persistence.
    """

    advice: str
    consultation: OracleConsultation


_SYSTEM_PROMPT = (
    "You are a consulting expert. Analyze the codebase context and provide "
    "advice on the given problem. Be specific, actionable, and reference "
    "concrete files and patterns from the codebase."
)


class Oracle:
    """Oracle agent for expert codebase consultations.

    Uses agentic LLM execution to analyze code and provide advice.
    The agent can read additional files and run shell commands during
    its reasoning process.

    Args:
        config: Agent configuration with driver, model, and options.
        event_bus: Optional EventBus for emitting consultation events.
    """

    def __init__(
        self,
        config: AgentConfig,
        event_bus: EventBus | None = None,
    ):
        self._driver = get_driver(config.driver, model=config.model)
        self._event_bus = event_bus
        self._config = config

    def _emit(self, event: WorkflowEvent) -> None:
        """Emit event via EventBus if available."""
        if self._event_bus is not None:
            self._event_bus.emit(event)

    def _make_event(
        self,
        event_type: EventType,
        session_id: str,
        message: str,
        **kwargs: object,
    ) -> WorkflowEvent:
        """Create a WorkflowEvent for Oracle consultations."""
        return WorkflowEvent(
            id=str(uuid4()),
            domain=EventDomain.ORACLE,
            workflow_id=session_id,
            sequence=0,
            timestamp=datetime.now(tz=UTC),
            agent="oracle",
            event_type=event_type,
            message=message,
            **kwargs,
        )

    async def consult(
        self,
        problem: str,
        working_dir: str,
        files: list[str] | None = None,
        workflow_id: str | None = None,
    ) -> OracleConsultResult:
        """Run an Oracle consultation.

        Gathers codebase context via FileBundler, then uses agentic LLM
        execution to analyze the problem and generate advice.

        Args:
            problem: The problem statement to analyze.
            working_dir: Root directory for codebase access.
            files: Optional glob patterns for files to include as context.
            workflow_id: Optional workflow ID for cross-referencing.

        Returns:
            OracleConsultResult with advice and consultation record.
        """
        session_id = str(uuid4())
        timestamp = datetime.now(tz=UTC)

        logger.info(
            "Oracle consultation started",
            session_id=session_id,
            working_dir=working_dir,
        )

        # Emit started event
        self._emit(self._make_event(
            EventType.ORACLE_CONSULTATION_STARTED,
            session_id=session_id,
            message=f"Oracle consultation started: {problem[:100]}",
        ))

        # Gather codebase context
        patterns = files or ["**/*.py", "**/*.md"]
        bundle = await bundle_files(working_dir=working_dir, patterns=patterns)

        files_consulted = [f.path for f in bundle.files]

        # Build prompt with context
        context_parts: list[str] = [f"## Problem\n\n{problem}"]
        if bundle.files:
            context_parts.append("\n## Codebase Context\n")
            for f in bundle.files:
                context_parts.append(f"### {f.path}\n```\n{f.content}\n```\n")

        user_prompt = "\n".join(context_parts)

        # Execute agentic consultation
        advice = ""
        try:
            async for message in self._driver.execute_agentic(
                prompt=user_prompt,
                cwd=working_dir,
                instructions=_SYSTEM_PROMPT,
            ):
                if message.type == AgenticMessageType.THINKING:
                    self._emit(self._make_event(
                        EventType.ORACLE_CONSULTATION_THINKING,
                        session_id=session_id,
                        message=message.content or "",
                    ))

                elif message.type == AgenticMessageType.RESULT:
                    advice = message.content or ""

            consultation = OracleConsultation(
                timestamp=timestamp,
                problem=problem,
                advice=advice,
                model=self._config.model,
                session_id=session_id,
                files_consulted=files_consulted,
                tokens={"context": bundle.total_tokens},
                outcome="success",
            )

            self._emit(self._make_event(
                EventType.ORACLE_CONSULTATION_COMPLETED,
                session_id=session_id,
                message="Oracle consultation completed",
            ))

            logger.info(
                "Oracle consultation completed",
                session_id=session_id,
                advice_length=len(advice),
            )

        except Exception as exc:
            logger.error(
                "Oracle consultation failed",
                session_id=session_id,
                error=str(exc),
            )

            consultation = OracleConsultation(
                timestamp=timestamp,
                problem=problem,
                model=self._config.model,
                session_id=session_id,
                files_consulted=files_consulted,
                outcome="error",
                error_message=str(exc),
            )

            self._emit(self._make_event(
                EventType.ORACLE_CONSULTATION_FAILED,
                session_id=session_id,
                message=f"Oracle consultation failed: {exc}",
            ))

            return OracleConsultResult(advice="", consultation=consultation)

        return OracleConsultResult(advice=advice, consultation=consultation)
```

**Step 4: Update `amelia/agents/__init__.py`**

Add Oracle to the exports:

Add import:
```python
from amelia.agents.oracle import Oracle
```

Add `"Oracle"` to `__all__`.

**Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/unit/agents/test_oracle.py -v`
Expected: All pass

**Step 6: Run linting**

Run: `uv run ruff check amelia/agents/oracle.py`
Expected: Clean

**Step 7: Commit**

```bash
git add amelia/agents/oracle.py amelia/agents/__init__.py tests/unit/agents/test_oracle.py
git commit -m "feat(oracle): add Oracle agent with agentic consultation"
```

---

### Task 7: Oracle API endpoint

**Files:**
- Create: `amelia/server/routes/oracle.py`
- Modify: `amelia/server/main.py` (register oracle_router)
- Test: `tests/unit/server/routes/test_oracle_routes.py`

**Step 1: Write the failing tests**

Create `tests/unit/server/routes/test_oracle_routes.py`:

```python
"""Tests for Oracle API routes."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from amelia.server.routes.oracle import router


@pytest.fixture
def app() -> FastAPI:
    """Create test FastAPI app with oracle router."""
    test_app = FastAPI()
    test_app.include_router(router, prefix="/api/oracle")
    return test_app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """Create test client."""
    return TestClient(app)


class TestOracleConsultRoute:
    """Tests for POST /api/oracle/consult."""

    def test_consult_returns_202(self, client: TestClient):
        """Consult endpoint should return 202 Accepted."""
        with (
            patch("amelia.server.routes.oracle._get_profile") as mock_get_profile,
            patch("amelia.server.routes.oracle._get_event_bus") as mock_get_bus,
            patch("amelia.server.routes.oracle.Oracle") as mock_oracle_cls,
        ):
            mock_profile = MagicMock()
            mock_profile.working_dir = "/tmp/work"
            mock_profile.get_agent_config.return_value = MagicMock(
                driver="cli", model="sonnet"
            )
            mock_get_profile.return_value = mock_profile
            mock_get_bus.return_value = MagicMock()

            mock_oracle = MagicMock()
            mock_oracle.consult = AsyncMock(return_value=MagicMock(
                advice="Use DI.",
                consultation=MagicMock(
                    model_dump=MagicMock(return_value={
                        "timestamp": "2026-01-01T00:00:00Z",
                        "problem": "Refactor auth",
                        "advice": "Use DI.",
                        "model": "sonnet",
                        "session_id": "abc",
                        "tokens": {},
                        "cost_usd": None,
                        "files_consulted": [],
                        "outcome": "success",
                        "error_message": None,
                    }),
                ),
            ))
            mock_oracle_cls.return_value = mock_oracle

            response = client.post("/api/oracle/consult", json={
                "problem": "How to refactor auth?",
                "working_dir": "/tmp/work",
            })

        assert response.status_code == 202

    def test_consult_validates_working_dir(self, client: TestClient):
        """Consult should reject working_dir outside profile root."""
        with (
            patch("amelia.server.routes.oracle._get_profile") as mock_get_profile,
        ):
            mock_profile = MagicMock()
            mock_profile.working_dir = "/home/user/projects"
            mock_get_profile.return_value = mock_profile

            response = client.post("/api/oracle/consult", json={
                "problem": "Analyze",
                "working_dir": "/etc/passwd",
            })

        assert response.status_code == 400

    def test_consult_missing_oracle_config(self, client: TestClient):
        """Consult should return 400 if profile lacks oracle agent config."""
        with (
            patch("amelia.server.routes.oracle._get_profile") as mock_get_profile,
        ):
            mock_profile = MagicMock()
            mock_profile.working_dir = "/tmp/work"
            mock_profile.get_agent_config.side_effect = ValueError(
                "Agent 'oracle' not configured"
            )
            mock_get_profile.return_value = mock_profile

            response = client.post("/api/oracle/consult", json={
                "problem": "Analyze",
                "working_dir": "/tmp/work",
            })

        assert response.status_code == 400
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/server/routes/test_oracle_routes.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'amelia.server.routes.oracle'`

**Step 3: Write the implementation**

Create `amelia/server/routes/oracle.py`:

```python
"""Oracle consultation API routes.

Provides the REST endpoint for standalone Oracle consultations.
Events stream via WebSocket in real-time using the same EventBus
pattern as brainstorm sessions.
"""

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from loguru import logger
from pydantic import BaseModel

from amelia.agents.oracle import Oracle, OracleConsultResult
from amelia.core.types import AgentConfig, OracleConsultation, Profile
from amelia.server.events.bus import EventBus


router = APIRouter(tags=["oracle"])


# --- Request / Response models ---


class OracleConsultRequest(BaseModel):
    """Request body for Oracle consultation.

    Attributes:
        problem: The problem statement to analyze.
        working_dir: Root directory for codebase access.
        files: Optional glob patterns for files to include.
        model: Optional model override.
        profile_id: Optional profile ID (uses active profile if omitted).
    """

    problem: str
    working_dir: str
    files: list[str] | None = None
    model: str | None = None
    profile_id: str | None = None


class OracleConsultResponse(BaseModel):
    """Response body for Oracle consultation.

    Attributes:
        advice: The Oracle's advice.
        consultation: Full consultation record.
    """

    advice: str
    consultation: OracleConsultation


# --- Dependency stubs (overridden in main.py) ---


async def _get_profile(profile_id: str | None = None) -> Profile:
    """Get profile — overridden in main.py."""
    raise NotImplementedError("Must be overridden via dependency_overrides")


def _get_event_bus() -> EventBus:
    """Get EventBus — overridden in main.py."""
    raise NotImplementedError("Must be overridden via dependency_overrides")


def _validate_working_dir(requested: str, profile_root: str) -> None:
    """Validate that requested working_dir is within profile root.

    Args:
        requested: The requested working directory.
        profile_root: The profile's configured working directory.

    Raises:
        HTTPException: If requested path is outside profile root.
    """
    try:
        Path(requested).resolve().relative_to(Path(profile_root).resolve())
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"working_dir must be within profile root: {profile_root}",
        )


# --- Route ---


@router.post(
    "/consult",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=OracleConsultResponse,
)
async def consult(
    request: OracleConsultRequest,
    background_tasks: BackgroundTasks,
) -> OracleConsultResponse:
    """Run an Oracle consultation.

    Accepts a problem statement and optional file patterns. The Oracle
    agent gathers codebase context and uses agentic LLM execution to
    provide expert advice.

    Events stream via WebSocket in real-time.

    Args:
        request: Consultation request with problem and context.
        background_tasks: FastAPI background tasks.

    Returns:
        OracleConsultResponse with advice and consultation record.

    Raises:
        HTTPException: 400 if working_dir invalid or oracle not configured.
    """
    # Resolve profile
    profile = await _get_profile(request.profile_id)

    # Validate working_dir
    _validate_working_dir(request.working_dir, profile.working_dir)

    # Get oracle agent config
    try:
        agent_config = profile.get_agent_config("oracle")
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    # Override model if provided
    if request.model:
        agent_config = AgentConfig(
            driver=agent_config.driver,
            model=request.model,
            options=agent_config.options,
        )

    # Get event bus
    event_bus = _get_event_bus()

    # Run consultation
    oracle = Oracle(config=agent_config, event_bus=event_bus)
    result: OracleConsultResult = await oracle.consult(
        problem=request.problem,
        working_dir=request.working_dir,
        files=request.files,
    )

    logger.info(
        "Oracle consultation API complete",
        session_id=result.consultation.session_id,
        outcome=result.consultation.outcome,
    )

    return OracleConsultResponse(
        advice=result.advice,
        consultation=result.consultation,
    )
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/server/routes/test_oracle_routes.py -v`
Expected: All pass

**Step 5: Run linting**

Run: `uv run ruff check amelia/server/routes/oracle.py`
Expected: Clean

**Step 6: Commit**

```bash
git add amelia/server/routes/oracle.py tests/unit/server/routes/test_oracle_routes.py
git commit -m "feat(oracle): add Oracle API endpoint POST /api/oracle/consult"
```

---

### Task 8: Register Oracle router in server

**Files:**
- Modify: `amelia/server/main.py` (import and mount oracle_router, wire dependencies)

**Step 1: Add import**

In `amelia/server/main.py`, add after the brainstorm router import block:

```python
from amelia.server.routes.oracle import (
    _get_event_bus as oracle_get_event_bus,
    _get_profile as oracle_get_profile,
    router as oracle_router,
)
```

**Step 2: Mount the router**

In `create_app()`, add after the brainstorm router line:

```python
    application.include_router(oracle_router, prefix="/api/oracle")
```

**Step 3: Wire dependency overrides**

In `create_app()`, add after the brainstorm cwd override block:

```python
    # Set up Oracle dependencies
    async def get_oracle_profile(profile_id: str | None = None) -> Profile:
        """Get profile for Oracle consultations."""
        profile_repo = get_profile_repository()
        if profile_id:
            profile = await profile_repo.get_profile(profile_id)
            if profile is None:
                from fastapi import HTTPException
                raise HTTPException(status_code=404, detail=f"Profile not found: {profile_id}")
            return profile
        active = await profile_repo.get_active_profile()
        if active is None:
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail="No active profile")
        return active

    application.dependency_overrides[oracle_get_profile] = get_oracle_profile

    def get_oracle_event_bus() -> EventBus:
        """Get EventBus for Oracle consultations."""
        return application.state.event_bus

    application.dependency_overrides[oracle_get_event_bus] = get_oracle_event_bus
```

Note: `Profile` is already imported via `amelia.core.types` at the top of the file (verify — if not, add the import).

**Step 4: Verify server starts**

Run: `uv run python -c "from amelia.server.main import create_app; app = create_app(); print('OK')"`
Expected: `OK` (no import errors)

**Step 5: Run full test suite**

Run: `uv run pytest tests/ --tb=short -q`
Expected: All pass

**Step 6: Run linting and type checking**

Run: `uv run ruff check amelia/server/main.py && uv run mypy amelia/server/main.py`
Expected: Clean

**Step 7: Commit**

```bash
git add amelia/server/main.py
git commit -m "feat(oracle): register Oracle router in FastAPI app"
```

---

### Task 9: Final verification — lint, types, full test suite

**Files:** None (verification only)

**Step 1: Run ruff on all modified files**

Run: `uv run ruff check amelia tests`
Expected: Clean

**Step 2: Run mypy**

Run: `uv run mypy amelia`
Expected: Clean (or pre-existing issues only)

**Step 3: Run full test suite**

Run: `uv run pytest`
Expected: All pass, including all new tests

**Step 4: Review new files list**

New files created:
- `amelia/tools/file_bundler.py` — FileBundler utility
- `amelia/agents/oracle.py` — Oracle agent
- `amelia/server/routes/oracle.py` — API endpoint
- `tests/unit/core/test_oracle_types.py` — OracleConsultation model tests
- `tests/unit/server/test_oracle_events.py` — Event type tests
- `tests/unit/pipelines/test_oracle_state.py` — Pipeline state tests
- `tests/unit/tools/test_file_bundler.py` — FileBundler tests
- `tests/unit/agents/test_oracle.py` — Oracle agent tests
- `tests/unit/server/routes/test_oracle_routes.py` — API endpoint tests

Modified files:
- `pyproject.toml` — tiktoken dependency
- `amelia/core/types.py` — OracleConsultation model
- `amelia/pipelines/base.py` — oracle_consultations field
- `amelia/server/models/events.py` — Oracle event types + domain
- `amelia/agents/__init__.py` — Oracle export
- `amelia/server/main.py` — Oracle router registration

---

## Dependency Graph

```
Task 1 (tiktoken dep) ──┐
                         ├── Task 5 (FileBundler) ──┐
Task 2 (types) ──────────┤                          ├── Task 6 (Oracle agent) ── Task 7 (API route) ── Task 8 (register) ── Task 9 (verify)
Task 3 (events) ─────────┤                          │
Task 4 (state) ──────────┘                          │
                                                     │
Tasks 1-4 can be done in parallel ───────────────────┘
```

Tasks 1, 2, 3, 4 are independent and can be parallelized.
Task 5 depends on Task 1 (tiktoken).
Task 6 depends on Tasks 2, 3, 5.
Task 7 depends on Task 6.
Task 8 depends on Task 7.
Task 9 depends on Task 8.
