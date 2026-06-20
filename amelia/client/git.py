"""Git worktree context detection for CLI client."""
import subprocess
from pathlib import Path


def get_worktree_context() -> tuple[str, str]:
    """Returns (worktree_path, worktree_name) for current directory.

    Detects the current git worktree root and derives a human-readable name
    from the current branch or directory name. All worktree context is
    resolved in a SINGLE git invocation to avoid serial subprocess overhead.

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
    # Single git invocation resolves all worktree context. Each flag emits one
    # output line, in order:
    #   1. --is-inside-work-tree   -> "true" / "false"
    #   2. --is-bare-repository    -> "true" / "false"
    #   3. --show-toplevel         -> absolute worktree root path
    #   4. --abbrev-ref HEAD       -> branch name, or "HEAD" if detached
    #   5. --short HEAD            -> short commit sha (used for detached HEAD)
    #
    # In a bare repo or non-repo, --show-toplevel makes rev-parse exit non-zero;
    # we re-probe --is-bare-repository in that path to distinguish the two cases.
    result = subprocess.run(
        [
            "git",
            "rev-parse",
            "--is-inside-work-tree",
            "--is-bare-repository",
            "--show-toplevel",
            "--abbrev-ref",
            "HEAD",
            "--short",
            "HEAD",
        ],
        capture_output=True,
        text=True,
    )

    lines = result.stdout.splitlines()

    if result.returncode != 0 or not lines or lines[0].strip() != "true":
        # rev-parse failed (or reported we're not in a work tree). Distinguish a
        # bare repository from "not a repo at all" with a single follow-up probe.
        bare_check = subprocess.run(
            ["git", "rev-parse", "--is-bare-repository"],
            capture_output=True,
            text=True,
        )
        if bare_check.returncode == 0 and bare_check.stdout.strip() == "true":
            raise ValueError("Cannot run workflows in a bare repository")
        raise ValueError("Not inside a git repository")

    # lines: [is_inside_work_tree, is_bare, toplevel, branch, short_sha]
    # The branch line may legitimately be empty (unborn branch), and the short
    # sha line may be empty too — but the toplevel/branch lines must be present.
    if len(lines) < 4:
        raise RuntimeError(
            f"Failed to determine worktree root: unexpected git output {lines!r}"
        )

    worktree_path = lines[2].strip()
    branch = lines[3].strip()
    short_hash = lines[4].strip() if len(lines) > 4 else ""

    # Handle detached HEAD state: --abbrev-ref reports "HEAD", so name from sha.
    if branch == "HEAD":
        branch = f"detached-{short_hash}" if short_hash else "detached"

    # Use directory name if branch is empty.
    return worktree_path, branch or Path(worktree_path).name
