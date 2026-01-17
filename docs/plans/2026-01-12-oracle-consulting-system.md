# Oracle Consulting System Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Integrate an Oracle-like consulting system into Amelia that provides expert guidance when agents get stuck, using file bundling, dedicated LLM models, and hybrid exploration.

**Architecture:** Oracle bundles file context using glob patterns (like the original Oracle npm package), queries a dedicated LLM model for consultation, and maintains a hybrid approach where agents can also explore further with tools if needed. Integration occurs at two levels: as a callable tool for agents during execution, and as a REST API endpoint for external clients. All consultations are tracked in ExecutionState and streamed in real-time via WebSocket events.

**Tech Stack:** FastAPI (endpoint), asyncio (subprocess execution), tiktoken (token estimation), gitignore-parser (.gitignore support), Pydantic (models), LangGraph (state persistence), WebSocket (event streaming), Python pathlib (glob expansion).

---

## Task 1: Add Dependencies to pyproject.toml

**Files:**
- Modify: `pyproject.toml`

**Step 1: Open pyproject.toml and locate dependencies section**

```bash
cat pyproject.toml | grep -A 20 "\[tool.poetry.dependencies\]"
```

Find where the existing dependencies are listed.

**Step 2: Add three new dependencies**

Add these three lines to the dependencies section (keeping them alphabetically ordered):

```toml
aiofiles = "^23.0.0"
gitignore-parser = "^0.1.0"
tiktoken = "^0.5.0"
```

**Step 3: Verify formatting is correct**

```bash
# Check that pyproject.toml is valid TOML
python -c "import toml; toml.load('pyproject.toml'); print('✓ Valid TOML')"
```

Expected: `✓ Valid TOML`

**Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "deps: add tiktoken, gitignore-parser, aiofiles for Oracle integration"
```

---

## Task 2: Create File Bundler Utility

**Files:**
- Create: `amelia/tools/file_bundler.py`
- Create: `tests/unit/tools/test_file_bundler.py`

**Step 1: Write failing test for FileSection model**

Create `tests/unit/tools/test_file_bundler.py`:

```python
"""Tests for file bundler utility."""

import pytest
from pathlib import Path
from pydantic import BaseModel
from amelia.tools.file_bundler import FileSection, FileBundler


def test_file_section_model_creation():
    """Test FileSection can be created with required fields."""
    section = FileSection(
        path="src/example.py",
        content="print('hello')",
        tokens=10,
        language="python",
    )
    assert section.path == "src/example.py"
    assert section.content == "print('hello')"
    assert section.tokens == 10
    assert section.language == "python"


def test_file_bundler_initialization():
    """Test FileBundler initializes correctly."""
    bundler = FileBundler()
    assert bundler is not None
```

Run: `pytest tests/unit/tools/test_file_bundler.py::test_file_section_model_creation -v`

Expected: FAIL - `ModuleNotFoundError: No module named 'amelia.tools.file_bundler'`

**Step 2: Create FileBundler module with FileSection model**

Create `amelia/tools/file_bundler.py`:

```python
"""File bundling utility for context gathering."""

from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field


class FileSection(BaseModel):
    """A single file section for bundling."""

    path: str
    """Path to the file relative to project root."""

    content: str
    """File contents."""

    tokens: int
    """Estimated token count for this file."""

    language: Optional[str] = None
    """Programming language for syntax highlighting."""


class FileBundler:
    """Bundles files using glob patterns with token estimation."""

    def __init__(self, max_file_size: int = 1_000_000):
        """Initialize FileBundler.

        Args:
            max_file_size: Maximum file size in bytes (default: 1MB)
        """
        self.max_file_size = max_file_size
```

Run: `pytest tests/unit/tools/test_file_bundler.py::test_file_section_model_creation -v`

Expected: PASS

Run: `pytest tests/unit/tools/test_file_bundler.py::test_file_bundler_initialization -v`

Expected: PASS

**Step 3: Add estimate_tokens method test**

Add to `tests/unit/tools/test_file_bundler.py`:

```python
@pytest.mark.asyncio
async def test_estimate_tokens_simple():
    """Test token estimation on simple text."""
    bundler = FileBundler()

    # Rough estimation: ~1 token per 4 characters
    text = "hello world"
    tokens = await bundler.estimate_tokens(text)

    # Should be roughly 3 tokens (allowing for tokenizer variance)
    assert 1 <= tokens <= 5
```

Run: `pytest tests/unit/tools/test_file_bundler.py::test_estimate_tokens_simple -v`

Expected: FAIL - `AttributeError: 'FileBundler' object has no attribute 'estimate_tokens'`

**Step 4: Implement estimate_tokens using tiktoken**

Add to `amelia/tools/file_bundler.py`:

```python
import tiktoken


class FileBundler:
    # ... existing code ...

    async def estimate_tokens(self, content: str, model: str = "gpt-4") -> int:
        """Estimate tokens in content using tiktoken.

        Args:
            content: Text to estimate tokens for
            model: Model to use for tokenization (default: gpt-4)

        Returns:
            Estimated token count
        """
        try:
            encoding = tiktoken.encoding_for_model(model)
        except KeyError:
            # Fallback to cl100k_base encoding if model not found
            encoding = tiktoken.get_encoding("cl100k_base")

        tokens = encoding.encode(content)
        return len(tokens)
```

Run: `pytest tests/unit/tools/test_file_bundler.py::test_estimate_tokens_simple -v`

Expected: PASS

**Step 5: Commit**

```bash
git add amelia/tools/file_bundler.py tests/unit/tools/test_file_bundler.py
git commit -m "feat: add FileBundler utility with FileSection model and token estimation"
```

---

## Task 3: Implement File Gathering in FileBundler

**Files:**
- Modify: `amelia/tools/file_bundler.py`
- Modify: `tests/unit/tools/test_file_bundler.py`

**Step 1: Add test for file gathering (with temporary test files)**

Add to `tests/unit/tools/test_file_bundler.py`:

```python
import tempfile
import os


@pytest.mark.asyncio
async def test_gather_files_basic(tmp_path):
    """Test gathering files from a directory."""
    # Create test directory structure
    src_dir = tmp_path / "src"
    src_dir.mkdir()

    # Create test files
    (src_dir / "main.py").write_text("print('main')")
    (src_dir / "utils.py").write_text("def helper(): pass")

    bundler = FileBundler()
    sections = await bundler.gather_files(
        patterns=["src/**/*.py"],
        cwd=str(tmp_path),
        max_tokens=10000,
    )

    assert len(sections) >= 2
    assert any(s.path.endswith("main.py") for s in sections)
    assert any(s.path.endswith("utils.py") for s in sections)
```

Run: `pytest tests/unit/tools/test_file_bundler.py::test_gather_files_basic -v`

Expected: FAIL - `AttributeError: 'FileBundler' object has no attribute 'gather_files'`

**Step 2: Implement gather_files method**

Add to `amelia/tools/file_bundler.py`:

```python
from pathlib import Path
from typing import List
import aiofiles


class FileBundler:
    # ... existing code ...

    async def gather_files(
        self,
        patterns: List[str],
        cwd: str,
        max_tokens: int,
    ) -> List[FileSection]:
        """Gather files matching glob patterns.

        Args:
            patterns: Glob patterns (e.g., ["src/**/*.py"])
            cwd: Current working directory (project root)
            max_tokens: Maximum total tokens to bundle

        Returns:
            List of FileSection objects
        """
        sections = []
        token_count = 0
        cwd_path = Path(cwd)

        for pattern in patterns:
            # Use glob to find matching files
            for file_path in cwd_path.glob(pattern):
                if not file_path.is_file():
                    continue

                # Skip if file is too large
                if file_path.stat().st_size > self.max_file_size:
                    continue

                # Read file content
                try:
                    async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
                        content = await f.read()
                except (UnicodeDecodeError, IOError):
                    continue

                # Estimate tokens
                tokens = await self.estimate_tokens(content)

                # Check if adding this file would exceed budget
                if token_count + tokens > max_tokens:
                    continue

                # Add section
                relative_path = str(file_path.relative_to(cwd_path))
                section = FileSection(
                    path=relative_path,
                    content=content,
                    tokens=tokens,
                    language=self._guess_language(relative_path),
                )
                sections.append(section)
                token_count += tokens

        return sections

    @staticmethod
    def _guess_language(path: str) -> str:
        """Guess programming language from file extension."""
        ext_to_lang = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".go": "go",
            ".rs": "rust",
            ".java": "java",
            ".cpp": "cpp",
            ".c": "c",
            ".h": "c",
            ".sh": "bash",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".json": "json",
            ".md": "markdown",
        }
        suffix = Path(path).suffix.lower()
        return ext_to_lang.get(suffix, None)
```

Run: `pytest tests/unit/tools/test_file_bundler.py::test_gather_files_basic -v`

Expected: PASS

**Step 3: Test markdown formatting**

Add to `tests/unit/tools/test_file_bundler.py`:

```python
@pytest.mark.asyncio
async def test_format_as_markdown():
    """Test formatting sections as markdown."""
    sections = [
        FileSection(
            path="src/main.py",
            content="print('hello')",
            tokens=5,
            language="python",
        ),
    ]

    bundler = FileBundler()
    markdown = bundler.format_as_markdown(sections)

    assert "### File: src/main.py" in markdown
    assert "```python" in markdown
    assert "print('hello')" in markdown
```

Run: `pytest tests/unit/tools/test_file_bundler.py::test_format_as_markdown -v`

Expected: FAIL - `AttributeError: 'FileBundler' object has no attribute 'format_as_markdown'`

**Step 4: Implement format_as_markdown**

Add to `amelia/tools/file_bundler.py`:

```python
class FileBundler:
    # ... existing code ...

    def format_as_markdown(self, sections: List[FileSection]) -> str:
        """Format file sections as markdown.

        Args:
            sections: List of FileSection objects

        Returns:
            Markdown-formatted string with syntax highlighting
        """
        lines = []

        for section in sections:
            # File header
            lines.append(f"### File: {section.path}")
            lines.append(f"**Tokens: {section.tokens}**")
            lines.append("")

            # Code block
            lang = section.language or "text"
            lines.append(f"```{lang}")
            lines.append(section.content)
            lines.append("```")
            lines.append("")

        return "\n".join(lines)
```

Run: `pytest tests/unit/tools/test_file_bundler.py::test_format_as_markdown -v`

Expected: PASS

**Step 5: Commit**

```bash
git add amelia/tools/file_bundler.py tests/unit/tools/test_file_bundler.py
git commit -m "feat: implement file gathering and markdown formatting in FileBundler"
```

---

## Task 4: Create Oracle Consultation State Models

**Files:**
- Modify: `amelia/core/state.py`

**Step 1: Examine current ExecutionState structure**

```bash
grep -A 30 "class ExecutionState" /Users/ka/github/existential-birds/amelia/amelia/core/state.py | head -40
```

**Step 2: Create OracleConsultation model in state.py**

Add to `amelia/core/state.py` (after imports, before ExecutionState):

```python
from datetime import datetime
from typing import Literal, Dict, List
from pydantic import BaseModel, Field, ConfigDict


class OracleConsultation(BaseModel):
    """Record of an Oracle consultation during workflow execution."""

    model_config = ConfigDict(frozen=True)

    timestamp: datetime
    """When the consultation occurred."""

    problem: str
    """Problem statement submitted to Oracle."""

    advice: str | None = None
    """Oracle's response text."""

    model: str
    """Model used for consultation (e.g., 'gpt-5.1-pro')."""

    session_id: str
    """Oracle session ID for replay/reference."""

    tokens: Dict[str, int] = Field(default_factory=dict)
    """Token usage breakdown: {input, output, reasoning, total}."""

    cost_usd: float | None = None
    """Estimated cost in USD."""

    files_consulted: List[str] = Field(default_factory=list)
    """List of file paths included in bundle."""

    outcome: Literal["success", "error"] = "success"
    """Whether consultation succeeded or failed."""

    error_message: str | None = None
    """Error details if outcome=error."""
```

**Step 3: Add oracle_consultations field to ExecutionState**

Find the ExecutionState class definition and add this field:

```python
import operator
from typing import Annotated

class ExecutionState(BaseModel):
    # ... existing fields ...

    oracle_consultations: Annotated[
        List[OracleConsultation],
        operator.add
    ] = Field(default_factory=list)
    """History of Oracle consultations for this workflow."""
```

Note: Using `operator.add` allows LangGraph to automatically append to this list when updating state.

**Step 4: Test that models load without errors**

```bash
python -c "from amelia.core.state import OracleConsultation, ExecutionState; print('✓ Models load correctly')"
```

Expected: `✓ Models load correctly`

**Step 5: Commit**

```bash
git add amelia/core/state.py
git commit -m "feat: add OracleConsultation model to ExecutionState"
```

---

## Task 5: Add Oracle Configuration to Profile

**Files:**
- Modify: `amelia/core/types.py`

**Step 1: Examine current Profile structure**

```bash
grep -A 20 "class Profile" /Users/ka/github/existential-birds/amelia/amelia/core/types.py | head -30
```

**Step 2: Create OracleConfig model**

Add to `amelia/core/types.py` (before Profile class):

```python
from pydantic import BaseModel, ConfigDict, Field
from typing import Dict, Optional


class OracleConfig(BaseModel):
    """Configuration for Oracle integration."""

    model_config = ConfigDict(frozen=True)

    enabled: bool = True
    """Whether Oracle consultations are enabled."""

    default_model: str = "gpt-5.1-pro"
    """Default model for consultations."""

    max_input_tokens: Optional[int] = None
    """Maximum input token budget (None = unlimited)."""

    timeout_seconds: Optional[int] = None
    """Consultation timeout in seconds (None = no timeout)."""

    enable_search: bool = True
    """Enable web search in Oracle."""

    api_keys: Dict[str, str] = Field(default_factory=dict)
    """API keys by provider (openai, anthropic, gemini)."""
```

**Step 3: Add oracle_config field to Profile**

Find the Profile class and add:

```python
class Profile(BaseModel):
    # ... existing fields ...

    oracle_config: OracleConfig = Field(default_factory=OracleConfig)
    """Configuration for Oracle consultations."""
```

**Step 4: Test that models load**

```bash
python -c "from amelia.core.types import OracleConfig, Profile; print('✓ Models load correctly')"
```

Expected: `✓ Models load correctly`

**Step 5: Commit**

```bash
git add amelia/core/types.py
git commit -m "feat: add OracleConfig and oracle_config to Profile"
```

---

## Task 6: Add Oracle Event Types

**Files:**
- Modify: `amelia/server/models/events.py`

**Step 1: Examine current EventType enum**

```bash
grep -A 50 "class EventType" /Users/ka/github/existential-birds/amelia/amelia/server/models/events.py | head -60
```

**Step 2: Add Oracle event types to EventType enum**

Find the EventType StrEnum and add these four new types:

```python
class EventType(StrEnum):
    # ... existing types ...

    # Oracle consultation events
    ORACLE_CONSULTATION_STARTED = "oracle_consultation_started"
    ORACLE_CONSULTATION_THINKING = "oracle_consultation_thinking"
    ORACLE_CONSULTATION_COMPLETED = "oracle_consultation_completed"
    ORACLE_CONSULTATION_FAILED = "oracle_consultation_failed"
```

**Step 3: Add THINKING to trace types**

Find the `_TRACE_TYPES` definition and add:

```python
_TRACE_TYPES: frozenset[EventType] = frozenset({
    # ... existing trace types ...
    EventType.ORACLE_CONSULTATION_THINKING,
})
```

(THINKING events should not be persisted to database by default)

**Step 4: Verify EventType enum is still valid**

```bash
python -c "from amelia.server.models.events import EventType; print(f'✓ Added {len([e for e in EventType if \"ORACLE\" in str(e)])} Oracle event types')"
```

Expected: `✓ Added 4 Oracle event types`

**Step 5: Commit**

```bash
git add amelia/server/models/events.py
git commit -m "feat: add Oracle consultation event types"
```

---

## Task 7: Create Oracle Client Tool

**Files:**
- Create: `amelia/tools/oracle_client.py`
- Create: `tests/unit/tools/test_oracle_client.py`

**Step 1: Write test for oracle_consult tool signature**

Create `tests/unit/tools/test_oracle_client.py`:

```python
"""Tests for Oracle client tool."""

import pytest
from amelia.tools.oracle_client import oracle_consult


@pytest.mark.asyncio
async def test_oracle_consult_signature():
    """Test oracle_consult has correct signature."""
    import inspect

    sig = inspect.signature(oracle_consult)
    params = list(sig.parameters.keys())

    # Check required parameters
    assert "problem" in params
    # Check optional parameters
    assert "files" in params
    assert "model" in params
    assert "max_input_tokens" in params
```

Run: `pytest tests/unit/tools/test_oracle_client.py::test_oracle_consult_signature -v`

Expected: FAIL - `ModuleNotFoundError: No module named 'amelia.tools.oracle_client'`

**Step 2: Create basic oracle_client.py with tool function**

Create `amelia/tools/oracle_client.py`:

```python
"""Oracle consulting tool integration."""

import asyncio
import json
import os
from typing import Any, Dict, List, Optional
from pathlib import Path
from loguru import logger


async def oracle_consult(
    problem: str,
    files: Optional[List[str]] = None,
    model: str = "gpt-5.1-pro",
    max_input_tokens: Optional[int] = None,
) -> Dict[str, Any]:
    """Consult Oracle for expert advice.

    Args:
        problem: Problem description or question
        files: Optional file paths/globs for context
        model: Model to consult (default: gpt-5.1-pro)
        max_input_tokens: Optional token budget limit

    Returns:
        Dictionary with keys:
            - advice: Oracle's response text
            - session_id: Oracle session ID
            - tokens: Token usage dict (input, output, total)
            - cost_usd: Estimated cost
            - files_consulted: List of files included
            - model_used: Actual model ID used
    """
    files = files or []

    # For now, return a stub response
    return {
        "advice": "Consultation feature coming soon",
        "session_id": "ora_stub",
        "tokens": {"input": 0, "output": 0, "total": 0},
        "cost_usd": 0.0,
        "files_consulted": [],
        "model_used": model,
    }
```

Run: `pytest tests/unit/tools/test_oracle_client.py::test_oracle_consult_signature -v`

Expected: PASS

**Step 3: Add test for return value structure**

Add to `tests/unit/tools/test_oracle_client.py`:

```python
@pytest.mark.asyncio
async def test_oracle_consult_returns_dict():
    """Test oracle_consult returns required fields."""
    result = await oracle_consult(
        problem="Test problem",
        model="gpt-5.1-pro",
    )

    assert isinstance(result, dict)
    assert "advice" in result
    assert "session_id" in result
    assert "tokens" in result
    assert "cost_usd" in result
    assert "files_consulted" in result
    assert "model_used" in result

    # Check token dict structure
    assert isinstance(result["tokens"], dict)
    assert "input" in result["tokens"]
    assert "output" in result["tokens"]
    assert "total" in result["tokens"]
```

Run: `pytest tests/unit/tools/test_oracle_client.py::test_oracle_consult_returns_dict -v`

Expected: PASS

**Step 4: Add test for error handling**

Add to `tests/unit/tools/test_oracle_client.py`:

```python
@pytest.mark.asyncio
async def test_oracle_consult_requires_problem():
    """Test oracle_consult requires a problem."""
    with pytest.raises(TypeError):
        await oracle_consult()  # Missing required 'problem' argument
```

Run: `pytest tests/unit/tools/test_oracle_client.py::test_oracle_consult_requires_problem -v`

Expected: PASS

**Step 5: Commit**

```bash
git add amelia/tools/oracle_client.py tests/unit/tools/test_oracle_client.py
git commit -m "feat: create oracle_consult tool with basic implementation"
```

---

## Task 8: Create FastAPI Request/Response Models

**Files:**
- Create: `amelia/server/models/oracle_models.py`

**Step 1: Write test for request model**

Create a test file `tests/unit/server/test_oracle_models.py`:

```python
"""Tests for Oracle API models."""

import pytest
from pathlib import Path
from pydantic import ValidationError
from amelia.server.models.oracle_models import (
    OracleConsultRequest,
    OracleConsultResponse,
)


def test_oracle_consult_request_valid():
    """Test OracleConsultRequest with valid data."""
    request = OracleConsultRequest(
        problem="How should I refactor this?",
        files=["src/**/*.py"],
        model="gpt-5.1-pro",
        working_dir="/tmp/project",
    )
    assert request.problem == "How should I refactor this?"
    assert request.files == ["src/**/*.py"]
    assert request.model == "gpt-5.1-pro"


def test_oracle_consult_request_missing_problem():
    """Test OracleConsultRequest requires problem."""
    with pytest.raises(ValidationError):
        OracleConsultRequest(
            files=["src/**/*.py"],
            model="gpt-5.1-pro",
            working_dir="/tmp/project",
        )


def test_oracle_consult_response_creation():
    """Test OracleConsultResponse can be created."""
    response = OracleConsultResponse(
        advice="The fix is...",
        session_id="ora_123",
        tokens={"input": 1000, "output": 100, "total": 1100},
        cost_usd=0.05,
        files_consulted=["src/main.py"],
        model_used="gpt-5.1-pro",
    )
    assert response.advice == "The fix is..."
    assert response.cost_usd == 0.05
```

Run: `pytest tests/unit/server/test_oracle_models.py -v`

Expected: FAIL - `ModuleNotFoundError: No module named 'amelia.server.models.oracle_models'`

**Step 2: Create oracle_models.py with Pydantic models**

Create `amelia/server/models/oracle_models.py`:

```python
"""Oracle API request/response models."""

from typing import Annotated, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator
from pathlib import Path


class OracleConsultRequest(BaseModel):
    """Request to consult Oracle."""

    problem: Annotated[
        str,
        Field(
            min_length=1,
            max_length=10000,
            description="Problem description or question",
        ),
    ]

    files: List[str] = Field(
        default_factory=list,
        description="File patterns (e.g., ['src/**/*.py'])",
    )

    model: str = Field(
        default="gpt-5.1-pro",
        description="Model to consult",
    )

    working_dir: str = Field(
        description="Absolute path to project directory",
    )

    max_input_tokens: Optional[int] = Field(
        default=None,
        description="Maximum input token budget",
    )

    @field_validator("working_dir", mode="after")
    @classmethod
    def validate_working_dir(cls, v: str) -> str:
        """Validate working directory exists and is absolute."""
        path = Path(v)
        if not path.is_absolute():
            raise ValueError("working_dir must be absolute path")
        if not path.exists():
            raise ValueError(f"working_dir does not exist: {v}")
        if not path.is_dir():
            raise ValueError(f"working_dir is not a directory: {v}")
        return v


class OracleConsultResponse(BaseModel):
    """Response from Oracle consultation."""

    advice: str = Field(description="Oracle's consultation advice")

    session_id: str = Field(description="Oracle session ID")

    tokens: Dict[str, int] = Field(description="Token usage breakdown")

    cost_usd: float = Field(description="Estimated cost in USD")

    files_consulted: List[str] = Field(description="Files included in bundle")

    model_used: str = Field(description="Actual model used")
```

Run: `pytest tests/unit/server/test_oracle_models.py -v`

Expected: PASS

**Step 3: Commit**

```bash
git add amelia/server/models/oracle_models.py tests/unit/server/test_oracle_models.py
git commit -m "feat: create Oracle API request/response models"
```

---

## Task 9: Create FastAPI Endpoint Route

**Files:**
- Create: `amelia/server/routes/oracle.py`

**Step 1: Write test for Oracle endpoint**

Add to `tests/integration/server/test_oracle_endpoint.py` (create if needed):

```python
"""Integration tests for Oracle API endpoint."""

import pytest
from httpx import AsyncClient
from pathlib import Path
import tempfile


@pytest.mark.asyncio
async def test_oracle_consult_endpoint_exists(client: AsyncClient):
    """Test POST /api/oracle/consult endpoint exists."""
    # Use temporary directory as working_dir
    with tempfile.TemporaryDirectory() as tmpdir:
        response = await client.post(
            "/api/oracle/consult",
            json={
                "problem": "How do I fix this?",
                "files": [],
                "model": "gpt-5.1-pro",
                "working_dir": tmpdir,
            },
        )

    # Endpoint should exist (not 404)
    assert response.status_code in [200, 422, 500]  # Any response except 404


@pytest.mark.asyncio
async def test_oracle_consult_validates_working_dir(client: AsyncClient):
    """Test endpoint validates working_dir."""
    response = await client.post(
        "/api/oracle/consult",
        json={
            "problem": "How do I fix this?",
            "files": [],
            "model": "gpt-5.1-pro",
            "working_dir": "/nonexistent/path",
        },
    )

    # Should reject invalid path
    assert response.status_code == 422
```

Run: `pytest tests/integration/server/test_oracle_endpoint.py -v`

Expected: FAIL - route doesn't exist

**Step 2: Create oracle.py route**

Create `amelia/server/routes/oracle.py`:

```python
"""Oracle consultation routes."""

from fastapi import APIRouter, Depends, HTTPException, status
from loguru import logger

from amelia.server.dependencies import get_orchestrator
from amelia.server.models.oracle_models import (
    OracleConsultRequest,
    OracleConsultResponse,
)
from amelia.server.orchestrator.service import OrchestratorService


router = APIRouter(prefix="/oracle", tags=["oracle"])


@router.post("/consult", response_model=OracleConsultResponse, status_code=status.HTTP_200_OK)
async def consult_oracle(
    request: OracleConsultRequest,
    orchestrator: OrchestratorService = Depends(get_orchestrator),
) -> OracleConsultResponse:
    """
    Consult Oracle for expert advice on complex problems.

    This endpoint invokes Oracle with the provided problem and context files,
    then returns the consultation result with usage metrics.
    """
    try:
        # Validate Oracle is enabled
        # TODO: Implement consultation logic in orchestrator

        # Placeholder response
        return OracleConsultResponse(
            advice="Consultation feature under development",
            session_id="ora_placeholder",
            tokens={"input": 0, "output": 0, "total": 0},
            cost_usd=0.0,
            files_consulted=[],
            model_used=request.model,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.exception("Oracle consultation failed")
        raise HTTPException(status_code=500, detail=f"Consultation failed: {e}") from e
```

**Step 3: Register route in main.py**

Edit `amelia/server/main.py`:

Find where other routers are imported and add:

```python
from amelia.server.routes import oracle_router
```

Find where routers are registered (`include_router`) and add:

```python
app.include_router(oracle_router, prefix="/api")
```

**Step 4: Run endpoint test**

```bash
# Start the test server (if not already running)
pytest tests/integration/server/test_oracle_endpoint.py::test_oracle_consult_endpoint_exists -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add amelia/server/routes/oracle.py amelia/server/main.py
git commit -m "feat: add Oracle consultation FastAPI endpoint"
```

---

## Task 10: Register oracle_consult Tool in Claude Driver

**Files:**
- Modify: `amelia/drivers/cli/claude.py`

**Step 1: Examine current tool registration**

```bash
grep -B 5 -A 15 "_build_tools" /Users/ka/github/existential-birds/amelia/amelia/drivers/cli/claude.py | head -30
```

**Step 2: Add oracle_consult to tool registration**

In `amelia/drivers/cli/claude.py`, find the `_build_tools()` method and add:

```python
from amelia.tools.oracle_client import oracle_consult

# In _build_tools() method, add this Tool:
Tool(
    name="oracle_consult",
    description=(
        "Consult Oracle for expert guidance when stuck on a problem. "
        "Provide a clear problem description and relevant file patterns. "
        "Returns structured advice, session ID, tokens, and estimated cost."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "problem": {
                "type": "string",
                "description": "Specific problem or question",
            },
            "files": {
                "type": "array",
                "items": {"type": "string"},
                "description": "File patterns (e.g., ['src/**/*.py'])",
            },
            "model": {
                "type": "string",
                "description": "Model to use",
                "default": "gpt-5.1-pro",
            },
            "max_input_tokens": {
                "type": "integer",
                "description": "Token budget limit",
            },
        },
        "required": ["problem"],
    },
    fn=oracle_consult,
)
```

**Step 3: Verify tool is registered**

```bash
python -c "
from amelia.drivers.cli.claude import ClaudeCliDriver
driver = ClaudeCliDriver()
# This will be expanded once actual implementation complete
print('✓ Tool registration updated')
"
```

Expected: `✓ Tool registration updated`

**Step 4: Commit**

```bash
git add amelia/drivers/cli/claude.py
git commit -m "feat: register oracle_consult tool in Claude CLI driver"
```

---

## Task 11: Register oracle_consult Tool in DeepAgents Driver

**Files:**
- Modify: `amelia/drivers/api/deepagents.py`

**Step 1: Examine DeepAgents driver tool registration**

```bash
grep -B 5 -A 15 "_register_tools\|_build_tools" /Users/ka/github/existential-birds/amelia/amelia/drivers/api/deepagents.py | head -40
```

**Step 2: Add oracle_consult registration**

In `amelia/drivers/api/deepagents.py`, find tool registration and add oracle_consult similarly:

```python
from amelia.tools.oracle_client import oracle_consult

# Register tool with same schema as Claude driver
# (Exact location depends on driver's tool registration pattern)
```

**Step 3: Verify both drivers have the tool**

```bash
python -c "
from amelia.drivers.cli.claude import ClaudeCliDriver
from amelia.drivers.api.deepagents import DeepAgentsDriver
print('✓ Both drivers updated')
"
```

Expected: `✓ Both drivers updated`

**Step 4: Commit**

```bash
git add amelia/drivers/api/deepagents.py
git commit -m "feat: register oracle_consult tool in DeepAgents driver"
```

---

## Task 12: Run All Tests and Verify Integration

**Files:**
- None (verification only)

**Step 1: Run all new unit tests**

```bash
pytest tests/unit/tools/test_file_bundler.py tests/unit/tools/test_oracle_client.py tests/unit/server/test_oracle_models.py -v
```

Expected: All tests pass (5+ tests)

**Step 2: Run integration tests**

```bash
pytest tests/integration/server/test_oracle_endpoint.py -v
```

Expected: Endpoint tests pass

**Step 3: Verify imports don't break existing code**

```bash
python -c "
from amelia.core.state import ExecutionState, OracleConsultation
from amelia.core.types import Profile, OracleConfig
from amelia.server.models.events import EventType
from amelia.server.models.oracle_models import OracleConsultRequest, OracleConsultResponse
from amelia.tools.oracle_client import oracle_consult
from amelia.server.routes.oracle import router
print('✓ All imports successful')
"
```

Expected: `✓ All imports successful`

**Step 4: Run existing tests to ensure no regression**

```bash
pytest tests/unit/core/ tests/unit/server/models/ -v --tb=short
```

Expected: No failures (existing tests still pass)

**Step 5: Final commit**

```bash
git add -A
git commit -m "test: verify all Oracle integration tests pass"
```

---

## Summary

This plan creates the foundation for Oracle integration in Amelia across 12 focused tasks:

1. Add dependencies
2. Create file bundler utility
3. Implement file gathering
4. Add state models
5. Add configuration
6. Add event types
7. Create tool
8. Create API models
9. Create endpoint
10. Register tool in Claude driver
11. Register tool in DeepAgents driver
12. Verify integration

Each task is 2-5 minutes of focused work following TDD: write test, run fail, implement, run pass, commit.

Next phases (not in this plan) would add:
- Full Oracle CLI integration with subprocess execution
- Event emission infrastructure
- Orchestrator method for consultation execution
- Agent prompt enhancements
- Dashboard visualization
- Security hardening
