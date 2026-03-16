# PR Auto-Fix Comment Flow Fix

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the PR auto-fix pipeline so comments flow from poller through orchestrator into pipeline state, and add integration tests that verify the full end-to-end flow.

**Architecture:** The poller already fetches comments but discards them before calling the orchestrator. Thread comments through `trigger_fix_cycle` → `_run_fix_cycle` → `_execute_pipeline` → `get_initial_state`. Also pass `autofix_config` which currently defaults to empty. Integration tests mock only at the external HTTP boundary (`asyncio.create_subprocess_exec` for `gh` CLI calls) and the LLM driver (`execute_agentic`), keeping the real orchestrator, pipeline, graph, and all nodes.

**Tech Stack:** Python 3.12+, pytest-asyncio, LangGraph, Pydantic

---

## Chunk 1: Integration Tests (TDD)

### Task 1: Create integration test file with fixtures

**Files:**
- Create: `tests/integration/test_pr_autofix_flow.py`

- [ ] **Step 1: Write the test file skeleton with shared fixtures**

```python
"""Integration tests for PR auto-fix end-to-end flow.

Tests the full pipeline: poller detects comments → orchestrator receives them
→ pipeline classifies/develops/commits/resolves. Mocks only at external
boundaries: gh CLI (subprocess) and LLM driver (execute_agentic).
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from amelia.core.types import (
    AgentConfig,
    DriverType,
    PRAutoFixConfig,
    PRReviewComment,
    PRSummary,
    Profile,
)
from amelia.pipelines.pr_auto_fix.orchestrator import PRAutoFixOrchestrator
from amelia.pipelines.pr_auto_fix.state import GroupFixStatus
from amelia.server.events.bus import EventBus
from amelia.server.models.events import EventType


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 3, 15, 12, 0, 0, tzinfo=UTC)


def _make_profile(tmp_path: object) -> Profile:
    return Profile(
        name="test-profile",
        repo_root=str(tmp_path),
        agents={
            "developer": AgentConfig(driver=DriverType.API, model="test-model"),
        },
        pr_autofix=PRAutoFixConfig(
            poll_label="amelia",
            poll_interval=60,
            ignore_authors=["bot-user"],
            post_push_cooldown_seconds=0,
            max_cooldown_seconds=0,
        ),
    )


def _make_comments(pr_number: int = 42) -> list[PRReviewComment]:
    return [
        PRReviewComment(
            id=100,
            body="Variable name `x` should be `count` for clarity.",
            author="reviewer1",
            created_at=_NOW,
            path="src/app.py",
            line=10,
            diff_hunk="@@ -8,3 +8,4 @@\n+x = 0",
            thread_id="PRRT_thread1",
            pr_number=pr_number,
        ),
        PRReviewComment(
            id=101,
            body="Missing null check before accessing `.name`.",
            author="reviewer2",
            created_at=_NOW,
            path="src/app.py",
            line=25,
            diff_hunk="@@ -23,3 +23,4 @@\n+print(obj.name)",
            thread_id="PRRT_thread2",
            pr_number=pr_number,
        ),
    ]


@pytest.fixture()
def profile(tmp_path: object) -> Profile:
    return _make_profile(tmp_path)


@pytest.fixture()
def comments() -> list[PRReviewComment]:
    return _make_comments()


@pytest.fixture()
def event_bus() -> EventBus:
    return EventBus()


@pytest.fixture()
def captured_events(event_bus: EventBus) -> list[Any]:
    events: list[Any] = []
    event_bus.subscribe(lambda e: events.append(e))
    return events


@pytest.fixture()
def orchestrator(event_bus: EventBus) -> PRAutoFixOrchestrator:
    github_pr = MagicMock()
    github_pr.create_issue_comment = AsyncMock()
    return PRAutoFixOrchestrator(
        event_bus=event_bus,
        github_pr_service=github_pr,
    )
```

- [ ] **Step 2: Commit skeleton**

```bash
git add tests/integration/test_pr_autofix_flow.py
git commit -m "test(pr-autofix): add integration test skeleton for comment flow"
```

### Task 2: Test that comments reach classify_node

**Files:**
- Modify: `tests/integration/test_pr_autofix_flow.py`

This test verifies the critical broken link: comments passed to `trigger_fix_cycle` must arrive in the pipeline state and be processed by `classify_node`.

- [ ] **Step 1: Write the failing test**

Add to the test file:

```python
# ---------------------------------------------------------------------------
# Test: Comments flow from orchestrator into pipeline state
# ---------------------------------------------------------------------------


class TestCommentsReachPipeline:
    """Verify comments passed to trigger_fix_cycle reach the pipeline nodes."""

    async def test_comments_populate_pipeline_state(
        self,
        orchestrator: PRAutoFixOrchestrator,
        profile: Profile,
        comments: list[PRReviewComment],
    ) -> None:
        """Comments passed to trigger_fix_cycle must appear in the
        initial state given to graph.ainvoke, not be silently dropped."""
        captured_state: dict[str, Any] = {}

        async def capture_ainvoke(state: Any, **kwargs: Any) -> dict[str, Any]:
            captured_state.update(state if isinstance(state, dict) else state.model_dump())
            return {"group_results": [], "comments": state.get("comments", []) if isinstance(state, dict) else state.comments}

        with patch(
            "amelia.pipelines.pr_auto_fix.orchestrator.PRAutoFixPipeline"
        ) as mock_pipeline_cls:
            mock_pipeline = MagicMock()
            mock_graph = AsyncMock()
            mock_graph.ainvoke = AsyncMock(side_effect=capture_ainvoke)
            mock_pipeline.create_graph.return_value = mock_graph
            mock_pipeline.get_initial_state = lambda **kw: __import__(
                "amelia.pipelines.pr_auto_fix.state", fromlist=["PRAutoFixState"]
            ).PRAutoFixState(**{k: v for k, v in kw.items()})
            mock_pipeline_cls.return_value = mock_pipeline

            # Patch git operations to no-op
            with patch("amelia.pipelines.pr_auto_fix.orchestrator.GitOperations"):
                await orchestrator.trigger_fix_cycle(
                    pr_number=42,
                    repo="owner/repo",
                    profile=profile,
                    head_branch="feat/test",
                    comments=comments,
                )

        # The critical assertion: comments must be in the pipeline state
        assert len(captured_state.get("comments", [])) == 2
        comment_ids = {c["id"] if isinstance(c, dict) else c.id for c in captured_state["comments"]}
        assert comment_ids == {100, 101}

    async def test_autofix_config_reaches_pipeline_state(
        self,
        orchestrator: PRAutoFixOrchestrator,
        profile: Profile,
        comments: list[PRReviewComment],
    ) -> None:
        """PRAutoFixConfig from the profile must be passed to pipeline state,
        not left as the empty default."""
        captured_state: dict[str, Any] = {}

        async def capture_ainvoke(state: Any, **kwargs: Any) -> dict[str, Any]:
            captured_state.update(state if isinstance(state, dict) else state.model_dump())
            return {}

        with patch(
            "amelia.pipelines.pr_auto_fix.orchestrator.PRAutoFixPipeline"
        ) as mock_pipeline_cls:
            mock_pipeline = MagicMock()
            mock_graph = AsyncMock()
            mock_graph.ainvoke = AsyncMock(side_effect=capture_ainvoke)
            mock_pipeline.create_graph.return_value = mock_graph
            mock_pipeline.get_initial_state = lambda **kw: __import__(
                "amelia.pipelines.pr_auto_fix.state", fromlist=["PRAutoFixState"]
            ).PRAutoFixState(**{k: v for k, v in kw.items()})
            mock_pipeline_cls.return_value = mock_pipeline

            with patch("amelia.pipelines.pr_auto_fix.orchestrator.GitOperations"):
                await orchestrator.trigger_fix_cycle(
                    pr_number=42,
                    repo="owner/repo",
                    profile=profile,
                    head_branch="feat/test",
                    comments=comments,
                )

        config = captured_state.get("autofix_config", {})
        if isinstance(config, dict):
            assert config.get("poll_label") == "amelia"
            assert config.get("ignore_authors") == ["bot-user"]
        else:
            assert config.poll_label == "amelia"
            assert config.ignore_authors == ["bot-user"]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/integration/test_pr_autofix_flow.py -x -v
```

Expected: FAIL — `trigger_fix_cycle()` does not accept `comments` parameter yet.

- [ ] **Step 3: Commit failing tests**

```bash
git add tests/integration/test_pr_autofix_flow.py
git commit -m "test(pr-autofix): add failing tests for comment flow into pipeline"
```

### Task 3: Test that poller passes comments to orchestrator

**Files:**
- Modify: `tests/integration/test_pr_autofix_flow.py`

- [ ] **Step 1: Write the failing poller integration test**

```python
# ---------------------------------------------------------------------------
# Test: Poller passes comments to orchestrator
# ---------------------------------------------------------------------------


class TestPollerPassesComments:
    """Verify the poller threads comments through to the orchestrator."""

    async def test_poller_passes_comments_to_trigger_fix_cycle(
        self,
        profile: Profile,
        comments: list[PRReviewComment],
        event_bus: EventBus,
    ) -> None:
        """When the poller detects unresolved comments, it must pass them
        to trigger_fix_cycle so the pipeline can process them."""
        from amelia.server.lifecycle.pr_poller import PRCommentPoller

        mock_orchestrator = MagicMock()
        mock_orchestrator.trigger_fix_cycle = AsyncMock()

        mock_settings_repo = AsyncMock()
        mock_settings_repo.get_server_settings = AsyncMock(
            return_value=MagicMock(pr_polling_enabled=True),
        )

        mock_profile_repo = AsyncMock()
        mock_profile_repo.list_profiles = AsyncMock(return_value=[profile])

        poller = PRCommentPoller(
            profile_repo=mock_profile_repo,
            settings_repo=mock_settings_repo,
            orchestrator=mock_orchestrator,
            event_bus=event_bus,
        )

        # Mock the GitHubPRService that _poll_profile creates
        mock_service = MagicMock()
        mock_service.list_labeled_prs = AsyncMock(
            return_value=[
                PRSummary(
                    number=42,
                    title="Fix: test PR",
                    head_branch="feat/test",
                    author="dev1",
                    updated_at="2026-03-15T12:00:00Z",
                ),
            ],
        )
        mock_service.fetch_review_comments = AsyncMock(return_value=comments)

        with (
            patch(
                "amelia.server.lifecycle.pr_poller.GitHubPRService",
                return_value=mock_service,
            ),
            patch.object(poller, "_get_repo_slug", return_value="owner/repo"),
        ):
            await poller._poll_profile(profile)

        # Wait for fire-and-forget task
        await asyncio.sleep(0.1)

        mock_orchestrator.trigger_fix_cycle.assert_called_once()
        call_kwargs = mock_orchestrator.trigger_fix_cycle.call_args.kwargs
        assert "comments" in call_kwargs, (
            "Poller must pass comments to trigger_fix_cycle"
        )
        assert len(call_kwargs["comments"]) == 2
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/integration/test_pr_autofix_flow.py::TestPollerPassesComments -x -v
```

Expected: FAIL — poller doesn't pass `comments` kwarg yet.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_pr_autofix_flow.py
git commit -m "test(pr-autofix): add failing test for poller passing comments"
```

### Task 4: Test that empty comments skip pipeline (no junk commits)

**Files:**
- Modify: `tests/integration/test_pr_autofix_flow.py`

- [ ] **Step 1: Write the test**

```python
class TestNoJunkCommits:
    """Verify that when classify_node produces no actionable comments,
    commit_push_node does NOT commit."""

    async def test_no_commit_when_no_actionable_comments(
        self,
        orchestrator: PRAutoFixOrchestrator,
        profile: Profile,
        event_bus: EventBus,
    ) -> None:
        """If comments are empty or all filtered, the pipeline must not
        create any git commits."""
        git_ops_mock = MagicMock()
        git_ops_mock.has_changes = AsyncMock(return_value=False)
        git_ops_mock.stage_and_commit = AsyncMock()
        git_ops_mock.fetch_origin = AsyncMock()
        git_ops_mock.checkout_and_reset = AsyncMock()

        with (
            patch(
                "amelia.pipelines.pr_auto_fix.orchestrator.GitOperations",
                return_value=git_ops_mock,
            ),
            patch(
                "amelia.pipelines.pr_auto_fix.nodes.GitOperations",
                return_value=git_ops_mock,
            ),
        ):
            await orchestrator.trigger_fix_cycle(
                pr_number=42,
                repo="owner/repo",
                profile=profile,
                head_branch="feat/test",
                comments=[],  # No comments
            )

        # stage_and_commit must NOT have been called
        git_ops_mock.stage_and_commit.assert_not_called()
```

- [ ] **Step 2: Run and verify failure**

```bash
uv run pytest tests/integration/test_pr_autofix_flow.py::TestNoJunkCommits -x -v
```

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_pr_autofix_flow.py
git commit -m "test(pr-autofix): add failing test for no-junk-commit guard"
```

---

## Chunk 2: Fix the Bug

### Task 5: Thread comments through the orchestrator

**Files:**
- Modify: `amelia/server/lifecycle/pr_poller.py:192` — pass `comments=comments`
- Modify: `amelia/pipelines/pr_auto_fix/orchestrator.py:97-165` — add `comments` param to `trigger_fix_cycle`, `_run_fix_cycle`, `_execute_pipeline`; pass `comments` and `autofix_config` to `get_initial_state`

- [ ] **Step 1: Add `comments` parameter to `trigger_fix_cycle`**

In `orchestrator.py`, update the method signature (line 97) to accept comments:

```python
async def trigger_fix_cycle(
    self,
    pr_number: int,
    repo: str,
    profile: Profile,
    head_branch: str = "",
    config: PRAutoFixConfig | None = None,
    pr_title: str = "",
    comments: list[PRReviewComment] | None = None,
) -> None:
```

Add the import at the top if not already present:
```python
from amelia.core.types import PRAutoFixConfig, PRReviewComment, Profile
```

Thread it through to `_run_fix_cycle` (around line 148):
```python
await self._run_fix_cycle(
    pr_number=pr_number,
    repo=repo,
    profile=profile,
    config=effective_config,
    head_branch=head_branch,
    pr_title=effective_title,
    comments=comments or [],
)
```

And in the pending-cycle loop (around line 159):
```python
await self._run_fix_cycle(
    pr_number=pr_number,
    repo=repo,
    profile=profile,
    config=effective_config,
    head_branch=head_branch,
    pr_title=effective_title,
    comments=comments or [],
)
```

- [ ] **Step 2: Add `comments` parameter to `_run_fix_cycle`**

Update signature (line 172):
```python
async def _run_fix_cycle(
    self,
    pr_number: int,
    repo: str,
    profile: Profile,
    config: PRAutoFixConfig,
    head_branch: str = "",
    pr_title: str = "",
    comments: list[PRReviewComment] | None = None,
) -> None:
```

Pass to `_execute_pipeline` (line 205):
```python
await self._execute_pipeline(
    pr_number, repo, profile, config, head_branch,
    pr_title=pr_title, comments=comments,
)
```

- [ ] **Step 3: Add `comments` to `_execute_pipeline` and pass to `get_initial_state`**

Update signature (line 258):
```python
async def _execute_pipeline(
    self,
    pr_number: int,
    repo: str,
    profile: Profile,
    config: PRAutoFixConfig,
    head_branch: str = "",
    pr_title: str = "",
    comments: list[PRReviewComment] | None = None,
) -> None:
```

Update `get_initial_state` call (line 322):
```python
initial_state = pipeline.get_initial_state(
    workflow_id=self.get_workflow_id(repo, pr_number),
    profile_id=profile.name,
    pr_number=pr_number,
    head_branch=head_branch,
    repo=repo,
    comments=comments or [],
    autofix_config=config,
)
```

Also update `issue_cache["comment_count"]` (line 288):
```python
issue_cache["comment_count"] = len(comments or []),
```

Wait — that creates a tuple. Use:
```python
"comment_count": len(comments or []),
```

- [ ] **Step 4: Update the poller to pass comments**

In `pr_poller.py` (line 192), add `comments=comments`:
```python
task = asyncio.create_task(
    self._orchestrator.trigger_fix_cycle(
        pr_number=pr.number,
        repo=repo_slug,
        profile=profile,
        head_branch=pr.head_branch,
        config=config,
        pr_title=pr.title,
        comments=comments,
    ),
)
```

- [ ] **Step 5: Run the integration tests**

```bash
uv run pytest tests/integration/test_pr_autofix_flow.py -x -v
```

Expected: All tests PASS.

- [ ] **Step 6: Run the full test suite**

```bash
uv run pytest -x -q
```

Fix any unit test failures caused by the new parameter (tests that mock `trigger_fix_cycle` or `_execute_pipeline` may need updating).

- [ ] **Step 7: Commit**

```bash
git add amelia/pipelines/pr_auto_fix/orchestrator.py amelia/server/lifecycle/pr_poller.py
git commit -m "fix(pr-autofix): thread comments and config from poller into pipeline state

Comments fetched by the poller were discarded before reaching the
pipeline. classify_node always saw an empty list and returned early,
so the pipeline never classified, developed, committed, or resolved
anything. Now comments and autofix_config flow through:
poller → trigger_fix_cycle → _run_fix_cycle → _execute_pipeline → get_initial_state"
```

### Task 6: Update existing unit tests for new parameter

**Files:**
- Modify: `tests/unit/pipelines/pr_auto_fix/test_orchestrator.py`
- Modify: `tests/unit/pipelines/pr_auto_fix/conftest.py`
- Modify: `tests/unit/server/lifecycle/test_pr_poller.py`

- [ ] **Step 1: Update unit test fixtures and assertions**

Any test calling `trigger_fix_cycle` or `_execute_pipeline` that doesn't pass `comments` should still work (defaults to `None`/`[]`). But tests asserting on `get_initial_state` kwargs need updating.

Search for all call sites:
```bash
uv run pytest tests/unit/pipelines/pr_auto_fix/ tests/unit/server/lifecycle/test_pr_poller.py -x -v 2>&1 | head -40
```

Fix any failures by adding `comments=[]` or updating assertions.

- [ ] **Step 2: Run full suite and fix**

```bash
uv run pytest -x -q
```

- [ ] **Step 3: Commit**

```bash
git add tests/
git commit -m "test(pr-autofix): update unit tests for comments parameter"
```

### Task 7: Update API route to fetch and pass comments

**Files:**
- Modify: `amelia/server/routes/github.py` — the `trigger_pr_autofix` handler

The API route currently calls `trigger_fix_cycle` without comments. It needs to fetch them first.

- [ ] **Step 1: Update the API handler**

In the `trigger_pr_autofix` handler (around line 380), after fetching `pr_summary` and before creating the async task, add comment fetching:

```python
# Fetch unresolved comments for the pipeline
comments = await github_service.fetch_review_comments(
    number,
    ignore_authors=effective_config.ignore_authors,
)
```

Then pass to `trigger_fix_cycle`:
```python
task = asyncio.create_task(
    orchestrator.trigger_fix_cycle(
        pr_number=number,
        repo=repo,
        profile=resolved,
        head_branch=pr_summary.head_branch,
        config=effective_config,
        pr_title=pr_summary.title,
        comments=comments,
    )
)
```

- [ ] **Step 2: Run tests**

```bash
uv run pytest tests/unit/server/routes/test_github_pr_routes.py tests/integration/test_pr_autofix_flow.py -x -v
```

- [ ] **Step 3: Commit**

```bash
git add amelia/server/routes/github.py
git commit -m "fix(pr-autofix): fetch and pass comments in API trigger endpoint"
```
