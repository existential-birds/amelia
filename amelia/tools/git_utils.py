"""Git utilities for repository operations."""

import asyncio
from pathlib import Path

from loguru import logger


async def get_current_commit(cwd: str | None = None) -> str | None:
    """Get the current HEAD commit SHA.

    Args:
        cwd: Working directory for git command.

    Returns:
        The current commit SHA, or None if not in a git repo.
    """
    try:
        repo_path = Path(cwd) if cwd else Path.cwd()
        proc = await asyncio.create_subprocess_exec(
            "git",
            "rev-parse",
            "HEAD",
            cwd=repo_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=60.0)
        if proc.returncode != 0:
            return None
        result = stdout.decode().strip()
        return result if result else None
    except TimeoutError:
        try:
            proc.kill()
            await proc.wait()
        except ProcessLookupError:
            pass
        logger.warning("Failed to get current commit", cwd=cwd)
        return None
    except (RuntimeError, OSError):
        logger.warning("Failed to get current commit", cwd=cwd)
        return None


PROTECTED_BRANCHES: frozenset[str] = frozenset({"main", "master", "develop", "release"})


class GitOperations:
    """Async git operations with safety guards for PR auto-fix.

    Uses create_subprocess_exec (not shell) for safety.
    """

    def __init__(self, repo_path: str | Path) -> None:
        self._repo_path = Path(repo_path)

    async def _run_git(
        self,
        *args: str,
        check: bool = True,
        timeout: float = 60.0,
    ) -> str:
        """Run a git command using create_subprocess_exec.

        Args:
            *args: Git command arguments (e.g., "add", "-A").
            check: If True, raise ValueError on non-zero exit code.
            timeout: Maximum time in seconds to wait for command.

        Returns:
            Command stdout as stripped string.

        Raises:
            ValueError: If command fails and check=True, or if timeout occurs.
        """
        process = await asyncio.create_subprocess_exec(
            "git",
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self._repo_path,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout,
            )
        except TimeoutError as e:
            try:
                process.kill()
                await process.wait()
            except ProcessLookupError:
                pass
            cmd_str = f"git {' '.join(args)}"
            raise ValueError(f"Git command timed out after {timeout}s: {cmd_str}") from e

        if check and process.returncode != 0:
            stderr_text = stderr.decode().strip()
            cmd_str = f"git {' '.join(args)}"
            raise ValueError(f"{cmd_str} failed: {stderr_text}")

        return stdout.decode().strip()

    async def has_changes(self) -> bool:
        """Check if there are uncommitted changes in the repository.

        Returns:
            True if there are staged or unstaged changes, False otherwise.
        """
        porcelain = await self._run_git(
            "status",
            "--porcelain",
            "--",
            ".",
            ":!.claude/",
        )
        return bool(porcelain.strip())

    async def stage_and_commit(self, message: str) -> str:
        """Stage all changes and commit with the given message.

        Args:
            message: Commit message.

        Returns:
            The commit SHA.

        Raises:
            ValueError: If the commit fails (e.g., nothing to commit).
        """
        await self._run_git("add", "-A", "--", ".", ":!.claude/")
        await self._run_git("commit", "-m", message)
        sha = await self._run_git("rev-parse", "HEAD")
        logger.info("Committed changes", sha=sha[:8], message=message)
        return sha

    async def safe_push(self, branch: str) -> str:
        """Push current branch to origin with safety guards.

        Refuses protected branches, detects divergence, never force-pushes.

        Args:
            branch: Branch name to push.

        Returns:
            The local SHA that was pushed.

        Raises:
            ValueError: If branch is protected or remote has diverged.
        """
        if branch in PROTECTED_BRANCHES:
            raise ValueError(f"Refusing to push to protected branch: {branch}")

        # Fetch remote state (don't fail if branch doesn't exist)
        await self._run_git("fetch", "origin", branch, check=False)

        local_sha = await self._run_git("rev-parse", "HEAD")

        # Check if remote branch exists
        remote_sha: str | None = None
        try:
            remote_sha = await self._run_git("rev-parse", f"origin/{branch}")
        except ValueError:
            remote_sha = None  # New branch, no remote tracking

        # Divergence check
        if remote_sha is not None and remote_sha != local_sha:
            merge_base = await self._run_git("merge-base", local_sha, remote_sha)
            if merge_base != remote_sha:
                raise ValueError(
                    f"Remote branch '{branch}' has diverged from local. "
                    f"merge-base={merge_base[:8]}, remote={remote_sha[:8]}. "
                    f"Aborting push (never rebase)."
                )

        await self._run_git("push", "origin", f"HEAD:refs/heads/{branch}")
        logger.info("Pushed to remote", branch=branch, sha=local_sha[:8])
        return local_sha

    async def fetch_origin(self) -> None:
        """Fetch from origin remote.

        Raises:
            ValueError: If fetch command fails.
        """
        await self._run_git("fetch", "origin")

    async def checkout_and_reset(self, branch: str) -> None:
        """Checkout branch and hard reset to remote HEAD.

        Args:
            branch: Branch name to checkout and reset.

        Raises:
            ValueError: If checkout or reset commands fail.
        """
        await self._run_git("checkout", branch)
        await self._run_git("reset", "--hard", f"origin/{branch}")
