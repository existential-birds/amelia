"""Tests for SandboxConfig model and Profile integration."""

from amelia.core.types import Profile, SandboxConfig


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
        assert config.network_allowed_hosts == ["example.com"]


class TestProfileSandboxConfig:
    def test_profile_sandbox_defaults_to_none_mode(self):
        profile = Profile(name="test", working_dir="/tmp")
        assert profile.sandbox.mode == "none"

    def test_profile_with_container_sandbox(self):
        sandbox = SandboxConfig(mode="container")
        profile = Profile(name="test", working_dir="/tmp", sandbox=sandbox)
        assert profile.sandbox.mode == "container"

    def test_profile_sandbox_is_frozen(self):
        import pytest
        from pydantic import ValidationError

        profile = Profile(name="test", working_dir="/tmp")
        with pytest.raises(ValidationError):
            profile.sandbox = SandboxConfig(mode="container")
