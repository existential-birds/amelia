"""Tests for conftest.py factory fixtures - validates test infrastructure."""

import pytest
from unittest.mock import AsyncMock

from amelia.core.state import ExecutionState, TaskDAG, Task
from amelia.core.types import Profile, Issue, Design


class TestFactoryDefaults:
    """Verify factories create valid objects with expected defaults."""

    @pytest.mark.parametrize(
        "factory_name,expected_type,check_field,expected_value",
        [
            ("mock_issue_factory", Issue, "id", "TEST-123"),
            ("mock_profile_factory", Profile, "driver", "cli:claude"),
            ("mock_task_factory", Task, "status", "pending"),
            ("mock_task_dag_factory", TaskDAG, "original_issue", "TEST-123"),
            ("mock_design_factory", Design, "title", "Test Feature"),
            ("mock_execution_state_factory", ExecutionState, "plan", None),
        ],
    )
    def test_factory_creates_valid_defaults(
        self, factory_name, expected_type, check_field, expected_value, request
    ):
        """Each factory should create objects with expected default values."""
        factory = request.getfixturevalue(factory_name)
        # task_factory requires id parameter
        obj = factory(id="1") if factory_name == "mock_task_factory" else factory()

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
        assert api.driver == "api:openai"
        assert comp.strategy == "competitive"

    def test_task_factory_with_dependencies(self, mock_task_factory):
        """Task factory should accept dependencies list."""
        task = mock_task_factory(id="A", dependencies=["B", "C"])

        assert task.id == "A"
        assert task.dependencies == ["B", "C"]

    def test_task_dag_factory_linear_dependencies(self, mock_task_dag_factory):
        """TaskDAG factory should support linear dependency chain."""
        dag = mock_task_dag_factory(num_tasks=3, linear=True)

        assert dag.tasks[1].dependencies == ["1"]
        assert dag.tasks[2].dependencies == ["2"]

    def test_execution_state_factory_with_preset(self, mock_execution_state_factory):
        """ExecutionState factory should accept profile presets."""
        state = mock_execution_state_factory(profile_preset="api_competitive")

        assert state.profile.strategy == "competitive"

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
