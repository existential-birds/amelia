# Coding Conventions

**Analysis Date:** 2026-03-13

## Naming Patterns

**Python Files:**
- snake_case for all modules: `agentic_state.py`, `retry.py`, `types.py`
- Prefix test files with `test_`: `test_retry.py`, `test_types.py`
- Module docstrings are required at top of every file

**Python Classes:**
- PascalCase: `Architect`, `DriverInterface`, `AgenticMessage`
- Pydantic models: PascalCase, always inherit from `BaseModel` or `BaseModel` subclass
- StrEnum classes: PascalCase with UPPER_SNAKE values: `DriverType.CLAUDE`, `SandboxMode.CONTAINER`
- Exception classes end with `Error`: `ConfigurationError`, `ModelProviderError`, `WorkflowNotFoundError`
- Test classes prefixed with `Test`: `TestArchitectPlanAsyncGenerator`, `TestDesign`

**Python Functions/Methods:**
- snake_case: `execute_agentic()`, `get_agent_config()`, `resolve_plan_path()`
- Private methods prefixed with underscore: `_build_agentic_prompt()`, `_validate_daytona()`
- Async functions use `async def` with no special naming prefix
- Test functions: `test_<what_is_tested>` or `test_<scenario>`: `test_successful_call_returns_immediately()`

**Python Variables:**
- snake_case for locals and parameters: `tool_calls`, `raw_output`, `captured_prompt`
- UPPER_SNAKE for module-level constants: `DEFAULT_NETWORK_ALLOWED_HOSTS`, `REQUIRED_AGENTS`, `OPENROUTER_FREE_MODEL`
- Type aliases in PascalCase: `GenerateResult`, `DriverType`

**Dashboard (TypeScript) Files:**
- PascalCase for React components: `UsageCard.tsx`, `PageHeader.tsx`, `ApprovalControls.tsx`
- camelCase for utilities: `format.ts`, `chart-colors.ts`
- Test files: `*.test.tsx` or `*.test.ts` co-located or in `__tests__/` subdirectory

**Dashboard Functions/Variables:**
- camelCase for functions and variables: `createMockTokenSummary`, `tokenUsage`
- PascalCase for React components and types/interfaces
- Factory functions prefixed with `create`: `createMockWorkflowSummary()`, `createMockTokenUsage()`

## Code Style

**Formatting (Python):**
- Ruff formatter (configured in `pyproject.toml`)
- Line length: 100 characters
- Target: Python 3.12+
- E501 (line-too-long) ignored in ruff linting

**Linting (Python):**
- Ruff with rules: E, F, I, UP, B, SIM, PLC0415
- `PLC0415` (import-outside-toplevel) enforced globally, ignored in test files
- `B008` (function-call-in-default-argument) ignored in `amelia/server/routes/*.py` for FastAPI `Depends()`
- Config: `pyproject.toml` `[tool.ruff]` section

**Type Checking (Python):**
- mypy in strict mode (`strict = true` in `pyproject.toml`)
- Python 3.12 target
- Custom stubs in `stubs/` directory
- Type hints required everywhere

**Linting (Dashboard):**
- ESLint with `@eslint/js`, `typescript-eslint`, `eslint-plugin-react-hooks`, `eslint-plugin-react-refresh`
- Config: `dashboard/eslint.config.js`
- Unused vars with `_` prefix allowed: `argsIgnorePattern: "^_"`
- `@typescript-eslint/no-explicit-any` disabled in test files
- React Refresh: warns on non-component exports

**Formatting (Dashboard):**
- No explicit Prettier config detected; formatting handled by ESLint + TypeScript

## Import Organization

**Python Import Order (enforced by ruff isort):**
1. `__future__` imports
2. Standard library (`import os`, `from pathlib import Path`)
3. Third-party (`from loguru import logger`, `from pydantic import BaseModel`)
4. First-party (`from amelia.core.types import ...`)
5. Local-folder (relative imports - rarely used)

**Import Rules:**
- `force-single-line = false` (multi-imports on one line allowed)
- `combine-as-imports = true`
- Two blank lines after imports (`lines-after-imports = 2`)
- `known-first-party = ["amelia"]`

**Example (from `amelia/agents/architect.py`):**
```python
from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from amelia.core.agentic_state import ToolCall, ToolResult
from amelia.core.constants import ToolName, resolve_plan_path
from amelia.core.types import AgentConfig, Profile
from amelia.drivers.base import AgenticMessage, AgenticMessageType
from amelia.drivers.factory import get_driver
from amelia.server.models.events import WorkflowEvent
```

**Circular Import Avoidance:**
- Use `from __future__ import annotations` for forward references
- Use `TYPE_CHECKING` guard for imports only needed for type annotations
- Use `noqa: PLC0415` for imports inside functions/methods when necessary

**Dashboard Path Aliases:**
- `@/` maps to `src/` (e.g., `import { createMockTokenSummary } from '@/__tests__/fixtures'`)

## Error Handling

**Exception Hierarchy (Python):**
- Base: `AmeliaError` (in `amelia/core/exceptions.py`)
- Config errors: `ConfigurationError(AmeliaError)`
- Provider errors with context: `ProviderAwareError(AmeliaError)` -> `ModelProviderError`, `SchemaValidationError`
- Server/API errors in `amelia/server/exceptions.py`: `WorkflowConflictError`, `ConcurrencyLimitError`, `InvalidStateError`, `WorkflowNotFoundError`, `InvalidWorktreeError`, `FileOperationError`

**Patterns:**
- Raise `ValueError` with clear messages for validation failures: `raise ValueError(f"Agent '{agent_name}' not configured in profile '{self.name}'")`
- Catch specific exception types in try/except, not bare `except`: `except (RuntimeError, ValueError) as exc:`
- Use Pydantic `model_validator` for cross-field validation (see `SandboxConfig._validate_daytona`)
- Use Pydantic `field_validator` for single-field validation (see `_validate_worktree_path`)
- Server exceptions carry HTTP status context in docstrings (e.g., `HTTP Status: 409 Conflict`)

**Async Error Handling:**
- Use `logger.exception("message")` for unexpected failures (logs traceback)
- Convert errors to domain events: `AgenticMessage(type=..., is_error=True).to_workflow_event(...)`
- Yield error state updates before returning from async generators

## Logging

**Framework:** Loguru (`from loguru import logger`)

**Configuration:** `amelia/logging.py` - `configure_logging()` function, called from CLI entry point

**Patterns:**
- Use structured kwargs, not string interpolation: `logger.info("Architect plan generated", agent="architect", raw_output_length=len(raw_output))`
- Use `logger.debug()` for tool-level detail, `logger.info()` for milestone events, `logger.warning()` for retriable issues
- Use `logger.exception()` for unexpected errors (includes traceback)
- Never use `print()` for logging

**Levels:**
- `DEBUG`: Tool calls, internal state transitions
- `INFO`: Agent milestones (started, completed), server startup
- `WARNING`: Retries, missing configs, unexpected states
- `ERROR`: Failures that stop execution
- Configurable via `AMELIA_LOG_LEVEL` env var (default: `INFO`)

## Comments

**Module Docstrings:**
- Required at top of every Python file
- Triple-quoted, describes module purpose
- Example: `"""Architect agent for generating implementation plans."""`

**Class Docstrings:**
- Required for all classes
- Describe purpose and key attributes
- Use `Attributes:` section for documenting instance variables

**Function Docstrings:**
- Required for all public functions and methods
- Google-style format: `Args:`, `Returns:`, `Raises:`, `Yields:`
- Example from `amelia/drivers/base.py`:
```python
async def generate(
    self,
    prompt: str,
    system_prompt: str | None = None,
    schema: type[BaseModel] | None = None,
    **kwargs: Any,
) -> GenerateResult:
    """Generate a response from the model.

    Args:
        prompt: The user prompt to send to the model.
        system_prompt: Optional system prompt for context/instructions.
        schema: Optional Pydantic model to validate/parse the output.
        **kwargs: Driver-specific parameters (e.g., cwd, session_id).

    Returns:
        GenerateResult tuple of (output, session_id):
        - output: str (if no schema) or instance of schema
        - session_id: str if driver supports sessions, None otherwise
    """
```

**Inline Comments:**
- Use sparingly, explain "why" not "what"
- `# noqa: PLC0415` for intentional import-inside-function
- `# noqa: S311` for intentional use of `random` (not for crypto)

## Function Design

**Size:** Functions are focused and typically under 50 lines of logic. Large orchestration methods (like `Architect.plan()`) are the exception and use clear section comments.

**Parameters:**
- Use keyword-only args (`*,`) for clarity: `async def plan(self, state, profile, *, workflow_id)`
- Use `**kwargs: Any` for driver-specific passthrough
- Default values via `Field(default_factory=...)` for mutable defaults in Pydantic models

**Return Values:**
- Async generators yield `tuple[State, Event]` for streaming updates
- Use `tuple` return types for multi-value returns: `GenerateResult = tuple[Any, str | None]`
- Use `| None` instead of `Optional[]`

## Module Design

**Exports:**
- No `__all__` typically used; imports are explicit
- Circular imports avoided via `TYPE_CHECKING` guard and `from __future__ import annotations`

**Barrel Files:**
- `__init__.py` files present in all packages
- Some re-export key classes (e.g., `amelia/server/database/__init__.py`)

**Pydantic Model Patterns:**
- Use `model_config = ConfigDict(frozen=True)` for immutable models
- Use `model_copy(update={...})` instead of mutation
- Use `Field(default_factory=...)` for mutable defaults
- Use `model_validator(mode="after")` for cross-field validation

**Protocol Pattern:**
- `DriverInterface` in `amelia/drivers/base.py` defines the driver contract using `typing.Protocol`
- All drivers implement this protocol (structural subtyping, not inheritance)

---

*Convention analysis: 2026-03-13*
