"""Tests for the knowledge_search tool registration via the registry factory.

Verifies the factory resolves from a ToolContext and produces a working handler,
and that graceful degradation kicks in when the knowledge deps are absent.
"""

from __future__ import annotations

import subprocess
import sys
from unittest.mock import AsyncMock

from amelia.tools.registry import ToolContext, registry
from amelia.tools.registry.registry import discover_builtin_tools


async def test_knowledge_search_factory_resolves_with_context() -> None:
    """With embedding_client + knowledge_repo, the factory produces a handler."""
    discover_builtin_tools()
    mock_embed = AsyncMock()
    mock_embed.embed = AsyncMock(return_value=[0.1] * 1536)
    mock_repo = AsyncMock()
    mock_repo.search_chunks = AsyncMock(return_value=[])

    ctx = ToolContext(
        cwd="/tmp",
        embedding_client=mock_embed,
        knowledge_repo=mock_repo,
    )
    spec = registry.get("knowledge_search")
    assert spec is not None
    assert spec.factory is not None

    handler = spec.factory(ctx)
    assert handler is not None
    results = await handler(query="test", top_k=3)
    assert results == []
    mock_embed.embed.assert_called_once()
    mock_repo.search_chunks.assert_called_once()


def test_knowledge_search_factory_returns_none_without_repo() -> None:
    """Without knowledge deps the factory returns None (omit signal)."""
    discover_builtin_tools()
    spec = registry.get("knowledge_search")
    assert spec is not None
    assert spec.factory is not None

    ctx = ToolContext(cwd="/tmp")
    assert spec.factory(ctx) is None


def test_knowledge_search_registered_in_knowledge_toolset() -> None:
    discover_builtin_tools()
    spec = registry.get("knowledge_search")
    assert spec is not None
    assert "knowledge" in spec.toolsets
    assert spec.handler is None  # factory-only


def test_knowledge_tool_registers_on_production_startup_import() -> None:
    """Importing the server entrypoint first must not break knowledge tool discovery.

    Regression for a circular import: importing ``amelia.server.main`` (the real
    uvicorn entrypoint) pulls in ``amelia.knowledge.repository`` -> database ->
    migrator. If the migrator imports the agents layer at module scope, that
    chains agents -> tools -> discovery -> ``amelia.tools.knowledge`` ->
    ``amelia.knowledge.repository`` while the latter is still partially
    initialized, so ``knowledge_search`` silently fails to register.

    In-process assertions miss this because conftest fully imports the knowledge
    package before these tests run, hiding the order-dependent cycle. We drive a
    fresh interpreter with the production import order to observe the real
    outcome: the tool is registered.
    """
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import amelia.server.main\n"
                "from amelia.tools.registry import registry\n"
                "assert registry.get('knowledge_search') is not None, "
                "'knowledge_search failed to register (circular import on startup)'\n"
                "print('OK')\n"
            ),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"fresh-import startup failed:\nstdout={result.stdout}\nstderr={result.stderr}"
    )
    assert "Failed to import self-registering tool module" not in result.stderr, (
        f"tool discovery logged an import failure:\n{result.stderr}"
    )
