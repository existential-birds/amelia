"""Git utilities for repository operations."""

from __future__ import annotations

import asyncio
import contextlib
import shutil
from pathlib import Path
from types import TracebackType

from loguru import logger


async def _run_git_cmd(
    repo_root: Path,
    *args: str,
    check: bool = True,
    timeout: float = 60.0,
) -> str:
    """Run a git command against a repo using create_subprocess_exec.

    Args:
        repo_root: Repository path to use as cwd.
        *args: Git command arguments.
        check: If True, raise ValueError on non-zero exit code.
        timeout: Maximum time in seconds to wait.

    Returns:
        Command stdout as stripped string.

    Raises:
        ValueError: If command fails and check=True.
    """
    process = await asyncio.create_subprocess_exec(
        "git",
        "-C",
        str(repo_root),
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
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
        cmd_str = f"git -C {repo_root} {' '.join(args)}"
        raise ValueError(f"Git command timed out after {timeout}s: {cmd_str}") from e

    if check and process.returncode != 0:
        stderr_text = stderr.decode().strip()
        cmd_str = f"git -C {repo_root} {' '.join(args)}"
        raise ValueError(f"{cmd_str} failed: {stderr_text}")

    return stdout.decode().strip()


class LocalWorktree:
    """Async context manager for isolated git worktrees.

    Creates a temporary worktree for a branch, yields the path,
    and cleans up on exit. Used by PR autofix to avoid touching
    the main checkout.
    """

    def __init__(self, repo_root: str | Path, branch: str, worktree_id: str) -> None:
        self._repo_root = Path(repo_root)
        self._branch = branch
        self._worktree_id = worktree_id
        self._worktree_path = self._repo_root.parent / ".amelia-worktrees" / worktree_id

    @property
    def path(self) -> Path:
        """The filesystem path where the worktree will be created."""
        return self._worktree_path

    async def __aenter__(self) -> str:
        """Create the worktree and return its path as a string.

        1. Ensures parent .amelia-worktrees/ directory exists
        2. Removes stale worktree if path already exists
        3. Fetches origin
        4. Creates detached worktree at origin/<branch>

        Returns:
            Worktree filesystem path as string.

        Raises:
            ValueError: If git worktree add fails.
        """
        # Ensure parent dir exists
        self._worktree_path.parent.mkdir(parents=True, exist_ok=True)

        # Remove stale worktree if path already exists
        if self._worktree_path.exists():
            logger.warning(
                "Removing stale worktree path",
                path=str(self._worktree_path),
            )
            with contextlib.suppress(ValueError):
                await _run_git_cmd(
                    self._repo_root,
                    "worktree",
                    "remove",
                    str(self._worktree_path),
                    "--force",
                    check=False,
                )
            # Fallback: rm -rf if git worktree remove didn't clean it
            if self._worktree_path.exists():
                shutil.rmtree(self._worktree_path, ignore_errors=True)

        # Prune stale worktree bookkeeping (e.g. leftover .git/worktrees entries
        # after the directory was removed above).
        await _run_git_cmd(
            self._repo_root, "worktree", "prune", check=False
        )

        # Fetch origin
        await _run_git_cmd(self._repo_root, "fetch", "origin")

        # Create detached worktree at origin/<branch>
        try:
            await _run_git_cmd(
                self._repo_root,
                "worktree",
                "add",
                str(self._worktree_path),
                f"origin/{self._branch}",
                "--detach",
            )
        except ValueError:
            # Retry once after aggressive cleanup — lock files or stale
            # bookkeeping can survive the prune above.
            logger.warning(
                "Worktree add failed, retrying after forced cleanup",
                path=str(self._worktree_path),
            )
            await _run_git_cmd(
                self._repo_root,
                "worktree",
                "remove",
                str(self._worktree_path),
                "--force",
                check=False,
            )
            shutil.rmtree(self._worktree_path, ignore_errors=True)
            await _run_git_cmd(self._repo_root, "worktree", "prune", check=False)
            await _run_git_cmd(
                self._repo_root,
                "worktree",
                "add",
                str(self._worktree_path),
                f"origin/{self._branch}",
                "--detach",
            )

        logger.info(
            "Created worktree",
            path=str(self._worktree_path),
            branch=self._branch,
        )
        return str(self._worktree_path)

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Remove the worktree. Never re-raises cleanup errors."""
        try:
            await _run_git_cmd(
                self._repo_root,
                "worktree",
                "remove",
                str(self._worktree_path),
                "--force",
            )
            logger.info("Removed worktree", path=str(self._worktree_path))
        except Exception as cleanup_exc:
            logger.warning(
                "Failed to remove worktree via git, falling back to rmtree",
                path=str(self._worktree_path),
                error=str(cleanup_exc),
            )
            shutil.rmtree(self._worktree_path, ignore_errors=True)
            # Also prune stale worktree entries
            with contextlib.suppress(Exception):
                await _run_git_cmd(
                    self._repo_root,
                    "worktree",
                    "prune",
                    check=False,
                )


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
        logger.opt(colors=False).info("Committed changes", sha=sha[:8], message=message)
        return sha

    async def safe_push(self, branch: str, *, skip_hooks: bool = False) -> str:
        """Push current branch to origin with safety guards.

        Refuses protected branches, detects divergence, never force-pushes.

        Args:
            branch: Branch name to push.
            skip_hooks: If True, pass --no-verify to skip pre-push hooks.
                Use for automated pipelines where the repo's pre-push hook
                (e.g. pre-commit running lint/tests) would block the push.

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
            logger.info(
                "Divergence check",
                branch=branch,
                local_sha=local_sha[:8],
                remote_sha=remote_sha[:8],
                merge_base=merge_base[:8],
                is_fast_forward=(merge_base == remote_sha),
            )
            if merge_base != remote_sha:
                raise ValueError(
                    f"Remote branch '{branch}' has diverged from local. "
                    f"merge-base={merge_base[:8]}, remote={remote_sha[:8]}. "
                    f"Aborting push (never rebase)."
                )
        else:
            logger.debug(
                "Push pre-check",
                branch=branch,
                local_sha=local_sha[:8],
                remote_sha=remote_sha[:8] if remote_sha else "none",
                status="in-sync" if remote_sha == local_sha else "new-branch",
            )

        logger.debug(
            "Pushing to remote",
            branch=branch,
            refspec=f"HEAD:refs/heads/{branch}",
            local_sha=local_sha[:8],
        )
        push_args = ["push", "origin", f"HEAD:refs/heads/{branch}"]
        if skip_hooks:
            push_args.insert(1, "--no-verify")
        await self._run_git(*push_args)
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
