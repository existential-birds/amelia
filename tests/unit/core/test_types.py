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
        repo_root="/tmp/test",
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
        repo_root="/tmp/test",
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


def test_agent_config_sandbox_default():
    """AgentConfig should default sandbox to SandboxConfig() with mode='none'."""
    from amelia.core.types import AgentConfig, SandboxConfig

    config = AgentConfig(driver="cli", model="sonnet")
    assert config.sandbox == SandboxConfig()
    assert config.sandbox.mode == "none"


def test_agent_config_profile_name_default():
    """AgentConfig should default profile_name to 'default'."""
    from amelia.core.types import AgentConfig

    config = AgentConfig(driver="cli", model="sonnet")
    assert config.profile_name == "default"


def test_agent_config_with_sandbox_config():
    """AgentConfig should accept explicit SandboxConfig."""
    from amelia.core.types import AgentConfig, SandboxConfig

    sandbox = SandboxConfig(mode="container", image="custom:latest")
    config = AgentConfig(
        driver="api", model="test-model",
        sandbox=sandbox, profile_name="work",
    )
    assert config.sandbox.mode == "container"
    assert config.sandbox.image == "custom:latest"
    assert config.profile_name == "work"


def test_get_agent_config_injects_sandbox():
    """get_agent_config should inject profile's sandbox config into AgentConfig."""
    from amelia.core.types import AgentConfig, Profile, SandboxConfig

    sandbox = SandboxConfig(mode="container", image="custom:latest")
    profile = Profile(
        name="work",
        tracker="noop",
        repo_root="/tmp/test",
        sandbox=sandbox,
        agents={"architect": AgentConfig(driver="api", model="opus")},
    )

    config = profile.get_agent_config("architect")
    assert config.sandbox.mode == "container"
    assert config.sandbox.image == "custom:latest"
    assert config.profile_name == "work"


def test_get_agent_config_injects_profile_name():
    """get_agent_config should set profile_name to profile.name."""
    from amelia.core.types import AgentConfig, Profile

    profile = Profile(
        name="personal",
        tracker="noop",
        repo_root="/tmp/test",
        agents={"developer": AgentConfig(driver="cli", model="sonnet")},
    )

    config = profile.get_agent_config("developer")
    assert config.profile_name == "personal"


def test_get_agent_config_preserves_original():
    """get_agent_config should not mutate the stored AgentConfig."""
    from amelia.core.types import AgentConfig, Profile, SandboxConfig

    sandbox = SandboxConfig(mode="container")
    original = AgentConfig(driver="api", model="opus")
    profile = Profile(
        name="work",
        tracker="noop",
        repo_root="/tmp/test",
        sandbox=sandbox,
        agents={"architect": original},
    )

    injected = profile.get_agent_config("architect")
    assert injected is not original
    assert original.sandbox.mode == "none"  # Original unchanged
    assert original.profile_name == "default"  # Original unchanged
    assert injected.sandbox.mode == "container"  # Injected has profile's sandbox
