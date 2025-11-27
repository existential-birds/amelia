import subprocess
from unittest.mock import AsyncMock
from unittest.mock import patch

import pytest
import yaml
from typer.testing import CliRunner

from amelia.agents.architect import TaskListResponse
from amelia.core.state import Task
from amelia.main import app


runner = CliRunner()


@pytest.fixture
def create_settings_file(tmp_path):
    def _creator(settings_data):
        settings_path = tmp_path / "settings.amelia.yaml"
        with open(settings_path, "w") as f:
            yaml.dump(settings_data, f)
        return settings_path
    return _creator


# Parametrized test data for CLI start command
CLI_START_TEST_CASES = [
    pytest.param(
        {
            "active_profile": "default",
            "profiles": {
                "default": {"name": "default", "driver": "cli:claude", "tracker": "none", "strategy": "single"},
                "work": {"name": "work", "driver": "cli:claude", "tracker": "jira", "strategy": "single"}
            }
        },
        ["start", "--profile", "work", "TEST-123"],
        id="work_profile"
    ),
    pytest.param(
        {
            "active_profile": "home",
            "profiles": {
                "home": {"name": "home", "driver": "api:openai", "tracker": "github", "strategy": "competitive"}
            }
        },
        ["start", "TEST-456"],
        id="default_profile"
    ),
    pytest.param(
        {
            "active_profile": "default",
            "profiles": {
                "default": {"name": "default", "driver": "cli:claude", "tracker": "none", "strategy": "single"},
                "home_api": {"name": "home_api", "driver": "api:openai", "tracker": "github", "strategy": "competitive"}
            }
        },
        ["start", "--profile", "home_api", "TEST-789"],
        id="home_api_profile"
    ),
    pytest.param(
        {
            "active_profile": "default",
            "profiles": {
                "default": {"name": "default", "driver": "cli:claude", "tracker": "none", "strategy": "single"},
                "hybrid_dev": {"name": "hybrid_dev", "driver": "api:openai", "tracker": "jira", "strategy": "single"}
            }
        },
        ["start", "--profile", "hybrid_dev", "TEST-ABC"],
        id="hybrid_profile"
    ),
]


@pytest.mark.parametrize("settings_data,cli_args", CLI_START_TEST_CASES)
def test_cli_start_commands(create_settings_file, settings_data, cli_args):
    """Parametrized test for CLI start command with different profile configurations."""
    settings_path = create_settings_file(settings_data)

    with runner.isolated_filesystem(temp_dir=settings_path.parent):
        create_settings_file(settings_data)
        result = runner.invoke(app, cli_args)
        assert result.exit_code != 0
        assert "Error" in result.stderr or "Missing command" in result.stderr


def test_cli_review_local_output(create_settings_file):
    """
    Verifies that 'amelia review --local' outputs review suggestions to stdout
    when executed in a 'Work' profile.
    """
    settings_data = {
        "active_profile": "work",
        "profiles": {
            "work": {"name": "work", "driver": "cli:claude", "tracker": "none", "strategy": "single"}
        }
    }
    settings_path = create_settings_file(settings_data)

    with runner.isolated_filesystem(temp_dir=settings_path.parent):
        create_settings_file(settings_data)

        # Setup git repo
        subprocess.run(["git", "init"], check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "you@example.com"], check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Your Name"], check=True, capture_output=True)

        # Create file and commit
        with open("test.txt", "w") as f:
            f.write("initial content")
        subprocess.run(["git", "add", "test.txt"], check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "initial"], check=True, capture_output=True)

        # Make change (unstaged)
        with open("test.txt", "w") as f:
            f.write("changed content")

        # Write settings.amelia.yaml to CWD
        with open("settings.amelia.yaml", "w") as f:
            yaml.dump(settings_data, f)

        from amelia.agents.reviewer import ReviewResponse

        with patch("amelia.drivers.factory.DriverFactory.get_driver") as mock_get_driver:
            mock_driver = AsyncMock()
            mock_driver.generate.return_value = ReviewResponse(
                approved=False,
                comments=["Change is bad"],
                severity="medium"
            )
            mock_get_driver.return_value = mock_driver

            result = runner.invoke(app, ["review", "--local"])

            if result.exit_code != 0:
                print(result.stdout)
                print(result.stderr)

            assert result.exit_code == 0
            assert "Starting Amelia Review process" in result.stdout
            assert "Found local changes" in result.stdout
            assert "Reviewer completed review" in result.stdout or "REVIEW RESULT" in result.stdout
            assert "Change is bad" in result.stdout


def test_cli_plan_only_command(create_settings_file):
    """
    Verifies that 'amelia plan-only' command generates and prints a plan.
    """
    settings_data = {
        "active_profile": "default",
        "profiles": {
            "default": {"name": "default", "driver": "cli:claude", "tracker": "noop", "strategy": "single"}
        }
    }
    settings_path = create_settings_file(settings_data)

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
