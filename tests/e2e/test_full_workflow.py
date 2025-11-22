import pytest
import yaml
from unittest.mock import patch, AsyncMock, MagicMock
from typer.testing import CliRunner
from amelia.main import app
from amelia.core.state import Task, ReviewResult
from amelia.agents.architect import TaskListResponse
from amelia.core.types import Issue

runner = CliRunner()

@pytest.fixture
def settings_file(tmp_path):
    settings = {
        "active_profile": "default",
        "profiles": {
            "default": {
                "name": "default",
                "driver": "cli:claude", # Use mock cli driver
                "tracker": "noop",
                "strategy": "single"
            }
        }
    }
    p = tmp_path / "settings.yaml"
    with open(p, "w") as f:
        yaml.dump(settings, f)
    return p

def test_full_workflow(settings_file):
    """
    End-to-end test of the full workflow:
    Start -> Fetch Issue (Noop) -> Architect Plan -> Developer Execute -> Review -> Done
    """
    
    mock_driver = AsyncMock()
    mock_driver.timeout = 30 
    mock_driver.max_retries = 0
    
    task_plan = TaskListResponse(tasks=[
        Task(id="T1", description="Do something", dependencies=[])
    ])
    
    review_result = ReviewResult(
        reviewer_persona="Senior Dev", 
        approved=True, 
        comments=["Looks good"],
        severity="low"
    )
    
    async def generate_side_effect(messages, schema=None):
        full_content = " ".join([m.content for m in messages])
        
        # Simple heuristic to identify the agent
        if "TaskDAG" in str(schema) or "TaskListResponse" in str(schema) or "expert software architect" in full_content:
             return task_plan
        elif "ReviewResult" in str(schema) or "code reviewer" in full_content:
             return review_result
        else:
             # Developer or generic
             return "Executed successfully"

    mock_driver.generate.side_effect = generate_side_effect
    mock_driver.execute_tool.return_value = "Tool output"

    with patch("amelia.drivers.factory.DriverFactory.get_driver", return_value=mock_driver):
         with runner.isolated_filesystem(temp_dir=settings_file.parent):
             # Ensure settings.yaml is in the CWD
             with open("settings.yaml", "w") as f:
                with open(settings_file) as src:
                    f.write(src.read())
             
             # Run amelia start PROJ-123
             # Providing "y\n\n" for potential plan approval prompt and optional comment
             result = runner.invoke(app, ["start", "PROJ-123"], input="y\n\n")
             
             if result.exit_code != 0:
                 print("STDOUT:", result.stdout)
                 print("STDERR:", result.stderr)
             
             assert result.exit_code == 0