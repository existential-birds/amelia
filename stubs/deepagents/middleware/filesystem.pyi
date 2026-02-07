"""Type stubs for deepagents.middleware.filesystem module."""

from collections.abc import Callable
from typing import Any, TypedDict

from deepagents.backends.protocol import BackendProtocol
from langchain.tools import ToolRuntime
from langchain_core.tools import BaseTool

class FilesystemState(TypedDict, total=False):
    """State for filesystem middleware operations."""

    files: dict[str, Any]


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

    backend: BackendProtocol | Callable[[ToolRuntime[Any, Any]], BackendProtocol] | None
    tools: list[BaseTool]
    _custom_system_prompt: str | None
    _custom_tool_descriptions: dict[str, str]
    _tool_token_limit_before_evict: int | None

    def __init__(
        self,
        *,
        backend: BackendProtocol | Callable[[ToolRuntime[Any, Any]], BackendProtocol] | None = None,
        system_prompt: str | None = None,
        custom_tool_descriptions: dict[str, str] | None = None,
        tool_token_limit_before_evict: int | None = ...,
    ) -> None: ...

    def _get_backend(self, runtime: ToolRuntime[Any, Any]) -> BackendProtocol: ...
    def _create_ls_tool(self) -> BaseTool: ...
    def _create_read_file_tool(self) -> BaseTool: ...
    def _create_write_file_tool(self) -> BaseTool: ...
    def _create_edit_file_tool(self) -> BaseTool: ...
    def _create_glob_tool(self) -> BaseTool: ...
    def _create_grep_tool(self) -> BaseTool: ...
    def _create_execute_tool(self) -> BaseTool: ...
