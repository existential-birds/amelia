"""Tests for ApiDriver allowed_tools parameter and the _resolve_allowed helper.

These cover the #621 wiring that replaced the previous NotImplementedError:
``allowed_tools`` is now resolved into custom StructuredTools (for tools with
real handlers / factories) plus a policy allow-set enforced by
``ToolPolicyMiddleware``.
"""

from __future__ import annotations

import pytest

from amelia.drivers.api.deepagents import ApiDriver
from amelia.tools.registry import ToolContext
from amelia.tools.registry.registry import discover_builtin_tools


async def test_resolve_allowed_returns_allow_set_for_library_stubs() -> None:
    """Library stubs (no handler) are allowed by name but not rendered as tools."""
    discover_builtin_tools()
    driver = ApiDriver(model="test/model", cwd="/tmp")
    custom_tools, allow_set = driver._resolve_allowed(
        allowed_tools=["read_file", "glob", "grep"],
        ctx=None,
    )
    assert "read_file" in allow_set
    assert "glob" in allow_set
    assert "grep" in allow_set
    # Stubs have no handler -> not rendered as custom StructuredTools.
    assert custom_tools == []


async def test_resolve_allowed_renders_handler_tools_as_structured_tools() -> None:
    """Tools with a real handler (e.g. git_diff) become LangChain tools."""
    discover_builtin_tools()
    driver = ApiDriver(model="test/model", cwd="/tmp")
    custom_tools, allow_set = driver._resolve_allowed(
        allowed_tools=["read_file", "git_diff"],
        ctx=None,
    )
    assert "git_diff" in allow_set
    assert "read_file" in allow_set
    names = [getattr(t, "name", "") for t in custom_tools]
    assert "git_diff" in names


async def test_resolve_allowed_skips_unknown_tools() -> None:
    """Unknown tool names are skipped (logged) without raising."""
    discover_builtin_tools()
    driver = ApiDriver(model="test/model", cwd="/tmp")
    custom_tools, allow_set = driver._resolve_allowed(
        allowed_tools=["read_file", "definitely_not_a_tool"],
        ctx=None,
    )
    assert "read_file" in allow_set
    assert "definitely_not_a_tool" not in allow_set
    assert custom_tools == []


async def test_execute_agentic_no_longer_raises_on_allowed_tools() -> None:
    """allowed_tools must not raise NotImplementedError when set.

    Drives the early part of execute_agentic to confirm the NotImplementedError
    block is gone. We don't run the full agent (no API key); instead we assert
    that the previous failure mode (NotImplementedError raised synchronously
    before any network call) no longer fires.
    """
    discover_builtin_tools()
    driver = ApiDriver(model="test/model", cwd="/tmp")

    # The old code raised NotImplementedError immediately when allowed_tools
    # was set. With API key absent, the driver now proceeds to build the chat
    # model (which raises a config/connection error), proving the gate is gone.
    with pytest.raises(Exception) as exc_info:  # noqa: PT011
        async for _ in driver.execute_agentic(
            prompt="test",
            cwd="/tmp",
            allowed_tools=["read_file"],
            max_continuations=0,
        ):
            pass
    assert not isinstance(exc_info.value, NotImplementedError)


def _make_factory_spec() -> None:
    """Ensure knowledge_search factory exists for the factory-resolution test."""
    discover_builtin_tools()


async def test_resolve_allowed_calls_factory_when_ctx_provided() -> None:
    """A factory tool is rendered when its runtime context deps are present."""
    _make_factory_spec()
    from unittest.mock import AsyncMock

    mock_embed = AsyncMock()
    mock_embed.embed = AsyncMock(return_value=[0.1] * 1536)
    mock_repo = AsyncMock()
    mock_repo.search_chunks = AsyncMock(return_value=[])

    ctx = ToolContext(
        cwd="/tmp",
        embedding_client=mock_embed,
        knowledge_repo=mock_repo,
    )
    driver = ApiDriver(model="test/model", cwd="/tmp")
    custom_tools, allow_set = driver._resolve_allowed(
        allowed_tools=["knowledge_search"],
        ctx=ctx,
    )
    assert "knowledge_search" in allow_set
    names = [getattr(t, "name", "") for t in custom_tools]
    assert "knowledge_search" in names


async def test_resolve_allowed_skips_factory_when_ctx_missing() -> None:
    """A factory tool is omitted entirely when ctx is None (deps unavailable).

    It is neither rendered nor added to the allow set: the policy middleware
    must refuse it because no handler is bound, so the model cannot invoke it.
    """
    _make_factory_spec()
    driver = ApiDriver(model="test/model", cwd="/tmp")
    custom_tools, allow_set = driver._resolve_allowed(
        allowed_tools=["knowledge_search"],
        ctx=None,
    )
    assert "knowledge_search" not in allow_set
    assert custom_tools == []
