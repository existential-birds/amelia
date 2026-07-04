"""Tests for the `profile update` CLI command (agent options / MoA config)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import typer

from amelia.cli.config import profile_update
from amelia.core.types import AgentConfig, DriverType, MoAConfig, Profile, TrackerType


def _make_profile(agents: dict[str, AgentConfig] | None = None) -> Profile:
    """Build a Profile with the given agents (defaults to architect+developer)."""
    if agents is None:
        agents = {
            "architect": AgentConfig(driver=DriverType.CLAUDE, model="opus"),
            "developer": AgentConfig(driver=DriverType.CLAUDE, model="sonnet"),
        }
    return Profile(
        name="dev",
        tracker=TrackerType.NOOP,
        repo_root="/tmp",
        agents=agents,
    )


def _mock_repo(profile: Profile | None) -> MagicMock:
    """Build a mock ProfileRepository returning `profile` from get_profile."""
    repo = MagicMock()
    repo.get_profile = AsyncMock(return_value=profile)
    repo.update_profile = AsyncMock(return_value=profile)
    return repo


class TestProfileUpdateMoA:
    """Tests for setting MoA options via `profile update`."""

    def test_profile_update_sets_moa_options(self, mock_db: MagicMock) -> None:
        """MoA flags are validated and written under agents[agent].options['moa']."""
        repo = _mock_repo(_make_profile())

        with patch("amelia.cli.config.get_database", return_value=mock_db), \
             patch("amelia.cli.config.ProfileRepository", return_value=repo):
            profile_update(
                name="dev",
                agent="developer",
                moa_enabled=True,
                moa_proposer_count=5,
                moa_proposer_models="a,b",
                moa_isolation=None,
                clear_options=False,
            )

        repo.update_profile.assert_called_once()
        call_name, updates = repo.update_profile.call_args[0]
        assert call_name == "dev"
        moa = updates["agents"]["developer"]["options"]["moa"]
        assert moa["enabled"] is True
        assert moa["proposer_count"] == 5
        assert moa["proposer_models"] == ["a", "b"]
        assert moa["isolation"] is False

    def test_profile_update_clears_options(self, mock_db: MagicMock) -> None:
        """--clear-options empties the agent's options dict."""
        agents = {
            "architect": AgentConfig(
                driver=DriverType.CLAUDE,
                model="opus",
                options={"moa": {"enabled": True, "proposer_count": 4}},
            ),
            "developer": AgentConfig(driver=DriverType.CLAUDE, model="sonnet"),
        }
        repo = _mock_repo(_make_profile(agents))

        with patch("amelia.cli.config.get_database", return_value=mock_db), \
             patch("amelia.cli.config.ProfileRepository", return_value=repo):
            profile_update(
                name="dev",
                agent="architect",
                moa_enabled=None,
                moa_proposer_count=None,
                moa_proposer_models=None,
                moa_isolation=None,
                clear_options=True,
            )

        updates = repo.update_profile.call_args[0][1]
        assert updates["agents"]["architect"]["options"] == {}

    def test_profile_update_preserves_other_agents(self, mock_db: MagicMock) -> None:
        """Updating one agent leaves the others' config unchanged."""
        repo = _mock_repo(_make_profile())

        with patch("amelia.cli.config.get_database", return_value=mock_db), \
             patch("amelia.cli.config.ProfileRepository", return_value=repo):
            profile_update(
                name="dev",
                agent="developer",
                moa_enabled=True,
                moa_proposer_count=None,
                moa_proposer_models=None,
                moa_isolation=None,
                clear_options=False,
            )

        agents = repo.update_profile.call_args[0][1]["agents"]
        assert set(agents.keys()) == {"architect", "developer"}
        assert agents["architect"]["driver"] == "claude"
        assert agents["architect"]["model"] == "opus"
        assert agents["architect"]["options"] == {}

    def test_profile_update_invalid_agent(self, mock_db: MagicMock) -> None:
        """An unknown --agent raises BadParameter and never writes."""
        repo = _mock_repo(_make_profile())

        with patch("amelia.cli.config.get_database", return_value=mock_db), \
             patch("amelia.cli.config.ProfileRepository", return_value=repo), \
             pytest.raises(typer.BadParameter):
            profile_update(
                name="dev",
                agent="nonexistent",
                moa_enabled=True,
                moa_proposer_count=None,
                moa_proposer_models=None,
                moa_isolation=None,
                clear_options=False,
            )

        repo.update_profile.assert_not_called()

    def test_profile_update_invalid_moa_config(self, mock_db: MagicMock) -> None:
        """An out-of-range proposer count surfaces as BadParameter."""
        repo = _mock_repo(_make_profile())

        with patch("amelia.cli.config.get_database", return_value=mock_db), \
             patch("amelia.cli.config.ProfileRepository", return_value=repo), \
             pytest.raises(typer.BadParameter):
            profile_update(
                name="dev",
                agent="developer",
                moa_enabled=None,
                moa_proposer_count=0,
                moa_proposer_models=None,
                moa_isolation=None,
                clear_options=False,
            )

        repo.update_profile.assert_not_called()

    def test_profile_update_not_found(self, mock_db: MagicMock) -> None:
        """A missing profile exits with code 1."""
        repo = _mock_repo(None)

        with patch("amelia.cli.config.get_database", return_value=mock_db), \
             patch("amelia.cli.config.ProfileRepository", return_value=repo), \
             pytest.raises(typer.Exit) as exc_info:
            profile_update(
                name="missing",
                agent="developer",
                moa_enabled=True,
                moa_proposer_count=None,
                moa_proposer_models=None,
                moa_isolation=None,
                clear_options=False,
            )

        assert exc_info.value.exit_code == 1
        repo.update_profile.assert_not_called()


class TestMoAConfigValidation:
    """Direct unit tests for the MoAConfig model."""

    def test_defaults(self) -> None:
        config = MoAConfig()
        assert config.enabled is False
        assert config.proposer_count == 3
        assert config.proposer_models == []
        assert config.isolation is False

    def test_valid_values(self) -> None:
        config = MoAConfig(
            enabled=True,
            proposer_count=7,
            proposer_models=["a", "b"],
            isolation=True,
        )
        assert config.enabled is True
        assert config.proposer_count == 7
        assert config.proposer_models == ["a", "b"]
        assert config.isolation is True

    @pytest.mark.parametrize("count", [0, 11])
    def test_invalid_proposer_count(self, count: int) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            MoAConfig(proposer_count=count)

    def test_frozen(self) -> None:
        from pydantic import ValidationError

        config = MoAConfig()
        with pytest.raises(ValidationError):
            config.enabled = True  # type: ignore[misc]
