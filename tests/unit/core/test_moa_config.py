"""Unit tests for MoAConfig and generative MoA config parsing."""

import pytest
from pydantic import ValidationError

from amelia.core.types import MoAConfig, MoAIsolation, MoAMode


class TestMoAConfigDefaults:
    def test_disabled_by_default(self) -> None:
        cfg = MoAConfig()
        assert cfg.enabled is False
        assert cfg.proposer_count == 1
        assert cfg.proposer_models == ()
        assert cfg.mode == MoAMode.GENERATIVE
        assert cfg.isolation == MoAIsolation.WORKTREE

    def test_frozen(self) -> None:
        cfg = MoAConfig()
        with pytest.raises(ValidationError):
            cfg.enabled = True


class TestMoAConfigValidation:
    def test_proposer_count_must_be_at_least_one(self) -> None:
        with pytest.raises(ValidationError):
            MoAConfig(proposer_count=0)

    def test_negative_proposer_count_rejected(self) -> None:
        with pytest.raises(ValidationError):
            MoAConfig(proposer_count=-3)

    def test_mode_parsed_from_string(self) -> None:
        cfg = MoAConfig.model_validate({"mode": "advisory"})
        assert cfg.mode == MoAMode.ADVISORY

    def test_isolation_parsed_from_string(self) -> None:
        cfg = MoAConfig.model_validate({"isolation": "worktree"})
        assert cfg.isolation == MoAIsolation.WORKTREE

    def test_invalid_mode_rejected(self) -> None:
        with pytest.raises(ValidationError):
            MoAConfig.model_validate({"mode": "nonsense"})


class TestResolveModels:
    def test_falls_back_to_base_model(self) -> None:
        cfg = MoAConfig(proposer_count=3)
        assert cfg.resolve_models("sonnet") == ["sonnet", "sonnet", "sonnet"]

    def test_exact_models_used(self) -> None:
        cfg = MoAConfig(proposer_count=2, proposer_models=("m0", "m1"))
        assert cfg.resolve_models("base") == ["m0", "m1"]

    def test_extra_models_truncated(self) -> None:
        cfg = MoAConfig(proposer_count=2, proposer_models=("m0", "m1", "m2"))
        assert cfg.resolve_models("base") == ["m0", "m1"]

    def test_shortfall_padded_with_base(self) -> None:
        cfg = MoAConfig(proposer_count=3, proposer_models=("m0",))
        assert cfg.resolve_models("base") == ["m0", "base", "base"]

    def test_always_returns_exactly_count(self) -> None:
        for count in (1, 2, 5):
            cfg = MoAConfig(proposer_count=count)
            assert len(cfg.resolve_models("x")) == count


class TestFromOptions:
    def test_missing_moa_key_returns_default(self) -> None:
        cfg = MoAConfig.from_options({"other": 1})
        assert cfg == MoAConfig()
        assert cfg.enabled is False

    def test_none_options_returns_default(self) -> None:
        assert MoAConfig.from_options(None) == MoAConfig()

    def test_dict_parsed(self) -> None:
        cfg = MoAConfig.from_options(
            {
                "moa": {
                    "enabled": True,
                    "mode": "generative",
                    "proposer_count": 3,
                    "proposer_models": ["a", "b"],
                }
            }
        )
        assert cfg.enabled is True
        assert cfg.mode == MoAMode.GENERATIVE
        assert cfg.proposer_count == 3
        assert cfg.proposer_models == ("a", "b")

    def test_moaconfig_passthrough(self) -> None:
        original = MoAConfig(enabled=True, proposer_count=2)
        cfg = MoAConfig.from_options({"moa": original})
        assert cfg is original

    def test_invalid_type_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid 'moa' option type"):
            MoAConfig.from_options({"moa": "enabled"})
