"""Stub ToolSpecs for library-provided tools.

These tools are implemented by deepagents (FilesystemMiddleware) and the
sandbox runtime, not by amelia. We register metadata-only specs (no handler,
no factory) so ``ToolPolicyMiddleware`` and toolset queries can reason about
them uniformly with amelia-owned tools.

Each spec is registered with a top-level ``register(...)`` call so that
``discover_builtin_tools`` detects this module via its AST scan.

See ``.beagle/concepts/tool-registry/spec.md`` §1 (Must Have #4).
"""

from __future__ import annotations

from pydantic import BaseModel

from amelia.tools.registry import Permission, RiskLevel, ToolSpec, register


class _ReadFileInput(BaseModel):
    file_path: str
    offset: int | None = None
    limit: int | None = None


class _WriteFileInput(BaseModel):
    file_path: str
    content: str


class _EditFileInput(BaseModel):
    file_path: str
    old_string: str
    new_string: str


class _GlobInput(BaseModel):
    pattern: str
    path: str | None = None


class _GrepInput(BaseModel):
    pattern: str
    path: str | None = None
    include: str | None = None


class _ExecuteInput(BaseModel):
    command: str
    timeout: int | None = 30


class _WebFetchInput(BaseModel):
    url: str
    prompt: str | None = None


class _WebSearchInput(BaseModel):
    query: str


register(
    ToolSpec(
        name="read_file",
        description="Read the contents of a file.",
        input_schema=_ReadFileInput,
        risk_level=RiskLevel.READ_ONLY,
        required_permissions=frozenset({Permission.FS_READ}),
        toolsets=frozenset({"readonly", "filesystem"}),
    )
)
register(
    ToolSpec(
        name="write_file",
        description="Write content to a file, overwriting if it exists.",
        input_schema=_WriteFileInput,
        risk_level=RiskLevel.WRITE,
        required_permissions=frozenset({Permission.FS_WRITE}),
        toolsets=frozenset({"filesystem"}),
    )
)
register(
    ToolSpec(
        name="edit_file",
        description="Replace a unique string in a file with a new string.",
        input_schema=_EditFileInput,
        risk_level=RiskLevel.WRITE,
        required_permissions=frozenset({Permission.FS_WRITE}),
        toolsets=frozenset({"filesystem"}),
    )
)
register(
    ToolSpec(
        name="glob",
        description="Find files matching a glob pattern.",
        input_schema=_GlobInput,
        risk_level=RiskLevel.READ_ONLY,
        required_permissions=frozenset({Permission.FS_READ}),
        toolsets=frozenset({"readonly", "filesystem"}),
    )
)
register(
    ToolSpec(
        name="grep",
        description="Search file contents for a pattern.",
        input_schema=_GrepInput,
        risk_level=RiskLevel.READ_ONLY,
        required_permissions=frozenset({Permission.FS_READ}),
        toolsets=frozenset({"readonly", "filesystem"}),
    )
)
register(
    ToolSpec(
        name="execute",
        description="Execute a shell command inside the sandbox.",
        input_schema=_ExecuteInput,
        risk_level=RiskLevel.EXECUTE,
        required_permissions=frozenset({Permission.SHELL_EXEC}),
        toolsets=frozenset({"execute"}),
    )
)
register(
    ToolSpec(
        name="web_fetch",
        description="Fetch the content of a URL.",
        input_schema=_WebFetchInput,
        risk_level=RiskLevel.READ_ONLY,
        required_permissions=frozenset({Permission.NET_READ}),
        toolsets=frozenset({"readonly", "web"}),
    )
)
register(
    ToolSpec(
        name="web_search",
        description="Search the web for a query.",
        input_schema=_WebSearchInput,
        risk_level=RiskLevel.READ_ONLY,
        required_permissions=frozenset({Permission.NET_READ}),
        toolsets=frozenset({"readonly", "web"}),
    )
)
