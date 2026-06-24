"""Read-only git inspection tools (``git_diff``, ``git_log``) for agent use.

Both tools wrap :class:`amelia.tools.git_utils.GitOperations` so agents can
inspect repository state without direct shell access. They are registered as
read-only members of the ``vcs`` toolset.
"""

from __future__ import annotations

from pydantic import BaseModel

from amelia.tools.git_utils import GitOperations
from amelia.tools.registry import Permission, RiskLevel, ToolSpec, register


class GitDiffInput(BaseModel):
    """Input schema for the ``git_diff`` tool."""

    repo_path: str
    target: str | None = None


class GitLogInput(BaseModel):
    """Input schema for the ``git_log`` tool."""

    repo_path: str
    max_count: int = 20
    oneline: bool = False


async def git_diff(
    repo_path: str,
    target: str | None = None,
) -> str:
    """Return the git diff for a repository.

    Args:
        repo_path: Path to the git repository root.
        target: Optional ref/path to diff against (e.g. ``HEAD~1``). When
            ``None``, returns changes against ``HEAD`` (staged + unstaged).

    Returns:
        The raw ``git diff`` output as a string.
    """
    ops = GitOperations(repo_path)
    args: list[str] = ["--no-color"]
    args.append(target if target is not None else "HEAD")
    return await ops._run_git("diff", *args, check=False)


async def git_log(
    repo_path: str,
    max_count: int = 20,
    oneline: bool = False,
) -> str:
    """Return the git log for a repository.

    Args:
        repo_path: Path to the git repository root.
        max_count: Maximum number of commits to return.
        oneline: When True, use ``--oneline`` formatting.

    Returns:
        The raw ``git log`` output as a string.
    """
    ops = GitOperations(repo_path)
    args: list[str] = [f"--max-count={max_count}"]
    if oneline:
        args.append("--oneline")
    return await ops._run_git("log", *args, check=False)


register(
    ToolSpec(
        name="git_diff",
        description=(
            "Show changes in a git repository (git diff). Read-only inspection "
            "of uncommitted or committed changes."
        ),
        input_schema=GitDiffInput,
        handler=git_diff,
        risk_level=RiskLevel.READ_ONLY,
        required_permissions=frozenset({Permission.FS_READ}),
        toolsets=frozenset({"readonly", "vcs"}),
    )
)
register(
    ToolSpec(
        name="git_log",
        description=(
            "Show the commit history of a git repository (git log). Read-only."
        ),
        input_schema=GitLogInput,
        handler=git_log,
        risk_level=RiskLevel.READ_ONLY,
        required_permissions=frozenset({Permission.FS_READ}),
        toolsets=frozenset({"readonly", "vcs"}),
    )
)
