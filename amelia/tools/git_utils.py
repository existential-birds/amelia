# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Git utilities for snapshot and revert operations.

Provides rollback capability for agentic execution.
"""

import asyncio
import shlex
from pathlib import Path

from pydantic import BaseModel


class GitSnapshot(BaseModel):
    """Captures git state at a point in time for potential rollback."""

    head_commit: str
    dirty_files: tuple[str, ...]
    stash_ref: str | None = None


async def _run_git_command(
    command: str,
    repo_path: Path | None = None,
    check: bool = True,
    timeout: float = 60.0,
) -> str:
    """Run a git command and return stdout.

    Args:
        command: Git command to run (e.g., "git rev-parse HEAD")
        repo_path: Repository path (defaults to current directory)
        check: If True, raise RuntimeError on non-zero exit code
        timeout: Maximum time in seconds to wait for command (default: 60.0)

    Returns:
        Command stdout as string

    Raises:
        RuntimeError: If command fails and check=True, or if timeout occurs
    """
    cwd = repo_path or Path.cwd()

    process = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
    )

    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=timeout,
        )
    except TimeoutError as e:
        # Kill the process if it's still running
        try:
            process.kill()
            await process.wait()
        except ProcessLookupError:
            pass  # Process already terminated
        raise RuntimeError(
            f"Git command timed out after {timeout} seconds: {command}"
        ) from e

    if check and process.returncode != 0:
        stderr_text = stderr.decode().strip()
        raise RuntimeError(
            f"Git command failed with exit code {process.returncode}: {stderr_text}"
        )

    return stdout.decode().strip()


async def take_git_snapshot(repo_path: Path | None = None) -> GitSnapshot:
    """Capture git state before batch execution.

    Captures:
    - Current HEAD commit hash
    - List of dirty/modified files
    - Creates a stash if there are uncommitted changes (not implemented in v1)

    Args:
        repo_path: Repository path (defaults to current directory)

    Returns:
        GitSnapshot containing HEAD commit and dirty files

    Raises:
        RuntimeError: If not a git repository or git command fails
    """
    # Get HEAD commit
    head_commit = await _run_git_command("git rev-parse HEAD", repo_path)

    # Get dirty files (both modified and untracked)
    # Use -z for null-separated output to handle filenames with spaces/special chars
    status_output = await _run_git_command("git status --porcelain -z", repo_path)

    # Parse null-separated output - each entry is: "XY filename\0"
    # where XY is status (M=modified, ??=untracked, etc.)
    dirty_files = []
    if status_output:
        for entry in status_output.split("\0"):
            if entry:
                # Extract filename (skip 3 chars: 2 for status + 1 for space)
                filename = entry[3:] if len(entry) > 3 else entry
                dirty_files.append(filename)

    return GitSnapshot(
        head_commit=head_commit,
        dirty_files=tuple(dirty_files),
        stash_ref=None,  # Not implementing stash in v1
    )


async def get_batch_changed_files(
    snapshot: GitSnapshot,
    repo_path: Path | None = None,
) -> set[str]:
    """Get files changed since snapshot.

    Returns set of file paths that have been modified, added, or deleted
    since the snapshot was taken.

    Args:
        snapshot: GitSnapshot to compare against
        repo_path: Repository path (defaults to current directory)

    Returns:
        Set of file paths changed since snapshot
    """
    # Get all files that differ from the snapshot HEAD
    # This includes modified, added, and deleted files
    diff_output = await _run_git_command(
        f"git diff --name-only {shlex.quote(snapshot.head_commit)}",
        repo_path,
        check=False,  # Don't fail if no changes
    )

    changed_files = set()
    if diff_output:
        for line in diff_output.split("\n"):
            if line.strip():
                changed_files.add(line.strip())

    # Also check for untracked files that weren't dirty before
    status_output = await _run_git_command("git status --porcelain", repo_path)
    if status_output:
        for line in status_output.split("\n"):
            if line.startswith("??"):
                filename = line[3:] if len(line) > 3 else ""
                # Only include if it wasn't dirty before the batch
                if filename and filename not in snapshot.dirty_files:
                    changed_files.add(filename)

    return changed_files


async def revert_to_git_snapshot(
    snapshot: GitSnapshot,
    repo_path: Path | None = None,
) -> None:
    """Revert to pre-batch state. Only reverts batch-changed files.

    IMPORTANT: This only reverts files changed during the batch.
    User's manual changes (if any) are preserved unless they overlap.

    Args:
        snapshot: GitSnapshot to revert to
        repo_path: Repository path (defaults to current directory)

    Raises:
        RuntimeError: If git commands fail
    """
    # Get files changed since snapshot
    batch_changed = await get_batch_changed_files(snapshot, repo_path)

    # Remove files that were dirty before the batch (preserve user changes)
    files_to_revert = batch_changed - set(snapshot.dirty_files)

    if not files_to_revert:
        # Nothing to revert
        return

    # Revert each file individually
    # We use git checkout for tracked files and git clean for untracked
    cwd = repo_path or Path.cwd()

    for file in files_to_revert:
        file_path = cwd / file

        # Check if file existed in snapshot commit
        try:
            await _run_git_command(
                f"git cat-file -e {shlex.quote(snapshot.head_commit)}:{shlex.quote(file)}",
                repo_path,
                check=True,
            )
            # File existed - restore it
            await _run_git_command(
                f"git checkout {shlex.quote(snapshot.head_commit)} -- {shlex.quote(file)}",
                repo_path,
            )
        except RuntimeError:
            # File didn't exist in snapshot - it's a new file, remove it
            if file_path.exists():
                file_path.unlink()
