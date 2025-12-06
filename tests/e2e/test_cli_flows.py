from unittest.mock import AsyncMock, patch

import yaml
from typer.testing import CliRunner

from amelia.agents.architect import TaskListResponse
from amelia.core.state import Task
from amelia.main import app


runner = CliRunner()


def test_cli_plan_only_command(settings_file_factory):
    """
    Verifies that 'amelia plan-only' command generates and prints a plan.
    """
    settings_data = {
        "active_profile": "default",
        "profiles": {
            "default": {"name": "default", "driver": "cli:claude", "tracker": "noop", "strategy": "single"}
        }
    }
    settings_path = settings_file_factory(settings_data)

    with runner.isolated_filesystem(temp_dir=settings_path.parent):
        with open("settings.amelia.yaml", "w") as f:
            yaml.dump(settings_data, f)

        with patch('amelia.drivers.cli.claude.ClaudeCliDriver.generate') as mock_generate:
            mock_generate.side_effect = AsyncMock(return_value=TaskListResponse(tasks=[
                Task(id="T1", description="Mock task 1", dependencies=[]),
                Task(id="T2", description="Mock task 2", dependencies=["T1"])
            ]))

            result = runner.invoke(app, ["plan-only", "PROJ-123"])

            assert result.exit_code == 0
            assert "--- GENERATED PLAN ---" in result.stdout
            assert "- [T1] Mock task 1" in result.stdout
            assert "- [T2] Mock task 2 (Dependencies: T1)" in result.stdout
