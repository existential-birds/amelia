"""Tests for the git_diff and git_log agent tools.

These tools wrap ``GitOperations._run_git`` so agents can inspect repository
state without shell access. Both are read-only VCS operations.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from amelia.tools.registry import RiskLevel, registry
from amelia.tools.registry.registry import discover_builtin_tools


def _init_repo(repo: Path) -> None:
    """Create a trivial git repo with one committed file."""
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True, capture_output=True)
    (repo / "f.py").write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=repo, check=True, capture_output=True)


async def test_git_diff_returns_diff_text(tmp_path: Path) -> None:
    """git_diff returns the unstaged diff for the working tree."""
    discover_builtin_tools()
    _init_repo(tmp_path)
    (tmp_path / "f.py").write_text("x = 2\n", encoding="utf-8")

    spec = registry.get("git_diff")
    assert spec is not None
    result = await spec.handler(repo_path=str(tmp_path))
    assert isinstance(result, str)
    assert "x = 2" in result or "+x = 2" in result


async def test_git_log_returns_log_text(tmp_path: Path) -> None:
    """git_log returns the commit log."""
    discover_builtin_tools()
    _init_repo(tmp_path)

    spec = registry.get("git_log")
    assert spec is not None
    result = await spec.handler(repo_path=str(tmp_path), max_count=5)
    assert "initial" in result


def test_git_tools_registered_with_correct_metadata() -> None:
    """Both git tools are registered read-only in the vcs toolset."""
    discover_builtin_tools()
    for name in ("git_diff", "git_log"):
        spec = registry.get(name)
        assert spec is not None, f"{name} not registered"
        assert spec.risk_level == RiskLevel.READ_ONLY
        assert "vcs" in spec.toolsets
        assert spec.handler is not None
