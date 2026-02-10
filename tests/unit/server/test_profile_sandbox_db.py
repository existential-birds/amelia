"""Tests for SandboxConfig persistence in ProfileRepository."""


from amelia.core.types import SandboxConfig


class TestProfileSandboxSerialization:
    def test_sandbox_config_serializes_to_dict(self) -> None:
        """Verify SandboxConfig model_dump produces expected dict."""
        config = SandboxConfig(mode="container", image="custom:latest")
        data = config.model_dump()
        assert data["mode"] == "container"
        assert data["image"] == "custom:latest"

    def test_sandbox_config_roundtrips_through_json(self) -> None:
        """Verify SandboxConfig survives JSON serialization roundtrip."""
        config = SandboxConfig(
            mode="container",
            network_allowlist_enabled=True,
            network_allowed_hosts=["example.com"],
        )
        json_str = config.model_dump_json()
        restored = SandboxConfig.model_validate_json(json_str)
        assert restored == config

    def test_default_sandbox_config_roundtrips(self) -> None:
        """Verify default SandboxConfig roundtrips through model_dump."""
        config = SandboxConfig()
        data = config.model_dump()
        restored = SandboxConfig(**data)
        assert restored.mode == "none"

    def test_profile_with_sandbox_serializes(self) -> None:
        """Verify Profile with sandbox config serializes correctly."""
        from amelia.core.types import AgentConfig, DriverType, Profile

        profile = Profile(
            name="test",
            working_dir="/tmp",
            sandbox=SandboxConfig(mode="container"),
            agents={
                "developer": AgentConfig(
                    driver=DriverType.API,
                    model="test-model",
                ),
            },
        )
        data = profile.model_dump()
        assert data["sandbox"]["mode"] == "container"
