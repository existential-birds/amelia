"""Tests for conftest.py factory fixtures."""

import pytest

from amelia.core.types import Issue


def test_issue_factory_defaults(mock_issue_factory):
    """Test that issue_factory creates Issue with sensible defaults."""
    issue = mock_issue_factory()
    assert issue.id == "TEST-123"
    assert issue.title == "Test Issue"
    assert issue.status == "open"


def test_issue_factory_custom(mock_issue_factory):
    """Test that issue_factory accepts custom values."""
    issue = mock_issue_factory(id="CUSTOM-1", title="Custom Title")
    assert issue.id == "CUSTOM-1"
    assert issue.title == "Custom Title"


def test_profile_factory_defaults(mock_profile_factory):
    """Test that profile_factory creates Profile with sensible defaults."""
    profile = mock_profile_factory()
    assert profile.name == "test"
    assert profile.driver == "cli:claude"
    assert profile.tracker == "noop"
    assert profile.strategy == "single"


def test_profile_factory_presets(mock_profile_factory):
    """Test that profile_factory supports presets."""
    cli = mock_profile_factory(preset="cli_single")
    assert cli.driver == "cli:claude"

    api = mock_profile_factory(preset="api_single")
    assert api.driver == "api:openai"

    comp = mock_profile_factory(preset="api_competitive")
    assert comp.strategy == "competitive"


def test_task_factory_defaults(mock_task_factory):
    """Test that task_factory creates Task with sensible defaults."""
    task = mock_task_factory(id="1")
    assert task.id == "1"
    assert task.description == "Task 1"
    assert task.status == "pending"
    assert task.dependencies == []


def test_task_factory_custom(mock_task_factory):
    """Test that task_factory accepts custom values."""
    task = mock_task_factory(id="2", description="Custom task", dependencies=["1"])
    assert task.description == "Custom task"
    assert task.dependencies == ["1"]


def test_task_dag_factory_simple(mock_task_dag_factory):
    """Test that task_dag_factory creates simple DAG."""
    dag = mock_task_dag_factory(num_tasks=2)
    assert len(dag.tasks) == 2
    assert dag.original_issue == "TEST-123"


def test_task_dag_factory_linear(mock_task_dag_factory):
    """Test that task_dag_factory creates linear dependencies."""
    dag = mock_task_dag_factory(num_tasks=3, linear=True)
    assert dag.tasks[1].dependencies == ["1"]
    assert dag.tasks[2].dependencies == ["2"]


def test_execution_state_factory_defaults(mock_execution_state_factory):
    """Test that execution_state_factory creates state with defaults."""
    state = mock_execution_state_factory()
    assert state.profile is not None
    assert state.issue is not None
    assert state.plan is None


def test_execution_state_factory_with_preset(mock_execution_state_factory):
    """Test that execution_state_factory accepts profile presets."""
    state = mock_execution_state_factory(profile_preset="api_competitive")
    assert state.profile.strategy == "competitive"


def test_async_driver_factory_defaults(mock_async_driver_factory):
    """Test that async_driver_factory creates mock driver."""
    from unittest.mock import AsyncMock
    driver = mock_async_driver_factory()
    assert hasattr(driver, 'generate')
    assert hasattr(driver, 'execute_tool')
    assert isinstance(driver.generate, AsyncMock)


def test_async_driver_factory_custom_return(mock_async_driver_factory):
    """Test that async_driver_factory accepts custom return values."""
    driver = mock_async_driver_factory(generate_return="custom response")
    # The return_value should be set
    assert driver.generate.return_value == "custom response"


def test_review_response_factory_approved(mock_review_response_factory):
    """Test that review_response_factory creates approved review."""
    response = mock_review_response_factory(approved=True)
    assert response.approved is True
    assert response.severity == "low"


def test_review_response_factory_rejected(mock_review_response_factory):
    """Test that review_response_factory creates rejected review."""
    response = mock_review_response_factory(approved=False, severity="high")
    assert response.approved is False
    assert response.severity == "high"


def test_design_factory_defaults(mock_design_factory):
    """Test that design_factory creates Design with defaults."""
    design = mock_design_factory()
    assert design.title == "Test Feature"
    assert design.goal == "Build test feature"
    assert design.tech_stack == ["Python"]


def test_design_factory_custom(mock_design_factory):
    """Test that design_factory accepts custom values."""
    design = mock_design_factory(title="Auth Feature", tech_stack=["FastAPI", "PyJWT"])
    assert design.title == "Auth Feature"
    assert design.tech_stack == ["FastAPI", "PyJWT"]
