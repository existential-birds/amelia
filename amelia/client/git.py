"""Git worktree context detection for CLI client."""
import subprocess
from pathlib import Path


def get_worktree_context() -> tuple[str, str]:
    """Returns (worktree_path, worktree_name) for current directory.

    Detects the current git worktree root and derives a human-readable name
    from the current branch or directory name. Worktree context is resolved in
    a single git invocation for the common (non-detached) case; detached HEAD
    requires a second targeted call to obtain the short commit sha.

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
    #
    # NOTE: --abbrev-ref is a sticky output-format mode in git rev-parse.
    # Appending --short HEAD after --abbrev-ref HEAD does NOT produce a short
    # sha; the sticky abbrev-ref mode causes git to emit the abbrev-ref value
    # ("HEAD") again instead.  The short sha for detached HEAD is therefore
    # fetched with a separate targeted call only when needed (see below).
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
        ],
        capture_output=True,
        text=True,
    )

    lines = result.stdout.splitlines()

    if not lines or lines[0].strip() != "true":
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

    # lines: [is_inside_work_tree, is_bare, toplevel, branch]
    # The branch line may legitimately be empty (unborn branch), but the
    # toplevel/branch lines must be present.
    if len(lines) < 4:
        raise RuntimeError(
            f"Failed to determine worktree root: unexpected git output {lines!r}"
        )

    worktree_path = lines[2].strip()
    branch = lines[3].strip()

    # Handle detached HEAD state: --abbrev-ref reports "HEAD", so name from sha.
    # Fetch the short sha with a separate call; combining --short with
    # --abbrev-ref in one invocation produces the wrong output due to sticky
    # output-format modes in git rev-parse (--abbrev-ref overrides --short).
    if branch == "HEAD":
        sha_result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
        )
        short_hash = sha_result.stdout.strip() if sha_result.returncode == 0 else ""
        branch = f"detached-{short_hash}" if short_hash else ""

    # Use directory name if branch is empty.
    return worktree_path, branch or Path(worktree_path).name
