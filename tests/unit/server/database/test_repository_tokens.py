"""Tests for WorkflowRepository token usage methods."""

from datetime import UTC, datetime

import pytest

from amelia.server.database.repository import WorkflowRepository
from amelia.server.models.state import ServerExecutionState
from amelia.server.models.tokens import TokenUsage


class TestTokenUsageRepository:
    """Tests for token usage persistence methods."""

    @pytest.fixture
    async def workflow(self, repository: WorkflowRepository) -> ServerExecutionState:
        """Create and save a test workflow for token usage tests.

        Args:
            repository: WorkflowRepository instance.

        Returns:
            Created workflow.
        """
        wf = ServerExecutionState(
            id="wf-tokens",
            issue_id="ISSUE-TOKEN",
            worktree_path="/tmp/test-tokens",
            worktree_name="test-tokens",
            workflow_status="in_progress",
            started_at=datetime.now(UTC),
        )
        await repository.create(wf)
        return wf

    def _make_token_usage(
        self,
        workflow_id: str,
        agent: str = "architect",
        **overrides,
    ) -> TokenUsage:
        """Create a TokenUsage instance with sensible defaults.

        Args:
            workflow_id: Workflow ID to associate with.
            agent: Agent name.
            **overrides: Field overrides.

        Returns:
            TokenUsage instance.
        """
        defaults = {
            "workflow_id": workflow_id,
            "agent": agent,
            "model": "claude-sonnet-4-20250514",
            "input_tokens": 1000,
            "output_tokens": 500,
            "cache_read_tokens": 200,
            "cache_creation_tokens": 100,
            "cost_usd": 0.012345,
            "duration_ms": 5000,
            "num_turns": 3,
            "timestamp": datetime.now(UTC),
        }
        defaults.update(overrides)
        return TokenUsage(**defaults)

    # =========================================================================
    # save_token_usage Tests
    # =========================================================================

    async def test_save_token_usage(
        self, repository: WorkflowRepository, workflow: ServerExecutionState
    ):
        """Should persist token usage to database."""
        usage = self._make_token_usage(workflow.id)

        await repository.save_token_usage(usage)

        # Verify by retrieving
        usages = await repository.get_token_usage(workflow.id)
        assert len(usages) == 1
        assert usages[0].id == usage.id

    async def test_save_token_usage_multiple_agents(
        self, repository: WorkflowRepository, workflow: ServerExecutionState
    ):
        """Should save multiple token usage records for different agents."""
        architect_usage = self._make_token_usage(
            workflow.id,
            agent="architect",
            input_tokens=500,
            output_tokens=200,
            cost_usd=0.005,
        )
        developer_usage = self._make_token_usage(
            workflow.id,
            agent="developer",
            input_tokens=2000,
            output_tokens=1000,
            cost_usd=0.025,
        )
        reviewer_usage = self._make_token_usage(
            workflow.id,
            agent="reviewer",
            input_tokens=1500,
            output_tokens=300,
            cost_usd=0.015,
        )

        await repository.save_token_usage(architect_usage)
        await repository.save_token_usage(developer_usage)
        await repository.save_token_usage(reviewer_usage)

        usages = await repository.get_token_usage(workflow.id)
        assert len(usages) == 3
        agents = {u.agent for u in usages}
        assert agents == {"architect", "developer", "reviewer"}

    async def test_save_token_usage_preserves_all_fields(
        self, repository: WorkflowRepository, workflow: ServerExecutionState
    ):
        """Should preserve all token usage fields after save and retrieve."""
        timestamp = datetime.now(UTC)
        usage = TokenUsage(
            id="usage-123",
            workflow_id=workflow.id,
            agent="developer",
            model="claude-opus-4-20250514",
            input_tokens=5000,
            output_tokens=2500,
            cache_read_tokens=1000,
            cache_creation_tokens=500,
            cost_usd=0.123456,
            duration_ms=15000,
            num_turns=7,
            timestamp=timestamp,
        )

        await repository.save_token_usage(usage)

        usages = await repository.get_token_usage(workflow.id)
        assert len(usages) == 1
        retrieved = usages[0]
        assert retrieved.id == "usage-123"
        assert retrieved.workflow_id == workflow.id
        assert retrieved.agent == "developer"
        assert retrieved.model == "claude-opus-4-20250514"
        assert retrieved.input_tokens == 5000
        assert retrieved.output_tokens == 2500
        assert retrieved.cache_read_tokens == 1000
        assert retrieved.cache_creation_tokens == 500
        assert retrieved.cost_usd == pytest.approx(0.123456, rel=1e-6)
        assert retrieved.duration_ms == 15000
        assert retrieved.num_turns == 7
        # Compare timestamps as ISO strings to avoid timezone precision issues
        assert retrieved.timestamp.isoformat()[:19] == timestamp.isoformat()[:19]

    # =========================================================================
    # get_token_usage Tests
    # =========================================================================

    async def test_get_token_usage_empty_workflow(
        self, repository: WorkflowRepository, workflow: ServerExecutionState
    ):
        """Should return empty list for workflow with no token usage."""
        usages = await repository.get_token_usage(workflow.id)
        assert usages == []

    async def test_get_token_usage_nonexistent_workflow(
        self, repository: WorkflowRepository
    ):
        """Should return empty list for non-existent workflow."""
        usages = await repository.get_token_usage("nonexistent-workflow-id")
        assert usages == []

    async def test_get_token_usage_ordered_by_timestamp(
        self, repository: WorkflowRepository, workflow: ServerExecutionState
    ):
        """Should return token usage records ordered by timestamp ascending."""
        from datetime import timedelta

        base_time = datetime.now(UTC)

        # Save in non-chronological order
        usage2 = self._make_token_usage(
            workflow.id,
            agent="developer",
            timestamp=base_time + timedelta(minutes=10),
        )
        usage1 = self._make_token_usage(
            workflow.id,
            agent="architect",
            timestamp=base_time,
        )
        usage3 = self._make_token_usage(
            workflow.id,
            agent="reviewer",
            timestamp=base_time + timedelta(minutes=20),
        )

        await repository.save_token_usage(usage2)
        await repository.save_token_usage(usage1)
        await repository.save_token_usage(usage3)

        usages = await repository.get_token_usage(workflow.id)
        assert len(usages) == 3
        # Should be in chronological order
        assert usages[0].agent == "architect"
        assert usages[1].agent == "developer"
        assert usages[2].agent == "reviewer"

    async def test_get_token_usage_filters_by_workflow(
        self, repository: WorkflowRepository, workflow: ServerExecutionState
    ):
        """Should only return token usage for the specified workflow."""
        # Create another workflow
        other_wf = ServerExecutionState(
            id="wf-other",
            issue_id="ISSUE-OTHER",
            worktree_path="/tmp/test-other",
            worktree_name="test-other",
            workflow_status="in_progress",
            started_at=datetime.now(UTC),
        )
        await repository.create(other_wf)

        # Save usage for both workflows
        usage1 = self._make_token_usage(workflow.id, agent="architect")
        usage2 = self._make_token_usage(other_wf.id, agent="developer")

        await repository.save_token_usage(usage1)
        await repository.save_token_usage(usage2)

        # Should only return usage for first workflow
        usages = await repository.get_token_usage(workflow.id)
        assert len(usages) == 1
        assert usages[0].workflow_id == workflow.id

    # =========================================================================
    # get_token_summary Tests
    # =========================================================================

    async def test_get_token_summary_empty_workflow(
        self, repository: WorkflowRepository, workflow: ServerExecutionState
    ):
        """Should return None for workflow with no token usage."""
        summary = await repository.get_token_summary(workflow.id)
        assert summary is None

    async def test_get_token_summary_single_usage(
        self, repository: WorkflowRepository, workflow: ServerExecutionState
    ):
        """Should return summary for single token usage record."""
        usage = TokenUsage(
            workflow_id=workflow.id,
            agent="architect",
            model="claude-sonnet-4-20250514",
            input_tokens=1000,
            output_tokens=500,
            cache_read_tokens=200,
            cache_creation_tokens=0,
            cost_usd=0.01,
            duration_ms=5000,
            num_turns=3,
            timestamp=datetime.now(UTC),
        )
        await repository.save_token_usage(usage)

        summary = await repository.get_token_summary(workflow.id)

        assert summary is not None
        assert summary.total_input_tokens == 1000
        assert summary.total_output_tokens == 500
        assert summary.total_cache_read_tokens == 200
        assert summary.total_cost_usd == pytest.approx(0.01, rel=1e-6)
        assert summary.total_duration_ms == 5000
        assert summary.total_turns == 3
        assert len(summary.breakdown) == 1
        assert summary.breakdown[0].id == usage.id

    async def test_get_token_summary_aggregates_multiple_usages(
        self, repository: WorkflowRepository, workflow: ServerExecutionState
    ):
        """Should correctly aggregate totals across multiple usage records."""
        usage1 = TokenUsage(
            workflow_id=workflow.id,
            agent="architect",
            input_tokens=500,
            output_tokens=200,
            cache_read_tokens=100,
            cache_creation_tokens=50,
            cost_usd=0.005,
            duration_ms=3000,
            num_turns=2,
            timestamp=datetime.now(UTC),
        )
        usage2 = TokenUsage(
            workflow_id=workflow.id,
            agent="developer",
            input_tokens=2000,
            output_tokens=1000,
            cache_read_tokens=500,
            cache_creation_tokens=200,
            cost_usd=0.025,
            duration_ms=10000,
            num_turns=5,
            timestamp=datetime.now(UTC),
        )
        usage3 = TokenUsage(
            workflow_id=workflow.id,
            agent="reviewer",
            input_tokens=1500,
            output_tokens=300,
            cache_read_tokens=400,
            cache_creation_tokens=100,
            cost_usd=0.015,
            duration_ms=7000,
            num_turns=4,
            timestamp=datetime.now(UTC),
        )

        await repository.save_token_usage(usage1)
        await repository.save_token_usage(usage2)
        await repository.save_token_usage(usage3)

        summary = await repository.get_token_summary(workflow.id)

        assert summary is not None
        # Verify aggregation
        assert summary.total_input_tokens == 500 + 2000 + 1500  # 4000
        assert summary.total_output_tokens == 200 + 1000 + 300  # 1500
        assert summary.total_cache_read_tokens == 100 + 500 + 400  # 1000
        assert summary.total_cost_usd == pytest.approx(0.005 + 0.025 + 0.015, rel=1e-6)
        assert summary.total_duration_ms == 3000 + 10000 + 7000  # 20000
        assert summary.total_turns == 2 + 5 + 4  # 11
        assert len(summary.breakdown) == 3

    async def test_get_token_summary_breakdown_in_order(
        self, repository: WorkflowRepository, workflow: ServerExecutionState
    ):
        """Summary breakdown should be ordered by timestamp."""
        from datetime import timedelta

        base_time = datetime.now(UTC)

        usage1 = self._make_token_usage(
            workflow.id,
            agent="architect",
            timestamp=base_time,
        )
        usage2 = self._make_token_usage(
            workflow.id,
            agent="developer",
            timestamp=base_time + timedelta(minutes=5),
        )
        usage3 = self._make_token_usage(
            workflow.id,
            agent="reviewer",
            timestamp=base_time + timedelta(minutes=10),
        )

        # Save in non-chronological order
        await repository.save_token_usage(usage3)
        await repository.save_token_usage(usage1)
        await repository.save_token_usage(usage2)

        summary = await repository.get_token_summary(workflow.id)

        assert summary is not None
        assert len(summary.breakdown) == 3
        # Should be in chronological order
        assert summary.breakdown[0].agent == "architect"
        assert summary.breakdown[1].agent == "developer"
        assert summary.breakdown[2].agent == "reviewer"

    async def test_get_token_summary_nonexistent_workflow(
        self, repository: WorkflowRepository
    ):
        """Should return None for non-existent workflow."""
        summary = await repository.get_token_summary("nonexistent-workflow-id")
        assert summary is None
