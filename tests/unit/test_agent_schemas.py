import pytest
from pydantic import ValidationError

from amelia.agents.architect import TaskListResponse
from amelia.agents.reviewer import ReviewResponse  # Import ReviewResponse


def test_architect_task_list_response_valid():
    """
    Tests valid TaskListResponse from Architect agent.
    """
    valid_data = {
        "tasks": [
            {"id": "task_1", "description": "First task", "dependencies": []},
            {"id": "task_2", "description": "Second task", "dependencies": ["task_1"]}
        ]
    }
    response = TaskListResponse(**valid_data)
    assert len(response.tasks) == 2
    assert response.tasks[0].id == "task_1"
    assert response.tasks[1].dependencies == ["task_1"]

def test_architect_task_list_response_invalid_task_structure():
    """
    Tests invalid TaskListResponse (e.g., malformed Task) from Architect agent.
    """
    invalid_data_missing_id = {
        "tasks": [
            {"description": "Task without ID", "dependencies": []}
        ]
    }
    with pytest.raises(ValidationError):
        TaskListResponse(**invalid_data_missing_id)

    invalid_data_wrong_type = {
        "tasks": [
            {"id": 123, "description": "ID is int", "dependencies": []}
        ]
    }
    with pytest.raises(ValidationError):
        TaskListResponse(**invalid_data_wrong_type)

def test_reviewer_response_schema_valid():
    """
    Tests valid ReviewResponse from Reviewer agent.
    """
    valid_data = {
        "approved": True,
        "comments": ["Looks good", "Minor style nit"],
        "severity": "low"
    }
    response = ReviewResponse(**valid_data)
    assert response.approved is True
    assert len(response.comments) == 2
    assert response.severity == "low"

def test_reviewer_response_schema_invalid_severity():
    """
    Tests invalid ReviewResponse (invalid severity).
    """
    invalid_data = {
        "approved": False,
        "comments": [],
        "severity": "catastrophic" # Invalid enum value
    }
    with pytest.raises(ValidationError):
        ReviewResponse(**invalid_data)

@pytest.mark.skip(reason="Developer agent's output schema not yet defined.")
def test_developer_output_schema_validation():
    """
    Tests validation for the Developer agent's output schema.
    """
    pass

