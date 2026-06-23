"""Integration test: ApiDriver with allowed_tools vetoes disallowed tools.

Requires a real LLM API key (``OPENROUTER_API_KEY``) because it drives the
actual agentic loop. Skipped in CI without a key.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest


pytestmark = pytest.mark.integration


@pytest.mark.skipif(
    not os.environ.get("OPENROUTER_API_KEY"),
    reason="Requires OPENROUTER_API_KEY for real agentic execution",
)
async def test_readonly_agent_cannot_write_file(tmp_path: Path) -> None:
    """An ApiDriver run with a read-only allow-list must veto write_file.

    The observable consequence: the file does NOT appear on disk, even when the
    model is explicitly instructed to create it.
    """
    from amelia.drivers.api import ApiDriver

    driver = ApiDriver(
        model=os.environ.get("AMELIA_TEST_MODEL", "anthropic/claude-3.5-sonnet"),
        cwd=str(tmp_path),
    )

    write_target = tmp_path / "should_not_exist.txt"
    prompt = f"Create a file at {write_target} with the content 'hello'."

    async for _ in driver.execute_agentic(
        prompt=prompt,
        cwd=str(tmp_path),
        allowed_tools=["read_file", "glob", "grep"],
        max_continuations=0,
    ):
        pass

    assert not write_target.exists(), (
        f"write_file was not vetoed — file appeared at {write_target}"
    )
