"""Git worktree lifecycle management inside sandbox containers.

All git commands run inside the container via the SandboxProvider interface.
The worktree manager does not call docker directly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger


if TYPE_CHECKING:
    from amelia.sandbox.provider import SandboxProvider

# Container filesystem layout
REPO_PATH = "/workspace/repo"
WORKTREES_PATH = "/workspace/worktrees"


class WorktreeManager:
    """Manages git worktrees inside a sandbox container.

    Uses a bare clone at /workspace/repo as the shared base. Each workflow
    gets a worktree under /workspace/worktrees/{workflow_id}.

    Args:
        provider: Sandbox provider for executing commands.
        repo_url: Git repository URL to clone.
    """

    def __init__(self, provider: SandboxProvider, repo_url: str) -> None:
        self._provider = provider
        self._repo_url = repo_url
        self._repo_initialized = False

    async def _run(
        self,
        command: list[str],
        cwd: str | None = None,
        env: dict[str, str] | None = None,
    ) -> list[str]:
        """Execute command and collect all output lines.

        Args:
            command: Command and arguments.
            cwd: Working directory inside the sandbox.
            env: Additional environment variables.

        Returns:
            List of stdout lines.
        """
        lines: list[str] = []
        stream = self._provider.exec_stream(command, cwd=cwd, env=env)
        async for line in stream:
            lines.append(line)
        return lines

    async def setup_repo(self) -> None:
        """Ensure the bare clone exists and is up to date.

        First call checks whether a git repo already exists at REPO_PATH
        (e.g. cloned by the sandbox provider). If so, it fetches latest
        instead of cloning. Subsequent calls just fetch.
        """
        if self._repo_initialized:
            logger.debug("Fetching latest from origin")
            if hasattr(self._provider, "git_fetch"):
                await self._provider.git_fetch(REPO_PATH)
            else:
                await self._run(
                    ["git", "-C", REPO_PATH, "fetch", "origin"],
                )
            return

        # Check if a repo already exists (e.g. provider pre-cloned it)
        try:
            result = await self._run(
                ["git", "-C", REPO_PATH, "rev-parse", "--git-dir"],
            )
            git_dir = result[0].strip() if result else ""
            if git_dir in (".", ".git"):
                logger.info(
                    "Detected existing repo, fetching",
                    path=REPO_PATH,
                    git_dir=git_dir,
                )
                if hasattr(self._provider, "git_fetch"):
                    await self._provider.git_fetch(REPO_PATH)
                else:
                    await self._run(
                        ["git", "-C", REPO_PATH, "fetch", "origin"],
                    )
                self._repo_initialized = True
                return
        except RuntimeError as exc:
            if "not a git repository" not in str(exc).lower():
                raise
            # rev-parse confirmed no repo at REPO_PATH, proceed with clone

        logger.info("Cloning bare repo", url=self._repo_url)
        await self._run(
            ["git", "clone", "--bare", self._repo_url, REPO_PATH],
        )
        self._repo_initialized = True

    async def create_worktree(
        self, workflow_id: str, base_branch: str = "main"
    ) -> str:
        """Create a git worktree for a workflow.

        Args:
            workflow_id: Identifier for the workflow (used as branch and dir name).
            base_branch: Remote branch to base the worktree on.

        Returns:
            Absolute path to the worktree inside the container.
        """
        worktree_path = f"{WORKTREES_PATH}/{workflow_id}"
        await self._run([
            "git", "-C", REPO_PATH, "worktree", "add",
            worktree_path, "-b", workflow_id, f"origin/{base_branch}",
        ])
        logger.info("Created worktree", path=worktree_path, branch=workflow_id)
        return worktree_path

    async def remove_worktree(self, workflow_id: str) -> None:
        """Remove a worktree after workflow completion.

        Args:
            workflow_id: Identifier for the workflow.
        """
        worktree_path = f"{WORKTREES_PATH}/{workflow_id}"
        await self._run([
            "git", "-C", REPO_PATH, "worktree", "remove", worktree_path,
        ])
        logger.info("Removed worktree", path=worktree_path)

    async def push(self, workflow_id: str) -> None:
        """Push worktree branch to remote.

        Args:
            workflow_id: Branch name to push.
        """
        worktree_path = f"{WORKTREES_PATH}/{workflow_id}"
        if hasattr(self._provider, "git_push"):
            await self._provider.git_push(worktree_path)
            logger.info("Pushed branch via SDK", branch=workflow_id)
        else:
            await self._run(
                ["git", "push", "origin", workflow_id],
                cwd=worktree_path,
            )
            logger.info("Pushed branch", branch=workflow_id)
