import pytest
from typer.testing import CliRunner
import yaml
from unittest.mock import patch, AsyncMock

from amelia.main import app
from amelia.agents.architect import TaskListResponse
from amelia.core.state import Task

runner = CliRunner()

@pytest.fixture
def create_settings_file(tmp_path):
    def _creator(settings_data):
        settings_path = tmp_path / "settings.amelia.yaml"
        with open(settings_path, "w") as f:
            yaml.dump(settings_data, f)
        return settings_path
    return _creator

def test_cli_start_with_profile(create_settings_file):
    settings_data = {
        "active_profile": "default",
        "profiles": {
            "default": {
                "name": "default",
                "driver": "cli:claude",
                "tracker": "none",
                "strategy": "single"
            },
            "work": {
                "name": "work",
                "driver": "cli:claude",
                "tracker": "jira",
                "strategy": "single"
            }
        }
    }
    settings_path = create_settings_file(settings_data)

    # Mock settings.amelia.yaml path for CLI, typically done via env var or explicit param
    # For now, we will assume a mechanism to tell the CLI where to find settings.amelia.yaml
    # Or rely on the default CWD behavior of load_settings in amelia.config
    # Temporarily change current working directory for the test
    with runner.isolated_filesystem(temp_dir=settings_path.parent):
        # Create a dummy settings.amelia.yaml in the isolated filesystem
        create_settings_file(settings_data) # Re-create in isolated_filesystem's tmp_path

        result = runner.invoke(app, ["start", "--profile", "work", "TEST-123"])
        # Expecting it to fail for now, as 'start' command and actual logic is not there
        # but we can check for specific error messages or a successful path later
        assert result.exit_code != 0
        assert "Error" in result.stderr or "Missing command" in result.stderr

def test_cli_start_default_profile(create_settings_file):
    settings_data = {
        "active_profile": "home",
        "profiles": {
            "home": {
                "name": "home",
                "driver": "api:openai",
                "tracker": "github",
                "strategy": "competitive"
            }
        }
    }
    settings_path = create_settings_file(settings_data)

    with runner.isolated_filesystem(temp_dir=settings_path.parent):
        create_settings_file(settings_data)
        result = runner.invoke(app, ["start", "TEST-456"]) # No --profile, should use active_profile
        assert result.exit_code != 0
        assert "Error" in result.stderr or "Missing command" in result.stderr

def test_cli_start_home_profile_api(create_settings_file):
    settings_data = {
        "active_profile": "default",
        "profiles": {
            "default": {
                "name": "default",
                "driver": "cli:claude",
                "tracker": "none",
                "strategy": "single"
            },
            "home_api": {
                "name": "home_api",
                "driver": "api:openai",
                "tracker": "github",
                "strategy": "competitive"
            }
        }
    }
    settings_path = create_settings_file(settings_data)

    with runner.isolated_filesystem(temp_dir=settings_path.parent):
        create_settings_file(settings_data)
        result = runner.invoke(app, ["start", "--profile", "home_api", "TEST-789"])
        assert result.exit_code != 0
        assert "Error" in result.stderr or "Missing command" in result.stderr

def test_cli_start_hybrid_profile(create_settings_file):
    settings_data = {
        "active_profile": "default",
        "profiles": {
            "default": {
                "name": "default",
                "driver": "cli:claude",
                "tracker": "none",
                "strategy": "single"
            },
            "hybrid_dev": {
                "name": "hybrid_dev",
                "driver": "api:openai",  # API for dev, but might use CLI tools
                "tracker": "jira",
                "strategy": "single"
            }
        }
    }
    settings_path = create_settings_file(settings_data)

    with runner.isolated_filesystem(temp_dir=settings_path.parent):
        create_settings_file(settings_data)
        result = runner.invoke(app, ["start", "--profile", "hybrid_dev", "TEST-ABC"])
        assert result.exit_code != 0
        assert "Error" in result.stderr or "Missing command" in result.stderr


# ... imports

def test_cli_review_local_output(create_settings_file):
    """
    Verifies that 'amelia review --local' outputs review suggestions to stdout
    when executed in a 'Work' profile.
    """
    settings_data = {
        "active_profile": "work",
        "profiles": {
            "work": {
                "name": "work",
                "driver": "cli:claude",
                "tracker": "none",
                "strategy": "single"
            }
        }
    }
    settings_path = create_settings_file(settings_data)

    with runner.isolated_filesystem(temp_dir=settings_path.parent):
        create_settings_file(settings_data)
        
        # Setup git repo
        import subprocess
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
            
        # Explicitly write settings.amelia.yaml to CWD
        import os
        with open("settings.amelia.yaml", "w") as f:
            yaml.dump(settings_data, f)
        
        print(f"DEBUG: CWD={os.getcwd()}")
        print(f"DEBUG: Files={os.listdir()}")
        
        # Mock the driver to return a review result so the command finishes successfully
        # We need to patch the driver used by 'review' command. 
        # 'review' uses call_reviewer_node -> Reviewer -> driver.
        # Since profile is 'cli:claude', we patch ClaudeCliDriver (or just DriverFactory)
        
        from amelia.agents.reviewer import ReviewResponse
        
        # We need to mock the driver instance that is created inside the review command
        with patch("amelia.drivers.factory.DriverFactory.get_driver") as mock_get_driver:
            mock_driver = AsyncMock()
            mock_driver.generate.return_value = ReviewResponse(
                approved=False, 
                comments=["Change is bad"], 
                severity="medium"
            )
            mock_get_driver.return_value = mock_driver
            
            # Need to patch get_git_diff? No, we set up real git repo, let's try using real tool.
            # But amelia.tools.git.get_git_diff is async and uses asyncio.create_subprocess_shell.
            # runner.invoke is synchronous. It runs the app. 
            # The app 'review' command is async?
            # amelia/main.py: @app.command() async def review(...)
            # Typer doesn't natively support async commands without a wrapper or just running them.
            # But our 'review' command implementation does:
            #   if local: ... code_changes = await get_git_diff(...)
            # Wait, if 'start' command had issues with asyncio.run, 'review' might too.
            # main.py handles async by using asyncio.run() explicitly?
            # No, the 'review' command is defined as `async def review`. Typer will try to run it?
            # Typer (via Click) doesn't auto-run async functions. We need to wrap it or use asyncio.run inside a sync function.
            
            # Let's check main.py review command definition.
            
            result = runner.invoke(app, ["review", "--local"])
            
            # If the command failed due to async execution issues, exit code might be != 0
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
            "default": {
                "name": "default",
                "driver": "cli:claude", # Using cli:claude, but mock its generate method
                "tracker": "noop",
                "strategy": "single"
            }
        }
    }
    settings_path = create_settings_file(settings_data)

    with runner.isolated_filesystem(temp_dir=settings_path.parent):
        # Explicitly write settings.amelia.yaml to CWD
        with open("settings.amelia.yaml", "w") as f:
            yaml.dump(settings_data, f)
        
        # Mock the driver.generate method to return a predictable plan
        with patch('amelia.drivers.cli.claude.ClaudeCliDriver.generate') as mock_generate:
            # Need to mock AsyncMock because Architect awaits it
            mock_generate.side_effect = AsyncMock(return_value=TaskListResponse(tasks=[
                Task(id="T1", description="Mock task 1", dependencies=[]),
                Task(id="T2", description="Mock task 2", dependencies=["T1"])
            ]))
            
            result = runner.invoke(app, ["plan-only", "PROJ-123"])
            
            assert result.exit_code == 0
            assert "--- GENERATED PLAN ---" in result.stdout
            assert "- [T1] Mock task 1" in result.stdout
            assert "- [T2] Mock task 2 (Dependencies: T1)" in result.stdout
            mock_generate.side_effect = AsyncMock(return_value=TaskListResponse(tasks=[
                Task(id="T1", description="Mock task 1", dependencies=[]),
                Task(id="T2", description="Mock task 2", dependencies=["T1"])
            ]))
            
            result = runner.invoke(app, ["plan-only", "PROJ-123"])
            
            assert result.exit_code == 0
            assert "--- GENERATED PLAN ---" in result.stdout
            assert "- [T1] Mock task 1" in result.stdout
            assert "- [T2] Mock task 2 (Dependencies: T1)" in result.stdout

