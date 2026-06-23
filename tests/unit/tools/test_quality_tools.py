"""Tests for the run_tests and run_linter agent tools.

Both wrap a quality-command runner (pytest / ruff) and report exit code +
output without raising on non-zero exit (a failing test suite is a result,
not an error).
"""

from __future__ import annotations

from pathlib import Path

from amelia.tools.registry import RiskLevel, registry
from amelia.tools.registry.registry import discover_builtin_tools


async def test_run_tests_executes_pytest(tmp_path: Path) -> None:
    """run_tests runs pytest and reports a passing exit code."""
    discover_builtin_tools()
    spec = registry.get("run_tests")
    assert spec is not None
    (tmp_path / "test_pass.py").write_text(
        "def test_ok():\n    assert True\n", encoding="utf-8"
    )
    result = await spec.handler(cwd=str(tmp_path), args="test_pass.py")
    assert result.exit_code == 0
    assert "passed" in result.stdout.lower() or "1 passed" in result.stdout.lower()


async def test_run_tests_reports_failure_without_raising(tmp_path: Path) -> None:
    """A failing test yields a non-zero exit code, not an exception."""
    discover_builtin_tools()
    spec = registry.get("run_tests")
    assert spec is not None
    (tmp_path / "test_fail.py").write_text(
        "def test_bad():\n    assert False\n", encoding="utf-8"
    )
    result = await spec.handler(cwd=str(tmp_path), args="test_fail.py")
    assert result.exit_code != 0


async def test_run_linter_executes_ruff(tmp_path: Path) -> None:
    """run_linter runs ruff check and reports a clean exit code."""
    discover_builtin_tools()
    spec = registry.get("run_linter")
    assert spec is not None
    (tmp_path / "clean.py").write_text("x = 1\n", encoding="utf-8")
    result = await spec.handler(cwd=str(tmp_path), args="clean.py")
    assert result.exit_code == 0


def test_quality_tools_metadata() -> None:
    """Both quality tools are registered EXECUTE in the quality toolset."""
    discover_builtin_tools()
    for name in ("run_tests", "run_linter"):
        spec = registry.get(name)
        assert spec is not None, f"{name} not registered"
        assert spec.risk_level == RiskLevel.EXECUTE
        assert "quality" in spec.toolsets
        assert spec.handler is not None
