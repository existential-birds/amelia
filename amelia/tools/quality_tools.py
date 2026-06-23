"""Quality-gate tools (``run_tests``, ``run_linter``) for agent use.

Both wrap a subprocess runner that invokes ``pytest`` and ``ruff check``
respectively, reporting exit code + output. A non-zero exit is reported as a
result, never raised — a failing test suite is information, not an exception.
"""

from __future__ import annotations

import asyncio
import shlex

from pydantic import BaseModel

from amelia.tools.registry import Permission, RiskLevel, ToolSpec, register


# Maximum captured output before truncation (256 KB).
_MAX_OUTPUT = 256_000


class RunTestsInput(BaseModel):
    """Input schema for the ``run_tests`` tool."""

    cwd: str
    args: str = ""
    timeout: int = 120


class RunLinterInput(BaseModel):
    """Input schema for the ``run_linter`` tool."""

    cwd: str
    args: str = ""
    timeout: int = 120


class QualityResult(BaseModel):
    """Result of a quality-gate command."""

    exit_code: int
    stdout: str
    stderr: str
    truncated: bool


async def _run_quality_cmd(
    cmd: list[str],
    cwd: str,
    timeout: int,
) -> QualityResult:
    """Run a quality command, capturing output without raising on failure."""
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
    except (OSError, FileNotFoundError) as e:
        return QualityResult(
            exit_code=127,
            stdout="",
            stderr=f"Failed to start {cmd[0]}: {e}",
            truncated=False,
        )

    try:
        stdout_b, stderr_b = await asyncio.wait_for(
            process.communicate(), timeout=timeout
        )
    except TimeoutError:
        process.kill()
        await process.wait()
        return QualityResult(
            exit_code=124,
            stdout="",
            stderr=f"Command timed out after {timeout}s",
            truncated=False,
        )

    stdout = stdout_b.decode(errors="replace")
    stderr = stderr_b.decode(errors="replace")
    truncated = len(stdout) + len(stderr) > _MAX_OUTPUT
    if truncated:
        stdout = stdout[: _MAX_OUTPUT // 2] + "\n... [stdout truncated]"
        stderr = stderr[: _MAX_OUTPUT // 2] + "\n... [stderr truncated]"

    return QualityResult(
        exit_code=process.returncode if process.returncode is not None else 1,
        stdout=stdout,
        stderr=stderr,
        truncated=truncated,
    )


async def run_tests(cwd: str, args: str = "", timeout: int = 120) -> QualityResult:
    """Run the test suite via ``pytest``.

    Args:
        cwd: Working directory to run pytest in.
        args: Extra arguments forwarded to pytest (e.g. ``"tests/unit -x"``).
        timeout: Maximum runtime in seconds.

    Returns:
        :class:`QualityResult` with exit code and captured output.
    """
    cmd = ["pytest", *shlex.split(args)]
    return await _run_quality_cmd(cmd, cwd, timeout)


async def run_linter(cwd: str, args: str = "", timeout: int = 120) -> QualityResult:
    """Run the linter via ``ruff check``.

    Args:
        cwd: Working directory to run ruff in.
        args: Extra arguments forwarded to ruff (e.g. ``"amelia --fix"``).
        timeout: Maximum runtime in seconds.

    Returns:
        :class:`QualityResult` with exit code and captured output.
    """
    cmd = ["ruff", "check", *shlex.split(args)]
    return await _run_quality_cmd(cmd, cwd, timeout)


register(
    ToolSpec(
        name="run_tests",
        description=(
            "Run the project test suite via pytest and return the exit code + "
            "output. A failing suite returns a non-zero exit code, not an error."
        ),
        input_schema=RunTestsInput,
        handler=run_tests,
        risk_level=RiskLevel.EXECUTE,
        required_permissions=frozenset({Permission.SHELL_EXEC}),
        toolsets=frozenset({"quality"}),
    )
)
register(
    ToolSpec(
        name="run_linter",
        description=(
            "Run the project linter via ruff check and return the exit code + "
            "output. Lint failures return a non-zero exit code, not an error."
        ),
        input_schema=RunLinterInput,
        handler=run_linter,
        risk_level=RiskLevel.EXECUTE,
        required_permissions=frozenset({Permission.SHELL_EXEC}),
        toolsets=frozenset({"quality"}),
    )
)
