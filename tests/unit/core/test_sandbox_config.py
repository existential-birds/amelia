"""Tests for SandboxConfig model and Profile integration."""

from amelia.core.types import DaytonaResources, Profile, SandboxConfig, SandboxMode


class TestSandboxConfig:
    def test_default_mode_is_none(self) -> None:
        config = SandboxConfig()
        assert config.mode == SandboxMode.NONE

    def test_container_mode(self) -> None:
        config = SandboxConfig(mode=SandboxMode.CONTAINER)
        assert config.mode == SandboxMode.CONTAINER

    def test_invalid_mode_rejected(self) -> None:
        import pytest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            SandboxConfig(mode="invalid")  # type: ignore[arg-type]

    def test_default_image(self) -> None:
        config = SandboxConfig()
        assert config.image == "amelia-sandbox:latest"

    def test_network_allowlist_disabled_by_default(self) -> None:
        config = SandboxConfig()
        assert config.network_allowlist_enabled is False

    def test_default_allowed_hosts(self) -> None:
        config = SandboxConfig()
        assert "api.anthropic.com" in config.network_allowed_hosts
        assert "github.com" in config.network_allowed_hosts

    def test_custom_allowed_hosts(self) -> None:
        config = SandboxConfig(network_allowed_hosts=("example.com",))
        assert config.network_allowed_hosts == ("example.com",)


class TestDaytonaSandboxConfig:
    def test_daytona_mode(self) -> None:
        config = SandboxConfig(
            mode=SandboxMode.DAYTONA,
            repo_url="https://github.com/org/repo.git",
        )
        assert config.mode == SandboxMode.DAYTONA

    def test_daytona_resources_defaults(self) -> None:
        r = DaytonaResources()
        assert r.cpu == 2
        assert r.memory == 4
        assert r.disk == 10

    def test_daytona_resources_custom(self) -> None:
        r = DaytonaResources(cpu=4, memory=8, disk=20)
        assert r.cpu == 4

    def test_sandbox_config_daytona_fields(self) -> None:
        config = SandboxConfig(
            mode=SandboxMode.DAYTONA,
            repo_url="https://github.com/org/repo.git",
            daytona_api_url="https://custom.daytona.io/api",
            daytona_target="eu",
            daytona_resources=DaytonaResources(cpu=4),
        )
        assert config.repo_url == "https://github.com/org/repo.git"
        assert config.daytona_api_url == "https://custom.daytona.io/api"
        assert config.daytona_target == "eu"
        assert config.daytona_resources is not None
        assert config.daytona_resources.cpu == 4

    def test_sandbox_config_daytona_fields_default_none(self) -> None:
        config = SandboxConfig()
        assert config.repo_url is None
        assert config.daytona_resources is None

    def test_existing_container_config_unchanged(self) -> None:
        """Daytona fields don't affect existing container configs."""
        config = SandboxConfig(mode=SandboxMode.CONTAINER, image="custom:latest")
        assert config.mode == SandboxMode.CONTAINER
        assert config.repo_url is None


class TestProfileSandboxConfig:
    def test_profile_sandbox_defaults_to_none_mode(self) -> None:
        profile = Profile(name="test", repo_root="/tmp")
        assert profile.sandbox.mode == SandboxMode.NONE

    def test_profile_with_container_sandbox(self) -> None:
        sandbox = SandboxConfig(mode=SandboxMode.CONTAINER)
        profile = Profile(name="test", repo_root="/tmp", sandbox=sandbox)
        assert profile.sandbox.mode == SandboxMode.CONTAINER

    def test_profile_sandbox_is_frozen(self) -> None:
        import pytest
        from pydantic import ValidationError

        profile = Profile(name="test", repo_root="/tmp")
        with pytest.raises(ValidationError):
            profile.sandbox = SandboxConfig(mode=SandboxMode.CONTAINER)
