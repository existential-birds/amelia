
from typer.testing import CliRunner

from amelia.main import app


runner = CliRunner()


def test_plan_only_accepts_design_flag() -> None:
    """Verify --design flag is accepted and parsed correctly."""
    result = runner.invoke(app, ["plan-only", "TEST-1", "--design", "/tmp/test.md"])
    # The flag should be recognized - it should NOT show "No such option" error
    # It may fail for other reasons (settings, file not found), but the flag itself should be valid
    if result.exit_code != 0:
        # If it failed, it should NOT be due to unknown option
        assert "No such option: --design" not in result.output, "The --design flag should be recognized"
