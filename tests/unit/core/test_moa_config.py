"""Unit tests for the MoAConfig advisory Mixture-of-Agents config model."""
import pytest
from pydantic import ValidationError

from amelia.core.types import MoAConfig


def test_from_options_empty_disabled() -> None:
    """An empty options dict yields a disabled MoAConfig with defaults."""
    config = MoAConfig.from_options({})

    assert config.enabled is False
    assert config.proposer_count == 2
    assert config.proposer_models == []


def test_from_options_round_trips_values() -> None:
    """from_options reads options['moa'] and round-trips the supplied fields."""
    config = MoAConfig.from_options(
        {"moa": {"enabled": True, "proposer_count": 3, "proposer_models": ["m1", "m2", "m3"]}}
    )

    assert config.enabled is True
    assert config.proposer_count == 3
    assert config.proposer_models == ["m1", "m2", "m3"]


def test_proposer_count_rejects_below_one() -> None:
    """proposer_count < 1 is rejected with a Pydantic ValidationError."""
    with pytest.raises(ValidationError):
        MoAConfig(proposer_count=0)

    with pytest.raises(ValidationError):
        MoAConfig.from_options({"moa": {"proposer_count": -1}})


def test_resolve_models_falls_back_to_base_model() -> None:
    """A proposer_models list shorter than proposer_count falls back to base_model."""
    config = MoAConfig.from_options(
        {"moa": {"enabled": True, "proposer_count": 3, "proposer_models": ["m1"]}}
    )

    resolved = config.resolve_models("base")

    assert resolved == ["m1", "base", "base"]


def test_resolve_models_returns_exactly_n_entries() -> None:
    """resolve_models returns exactly proposer_count entries, truncating extras."""
    config = MoAConfig.from_options(
        {"moa": {"proposer_count": 2, "proposer_models": ["m1", "m2", "m3"]}}
    )

    resolved = config.resolve_models("base")

    assert resolved == ["m1", "m2"]


def test_resolve_models_all_default_to_base() -> None:
    """With no proposer_models, every slot falls back to base_model."""
    config = MoAConfig(proposer_count=2)

    assert config.resolve_models("base") == ["base", "base"]


def test_frozen() -> None:
    """MoAConfig is immutable."""
    config = MoAConfig()
    with pytest.raises(ValidationError):
        config.enabled = True  # type: ignore[misc]
