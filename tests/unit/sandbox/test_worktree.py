"""Tests for git worktree management inside sandbox containers."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import MagicMock

import pytest

from amelia.sandbox.worktree import WorktreeManager


class _AsyncIteratorMock:
    """Mock that records calls and returns an empty async iterator.

    Stores call args in the same format as AsyncMock.call_args_list
    so that ``calls[i][0][0]`` yields the first positional argument.
    """

    def __init__(self) -> None:
        self.call_args_list: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def __call__(self, command: list[str], **kwargs: object) -> AsyncIterator[str]:
        self.call_args_list.append(((command,), dict(kwargs)))
        return self._empty_iter()

    async def _empty_iter(self) -> AsyncIterator[str]:
        if False:
            yield  # pragma: no cover — makes this an async generator


class TestWorktreeManager:
    """Tests for WorktreeManager lifecycle operations."""

    @pytest.fixture
    def mock_provider(self) -> MagicMock:
        """Mock SandboxProvider that records exec_stream calls."""
        provider = MagicMock()
        provider.exec_stream = _AsyncIteratorMock()
        return provider

    @pytest.fixture
    def manager(self, mock_provider: MagicMock) -> WorktreeManager:
        return WorktreeManager(
            provider=mock_provider,
            repo_url="https://github.com/org/repo.git",
        )

    async def test_setup_repo_clones_bare_on_first_use(self, manager: WorktreeManager, mock_provider: MagicMock) -> None:
        await manager.setup_repo()

        calls = mock_provider.exec_stream.call_args_list
        # First call should be git clone --bare
        first_cmd = calls[0][0][0]
        assert "clone" in first_cmd
        assert "--bare" in first_cmd
        assert "https://github.com/org/repo.git" in first_cmd

    async def test_setup_repo_fetches_on_subsequent_use(self, manager: WorktreeManager, mock_provider: MagicMock) -> None:
        manager._repo_initialized = True
        await manager.setup_repo()

        calls = mock_provider.exec_stream.call_args_list
        first_cmd = calls[0][0][0]
        assert "fetch" in first_cmd

    async def test_create_worktree_returns_path(self, manager: WorktreeManager, mock_provider: MagicMock) -> None:
        manager._repo_initialized = True
        path = await manager.create_worktree("issue-123", "main")

        assert path == "/workspace/worktrees/issue-123"
        calls = mock_provider.exec_stream.call_args_list
        cmd = calls[-1][0][0]
        assert "worktree" in cmd
        assert "add" in cmd

    async def test_remove_worktree(self, manager: WorktreeManager, mock_provider: MagicMock) -> None:
        await manager.remove_worktree("issue-123")

        calls = mock_provider.exec_stream.call_args_list
        cmd = calls[0][0][0]
        assert "worktree" in cmd
        assert "remove" in cmd

    async def test_push_worktree(self, manager: WorktreeManager, mock_provider: MagicMock) -> None:
        await manager.push("issue-123")

        calls = mock_provider.exec_stream.call_args_list
        cmd = calls[0][0][0]
        assert "push" in cmd
        assert "origin" in cmd
        assert "issue-123" in cmd
