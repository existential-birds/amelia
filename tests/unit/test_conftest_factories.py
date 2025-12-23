# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Tests for conftest.py factory fixtures - validates test infrastructure."""

from unittest.mock import AsyncMock

import pytest

from amelia.core.state import ExecutionPlan
from amelia.core.types import Design, Issue, Profile


class TestFactoryDefaults:
    """Verify factories create valid objects with expected defaults."""

    @pytest.mark.parametrize(
        "factory_name,expected_type,check_field,expected_value",
        [
            ("mock_issue_factory", Issue, "id", "TEST-123"),
            ("mock_profile_factory", Profile, "driver", "cli:claude"),
            ("mock_design_factory", Design, "title", "Test Feature"),
            ("mock_execution_plan_factory", ExecutionPlan, "tdd_approach", True),
        ],
    )
    def test_factory_creates_valid_defaults(
        self, factory_name, expected_type, check_field, expected_value, request
    ):
        """Each factory should create objects with expected default values."""
        factory = request.getfixturevalue(factory_name)
        obj = factory()

        assert isinstance(obj, expected_type)
        assert getattr(obj, check_field) == expected_value


class TestFactoryCustomization:
    """Verify factories accept custom parameters."""

    def test_issue_factory_custom_values(self, mock_issue_factory):
        """Issue factory should accept custom id and title."""
        issue = mock_issue_factory(id="CUSTOM-1", title="Custom Title")

        assert issue.id == "CUSTOM-1"
        assert issue.title == "Custom Title"

    def test_profile_factory_presets(self, mock_profile_factory):
        """Profile presets should have correct driver configurations."""
        cli = mock_profile_factory(preset="cli_single")
        api = mock_profile_factory(preset="api_single")
        comp = mock_profile_factory(preset="api_competitive")

        assert cli.driver == "cli:claude"
        assert api.driver == "api:openrouter"
        assert comp.strategy == "competitive"

    def test_execution_plan_factory_custom_batches(self, mock_execution_plan_factory):
        """ExecutionPlan factory should accept custom num_batches and steps_per_batch."""
        plan = mock_execution_plan_factory(num_batches=3, steps_per_batch=2)

        assert len(plan.batches) == 3
        assert len(plan.batches[0].steps) == 2
        assert len(plan.batches[1].steps) == 2
        assert len(plan.batches[2].steps) == 2

    def test_execution_plan_factory_goal(self, mock_execution_plan_factory):
        """ExecutionPlan factory should accept custom goal."""
        plan = mock_execution_plan_factory(goal="Implement authentication")

        assert plan.goal == "Implement authentication"

    def test_execution_plan_factory_risk_levels(self, mock_execution_plan_factory):
        """ExecutionPlan factory should accept custom risk_levels."""
        plan = mock_execution_plan_factory(
            num_batches=3,
            steps_per_batch=2,
            risk_levels=["low", "medium", "high"]
        )

        assert len(plan.batches) == 3
        assert plan.batches[0].risk_summary == "low"
        assert plan.batches[1].risk_summary == "medium"
        assert plan.batches[2].risk_summary == "high"
        # Verify steps also have correct risk levels
        for step in plan.batches[0].steps:
            assert step.risk_level == "low"
        for step in plan.batches[1].steps:
            assert step.risk_level == "medium"
        for step in plan.batches[2].steps:
            assert step.risk_level == "high"

    def test_execution_plan_factory_default_risk_levels(self, mock_execution_plan_factory):
        """ExecutionPlan factory should default to low risk when risk_levels not provided."""
        plan = mock_execution_plan_factory(num_batches=2, steps_per_batch=1)

        assert plan.batches[0].risk_summary == "low"
        assert plan.batches[1].risk_summary == "low"
        for step in plan.batches[0].steps:
            assert step.risk_level == "low"
        for step in plan.batches[1].steps:
            assert step.risk_level == "low"

    def test_execution_state_factory_with_preset(self, mock_execution_state_factory):
        """ExecutionState factory should accept profile presets."""
        state, profile = mock_execution_state_factory(profile_preset="api_competitive")

        assert profile.strategy == "competitive"

    def test_execution_state_factory_with_execution_plan(
        self, mock_execution_state_factory, mock_execution_plan_factory
    ):
        """ExecutionState factory should accept execution_plan parameter."""
        plan = mock_execution_plan_factory(goal="Custom goal")
        state, _profile = mock_execution_state_factory(execution_plan=plan)

        assert state.execution_plan is not None
        assert state.execution_plan.goal == "Custom goal"

    def test_design_factory_custom_values(self, mock_design_factory):
        """Design factory should accept custom values."""
        design = mock_design_factory(title="Auth Feature", tech_stack=["FastAPI", "PyJWT"])

        assert design.title == "Auth Feature"
        assert design.tech_stack == ["FastAPI", "PyJWT"]

    def test_review_response_factory_states(self, mock_review_response_factory):
        """ReviewResponse factory should support approved and rejected states."""
        approved = mock_review_response_factory(approved=True)
        rejected = mock_review_response_factory(approved=False, severity="high")

        assert approved.approved is True
        assert rejected.approved is False
        assert rejected.severity == "high"


class TestAsyncDriverFactory:
    """Verify async driver factory behavior."""

    def test_async_driver_factory_creates_mock(self, mock_async_driver_factory):
        """Async driver should have expected mock methods."""
        driver = mock_async_driver_factory()

        assert hasattr(driver, "generate")
        assert hasattr(driver, "execute_tool")
        assert isinstance(driver.generate, AsyncMock)

    def test_async_driver_factory_custom_return(self, mock_async_driver_factory):
        """Async driver should accept custom return value."""
        driver = mock_async_driver_factory(generate_return="custom response")

        assert driver.generate.return_value == "custom response"
