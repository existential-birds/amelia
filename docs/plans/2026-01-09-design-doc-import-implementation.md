# Design Document Import Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enable users to import design documents into the Quick Shot modal with drag-drop and manual path input, with auto-populated fields and worktree pre-fill from server config.

**Architecture:** Backend exposes `/api/config` and `/api/files/read` endpoints with path security scoping via `working_dir`. Frontend adds drag-drop zone to QuickShotModal that extracts title from H1 and generates timestamp IDs.

**Tech Stack:** Python/FastAPI/Pydantic (backend), React/TypeScript/react-hook-form/shadcn-ui (frontend)

---

## Task 1: Add working_dir to ServerConfig

**Files:**
- Modify: `amelia/server/config.py:1-98`
- Test: `tests/unit/server/test_config.py`

**Step 1: Write the failing test**

Create the test file if it doesn't exist:

```python
# tests/unit/server/test_config.py
"""Tests for server configuration."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from amelia.server.config import ServerConfig


class TestWorkingDir:
    """Tests for working_dir configuration."""

    def test_working_dir_defaults_to_none(self) -> None:
        """working_dir should default to None when not set."""
        with patch.dict(os.environ, {}, clear=True):
            # Clear any AMELIA_ prefixed env vars
            env = {k: v for k, v in os.environ.items() if not k.startswith("AMELIA_")}
            with patch.dict(os.environ, env, clear=True):
                config = ServerConfig()
                assert config.working_dir is None

    def test_working_dir_from_env(self, tmp_path: Path) -> None:
        """working_dir should be set from AMELIA_WORKING_DIR env var."""
        with patch.dict(os.environ, {"AMELIA_WORKING_DIR": str(tmp_path)}, clear=False):
            config = ServerConfig()
            assert config.working_dir == tmp_path

    def test_working_dir_must_be_absolute(self) -> None:
        """working_dir must be an absolute path."""
        with patch.dict(os.environ, {"AMELIA_WORKING_DIR": "relative/path"}, clear=False):
            with pytest.raises(ValueError, match="must be absolute"):
                ServerConfig()

    def test_working_dir_must_exist(self, tmp_path: Path) -> None:
        """working_dir must point to an existing directory."""
        nonexistent = tmp_path / "does-not-exist"
        with patch.dict(os.environ, {"AMELIA_WORKING_DIR": str(nonexistent)}, clear=False):
            with pytest.raises(ValueError, match="does not exist"):
                ServerConfig()

    def test_working_dir_must_be_directory(self, tmp_path: Path) -> None:
        """working_dir must be a directory, not a file."""
        file_path = tmp_path / "file.txt"
        file_path.write_text("content")
        with patch.dict(os.environ, {"AMELIA_WORKING_DIR": str(file_path)}, clear=False):
            with pytest.raises(ValueError, match="not a directory"):
                ServerConfig()
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/test_config.py -v`
Expected: FAIL with "AttributeError: 'ServerConfig' object has no attribute 'working_dir'"

**Step 3: Write minimal implementation**

Add to `amelia/server/config.py` after the existing fields:

```python
from pydantic import field_validator

# Add this field after stream_tool_results:
working_dir: Path | None = Field(
    default=None,
    description="Working directory to scope file access and pre-fill worktree path. "
    "Set via AMELIA_WORKING_DIR environment variable.",
)

@field_validator("working_dir", mode="after")
@classmethod
def validate_working_dir(cls, v: Path | None) -> Path | None:
    """Validate working_dir is an existing absolute directory."""
    if v is None:
        return None
    if not v.is_absolute():
        raise ValueError(f"working_dir must be absolute, got: {v}")
    if not v.exists():
        raise ValueError(f"working_dir does not exist: {v}")
    if not v.is_dir():
        raise ValueError(f"working_dir is not a directory: {v}")
    return v
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/test_config.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/server/config.py tests/unit/server/test_config.py
git commit -m "feat(server): add working_dir config option"
```

---

## Task 2: Add --working-dir CLI option

**Files:**
- Modify: `amelia/server/cli.py:1-113`
- Test: `tests/unit/server/test_cli.py`

**Step 1: Write the failing test**

```python
# tests/unit/server/test_cli.py
"""Tests for server CLI commands."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from amelia.cli import app


runner = CliRunner()


class TestServerWorkingDir:
    """Tests for --working-dir CLI option."""

    def test_working_dir_option_exists(self) -> None:
        """--working-dir option should be recognized."""
        result = runner.invoke(app, ["server", "--help"])
        assert result.exit_code == 0
        assert "--working-dir" in result.stdout

    def test_working_dir_passed_to_config(self, tmp_path: Path) -> None:
        """--working-dir should override AMELIA_WORKING_DIR env var."""
        with patch("amelia.server.cli.uvicorn") as mock_uvicorn:
            mock_uvicorn.run = MagicMock()
            with patch.dict("os.environ", {}, clear=False):
                result = runner.invoke(
                    app, ["server", "--working-dir", str(tmp_path)]
                )
                # Server starts without error (uvicorn.run is called)
                # The working_dir is set in environment before run
                assert "AMELIA_WORKING_DIR" in result.output or mock_uvicorn.run.called

    def test_working_dir_validates_path(self, tmp_path: Path) -> None:
        """--working-dir should validate the path exists."""
        nonexistent = tmp_path / "nonexistent"
        result = runner.invoke(app, ["server", "--working-dir", str(nonexistent)])
        assert result.exit_code != 0
        assert "does not exist" in result.stdout or "Error" in result.stdout
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/test_cli.py::TestServerWorkingDir -v`
Expected: FAIL with "--working-dir" not in result.stdout

**Step 3: Write minimal implementation**

Modify `amelia/server/cli.py`:

```python
# Add to imports
import os

# Modify the server function signature to add working_dir parameter:
@server_app.callback(invoke_without_command=True)
def server(
    ctx: typer.Context,
    port: Annotated[int | None, typer.Option("--port", "-p", help="Port to run the server on.")] = None,
    bind_all: Annotated[
        bool,
        typer.Option(
            "--bind-all",
            help="Bind to all network interfaces (0.0.0.0) instead of localhost only.",
        ),
    ] = False,
    reload: Annotated[
        bool,
        typer.Option(
            "--reload",
            help="Enable auto-reload for development.",
        ),
    ] = False,
    working_dir: Annotated[
        Path | None,
        typer.Option(
            "--working-dir",
            "-w",
            help="Working directory to scope file access and pre-fill worktree path.",
            exists=True,
            file_okay=False,
            dir_okay=True,
            resolve_path=True,
        ),
    ] = None,
) -> None:
    """Start the Amelia API server."""
    if ctx.invoked_subcommand is not None:
        return

    # Set working_dir in environment before config is loaded
    if working_dir is not None:
        os.environ["AMELIA_WORKING_DIR"] = str(working_dir)

    # ... rest of function unchanged
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/test_cli.py::TestServerWorkingDir -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/server/cli.py tests/unit/server/test_cli.py
git commit -m "feat(cli): add --working-dir option to server command"
```

---

## Task 3: Add config dependency injection

**Files:**
- Modify: `amelia/server/dependencies.py:1-98`
- Modify: `amelia/server/main.py:1-260`
- Test: `tests/unit/server/test_dependencies.py`

**Step 1: Write the failing test**

```python
# tests/unit/server/test_dependencies.py
"""Tests for server dependency injection."""

import pytest

from amelia.server.config import ServerConfig
from amelia.server.dependencies import (
    clear_config,
    get_config,
    set_config,
)


class TestConfigDependency:
    """Tests for config dependency injection."""

    def setup_method(self) -> None:
        """Clear config before each test."""
        clear_config()

    def teardown_method(self) -> None:
        """Clear config after each test."""
        clear_config()

    def test_get_config_raises_when_not_set(self) -> None:
        """get_config should raise when config not initialized."""
        with pytest.raises(RuntimeError, match="Config not initialized"):
            get_config()

    def test_set_and_get_config(self) -> None:
        """set_config should make config available via get_config."""
        config = ServerConfig()
        set_config(config)
        assert get_config() is config

    def test_clear_config(self) -> None:
        """clear_config should reset config state."""
        config = ServerConfig()
        set_config(config)
        clear_config()
        with pytest.raises(RuntimeError):
            get_config()
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/test_dependencies.py::TestConfigDependency -v`
Expected: FAIL with "cannot import name 'get_config' from 'amelia.server.dependencies'"

**Step 3: Write minimal implementation**

Add to `amelia/server/dependencies.py`:

```python
from amelia.server.config import ServerConfig

# Module-level config storage
_config: ServerConfig | None = None


def set_config(config: ServerConfig) -> None:
    """Set the global server config instance."""
    global _config
    _config = config


def get_config() -> ServerConfig:
    """Get the global server config instance."""
    if _config is None:
        raise RuntimeError("Config not initialized. Is the server running?")
    return _config


def clear_config() -> None:
    """Clear the global config instance."""
    global _config
    _config = None
```

Update `amelia/server/main.py` lifespan to set config:

```python
# Add import
from amelia.server.dependencies import set_config, clear_config

# In lifespan function, after creating _config:
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage application lifespan."""
    _config = ServerConfig()
    set_config(_config)  # Add this line
    # ... rest of startup code ...

    yield

    # ... shutdown code ...
    clear_config()  # Add this line before final cleanup
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/test_dependencies.py::TestConfigDependency -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/server/dependencies.py amelia/server/main.py tests/unit/server/test_dependencies.py
git commit -m "feat(server): add config dependency injection"
```

---

## Task 4: Create GET /api/config endpoint

**Files:**
- Create: `amelia/server/routes/config.py`
- Modify: `amelia/server/main.py`
- Test: `tests/unit/server/routes/test_config.py`

**Step 1: Write the failing test**

```python
# tests/unit/server/routes/test_config.py
"""Tests for config API routes."""

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from amelia.server.config import ServerConfig
from amelia.server.dependencies import clear_config, set_config


@pytest.fixture
def client() -> TestClient:
    """Create test client with config dependency."""
    from amelia.server.main import application

    return TestClient(application, raise_server_exceptions=False)


class TestGetConfig:
    """Tests for GET /api/config endpoint."""

    def setup_method(self) -> None:
        """Set up test config."""
        self.config = ServerConfig()
        set_config(self.config)

    def teardown_method(self) -> None:
        """Clean up config."""
        clear_config()

    def test_get_config_returns_working_dir_null(self, client: TestClient) -> None:
        """GET /api/config returns working_dir as null when not set."""
        response = client.get("/api/config")
        assert response.status_code == 200
        data = response.json()
        assert data["working_dir"] is None
        assert "max_concurrent" in data

    def test_get_config_returns_working_dir(
        self, client: TestClient, tmp_path: Path
    ) -> None:
        """GET /api/config returns working_dir when set."""
        with patch.dict("os.environ", {"AMELIA_WORKING_DIR": str(tmp_path)}):
            config = ServerConfig()
            set_config(config)
            response = client.get("/api/config")
            assert response.status_code == 200
            data = response.json()
            assert data["working_dir"] == str(tmp_path)

    def test_get_config_returns_max_concurrent(self, client: TestClient) -> None:
        """GET /api/config returns max_concurrent setting."""
        response = client.get("/api/config")
        assert response.status_code == 200
        data = response.json()
        assert data["max_concurrent"] == 5  # default value
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/routes/test_config.py -v`
Expected: FAIL with 404 Not Found

**Step 3: Write minimal implementation**

Create `amelia/server/routes/config.py`:

```python
"""Config API routes."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from amelia.server.config import ServerConfig
from amelia.server.dependencies import get_config

router = APIRouter(prefix="/api/config", tags=["config"])


class ConfigResponse(BaseModel):
    """Response model for GET /api/config."""

    working_dir: str | None
    max_concurrent: int


@router.get("", response_model=ConfigResponse)
async def get_server_config(
    config: ServerConfig = Depends(get_config),
) -> ConfigResponse:
    """Get server configuration for dashboard."""
    return ConfigResponse(
        working_dir=str(config.working_dir) if config.working_dir else None,
        max_concurrent=config.max_concurrent,
    )
```

Register in `amelia/server/main.py`:

```python
# Add import
from amelia.server.routes.config import router as config_router

# Add after other router includes:
application.include_router(config_router)
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/routes/test_config.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/server/routes/config.py amelia/server/main.py tests/unit/server/routes/test_config.py
git commit -m "feat(api): add GET /api/config endpoint"
```

---

## Task 5: Create POST /api/files/read endpoint

**Files:**
- Create: `amelia/server/routes/files.py`
- Modify: `amelia/server/main.py`
- Test: `tests/unit/server/routes/test_files.py`

**Step 1: Write the failing test**

```python
# tests/unit/server/routes/test_files.py
"""Tests for files API routes."""

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from amelia.server.config import ServerConfig
from amelia.server.dependencies import clear_config, set_config


@pytest.fixture
def client() -> TestClient:
    """Create test client."""
    from amelia.server.main import application

    return TestClient(application, raise_server_exceptions=False)


class TestReadFile:
    """Tests for POST /api/files/read endpoint."""

    def setup_method(self) -> None:
        """Set up test config."""
        self.config = ServerConfig()
        set_config(self.config)

    def teardown_method(self) -> None:
        """Clean up config."""
        clear_config()

    def test_read_file_success(self, client: TestClient, tmp_path: Path) -> None:
        """POST /api/files/read returns file content."""
        file_path = tmp_path / "design.md"
        file_path.write_text("# My Design\n\nContent here.")

        response = client.post(
            "/api/files/read", json={"path": str(file_path)}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["content"] == "# My Design\n\nContent here."
        assert data["filename"] == "design.md"

    def test_read_file_not_found(self, client: TestClient, tmp_path: Path) -> None:
        """POST /api/files/read returns 404 for missing file."""
        response = client.post(
            "/api/files/read", json={"path": str(tmp_path / "missing.md")}
        )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_read_file_requires_absolute_path(self, client: TestClient) -> None:
        """POST /api/files/read rejects relative paths."""
        response = client.post("/api/files/read", json={"path": "relative/path.md"})
        assert response.status_code == 400
        assert "absolute" in response.json()["detail"].lower()

    def test_read_file_scoped_to_working_dir(
        self, client: TestClient, tmp_path: Path
    ) -> None:
        """POST /api/files/read rejects paths outside working_dir."""
        working_dir = tmp_path / "allowed"
        working_dir.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()
        outside_file = outside / "secret.md"
        outside_file.write_text("secret")

        with patch.dict("os.environ", {"AMELIA_WORKING_DIR": str(working_dir)}):
            config = ServerConfig()
            set_config(config)
            response = client.post(
                "/api/files/read", json={"path": str(outside_file)}
            )
            assert response.status_code == 400
            assert "not accessible" in response.json()["detail"].lower()

    def test_read_file_allows_within_working_dir(
        self, client: TestClient, tmp_path: Path
    ) -> None:
        """POST /api/files/read allows paths within working_dir."""
        working_dir = tmp_path / "allowed"
        working_dir.mkdir()
        allowed_file = working_dir / "design.md"
        allowed_file.write_text("# Allowed")

        with patch.dict("os.environ", {"AMELIA_WORKING_DIR": str(working_dir)}):
            config = ServerConfig()
            set_config(config)
            response = client.post(
                "/api/files/read", json={"path": str(allowed_file)}
            )
            assert response.status_code == 200
            assert response.json()["content"] == "# Allowed"

    def test_read_file_blocks_path_traversal(
        self, client: TestClient, tmp_path: Path
    ) -> None:
        """POST /api/files/read blocks path traversal attacks."""
        working_dir = tmp_path / "allowed"
        working_dir.mkdir()
        outside = tmp_path / "secret.md"
        outside.write_text("secret")

        with patch.dict("os.environ", {"AMELIA_WORKING_DIR": str(working_dir)}):
            config = ServerConfig()
            set_config(config)
            # Try path traversal
            traversal_path = str(working_dir / ".." / "secret.md")
            response = client.post(
                "/api/files/read", json={"path": traversal_path}
            )
            assert response.status_code == 400
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/routes/test_files.py -v`
Expected: FAIL with 404 Not Found

**Step 3: Write minimal implementation**

Create `amelia/server/routes/files.py`:

```python
"""Files API routes."""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator

from amelia.server.config import ServerConfig
from amelia.server.dependencies import get_config

router = APIRouter(prefix="/api/files", tags=["files"])


class ReadFileRequest(BaseModel):
    """Request model for POST /api/files/read."""

    path: str

    @field_validator("path")
    @classmethod
    def validate_path(cls, v: str) -> str:
        """Validate path is absolute."""
        if not Path(v).is_absolute():
            raise ValueError("path must be absolute")
        return v


class ReadFileResponse(BaseModel):
    """Response model for POST /api/files/read."""

    content: str
    filename: str


def _is_path_within(path: Path, parent: Path) -> bool:
    """Check if path is within parent directory (resolving symlinks)."""
    try:
        resolved_path = path.resolve()
        resolved_parent = parent.resolve()
        return str(resolved_path).startswith(str(resolved_parent) + "/") or resolved_path == resolved_parent
    except (OSError, ValueError):
        return False


@router.post("/read", response_model=ReadFileResponse)
async def read_file(
    request: ReadFileRequest,
    config: ServerConfig = Depends(get_config),
) -> ReadFileResponse:
    """Read file content for design document import.

    Security:
    - Path must be absolute
    - If working_dir is set, path must be within that directory
    - Path traversal is blocked by resolving the path
    """
    file_path = Path(request.path)

    # Security: Check path is within working_dir if set
    if config.working_dir is not None:
        if not _is_path_within(file_path, config.working_dir):
            raise HTTPException(
                status_code=400,
                detail=f"Path not accessible: must be within {config.working_dir}",
            )

    # Resolve to prevent path traversal
    resolved_path = file_path.resolve()

    # Re-check after resolution (handles ../ attacks)
    if config.working_dir is not None:
        if not _is_path_within(resolved_path, config.working_dir):
            raise HTTPException(
                status_code=400,
                detail=f"Path not accessible: must be within {config.working_dir}",
            )

    # Check file exists
    if not resolved_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {request.path}")

    if not resolved_path.is_file():
        raise HTTPException(status_code=400, detail=f"Not a file: {request.path}")

    try:
        content = resolved_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        raise HTTPException(status_code=400, detail=f"Failed to read file: {e}")

    return ReadFileResponse(
        content=content,
        filename=resolved_path.name,
    )
```

Register in `amelia/server/main.py`:

```python
# Add import
from amelia.server.routes.files import router as files_router

# Add after config_router:
application.include_router(files_router)
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/routes/test_files.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/server/routes/files.py amelia/server/main.py tests/unit/server/routes/test_files.py
git commit -m "feat(api): add POST /api/files/read endpoint with security scoping"
```

---

## Task 6: Add frontend API client methods

**Files:**
- Modify: `dashboard/src/api/client.ts:1-565`
- Modify: `dashboard/src/types/index.ts`
- Test: `dashboard/src/api/client.test.ts`

**Step 1: Write the failing test**

```typescript
// dashboard/src/api/client.test.ts
// Add these tests to the existing test file

describe('api.getConfig', () => {
  it('returns config with working_dir and max_concurrent', async () => {
    fetchMock.mockResponseOnce(
      JSON.stringify({ working_dir: '/path/to/repo', max_concurrent: 5 })
    );

    const result = await api.getConfig();

    expect(result.working_dir).toBe('/path/to/repo');
    expect(result.max_concurrent).toBe(5);
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/config'),
      expect.any(Object)
    );
  });

  it('returns null working_dir when not set', async () => {
    fetchMock.mockResponseOnce(
      JSON.stringify({ working_dir: null, max_concurrent: 5 })
    );

    const result = await api.getConfig();

    expect(result.working_dir).toBeNull();
  });
});

describe('api.readFile', () => {
  it('returns file content and filename', async () => {
    fetchMock.mockResponseOnce(
      JSON.stringify({ content: '# Design Doc', filename: 'design.md' })
    );

    const result = await api.readFile('/path/to/design.md');

    expect(result.content).toBe('# Design Doc');
    expect(result.filename).toBe('design.md');
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/files/read'),
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ path: '/path/to/design.md' }),
      })
    );
  });

  it('throws ApiError on file not found', async () => {
    fetchMock.mockResponseOnce(
      JSON.stringify({ error: 'File not found', code: 'NOT_FOUND' }),
      { status: 404 }
    );

    await expect(api.readFile('/missing.md')).rejects.toThrow(ApiError);
  });
});
```

**Step 2: Run test to verify it fails**

Run: `cd dashboard && pnpm test -- --run client.test.ts`
Expected: FAIL with "api.getConfig is not a function"

**Step 3: Write minimal implementation**

Add types to `dashboard/src/types/index.ts`:

```typescript
// Add these types
export interface ServerConfig {
  working_dir: string | null;
  max_concurrent: number;
}

export interface ReadFileResponse {
  content: string;
  filename: string;
}
```

Add methods to `dashboard/src/api/client.ts`:

```typescript
// Add these imports if not present
import type { ServerConfig, ReadFileResponse } from '../types';

// Add these methods to the api object:

async getConfig(): Promise<ServerConfig> {
  const response = await fetchWithTimeout(`${API_BASE_URL}/config`);
  return handleResponse<ServerConfig>(response);
},

async readFile(path: string): Promise<ReadFileResponse> {
  const response = await fetchWithTimeout(`${API_BASE_URL}/files/read`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path }),
  });
  return handleResponse<ReadFileResponse>(response);
},
```

**Step 4: Run test to verify it passes**

Run: `cd dashboard && pnpm test -- --run client.test.ts`
Expected: PASS

**Step 5: Commit**

```bash
git add dashboard/src/api/client.ts dashboard/src/types/index.ts dashboard/src/api/client.test.ts
git commit -m "feat(dashboard): add getConfig and readFile API methods"
```

---

## Task 7: Create design-doc utility functions

**Files:**
- Create: `dashboard/src/lib/design-doc.ts`
- Test: `dashboard/src/lib/design-doc.test.ts`

**Step 1: Write the failing test**

```typescript
// dashboard/src/lib/design-doc.test.ts
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { extractTitle, generateDesignId } from './design-doc';

describe('extractTitle', () => {
  it('extracts title from H1 heading', () => {
    const markdown = '# Queue Workflows\n\n## Problem\n...';
    expect(extractTitle(markdown)).toBe('Queue Workflows');
  });

  it('strips Design suffix from title', () => {
    const markdown = '# Queue Workflows Design\n\nContent...';
    expect(extractTitle(markdown)).toBe('Queue Workflows');
  });

  it('handles Design in middle of title', () => {
    const markdown = '# Foo Design Bar\n\nContent...';
    expect(extractTitle(markdown)).toBe('Foo Design Bar');
  });

  it('returns Untitled when no H1 found', () => {
    const markdown = '## No H1 here\n\nContent...';
    expect(extractTitle(markdown)).toBe('Untitled');
  });

  it('handles empty markdown', () => {
    expect(extractTitle('')).toBe('Untitled');
  });

  it('trims whitespace from title', () => {
    const markdown = '#   Spaced Title   \n\nContent...';
    expect(extractTitle(markdown)).toBe('Spaced Title');
  });
});

describe('generateDesignId', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('generates timestamp-based ID', () => {
    vi.setSystemTime(new Date('2026-01-09T14:30:52.000Z'));
    expect(generateDesignId()).toBe('design-20260109143052');
  });

  it('generates unique IDs for different times', () => {
    vi.setSystemTime(new Date('2026-01-09T14:30:52.000Z'));
    const id1 = generateDesignId();

    vi.setSystemTime(new Date('2026-01-09T14:30:53.000Z'));
    const id2 = generateDesignId();

    expect(id1).not.toBe(id2);
  });
});

describe('extractTitleFromFilename', () => {
  it('extracts title from filename without date prefix', () => {
    const { extractTitleFromFilename } = require('./design-doc');
    expect(extractTitleFromFilename('2026-01-09-queue-workflows-design.md')).toBe(
      'queue-workflows-design'
    );
  });

  it('handles filename without date prefix', () => {
    const { extractTitleFromFilename } = require('./design-doc');
    expect(extractTitleFromFilename('my-feature.md')).toBe('my-feature');
  });

  it('removes .md extension', () => {
    const { extractTitleFromFilename } = require('./design-doc');
    expect(extractTitleFromFilename('feature.md')).toBe('feature');
  });
});
```

**Step 2: Run test to verify it fails**

Run: `cd dashboard && pnpm test -- --run design-doc.test.ts`
Expected: FAIL with "Cannot find module './design-doc'"

**Step 3: Write minimal implementation**

Create `dashboard/src/lib/design-doc.ts`:

```typescript
/**
 * Design document import utilities.
 */

/**
 * Extract title from markdown H1 heading, stripping "Design" suffix.
 */
export function extractTitle(markdown: string): string {
  const match = markdown.match(/^#\s+(.+?)(?:\s+Design)?$/m);
  if (!match) {
    return 'Untitled';
  }
  return match[1].trim();
}

/**
 * Generate timestamp-based design document ID.
 * Format: design-YYYYMMDDHHmmss
 */
export function generateDesignId(): string {
  const now = new Date();
  const ts = now
    .toISOString()
    .replace(/[-:T]/g, '')
    .slice(0, 14);
  return `design-${ts}`;
}

/**
 * Extract title from filename, removing date prefix and extension.
 * Example: "2026-01-09-queue-workflows-design.md" -> "queue-workflows-design"
 */
export function extractTitleFromFilename(filename: string): string {
  // Remove .md extension
  let name = filename.replace(/\.md$/i, '');
  // Remove date prefix (YYYY-MM-DD-)
  name = name.replace(/^\d{4}-\d{2}-\d{2}-/, '');
  return name;
}
```

**Step 4: Run test to verify it passes**

Run: `cd dashboard && pnpm test -- --run design-doc.test.ts`
Expected: PASS

**Step 5: Commit**

```bash
git add dashboard/src/lib/design-doc.ts dashboard/src/lib/design-doc.test.ts
git commit -m "feat(dashboard): add design document utility functions"
```

---

## Task 8: Add design doc import UI to QuickShotModal

**Files:**
- Modify: `dashboard/src/components/QuickShotModal.tsx:1-356`
- Test: `dashboard/src/components/QuickShotModal.test.tsx`

**Step 1: Write the failing test**

Add to `dashboard/src/components/QuickShotModal.test.tsx`:

```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QuickShotModal } from './QuickShotModal';
import { api } from '../api/client';

vi.mock('../api/client', () => ({
  api: {
    getConfig: vi.fn(),
    readFile: vi.fn(),
    createWorkflow: vi.fn(),
    getWorkflowDefaults: vi.fn(),
  },
  ApiError: class ApiError extends Error {
    constructor(message: string, public code: string, public status: number) {
      super(message);
    }
  },
}));

describe('QuickShotModal design doc import', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (api.getConfig as vi.Mock).mockResolvedValue({
      working_dir: '/test/repo',
      max_concurrent: 5,
    });
    (api.getWorkflowDefaults as vi.Mock).mockResolvedValue({
      worktree_path: null,
      profile: null,
    });
  });

  it('shows import area with drop zone', async () => {
    render(<QuickShotModal open={true} onOpenChange={() => {}} />);

    await waitFor(() => {
      expect(screen.getByText(/drop design doc/i)).toBeInTheDocument();
    });
  });

  it('pre-fills worktree path from config working_dir', async () => {
    render(<QuickShotModal open={true} onOpenChange={() => {}} />);

    await waitFor(() => {
      const input = screen.getByLabelText(/worktree path/i);
      expect(input).toHaveValue('/test/repo');
    });
  });

  it('imports file via path input', async () => {
    (api.readFile as vi.Mock).mockResolvedValue({
      content: '# My Feature Design\n\n## Problem\nDescription here.',
      filename: '2026-01-09-my-feature-design.md',
    });

    render(<QuickShotModal open={true} onOpenChange={() => {}} />);

    await waitFor(() => {
      expect(screen.getByText(/drop design doc/i)).toBeInTheDocument();
    });

    const pathInput = screen.getByPlaceholderText(/path to design doc/i);
    await userEvent.type(pathInput, '/path/to/design.md');

    const importButton = screen.getByRole('button', { name: /import/i });
    await userEvent.click(importButton);

    await waitFor(() => {
      expect(api.readFile).toHaveBeenCalledWith('/path/to/design.md');
      expect(screen.getByLabelText(/task title/i)).toHaveValue('My Feature');
      expect(screen.getByLabelText(/task id/i)).toHaveValue(
        expect.stringMatching(/^design-\d{14}$/)
      );
    });
  });

  it('shows error toast for invalid file', async () => {
    (api.readFile as vi.Mock).mockRejectedValue(
      new Error('File not found')
    );

    render(<QuickShotModal open={true} onOpenChange={() => {}} />);

    await waitFor(() => {
      expect(screen.getByText(/drop design doc/i)).toBeInTheDocument();
    });

    const pathInput = screen.getByPlaceholderText(/path to design doc/i);
    await userEvent.type(pathInput, '/invalid/path.md');

    const importButton = screen.getByRole('button', { name: /import/i });
    await userEvent.click(importButton);

    await waitFor(() => {
      expect(screen.getByText(/failed to read/i)).toBeInTheDocument();
    });
  });
});
```

**Step 2: Run test to verify it fails**

Run: `cd dashboard && pnpm test -- --run QuickShotModal.test.tsx`
Expected: FAIL with "Unable to find an element with the text: /drop design doc/i"

**Step 3: Write minimal implementation**

Update `dashboard/src/components/QuickShotModal.tsx`. Add imports:

```typescript
import { useCallback, useEffect, useState } from 'react';
import { Card } from './ui/card';
import { extractTitle, generateDesignId, extractTitleFromFilename } from '../lib/design-doc';
```

Add state and effects inside the component:

```typescript
// After existing useState declarations
const [importPath, setImportPath] = useState('');
const [isImporting, setIsImporting] = useState(false);
const [isDragOver, setIsDragOver] = useState(false);

// Fetch config on mount to pre-fill worktree path
useEffect(() => {
  if (open) {
    api.getConfig().then((config) => {
      if (config.working_dir && !getValues('worktree_path')) {
        setValue('worktree_path', config.working_dir);
      }
    }).catch(() => {
      // Config fetch failed, continue without pre-fill
    });
  }
}, [open, setValue, getValues]);

// Handle file import from path
const handleImportFromPath = useCallback(async () => {
  if (!importPath.trim()) return;

  setIsImporting(true);
  try {
    const { content, filename } = await api.readFile(importPath);
    const title = extractTitle(content) || extractTitleFromFilename(filename);
    const issueId = generateDesignId();

    setValue('issue_id', issueId);
    setValue('task_title', title);
    setValue('task_description', content);
    setImportPath('');
    toast.success('Design document imported');
  } catch (error) {
    toast.error(error instanceof Error ? error.message : 'Failed to read file');
  } finally {
    setIsImporting(false);
  }
}, [importPath, setValue]);

// Handle drag and drop
const handleDragOver = useCallback((e: React.DragEvent) => {
  e.preventDefault();
  setIsDragOver(true);
}, []);

const handleDragLeave = useCallback((e: React.DragEvent) => {
  e.preventDefault();
  setIsDragOver(false);
}, []);

const handleDrop = useCallback(async (e: React.DragEvent) => {
  e.preventDefault();
  setIsDragOver(false);

  const file = e.dataTransfer.files[0];
  if (!file) return;

  if (!file.name.endsWith('.md')) {
    toast.error('Only .md files supported');
    return;
  }

  try {
    const content = await file.text();
    const title = extractTitle(content) || extractTitleFromFilename(file.name);
    const issueId = generateDesignId();

    setValue('issue_id', issueId);
    setValue('task_title', title);
    setValue('task_description', content);
    toast.success('Design document imported');
  } catch {
    toast.error('Failed to read file');
  }
}, [setValue]);
```

Add the import UI at the top of the form (after DialogHeader):

```tsx
{/* Design Doc Import Area */}
<Card
  className={`border-2 border-dashed p-4 mb-4 transition-colors ${
    isDragOver ? 'border-primary bg-primary/5' : 'border-muted-foreground/25'
  }`}
  onDragOver={handleDragOver}
  onDragLeave={handleDragLeave}
  onDrop={handleDrop}
>
  <div className="text-center text-sm text-muted-foreground mb-3">
    Drop design doc here
    <span className="block text-xs">or</span>
  </div>
  <div className="flex gap-2">
    <Input
      placeholder="Path to design doc..."
      value={importPath}
      onChange={(e) => setImportPath(e.target.value)}
      className="flex-1"
    />
    <Button
      type="button"
      variant="secondary"
      onClick={handleImportFromPath}
      disabled={isImporting || !importPath.trim()}
    >
      {isImporting ? 'Importing...' : 'Import'}
    </Button>
  </div>
</Card>
```

**Step 4: Run test to verify it passes**

Run: `cd dashboard && pnpm test -- --run QuickShotModal.test.tsx`
Expected: PASS

**Step 5: Commit**

```bash
git add dashboard/src/components/QuickShotModal.tsx dashboard/src/components/QuickShotModal.test.tsx
git commit -m "feat(dashboard): add design doc import to QuickShotModal"
```

---

## Task 9: Run full test suite and lint

**Files:**
- None (verification only)

**Step 1: Run backend tests**

Run: `uv run pytest tests/ -v`
Expected: All tests PASS

**Step 2: Run backend lint and type check**

Run: `uv run ruff check amelia tests && uv run mypy amelia`
Expected: No errors

**Step 3: Run frontend tests**

Run: `cd dashboard && pnpm test:run`
Expected: All tests PASS

**Step 4: Run frontend lint and type check**

Run: `cd dashboard && pnpm lint && pnpm type-check`
Expected: No errors

**Step 5: Build frontend**

Run: `cd dashboard && pnpm build`
Expected: Build succeeds

**Step 6: Final commit (if any fixes needed)**

```bash
git add -A
git commit -m "chore: fix lint and type errors"
```

---

## Task 10: Manual integration test

**Files:**
- None (manual testing)

**Step 1: Start the server with working-dir**

Run: `uv run amelia dev --working-dir $(pwd)`
Expected: Server starts on port 8420

**Step 2: Open dashboard and test import**

1. Open http://localhost:8420
2. Open Quick Shot modal (keyboard shortcut or button)
3. Verify worktree path is pre-filled with current directory
4. Create a test design doc: `echo "# Test Feature Design\n\n## Problem\nTest" > /tmp/test-design.md`
5. Enter `/tmp/test-design.md` in import path and click Import
6. Verify:
   - Issue ID is `design-YYYYMMDDHHMMSS` format
   - Task Title is "Test Feature"
   - Description contains the markdown content

**Step 3: Test drag-drop (if supported by browser)**

1. Drag a .md file onto the drop zone
2. Verify fields are populated

**Step 4: Test security scoping**

1. Try importing a file outside the working directory
2. Verify error message appears: "Path not accessible"

**Step 5: Document any issues found**

If issues found, create fix commits as needed.

---

## Summary

| Task | Description | Files Changed |
|------|-------------|---------------|
| 1 | Add working_dir to ServerConfig | config.py, test_config.py |
| 2 | Add --working-dir CLI option | cli.py, test_cli.py |
| 3 | Add config dependency injection | dependencies.py, main.py, test_dependencies.py |
| 4 | Create GET /api/config endpoint | routes/config.py, main.py, test_config.py |
| 5 | Create POST /api/files/read endpoint | routes/files.py, main.py, test_files.py |
| 6 | Add frontend API client methods | client.ts, types/index.ts, client.test.ts |
| 7 | Create design-doc utilities | design-doc.ts, design-doc.test.ts |
| 8 | Add import UI to QuickShotModal | QuickShotModal.tsx, QuickShotModal.test.tsx |
| 9 | Run full test suite | None (verification) |
| 10 | Manual integration test | None (manual) |
