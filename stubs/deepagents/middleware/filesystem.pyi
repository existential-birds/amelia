"""Type stubs for deepagents.middleware.filesystem module."""

from collections.abc import Callable
from typing import Any, TypedDict

from langchain.tools import ToolRuntime
from langchain_core.tools import BaseTool

from deepagents.backends.protocol import BackendProtocol


class FilesystemState(TypedDict, total=False):
    """State for filesystem middleware operations."""

    files: dict[str, Any]


# Tool generator functions that create tools from a backend or factory
TOOL_GENERATORS: dict[
    str, Callable[[BackendProtocol | Callable[[ToolRuntime[Any, Any]], BackendProtocol]], BaseTool]
]


def _get_backend(
    backend: BackendProtocol | Callable[[ToolRuntime[Any, Any]], BackendProtocol] | None,
    runtime: ToolRuntime[Any, Any],
) -> BackendProtocol:
    """Get the resolved backend from a backend or factory.

    Args:
        backend: Backend or factory function to resolve.
        runtime: Tool runtime context.

    Returns:
        Resolved backend protocol instance.
    """
    ...


def _validate_path(file_path: str) -> str:
    """Validate and normalize a file path.

    Args:
        file_path: Path to validate.

    Returns:
        Validated path string.

    Raises:
        ValueError: If path is invalid.
    """
    ...


class FilesystemMiddleware:
    """Middleware for filesystem operations in deepagents.

    Provides tools for reading and writing files through a backend.
    """

    tool_token_limit_before_evict: int | None
    backend: BackendProtocol | Callable[[ToolRuntime[Any, Any]], BackendProtocol] | None
    tools: list[BaseTool]
    _custom_system_prompt: str | None

    def __init__(
        self,
        *,
        backend: BackendProtocol | Callable[[ToolRuntime[Any, Any]], BackendProtocol] | None = None,
        tool_token_limit_before_evict: int | None = ...,
    ) -> None:
        """Initialize filesystem middleware.

        Args:
            backend: Backend for file storage.
            tool_token_limit_before_evict: Token limit before evicting tool results.
        """
        ...
