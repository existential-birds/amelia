"""Brainstormer agent configuration: prompts and restricted filesystem tooling.

Defines the design-collaborator agent's prompts and a filesystem middleware
restricted to read operations plus a markdown-only ``write_design_doc`` tool.
Kept separate from :mod:`amelia.server.services.brainstorm` so the service
layer stays focused on session lifecycle and message handling.
"""

from collections.abc import Callable
from typing import Any

from deepagents.backends.protocol import BackendProtocol, WriteResult
from deepagents.middleware.filesystem import (
    FilesystemMiddleware,
    FilesystemState,
    validate_path,
)
from langchain.tools import ToolRuntime
from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool, StructuredTool
from langgraph.types import Command


# Tool description for the write_design_doc tool (markdown-only write)
WRITE_DESIGN_DOC_DESCRIPTION = """Write a design document (markdown file) to the filesystem.

Usage:
- The file_path parameter must be an absolute path ending with .md
- ONLY markdown files (.md) can be written - this tool will reject other file types
- The content parameter must be a string containing markdown content
- This tool creates new files only; use for design docs, ADRs, specs, etc.
- Typical paths: /docs/plans/YYYY-MM-DD-feature-design.md, /docs/adr/NNNN-decision.md"""


def _design_doc_result(res: WriteResult, tool_call_id: str | None) -> Command[Any] | str:
    """Build the tool result for a write_design_doc write.

    Shared by the sync and async tool implementations: returns the backend
    error, a Command updating filesystem state, or a plain success string.
    """
    if res.error:
        return res.error
    if res.files_update is not None:
        return Command(
            update={
                "files": res.files_update,
                "messages": [
                    ToolMessage(
                        content=f"Created design document: {res.path}",
                        tool_call_id=tool_call_id,
                    )
                ],
            }
        )
    return f"Created design document: {res.path}"


def _write_design_doc_tool_generator(
    middleware: FilesystemMiddleware,
) -> BaseTool:
    """Generate the write_design_doc tool (markdown-only write).

    This is a restricted version of write_file that only allows writing
    markdown (.md) files. Used by the brainstormer to prevent accidental
    code generation.

    Args:
        middleware: FilesystemMiddleware instance (used for backend resolution).

    Returns:
        Configured write_design_doc tool.
    """

    def sync_write_design_doc(
        file_path: str,
        content: str,
        runtime: ToolRuntime[None, FilesystemState],
    ) -> Command[Any] | str:
        """Synchronous write_design_doc implementation."""
        # Validate markdown extension
        if not file_path.lower().endswith(".md"):
            return (
                f"Error: write_design_doc only allows markdown files (.md). "
                f"Got: {file_path}. The brainstormer cannot write code files."
            )

        resolved_backend = middleware._get_backend(runtime)
        validated_path = validate_path(file_path)
        res: WriteResult = resolved_backend.write(validated_path, content)
        return _design_doc_result(res, runtime.tool_call_id)

    async def async_write_design_doc(
        file_path: str,
        content: str,
        runtime: ToolRuntime[None, FilesystemState],
    ) -> Command[Any] | str:
        """Asynchronous write_design_doc implementation."""
        # Validate markdown extension
        if not file_path.lower().endswith(".md"):
            return (
                f"Error: write_design_doc only allows markdown files (.md). "
                f"Got: {file_path}. The brainstormer cannot write code files."
            )

        resolved_backend = middleware._get_backend(runtime)
        validated_path = validate_path(file_path)
        res: WriteResult = await resolved_backend.awrite(validated_path, content)
        return _design_doc_result(res, runtime.tool_call_id)

    return StructuredTool.from_function(
        name="write_design_doc",
        description=WRITE_DESIGN_DOC_DESCRIPTION,
        func=sync_write_design_doc,
        coroutine=async_write_design_doc,
    )


# Custom restricted filesystem prompt for brainstormer
BRAINSTORMER_FILESYSTEM_PROMPT = """## Filesystem Tools

You have access to: `ls`, `read_file`, `glob`, `grep`, `write_design_doc`

**IMPORTANT RESTRICTIONS:**
- You can ONLY write markdown files (.md) using `write_design_doc`
- You cannot write code files (.py, .ts, .js, etc.)
- You cannot execute shell commands
- Your output is a DESIGN DOCUMENT, not an implementation

Use the read tools to understand the codebase. Use `write_design_doc` to save your final design."""


# System prompt for the brainstormer agent - defines role and behavior
BRAINSTORMER_SYSTEM_PROMPT = """# Role

You are a design collaborator that helps turn ideas into fully formed designs through natural dialogue.

**CRITICAL: You are a designer, NOT an implementer.**
- Your job is to produce a design DOCUMENT, not code
- NEVER write implementation code (Python, TypeScript, etc.)
- NEVER create source files, only markdown design documents
- The design document will be handed off to a developer agent for implementation
- If you catch yourself about to write code, STOP and write prose describing what should be built instead

# Process

**Understanding the idea:**
- Check out the current project state first (files, docs, recent commits)
- Ask questions one at a time to refine the idea
- Prefer multiple choice questions when possible
- Only one question per message
- Focus on: purpose, constraints, success criteria

**Exploring approaches:**
- Propose 2-3 different approaches with trade-offs
- Lead with your recommendation and explain why

**Presenting the design:**
- Present in sections of 200-300 words
- Ask after each section whether it looks right
- Cover: architecture, components, data flow, error handling, testing
- Go back and clarify when needed

**Finalizing:**
- Write the validated design to `{plan_path}`
- The document should contain enough detail for a developer to implement
- Include pseudocode or interface sketches if helpful, but NOT runnable code
- After writing the document, tell the user it's ready for handoff to implementation

# Principles

- One question at a time
- Multiple choice preferred
- YAGNI ruthlessly
- Always explore 2-3 alternatives before settling
- Incremental validation - present design in sections
- **Design documents only - no implementation code**
"""

# User prompt template for the first message in a session
BRAINSTORMER_USER_PROMPT_TEMPLATE = "Help me design: {idea}"


def build_brainstormer_instructions(plan_path: str) -> str:
    """Format BRAINSTORMER_SYSTEM_PROMPT with the resolved plan path."""
    return BRAINSTORMER_SYSTEM_PROMPT.format(plan_path=plan_path)


class BrainstormerFilesystemMiddleware(FilesystemMiddleware):
    """Restricted filesystem middleware for brainstormer agent.

    Provides only read operations (ls, read_file, glob, grep) and a
    markdown-only write tool (write_design_doc). Does not include:
    - write_file (unrestricted file creation)
    - edit_file (code modification)
    - execute (shell command execution)

    This ensures the brainstormer can only create design documents,
    not modify code or run commands.
    """

    def __init__(
        self,
        *,
        backend: BackendProtocol | Callable[[ToolRuntime], BackendProtocol] | None = None,
        tool_token_limit_before_evict: int | None = 20000,
    ) -> None:
        """Initialize with restricted tools.

        Args:
            backend: Backend for file storage.
            tool_token_limit_before_evict: Token limit before evicting tool results.
        """
        # Initialize parent with restricted system prompt, but we'll override tools
        super().__init__(
            backend=backend,
            system_prompt=BRAINSTORMER_FILESYSTEM_PROMPT,
            tool_token_limit_before_evict=tool_token_limit_before_evict,
        )

        # Override tools with restricted set:
        # Read-only tools + markdown-only write
        self.tools = [
            self._create_ls_tool(),
            self._create_read_file_tool(),
            self._create_glob_tool(),
            self._create_grep_tool(),
            _write_design_doc_tool_generator(self),
        ]
