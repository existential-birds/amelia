"""Unit tests for amelia.core.types module."""

from pathlib import Path

from amelia.core.types import Design, Profile


def test_agent_config_creation():
    """AgentConfig should store driver, model, and optional options."""
    from amelia.core.types import AgentConfig

    config = AgentConfig(driver="cli:claude", model="sonnet")
    assert config.driver == "cli:claude"
    assert config.model == "sonnet"
    assert config.options == {}


def test_agent_config_with_options():
    """AgentConfig should accept arbitrary options dict."""
    from amelia.core.types import AgentConfig

    config = AgentConfig(
        driver="api:openrouter",
        model="anthropic/claude-sonnet-4",
        options={"max_iterations": 5, "temperature": 0.7},
    )
    assert config.options["max_iterations"] == 5
    assert config.options["temperature"] == 0.7


def test_profile_max_task_review_iterations_default():
    """Profile should have max_task_review_iterations with default value."""
    profile = Profile(
        name="test",
        driver="cli:claude",
        model="sonnet",
        validator_model="sonnet",
        working_dir="/tmp/test",
    )

    assert profile.max_task_review_iterations == 5


def test_profile_max_task_review_iterations_override():
    """Profile max_task_review_iterations should be configurable."""
    profile = Profile(
        name="test",
        driver="cli:claude",
        model="sonnet",
        validator_model="sonnet",
        working_dir="/tmp/test",
        max_task_review_iterations=10,
    )

    assert profile.max_task_review_iterations == 10


class TestDesign:
    """Tests for Design model."""

    def test_design_creation(self) -> None:
        """Design should store content and source."""
        design = Design(content="# My Design\n\nDetails here.", source="import")
        assert design.content == "# My Design\n\nDetails here."
        assert design.source == "import"

    def test_design_default_source(self) -> None:
        """Design should default source to 'import'."""
        design = Design(content="content")
        assert design.source == "import"

    def test_design_from_file(self, tmp_path: Path) -> None:
        """Design.from_file should load markdown content."""
        design_file = tmp_path / "design.md"
        design_file.write_text("# Design from file\n\nLoaded.", encoding="utf-8")

        design = Design.from_file(design_file)
        assert design.content == "# Design from file\n\nLoaded."
        assert design.source == "file"

    def test_design_from_file_str_path(self, tmp_path: Path) -> None:
        """Design.from_file should accept string paths."""
        design_file = tmp_path / "design.md"
        design_file.write_text("content", encoding="utf-8")

        design = Design.from_file(str(design_file))
        assert design.content == "content"
