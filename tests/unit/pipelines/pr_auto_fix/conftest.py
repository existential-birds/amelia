"""Shared fixtures and factories for PR auto-fix pipeline tests."""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from amelia.agents.schemas.classifier import CommentCategory, CommentClassification
from amelia.core.types import (
    AgentConfig,
    DriverType,
    PRAutoFixConfig,
    Profile,
    PRReviewComment,
    PRSummary,
)
from amelia.pipelines.pr_auto_fix.orchestrator import PRAutoFixOrchestrator
from amelia.pipelines.pr_auto_fix.state import PRAutoFixState
from amelia.server.database import MetricsRepository, WorkflowRepository
from amelia.server.events.bus import EventBus
from amelia.server.models.events import WorkflowEvent
from amelia.services.github_pr import GitHubPRService


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------


def make_comment(
    *,
    id: int = 1,
    body: str = "Fix this bug",
    author: str = "reviewer1",
    path: str | None = "src/app.py",
    line: int | None = 42,
    original_line: int | None = None,
    start_line: int | None = None,
    original_start_line: int | None = None,
    side: str | None = "RIGHT",
    subject_type: str | None = "line",
    diff_hunk: str | None = "@@ -1,3 +1,4 @@\n+new line",
    thread_id: str | None = None,
    in_reply_to_id: int | None = None,
) -> PRReviewComment:
    return PRReviewComment(
        id=id,
        body=body,
        author=author,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        path=path,
        line=line,
        original_line=original_line,
        start_line=start_line,
        original_start_line=original_start_line,
        side=side,
        subject_type=subject_type,
        diff_hunk=diff_hunk,
        thread_id=thread_id,
        in_reply_to_id=in_reply_to_id,
    )


def make_state(
    *,
    comments: list[PRReviewComment] | None = None,
    file_groups: dict[str | None, list[int]] | None = None,
    classified_comments: list[CommentClassification] | None = None,
    pr_number: int = 123,
    head_branch: str = "feat/my-feature",
    repo: str = "owner/repo",
    commit_sha: str | None = None,
    group_results: list[Any] | None = None,
    autofix_config: PRAutoFixConfig | None = None,
) -> PRAutoFixState:
    kwargs: dict[str, Any] = {
        "workflow_id": uuid.uuid4(),
        "profile_id": "test",
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
        "pr_number": pr_number,
        "head_branch": head_branch,
        "repo": repo,
        "comments": comments or [],
        "file_groups": file_groups or {},
        "classified_comments": classified_comments or [],
    }
    if commit_sha is not None:
        kwargs["commit_sha"] = commit_sha
    if group_results is not None:
        kwargs["group_results"] = group_results
    if autofix_config is not None:
        kwargs["autofix_config"] = autofix_config
    return PRAutoFixState(**kwargs)


def make_node_profile() -> Profile:
    """Profile with agent configs for node tests."""
    return Profile(
        name="test",
        repo_root="/tmp/test-repo",
        agents={
            "developer": AgentConfig(driver=DriverType.CLAUDE, model="test-model"),
            "classifier": AgentConfig(driver=DriverType.API, model="test-model"),
        },
    )


def make_runnable_config(profile: Profile | None = None) -> dict[str, Any]:
    """Build a LangGraph-style RunnableConfig."""
    if profile is None:
        profile = make_node_profile()
    return {
        "configurable": {
            "thread_id": uuid.uuid4(),
            "profile": profile,
            "event_bus": None,
        }
    }


def make_classification(
    comment_id: int,
    *,
    category: CommentCategory = CommentCategory.BUG,
    actionable: bool = True,
) -> CommentClassification:
    return CommentClassification(
        comment_id=comment_id,
        category=category,
        confidence=0.95,
        actionable=actionable,
        reason="test classification",
    )


def make_metrics_profile(**overrides: object) -> Profile:
    """Build a minimal Profile for metrics tests."""
    defaults: dict[str, Any] = {
        "name": "test-profile",
        "repo_root": "/tmp/test-repo",
        "agents": {
            "developer": {"driver": "claude", "model": "sonnet"},
        },
    }
    defaults.update(overrides)
    return Profile(**defaults)


def make_orchestrator(
    metrics_repo: MetricsRepository | None = None,
    workflow_repo: WorkflowRepository | None = None,
) -> PRAutoFixOrchestrator:
    """Build orchestrator with mock dependencies for metrics tests."""
    event_bus = MagicMock(spec=EventBus)
    event_bus.emit = MagicMock()
    github_pr = MagicMock(spec=GitHubPRService)
    github_pr.get_pr_summary = AsyncMock(
        return_value=PRSummary(
            number=42,
            title="Test PR",
            head_branch="feat",
            author="user",
            updated_at="2026-03-14T00:00:00Z",
        ),
    )
    return PRAutoFixOrchestrator(
        event_bus=event_bus,
        github_pr_service=github_pr,
        workflow_repo=workflow_repo,
        metrics_repo=metrics_repo,
    )


# ---------------------------------------------------------------------------
# Mock pipeline context manager (reduces ~15 lines per usage)
# ---------------------------------------------------------------------------


@asynccontextmanager
async def mock_pipeline_context(
    *,
    ainvoke_return: dict[str, Any] | None = None,
    ainvoke_side_effect: Exception | None = None,
    initial_state: dict[str, Any] | None = None,
) -> AsyncGenerator[tuple[MagicMock, MagicMock]]:
    """Context manager that patches PRAutoFixPipeline with mock graph.

    Yields (mock_pipeline, mock_graph) for assertion access.
    """
    mock_graph = AsyncMock()
    if ainvoke_side_effect:
        mock_graph.ainvoke = AsyncMock(side_effect=ainvoke_side_effect)
    else:
        mock_graph.ainvoke = AsyncMock(return_value=ainvoke_return or {})

    mock_pipeline = MagicMock()
    mock_pipeline.create_graph.return_value = mock_graph
    mock_pipeline.get_initial_state.return_value = (
        initial_state if initial_state is not None else {"mock": "state"}
    )

    with patch(
        "amelia.pipelines.pr_auto_fix.orchestrator.PRAutoFixPipeline",
        return_value=mock_pipeline,
    ):
        yield mock_pipeline, mock_graph


# ---------------------------------------------------------------------------
# Shared orchestrator fixtures (used by test_orchestrator.py)
# ---------------------------------------------------------------------------


@pytest.fixture()
def event_bus() -> EventBus:
    """Create a real EventBus to capture emitted events."""
    return EventBus()


@pytest.fixture()
def captured_events(event_bus: EventBus) -> list[WorkflowEvent]:
    """Subscribe to EventBus and capture all emitted events."""
    events: list[WorkflowEvent] = []
    event_bus.subscribe(lambda e: events.append(e))
    return events


@pytest.fixture()
def github_pr_service() -> MagicMock:
    """Mock GitHubPRService."""
    svc = MagicMock(spec=GitHubPRService)
    svc.create_issue_comment = AsyncMock()
    svc.get_pr_summary = AsyncMock(
        return_value=PRSummary(
            number=42,
            title="Fix: broken tests",
            head_branch="feat/test",
            author="testuser",
            updated_at=datetime.now(UTC),
        )
    )
    return svc


@pytest.fixture()
def workflow_repo() -> MagicMock:
    """Mock WorkflowRepository."""
    repo = MagicMock(spec=WorkflowRepository)
    repo.create = AsyncMock()
    repo.update = AsyncMock()
    return repo


@pytest.fixture()
def mock_git_operations() -> MagicMock:
    """Create a mock GitOperations that does nothing."""
    mock_git = MagicMock()
    mock_git._run_git = AsyncMock(return_value="")
    mock_git.fetch_origin = AsyncMock()
    mock_git.checkout_and_reset = AsyncMock()
    mock_git.has_changes = AsyncMock(return_value=False)
    return mock_git


@pytest.fixture()
def orchestrator(
    event_bus: EventBus,
    github_pr_service: MagicMock,
    workflow_repo: MagicMock,
) -> PRAutoFixOrchestrator:
    """Create orchestrator with mocked dependencies."""
    return PRAutoFixOrchestrator(
        event_bus=event_bus,
        github_pr_service=github_pr_service,
        workflow_repo=workflow_repo,
    )


@pytest.fixture()
def orch_profile() -> Profile:
    """Minimal profile for orchestrator testing."""
    return Profile(
        name="test",
        repo_root="/tmp/test-repo",
        pr_autofix=PRAutoFixConfig(
            post_push_cooldown_seconds=0,
            max_cooldown_seconds=0,
        ),
    )


@pytest.fixture()
def pr_autofix_config(orch_profile: Profile) -> PRAutoFixConfig:
    """Extract PR auto-fix config from profile (guaranteed non-None in tests)."""
    assert orch_profile.pr_autofix is not None
    return orch_profile.pr_autofix
