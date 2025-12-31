"""Git worktree context detection for CLI client."""
import subprocess
from pathlib import Path


def get_worktree_context() -> tuple[str, str]:
    """Returns (worktree_path, worktree_name) for current directory.

    Detects the current git worktree root and derives a human-readable name
    from the current branch or directory name.

    Handles edge cases:
    - Detached HEAD: Uses short commit hash as name (e.g., "detached-abc1234")
    - Corrupted repo: Raises clear error
    - Submodules: Works correctly (has .git file pointing to parent)
    - Bare repository: Raises clear error

    Returns:
        Tuple of (absolute_worktree_path, worktree_name)

    Raises:
        ValueError: If not in a git repository or in a bare repository.
        RuntimeError: If git commands fail unexpectedly.

    Examples:
        >>> get_worktree_context()
        ('/home/user/myproject', 'main')

        >>> # In detached HEAD state
        >>> get_worktree_context()
        ('/home/user/myproject', 'detached-abc1234')
    """
    # Check if we're in a git repo at all
    result = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or result.stdout.strip() != "true":
        # Could be bare repo or not a repo at all
        bare_check = subprocess.run(
            ["git", "rev-parse", "--is-bare-repository"],
            capture_output=True,
            text=True,
        )
        if bare_check.returncode == 0 and bare_check.stdout.strip() == "true":
            raise ValueError("Cannot run workflows in a bare repository")
        raise ValueError("Not inside a git repository")

    # Get worktree root (works for main repo and worktrees)
    try:
        worktree_path = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Failed to determine worktree root: {e.stderr}") from e

    # Get branch name for display
    try:
        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except subprocess.CalledProcessError:
        # Fallback to directory name if branch detection fails
        return worktree_path, Path(worktree_path).name

    # Handle detached HEAD state
    if branch == "HEAD":
        try:
            short_hash = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
            branch = f"detached-{short_hash}"
        except subprocess.CalledProcessError:
            branch = "detached"

    # Use directory name if branch is empty
    return worktree_path, branch or Path(worktree_path).name
