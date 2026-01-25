"""Unit tests for amelia.core.types module."""

from pathlib import Path

from amelia.core.types import Design


def test_agent_config_creation():
    """AgentConfig should store driver, model, and optional options."""
    from amelia.core.types import AgentConfig

    config = AgentConfig(driver="cli", model="sonnet")
    assert config.driver == "cli"
    assert config.model == "sonnet"
    assert config.options == {}


def test_agent_config_with_options():
    """AgentConfig should accept arbitrary options dict."""
    from amelia.core.types import AgentConfig

    config = AgentConfig(
        driver="api",
        model="anthropic/claude-sonnet-4",
        options={"max_iterations": 5, "temperature": 0.7},
    )
    assert config.options["max_iterations"] == 5
    assert config.options["temperature"] == 0.7


def test_profile_with_agents_dict():
    """Profile should accept agents dict configuration."""
    from amelia.core.types import AgentConfig, Profile

    profile = Profile(
        name="test",
        tracker="noop",
        working_dir="/tmp/test",
        agents={
            "architect": AgentConfig(driver="cli", model="opus"),
            "developer": AgentConfig(driver="cli", model="sonnet"),
        },
    )
    assert profile.agents["architect"].model == "opus"
    assert profile.agents["developer"].model == "sonnet"


def test_profile_get_agent_config():
    """Profile.get_agent_config should return config or raise if missing."""
    from amelia.core.types import AgentConfig, Profile

    profile = Profile(
        name="test",
        tracker="noop",
        working_dir="/tmp/test",
        agents={
            "architect": AgentConfig(driver="cli", model="opus"),
        },
    )

    config = profile.get_agent_config("architect")
    assert config.model == "opus"

    import pytest
    with pytest.raises(ValueError, match="Agent 'developer' not configured"):
        profile.get_agent_config("developer")


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
