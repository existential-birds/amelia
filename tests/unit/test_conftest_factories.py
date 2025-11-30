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
