# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Integration tests for boundary conditions and edge cases.

These tests verify graceful handling of edge cases like:
- current_batch_index exceeding batches length
- Empty batches list
- ExecutionPlan is None

These are regression tests for bugs identified in the test gap analysis.
"""

import pytest

from amelia.core.orchestrator import route_after_developer
from amelia.core.state import ExecutionPlan
from amelia.core.types import DeveloperStatus

from .conftest import (
    make_execution_state,
    make_plan,
)


class TestIndexBoundaryConditions:
    """Tests for batch index boundary handling.

    Regression tests for Bug #2 from integration-test-gaps-analysis.md:
    Index out of bounds vulnerability in route_after_developer().
    """

    @pytest.mark.parametrize("current_batch_index,num_batches,description", [
        (2, 2, "past end"),
        (1, 1, "at end"),
        (100, 3, "way past end"),
    ])
    def test_route_after_developer_handles_index_beyond_batches(
        self,
        current_batch_index: int,
        num_batches: int,
        description: str,
    ) -> None:
        """Routing should handle when batch index exceeds or equals batches length.

        This can happen when Developer completes the last batch and increments
        current_batch_index beyond len(batches).

        Args:
            current_batch_index: The batch index to test
            num_batches: Number of batches in the plan
            description: Test case description (past end/at end/way past end)
        """
        plan = make_plan(num_batches=num_batches, steps_per_batch=1)

        state = make_execution_state(
            execution_plan=plan,
            current_batch_index=current_batch_index,
            developer_status=DeveloperStatus.BATCH_COMPLETE,
            human_approved=True,
        )

        # Should NOT raise IndexError, should route to reviewer (all done)
        route = route_after_developer(state)
        assert route == "reviewer"


class TestExecutionPlanNoneHandling:
    """Tests for handling when execution_plan is None.

    Regression tests for Bug #3 from integration-test-gaps-analysis.md:
    ExecutionPlan None not validated in various locations.
    """

    @pytest.mark.parametrize("developer_status,expected_route", [
        # BATCH_COMPLETE with None plan fails fast to __end__ (approving would crash in developer)
        (DeveloperStatus.BATCH_COMPLETE, "__end__"),
        (DeveloperStatus.ALL_DONE, "reviewer"),
        (DeveloperStatus.BLOCKED, "blocker_resolution"),
        (DeveloperStatus.EXECUTING, "developer"),
    ])
    def test_route_after_developer_handles_none_plan(
        self,
        developer_status: DeveloperStatus,
        expected_route: str,
    ) -> None:
        """Routing should handle None execution_plan with different statuses.

        BATCH_COMPLETE routes to __end__ rather than batch_approval because
        approving would inevitably crash in call_developer_node (which requires
        an execution plan). Fail-fast is safer for state corruption scenarios.

        Args:
            developer_status: The developer status to test
            expected_route: The expected routing destination
        """
        state = make_execution_state(
            execution_plan=None,
            current_batch_index=0,
            developer_status=developer_status,
            human_approved=True,
        )

        route = route_after_developer(state)
        assert route == expected_route


class TestEmptyBatchesList:
    """Tests for handling empty batches list."""

    @pytest.mark.parametrize("developer_status,expected_route", [
        (DeveloperStatus.BATCH_COMPLETE, "reviewer"),
        (DeveloperStatus.ALL_DONE, "reviewer"),
    ])
    def test_route_after_developer_handles_empty_batches(
        self,
        developer_status: DeveloperStatus,
        expected_route: str,
    ) -> None:
        """Routing should handle empty batches list with different statuses.

        Args:
            developer_status: The developer status to test
            expected_route: The expected routing destination
        """
        # Create plan with empty batches
        plan = ExecutionPlan(
            goal="Empty plan",
            batches=(),  # Empty!
            total_estimated_minutes=0,
            tdd_approach=False,
        )

        state = make_execution_state(
            execution_plan=plan,
            current_batch_index=0,
            developer_status=developer_status,
            human_approved=True,
        )

        # With empty batches, any index is "past end", should route to reviewer
        route = route_after_developer(state)
        assert route == expected_route


class TestBatchIndexValidIndex:
    """Tests verifying normal behavior when batch index is valid."""

    @pytest.mark.parametrize("developer_status,expected_route", [
        (DeveloperStatus.BATCH_COMPLETE, "batch_approval"),
        (DeveloperStatus.EXECUTING, "developer"),
        (DeveloperStatus.ALL_DONE, "reviewer"),
    ])
    def test_route_after_developer_valid_index(
        self,
        developer_status: DeveloperStatus,
        expected_route: str,
    ) -> None:
        """Routing should work normally when batch index is valid.

        Args:
            developer_status: The developer status to test
            expected_route: The expected routing destination
        """
        plan = make_plan(num_batches=3, steps_per_batch=1)

        # Use appropriate batch index based on status
        current_batch_index = 1 if developer_status == DeveloperStatus.BATCH_COMPLETE else 0

        state = make_execution_state(
            execution_plan=plan,
            current_batch_index=current_batch_index,
            developer_status=developer_status,
            human_approved=True,
        )

        route = route_after_developer(state)
        assert route == expected_route
