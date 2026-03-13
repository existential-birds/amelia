# Testing Patterns

**Analysis Date:** 2026-03-13

## Test Framework

### Python Backend

**Runner:**
- pytest 8.3.4+
- pytest-asyncio 0.24.0+ with `asyncio_mode = "auto"`
- Config: `pyproject.toml` `[tool.pytest.ini_options]`

**Assertion Library:**
- Built-in `assert` statements (pytest rewrites for detailed diffs)
- Pydantic `ValidationError` for schema validation tests

**Run Commands:**
```bash
uv run pytest                          # Run all unit tests (integration excluded by default)
uv run pytest tests/unit/              # Unit tests only
uv run pytest -m integration           # Integration tests only
uv run pytest tests/unit/core/test_retry.py::test_successful_call_returns_immediately -v  # Single test
uv run ruff check --fix amelia tests   # Lint
uv run mypy amelia                     # Type check
```

**Default Marker Filter:** `addopts = "-m 'not integration'"` -- integration tests are excluded by default and require explicit `-m integration` flag.

### Dashboard Frontend

**Runner:**
- Vitest 4.0.15+
- Config: `dashboard/vitest.config.ts`
- Environment: jsdom
- Globals enabled (`globals: true`)

**Assertion/Testing Libraries:**
- `@testing-library/react` 16.1.0+ for component rendering
- `@testing-library/jest-dom` 6.6.3+ for DOM matchers
- `@testing-library/user-event` 14.6.1+ for user interaction simulation
- `vitest` built-in `vi` for mocking

**Run Commands:**
```bash
cd dashboard && pnpm test:run          # CI mode (run once)
cd dashboard && pnpm test              # Watch mode
cd dashboard && pnpm test:ui           # UI mode (browser)
```

**Setup File:** `dashboard/src/test/setup.ts` -- mocks `scrollIntoView`, `ResizeObserver`, and `matchMedia` for browser API compatibility.

## Test File Organization

### Python

**Location:** Separate `tests/` directory mirroring source structure

**Naming:** `test_<module_or_feature>.py`

**Structure:**
```
tests/
├── conftest.py                        # Shared fixtures, factory helpers, mock utilities
├── unit/
│   ├── __init__.py
│   ├── conftest.py                    # (if needed for unit-specific fixtures)
│   ├── core/
│   │   ├── __init__.py
│   │   ├── test_retry.py
│   │   ├── test_types.py
│   │   ├── test_extraction.py
│   │   └── test_exceptions.py
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── test_architect_agentic.py
│   │   ├── test_developer.py
│   │   ├── test_reviewer.py
│   │   └── prompts/
│   │       ├── test_models.py
│   │       └── test_resolver.py
│   ├── drivers/
│   │   ├── __init__.py
│   │   ├── test_factory.py
│   │   └── api/
│   │       └── test_deepagents_transient_errors.py
│   ├── server/
│   │   ├── conftest.py                # Server-specific fixtures (mock_app_client, db_with_schema)
│   │   ├── database/
│   │   │   ├── conftest.py
│   │   │   └── test_*.py
│   │   ├── lifecycle/
│   │   │   └── test_*.py
│   │   └── models/
│   │       └── test_*.py
│   └── tools/
│       └── test_*.py
├── integration/
│   ├── __init__.py
│   ├── conftest.py                    # Integration fixtures, factory functions, database setup
│   ├── test_multi_driver_agents.py
│   ├── test_workflow_endpoints.py
│   └── server/
│       ├── conftest.py
│       └── database/
│           └── test_*.py
```

**File counts:** 159 unit test files, 38 integration test files

### Dashboard

**Location:** Mix of co-located and `__tests__/` subdirectories

**Naming:** `*.test.tsx` or `*.test.ts`

**Structure:**
```
dashboard/src/
├── __tests__/
│   └── fixtures.ts                    # Shared factory functions
├── components/
│   ├── UsageCard.test.tsx             # Co-located with component
│   ├── PageHeader.test.tsx
│   ├── settings/
│   │   └── __tests__/
│   │       ├── ProfileCard.test.tsx   # In __tests__ subdirectory
│   │       └── SandboxTab.test.tsx
│   └── brainstorm/
│       └── __tests__/
│           ├── ArtifactCard.test.tsx
│           └── SessionDrawer.test.tsx
├── utils/
│   ├── format.test.ts                 # Co-located
│   └── __tests__/
│       └── chart-colors.test.ts
└── types/
    └── __tests__/
        └── index.test.ts
```

**File count:** 86 dashboard test files

## Test Structure

### Python: Class-based grouping

Tests are organized into classes by feature area. Each class groups related test functions:

```python
class TestArchitectPlanAsyncGenerator:
    """Tests for Architect.plan() as async generator."""

    @pytest.fixture
    def mock_agentic_driver(self) -> MagicMock:
        """Driver that supports execute_agentic."""
        driver = MagicMock()
        driver.execute_agentic = AsyncMock()
        return driver

    async def test_plan_returns_async_iterator(
        self,
        mock_agentic_driver: MagicMock,
        state_with_issue: tuple[ImplementationState, Profile],
    ) -> None:
        """plan() should return an async iterator."""
        state, profile = state_with_issue
        # ... test body
```

**Key patterns:**
- Test classes group related tests: `TestArchitectInitWithAgentConfig`, `TestArchitectPlanAsyncGenerator`
- Class-scoped fixtures via `@pytest.fixture` inside the class
- Each test function has a descriptive docstring explaining expected behavior
- All test functions have `-> None` return type annotation
- Async tests need no special decorator (`asyncio_mode = "auto"` handles it)

### Python: Standalone functions

Simple tests use standalone async functions:

```python
async def test_successful_call_returns_immediately() -> None:
    """A successful call should return its value without any retry."""
    fn = AsyncMock(return_value=42)
    result = await with_retry(fn, RetryConfig(max_retries=3))
    assert result == 42
    fn.assert_awaited_once()
```

### Dashboard: describe/it blocks

```typescript
describe('UsageCard', () => {
  describe('rendering with token usage data', () => {
    it('renders the USAGE header', () => {
      const tokenUsage = createMockTokenSummary();
      render(<UsageCard tokenUsage={tokenUsage} />);
      expect(screen.getByText('USAGE')).toBeInTheDocument();
    });
  });

  describe('null token usage', () => {
    it('returns null when tokenUsage is null', () => {
      const { container } = render(<UsageCard tokenUsage={null} />);
      expect(container.firstChild).toBeNull();
    });
  });
});
```

## Mocking

### Python Mocking

**Framework:** `unittest.mock` (MagicMock, AsyncMock, patch)

**Driver Mocking Pattern:**
```python
# Mock a driver with spec enforcement
@pytest.fixture
def mock_driver() -> MagicMock:
    """Returns a mock driver that implements DriverInterface."""
    mock = MagicMock(spec=DriverInterface)
    mock.generate = AsyncMock(return_value=("mocked AI response", None))
    mock.execute_agentic = AsyncMock(return_value=AsyncIteratorMock([]))
    return mock
```

**Async Generator Mocking (key pattern):**
```python
# Custom async iterator mock (from tests/conftest.py)
class AsyncIteratorMock:
    """Mock async iterator for testing async generators."""
    def __init__(self, items: list[Any]) -> None:
        self.items = items
        self.index = 0

    def __aiter__(self) -> "AsyncIteratorMock":
        return self

    async def __anext__(self) -> Any:
        if self.index >= len(self.items):
            raise StopAsyncIteration
        item = self.items[self.index]
        self.index += 1
        return item

# Usage: mock async generators by defining inline async functions
async def mock_stream(*args, **kwargs):
    yield AgenticMessage(type=AgenticMessageType.RESULT, content="Done")

mock_driver.execute_agentic = mock_stream
```

**Patching Pattern (agent construction):**
```python
# Patch the driver factory to inject mock driver
with patch("amelia.agents.architect.get_driver", return_value=mock_driver):
    architect = Architect(config)
    # ... test architect behavior
```

**Capturing kwargs for assertion:**
```python
captured_cwd = None

async def mock_stream(*args, **kwargs):
    nonlocal captured_cwd
    captured_cwd = kwargs.get("cwd")
    yield AgenticMessage(type=AgenticMessageType.RESULT, content="Done")

mock_driver.execute_agentic = mock_stream
# ... run code ...
assert captured_cwd == expected_cwd
```

**What to Mock (unit tests):**
- LLM driver calls (`execute_agentic`, `generate`)
- External API calls (HTTP, database connections)
- Driver factory (`get_driver`)
- Time-dependent operations (`asyncio.sleep`)
- Environment variables (`patch.dict(os.environ, {...})`)

**What NOT to Mock (integration tests):**
- Internal classes like `Architect`, `Developer`, `Reviewer` -- these must use real implementations
- Pydantic model construction and validation
- State transitions and data flow between components
- Only mock at the external boundary (HTTP calls to LLM APIs)

### Dashboard Mocking

**Framework:** Vitest `vi`

**Browser API Mocks (in setup.ts):**
```typescript
Element.prototype.scrollIntoView = vi.fn();
global.ResizeObserver = class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
};
```

## Fixtures and Factories

### Python Root Conftest (`tests/conftest.py`)

**Factory Fixtures (return callables that create instances):**

```python
@pytest.fixture
def mock_issue_factory() -> Callable[..., Issue]:
    """Factory fixture for creating test Issue instances with sensible defaults."""
    def _create(
        id: str = "TEST-123",
        title: str = "Test Issue",
        description: str = "Test issue description for unit testing",
        status: str = "open"
    ) -> Issue:
        return Issue(id=id, title=title, description=description, status=status)
    return _create

@pytest.fixture
def mock_profile_factory(tmp_path_factory: TempPathFactory) -> Callable[..., Profile]:
    """Factory fixture with presets (cli_single, api_single)."""
    # Uses tmp_path_factory for unique temp directories
    def _create(preset: str | None = None, ...) -> Profile:
        ...
    return _create

@pytest.fixture
def mock_execution_state_factory(
    mock_profile_factory, mock_issue_factory
) -> Callable[..., tuple[ImplementationState, Profile]]:
    """Factory that returns (state, profile) tuples."""
    ...
```

**Helper Functions (module-level, not fixtures):**

```python
def create_mock_execute_agentic(
    messages: list[AgenticMessage],
    capture_kwargs: list[dict[str, Any]] | None = None,
) -> Callable[..., AsyncGenerator[AgenticMessage, None]]:
    """Create a mock execute_agentic async generator function."""
    ...

def make_agents_json(driver="claude", model="sonnet", ...) -> str:
    """Create agents JSON blob for ProfileRecord."""
    ...
```

### Integration Conftest (`tests/integration/conftest.py`)

**Module-level factory functions (not fixtures):**
```python
def make_issue(id="TEST-123", title="Test Issue", ...) -> Issue:
def make_profile(name="test", driver="api", model="...", ...) -> Profile:
def make_execution_state(issue=..., profile=None, ...) -> ImplementationState:
def make_config(thread_id, profile=None, ...) -> dict:
def make_agentic_messages(*, include_thinking=True, ...) -> list[AgenticMessage]:
def make_reviewer_agentic_messages(*, approved=True, ...) -> list[AgenticMessage]:
```

**Database Fixtures:**
```python
@pytest.fixture
async def test_db() -> AsyncGenerator[Database, None]:
    """Create and initialize test database with PostgreSQL."""
    async with Database(DATABASE_URL) as db:
        migrator = Migrator(db)
        await migrator.run()
        await db.execute("TRUNCATE TABLE ... CASCADE")
        yield db

@pytest.fixture
def test_repository(test_db: Database) -> WorkflowRepository:
    """Create repository backed by test database."""
    return WorkflowRepository(test_db)
```

### Dashboard Fixtures (`dashboard/src/__tests__/fixtures.ts`)

```typescript
export function createMockWorkflowSummary(
  overrides?: Partial<WorkflowSummary>
): WorkflowSummary {
  return {
    id: 'wf-test-123',
    issue_id: 'ISSUE-123',
    status: 'in_progress',
    ...overrides,
  };
}

export function createMockTokenSummary(
  overrides?: Partial<TokenSummary>
): TokenSummary {
  // Returns full TokenSummary with agent breakdown
}
```

**Pattern:** Factory functions accept `Partial<T>` overrides spread over sensible defaults.

## Coverage

**Requirements:** No coverage thresholds enforced in config.

**Running Coverage (Python):**
```bash
uv run pytest --cov=amelia --cov-report=html
```

**Running Coverage (Dashboard):**
```bash
cd dashboard && pnpm test:run -- --coverage
```

## Test Types

### Unit Tests (`tests/unit/`)

- **Scope:** Single module or class in isolation
- **External Dependencies:** All mocked (drivers, databases, HTTP)
- **Async:** Handled automatically by `asyncio_mode = "auto"`
- **Run by default:** Yes (default marker filter excludes integration)
- **Speed:** Fast, no external services required

### Integration Tests (`tests/integration/`)

- **Scope:** Multiple components working together, real database
- **External Dependencies:** Real PostgreSQL database, mock only at LLM API boundary
- **Marker:** `@pytest.mark.integration` required on classes/functions
- **Run explicitly:** `uv run pytest -m integration`
- **Key rule:** Never mock internal classes (`Architect`, `Developer`, `Reviewer`). Only mock external HTTP calls to LLM APIs.
- **Database:** Uses `postgresql://amelia:amelia@localhost:5432/amelia_test` (configurable via `DATABASE_URL` env var)
- **Parametrized driver tests:** Test behavior across all driver types (`api`, `claude`, `codex`)

### Dashboard Tests

- **Unit tests:** Component rendering with `@testing-library/react`
- **Integration tests:** Named `*.integration.test.tsx` (e.g., `ProfileEditModal.integration.test.tsx`)
- **Approach:** Render components, query DOM with `screen.getByText()`, `screen.getByRole()`, assert with `toBeInTheDocument()`
- **Accessibility:** Tests verify ARIA roles, heading hierarchy, table structure

## Common Patterns

### Async Testing (Python)

```python
# No decorator needed - asyncio_mode = "auto" handles it
async def test_plan_yields_state_and_event_tuples(self, ...) -> None:
    """plan() should yield (ImplementationState, WorkflowEvent) tuples."""
    # ... setup ...

    async for new_state, event in architect.plan(state, profile, workflow_id=uuid4()):
        results.append((new_state, event))

    assert [event.event_type for _, event in results] == [
        EventType.CLAUDE_TOOL_CALL,
        EventType.CLAUDE_TOOL_RESULT,
        EventType.AGENT_OUTPUT,
    ]
```

### Error Testing (Python)

```python
# Using pytest.raises with match pattern
async def test_exhausts_retries_and_raises_last_exception() -> None:
    fn = AsyncMock(side_effect=[ValueError("fail1"), ValueError("fail2")])

    with (
        patch("amelia.core.retry.asyncio.sleep", new_callable=AsyncMock),
        pytest.raises(ValueError, match="fail2"),
    ):
        await with_retry(fn, RetryConfig(max_retries=1), retryable_exceptions=(ValueError,))

# Pydantic validation error testing
def test_agent_config_rejects_legacy_cli_driver() -> None:
    with pytest.raises(ValueError, match="Input should be 'claude', 'codex' or 'api'"):
        AgentConfig(driver="cli", model="sonnet")
```

### High-Fidelity Mocking (Python)

Always return proper Pydantic model instances, not dicts:

```python
# CORRECT: Return Pydantic model instances
mock.generate = AsyncMock(return_value=("mocked AI response", None))

# CORRECT: Use AgenticMessage (Pydantic model) not raw dicts
async def mock_stream(*args, **kwargs):
    yield AgenticMessage(
        type=AgenticMessageType.TOOL_CALL,
        tool_name="read_file",
        tool_input={"path": "src/main.py"},
        tool_call_id="call-1",
    )

# WRONG: Never return .model_dump() dicts where production code expects models
```

### FastAPI Testing (Python)

```python
@pytest.fixture
def mock_app_client() -> Generator[TestClient, None, None]:
    """FastAPI test client with noop lifespan and dependency overrides."""
    from amelia.server.main import create_app
    app = create_app()

    # Override lifespan to skip database/migrator
    @asynccontextmanager
    async def noop_lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield
    app.router.lifespan_context = noop_lifespan

    # Override dependencies
    app.dependency_overrides[get_repository] = lambda: mock_repo

    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
```

### Component Testing (Dashboard)

```typescript
import { render, screen, within } from '@testing-library/react';

it('renders agent breakdown table with headers', () => {
  const tokenUsage = createMockTokenSummary();
  render(<UsageCard tokenUsage={tokenUsage} />);

  expect(screen.getByRole('table')).toBeInTheDocument();
  expect(screen.getByText('Agent')).toBeInTheDocument();

  const rows = screen.getAllByRole('row');
  expect(rows).toHaveLength(4);  // Header + 3 agent rows
});
```

---

*Testing analysis: 2026-03-13*
