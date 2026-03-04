"""Tests for SandboxConfig model and Profile integration."""

from amelia.core.types import DaytonaResources, Profile, SandboxConfig


class TestSandboxConfig:
    def test_default_mode_is_none(self):
        config = SandboxConfig()
        assert config.mode == "none"

    def test_container_mode(self):
        config = SandboxConfig(mode="container")
        assert config.mode == "container"

    def test_invalid_mode_rejected(self):
        import pytest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            SandboxConfig(mode="invalid")

    def test_default_image(self):
        config = SandboxConfig()
        assert config.image == "amelia-sandbox:latest"

    def test_network_allowlist_disabled_by_default(self):
        config = SandboxConfig()
        assert config.network_allowlist_enabled is False

    def test_default_allowed_hosts(self):
        config = SandboxConfig()
        assert "api.anthropic.com" in config.network_allowed_hosts
        assert "github.com" in config.network_allowed_hosts

    def test_custom_allowed_hosts(self):
        config = SandboxConfig(network_allowed_hosts=["example.com"])
        assert config.network_allowed_hosts == ("example.com",)


class TestDaytonaSandboxConfig:
    def test_daytona_mode(self):
        config = SandboxConfig(mode="daytona")
        assert config.mode == "daytona"

    def test_daytona_resources_defaults(self):
        r = DaytonaResources()
        assert r.cpu == 2
        assert r.memory == 4
        assert r.disk == 10

    def test_daytona_resources_custom(self):
        r = DaytonaResources(cpu=4, memory=8, disk=20)
        assert r.cpu == 4

    def test_sandbox_config_daytona_fields(self):
        config = SandboxConfig(
            mode="daytona",
            repo_url="https://github.com/org/repo.git",
            daytona_api_url="https://custom.daytona.io/api",
            daytona_target="eu",
            daytona_resources=DaytonaResources(cpu=4),
        )
        assert config.repo_url == "https://github.com/org/repo.git"
        assert config.daytona_api_url == "https://custom.daytona.io/api"
        assert config.daytona_target == "eu"
        assert config.daytona_resources.cpu == 4

    def test_sandbox_config_daytona_fields_default_none(self):
        config = SandboxConfig()
        assert config.repo_url is None
        assert config.daytona_resources is None

    def test_existing_container_config_unchanged(self):
        """Daytona fields don't affect existing container configs."""
        config = SandboxConfig(mode="container", image="custom:latest")
        assert config.mode == "container"
        assert config.repo_url is None


class TestProfileSandboxConfig:
    def test_profile_sandbox_defaults_to_none_mode(self):
        profile = Profile(name="test", repo_root="/tmp")
        assert profile.sandbox.mode == "none"

    def test_profile_with_container_sandbox(self):
        sandbox = SandboxConfig(mode="container")
        profile = Profile(name="test", repo_root="/tmp", sandbox=sandbox)
        assert profile.sandbox.mode == "container"

    def test_profile_sandbox_is_frozen(self):
        import pytest
        from pydantic import ValidationError

        profile = Profile(name="test", repo_root="/tmp")
        with pytest.raises(ValidationError):
            profile.sandbox = SandboxConfig(mode="container")
