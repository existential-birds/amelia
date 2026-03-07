"""Unit tests for the driver factory."""
import os
from unittest.mock import MagicMock, patch

import pytest

from amelia.core.types import SandboxConfig, SandboxMode
from amelia.drivers.factory import cleanup_driver_session, create_daytona_provider, get_driver


class TestGetDriverExistingBehavior:
    """Existing behavior must be preserved with the new signature."""

    @pytest.mark.parametrize(
        "driver_key,expected_class",
        [
            ("claude", "ClaudeCliDriver"),
            ("codex", "CodexCliDriver"),
            ("api", "ApiDriver"),
        ],
    )
    def test_get_driver_routes_explicit_driver_keys(self, driver_key: str, expected_class: str) -> None:
        """get_driver should route to correct driver class for explicit keys."""
        with patch(f"amelia.drivers.factory.{expected_class}") as mock_cls:
            mock_cls.return_value = MagicMock()
            _driver = get_driver(driver_key, model="test-model")
            mock_cls.assert_called_once()
            kwargs = mock_cls.call_args.kwargs
            assert kwargs["model"] == "test-model"

    def test_get_driver_rejects_legacy_cli(self) -> None:
        """Legacy 'cli' driver key should raise clear error."""
        with pytest.raises(ValueError, match="Valid options: 'claude', 'codex', 'api'"):
            get_driver("cli")

    def test_api_driver(self) -> None:
        with patch("amelia.drivers.factory.ApiDriver") as mock_cls:
            mock_cls.return_value = MagicMock()
            _driver = get_driver("api", model="test-model")
            mock_cls.assert_called_once_with(provider="openrouter", model="test-model")

    def test_unknown_driver_raises(self) -> None:
        with pytest.raises(ValueError, match=r"Unknown driver key: 'unknown'\."):
            get_driver("unknown")


class TestGetDriverContainerBranch:
    """Container sandbox driver creation."""

    def test_container_mode_returns_container_driver(self) -> None:
        sandbox = SandboxConfig(mode=SandboxMode.CONTAINER, image="test:latest")
        with patch("amelia.sandbox.docker.DockerSandboxProvider") as mock_provider_cls, \
             patch("amelia.sandbox.driver.ContainerDriver") as mock_driver_cls:
            mock_driver_cls.return_value = MagicMock()
            _driver = get_driver(
                "api", model="test-model",
                sandbox_config=sandbox, profile_name="work",
            )
            mock_provider_cls.assert_called_once_with(
                profile_name="work",
                image="test:latest",
                network_allowlist_enabled=False,
                network_allowed_hosts=sandbox.network_allowed_hosts,
            )
            mock_driver_cls.assert_called_once_with(
                model="test-model",
                provider=mock_provider_cls.return_value,
            )

    @pytest.mark.parametrize("driver_key", ["claude", "codex"])
    def test_container_mode_rejects_cli_wrappers(self, driver_key: str) -> None:
        """Container sandbox should reject CLI wrapper drivers."""
        sandbox = SandboxConfig(mode=SandboxMode.CONTAINER)
        with pytest.raises(ValueError, match="Container sandbox requires API driver"):
            get_driver(driver_key, sandbox_config=sandbox, profile_name="test")

    def test_none_mode_returns_normal_driver(self) -> None:
        sandbox = SandboxConfig(mode=SandboxMode.NONE)
        with patch("amelia.drivers.factory.ApiDriver") as mock_cls:
            mock_cls.return_value = MagicMock()
            _driver = get_driver("api", model="test-model", sandbox_config=sandbox)
            mock_cls.assert_called_once_with(provider="openrouter", model="test-model")

    def test_no_sandbox_config_returns_normal_driver(self) -> None:
        with patch("amelia.drivers.factory.ApiDriver") as mock_cls:
            mock_cls.return_value = MagicMock()
            _driver = get_driver("api", model="test-model")
            mock_cls.assert_called_once_with(provider="openrouter", model="test-model")


class TestLegacyDriverRejection:
    """Legacy driver forms should be rejected with clear errors."""

    def test_legacy_cli_driver_rejected(self) -> None:
        """Legacy cli:claude driver form should raise clear error."""
        with pytest.raises(
            ValueError,
            match=r"Unknown driver key: 'cli:claude'.*Legacy forms.*no longer supported",
        ):
            get_driver("cli:claude", model="test-model")

    def test_legacy_api_driver_rejected(self) -> None:
        """Legacy api:openrouter driver form should raise clear error."""
        with pytest.raises(
            ValueError,
            match=r"Unknown driver key: 'api:openrouter'.*Legacy forms.*no longer supported",
        ):
            get_driver("api:openrouter", model="test-model")

    @pytest.mark.asyncio
    async def test_legacy_cleanup_driver_rejected(self) -> None:
        """Legacy driver values should be rejected in cleanup."""
        with pytest.raises(
            ValueError,
            match=r"Unknown driver key: 'cli:claude'",
        ):
            await cleanup_driver_session("cli:claude", "test-session-id")

        with pytest.raises(
            ValueError,
            match=r"Unknown driver key: 'api:openrouter'",
        ):
            await cleanup_driver_session("api:openrouter", "test-session-id")

    @pytest.mark.asyncio
    async def test_cleanup_driver_session_codex_returns_false(self) -> None:
        """cleanup_driver_session should return False for codex driver."""
        result = await cleanup_driver_session("codex", "any-session-id")
        assert result is False


class TestGetDriverDaytonaBranch:
    """Daytona sandbox driver creation."""

    def test_daytona_mode_returns_container_driver(self) -> None:
        sandbox = SandboxConfig(
            mode=SandboxMode.DAYTONA,
            repo_url="https://github.com/org/repo.git",
            daytona_api_url="https://test.daytona.io/api",
            daytona_target="eu",
        )
        with patch("amelia.sandbox.daytona.DaytonaSandboxProvider") as mock_provider_cls, \
             patch("amelia.sandbox.driver.ContainerDriver") as mock_driver_cls, \
             patch.dict(os.environ, {"DAYTONA_API_KEY": "test-key", "OPENROUTER_API_KEY": "or-test-key"}, clear=True):
            mock_driver_cls.return_value = MagicMock()
            _driver = get_driver(
                "api", model="test-model",
                sandbox_config=sandbox, profile_name="work",
            )
            mock_provider_cls.assert_called_once_with(
                api_key="test-key",
                api_url="https://test.daytona.io/api",
                target="eu",
                repo_url="https://github.com/org/repo.git",
                resources=None,
                image="python:3.12-slim",
                snapshot=None,
                timeout=120.0,
                retry_config=None,
                git_token=None,
                worker_env={
                    "LLM_PROXY_URL": "https://openrouter.ai/api/v1",
                    "OPENAI_API_KEY": "or-test-key",
                    "OPENROUTER_SITE_URL": "https://github.com/existential-birds/amelia",
                    "OPENROUTER_SITE_NAME": "Amelia",
                },
            )
            mock_driver_cls.assert_called_once_with(
                model="test-model",
                provider=mock_provider_cls.return_value,
                env={
                    "LLM_PROXY_URL": "https://openrouter.ai/api/v1",
                    "OPENAI_API_KEY": "or-test-key",
                    "OPENROUTER_SITE_URL": "https://github.com/existential-birds/amelia",
                    "OPENROUTER_SITE_NAME": "Amelia",
                },
            )

    def test_daytona_mode_missing_api_key_raises(self) -> None:
        sandbox = SandboxConfig(mode=SandboxMode.DAYTONA, repo_url="https://github.com/org/repo.git")
        with patch.dict(os.environ, {}, clear=True), \
             pytest.raises(ValueError, match="DAYTONA_API_KEY"):
            get_driver("api", sandbox_config=sandbox, profile_name="test")

    @pytest.mark.parametrize("driver_key", ["claude", "codex"])
    def test_daytona_mode_rejects_cli_wrappers(self, driver_key: str) -> None:
        sandbox = SandboxConfig(mode=SandboxMode.DAYTONA, repo_url="https://github.com/org/repo.git")
        with patch.dict(os.environ, {"DAYTONA_API_KEY": "test-key"}), \
             pytest.raises(ValueError, match="Daytona sandbox requires API driver"):
            get_driver(driver_key, sandbox_config=sandbox, profile_name="test")

    def test_daytona_mode_rejects_network_allowlist(self) -> None:
        """Network allowlist should be rejected for Daytona mode at construction."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError, match="Network allowlist is not supported with Daytona"):
            SandboxConfig(
                mode=SandboxMode.DAYTONA,
                repo_url="https://github.com/org/repo.git",
                network_allowlist_enabled=True,
            )

    def test_daytona_mode_passes_image(self) -> None:
        """Custom daytona_image should be forwarded to DaytonaSandboxProvider."""
        sandbox = SandboxConfig(
            mode=SandboxMode.DAYTONA,
            repo_url="https://github.com/org/repo.git",
            daytona_image="ubuntu:22.04",
        )
        with patch("amelia.sandbox.daytona.DaytonaSandboxProvider") as mock_provider_cls, \
             patch("amelia.sandbox.driver.ContainerDriver") as mock_driver_cls, \
             patch.dict(os.environ, {"DAYTONA_API_KEY": "test-key", "OPENROUTER_API_KEY": "or-test-key"}, clear=True):
            mock_driver_cls.return_value = MagicMock()
            get_driver("api", model="test-model", sandbox_config=sandbox, profile_name="work")
            mock_provider_cls.assert_called_once_with(
                api_key="test-key",
                api_url="https://app.daytona.io/api",
                target="us",
                repo_url="https://github.com/org/repo.git",
                resources=None,
                image="ubuntu:22.04",
                snapshot=None,
                timeout=120.0,
                retry_config=None,
                git_token=None,
                worker_env={
                    "LLM_PROXY_URL": "https://openrouter.ai/api/v1",
                    "OPENAI_API_KEY": "or-test-key",
                    "OPENROUTER_SITE_URL": "https://github.com/existential-birds/amelia",
                    "OPENROUTER_SITE_NAME": "Amelia",
                },
            )

    def test_daytona_mode_passes_github_token(self) -> None:
        """GITHUB_TOKEN env var should be forwarded as git_token."""
        sandbox = SandboxConfig(
            mode=SandboxMode.DAYTONA,
            repo_url="https://github.com/org/repo.git",
        )
        with patch("amelia.sandbox.daytona.DaytonaSandboxProvider") as mock_provider_cls, \
             patch("amelia.sandbox.driver.ContainerDriver") as mock_driver_cls, \
             patch.dict(os.environ, {"DAYTONA_API_KEY": "test-key", "GITHUB_TOKEN": "ghp_abc123", "AMELIA_GITHUB_TOKEN": "", "OPENROUTER_API_KEY": "or-test-key"}):
            mock_driver_cls.return_value = MagicMock()
            get_driver("api", model="test-model", sandbox_config=sandbox, profile_name="work")
            assert mock_provider_cls.call_args.kwargs["git_token"] == "ghp_abc123"

    def test_daytona_mode_missing_llm_api_key_raises(self) -> None:
        """Missing LLM API key should raise ValueError."""
        sandbox = SandboxConfig(
            mode=SandboxMode.DAYTONA,
            repo_url="https://github.com/org/repo.git",
        )
        with patch("amelia.sandbox.daytona.DaytonaSandboxProvider"), \
             patch("amelia.sandbox.driver.ContainerDriver"), \
             patch.dict(os.environ, {"DAYTONA_API_KEY": "test-key"}, clear=True), \
             pytest.raises(ValueError, match="OPENROUTER_API_KEY environment variable is required"):
            get_driver("api", model="test-model", sandbox_config=sandbox, profile_name="work")

    def test_daytona_mode_custom_provider_resolves(self) -> None:
        """Custom provider option should resolve to correct URL and env var."""
        sandbox = SandboxConfig(
            mode=SandboxMode.DAYTONA,
            repo_url="https://github.com/org/repo.git",
        )
        with patch("amelia.sandbox.daytona.DaytonaSandboxProvider") as mock_provider_cls, \
             patch("amelia.sandbox.driver.ContainerDriver") as mock_driver_cls, \
             patch.dict(os.environ, {"DAYTONA_API_KEY": "test-key", "OPENAI_API_KEY": "sk-test"}, clear=True):
            mock_driver_cls.return_value = MagicMock()
            get_driver(
                "api", model="test-model",
                sandbox_config=sandbox, profile_name="work",
                options={"provider": "openai"},
            )
            mock_driver_cls.assert_called_once_with(
                model="test-model",
                provider=mock_provider_cls.return_value,
                env={
                    "LLM_PROXY_URL": "https://api.openai.com/v1",
                    "OPENAI_API_KEY": "sk-test",
                    "OPENROUTER_SITE_URL": "https://github.com/existential-birds/amelia",
                    "OPENROUTER_SITE_NAME": "Amelia",
                },
            )

    def test_daytona_mode_unsupported_provider_raises(self) -> None:
        """Unsupported LLM provider should raise ValueError."""
        sandbox = SandboxConfig(
            mode=SandboxMode.DAYTONA,
            repo_url="https://github.com/org/repo.git",
        )
        with patch("amelia.sandbox.daytona.DaytonaSandboxProvider"), \
             patch("amelia.sandbox.driver.ContainerDriver"), \
             patch.dict(os.environ, {"DAYTONA_API_KEY": "test-key"}, clear=True), \
             pytest.raises(ValueError, match="Unsupported LLM provider"):
            get_driver(
                "api", model="test-model",
                sandbox_config=sandbox, profile_name="work",
                options={"provider": "anthropic"},
            )


class TestGetDriverWithSharedProvider:
    """Tests for sandbox_provider parameter (sandbox reuse)."""

    def test_shared_provider_skips_creation(self) -> None:
        """When sandbox_provider is passed, get_driver wraps it directly."""
        mock_provider = MagicMock()
        mock_provider.worker_env = {"LLM_PROXY_URL": "https://example.com", "OPENAI_API_KEY": "sk-test"}
        with patch("amelia.sandbox.driver.ContainerDriver") as mock_driver_cls:
            mock_driver_cls.return_value = MagicMock()
            get_driver(
                "api",
                model="test-model",
                sandbox_provider=mock_provider,
            )
            mock_driver_cls.assert_called_once_with(
                model="test-model",
                provider=mock_provider,
                env={"LLM_PROXY_URL": "https://example.com", "OPENAI_API_KEY": "sk-test"},
            )

    def test_shared_provider_ignores_sandbox_config(self) -> None:
        """sandbox_provider takes precedence over sandbox_config."""
        mock_provider = MagicMock()
        mock_provider.worker_env = {}
        sandbox = SandboxConfig(mode="container", image="test:latest")
        with patch("amelia.sandbox.driver.ContainerDriver") as mock_driver_cls:
            mock_driver_cls.return_value = MagicMock()
            get_driver(
                "api",
                model="test-model",
                sandbox_config=sandbox,
                sandbox_provider=mock_provider,
            )
            mock_driver_cls.assert_called_once_with(
                model="test-model",
                provider=mock_provider,
                env={},
            )

    def test_none_provider_preserves_existing_behavior(self) -> None:
        """sandbox_provider=None (default) doesn't change behavior."""
        with patch("amelia.drivers.factory.ApiDriver") as mock_cls:
            mock_cls.return_value = MagicMock()
            get_driver("api", model="test-model", sandbox_provider=None)
            mock_cls.assert_called_once_with(provider="openrouter", model="test-model")


class TestCreateDaytonaProvider:
    """Tests for the standalone create_daytona_provider function."""

    def test_creates_provider_with_required_fields(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DAYTONA_API_KEY", "test-key")
        monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
        sandbox = SandboxConfig(mode="daytona", repo_url="https://github.com/test/repo")
        with patch("amelia.sandbox.daytona.DaytonaSandboxProvider") as mock_cls:
            mock_cls.return_value = MagicMock()
            provider, worker_env = create_daytona_provider(sandbox)
            mock_cls.assert_called_once()
            assert "LLM_PROXY_URL" in worker_env
            assert "OPENAI_API_KEY" in worker_env

    def test_raises_without_api_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DAYTONA_API_KEY", raising=False)
        sandbox = SandboxConfig(mode="daytona", repo_url="https://github.com/test/repo")
        with pytest.raises(ValueError, match="DAYTONA_API_KEY"):
            create_daytona_provider(sandbox)

    def test_raises_without_repo_url(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError, match="repo_url"):
            SandboxConfig(mode="daytona")
