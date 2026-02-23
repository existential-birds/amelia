"""Unit tests for amelia.core.types module."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from amelia.core.types import (
    AskUserOption,
    AskUserQuestionItem,
    AskUserQuestionPayload,
    Design,
    DriverType,
    PlanValidationResult,
    SandboxMode,
    Severity,
    TrackerType,
)


def test_agent_config_accepts_claude_driver() -> None:
    from amelia.core.types import AgentConfig

    config = AgentConfig(driver="claude", model="sonnet")
    assert config.driver == "claude"


def test_agent_config_accepts_codex_driver() -> None:
    from amelia.core.types import AgentConfig

    config = AgentConfig(driver="codex", model="gpt-5-codex")
    assert config.driver == "codex"


def test_agent_config_accepts_api_driver() -> None:
    from amelia.core.types import AgentConfig

    config = AgentConfig(driver="api", model="anthropic/claude-sonnet-4")
    assert config.driver == "api"


def test_agent_config_rejects_legacy_cli_driver() -> None:
    import pytest

    from amelia.core.types import AgentConfig

    # Legacy "cli" driver should be rejected
    with pytest.raises(ValueError, match="Input should be 'claude', 'codex' or 'api'"):
        AgentConfig(driver="cli", model="sonnet")


def test_agent_config_creation() -> None:
    """AgentConfig should store driver, model, and optional options."""
    from amelia.core.types import AgentConfig

    config = AgentConfig(driver="claude", model="sonnet")
    assert config.driver == "claude"
    assert config.model == "sonnet"
    assert config.options == {}


def test_agent_config_with_options() -> None:
    """AgentConfig should accept arbitrary options dict."""
    from amelia.core.types import AgentConfig

    config = AgentConfig(
        driver="claude",
        model="anthropic/claude-sonnet-4",
        options={"max_iterations": 5, "temperature": 0.7},
    )
    assert config.options["max_iterations"] == 5
    assert config.options["temperature"] == 0.7


def test_profile_with_agents_dict() -> None:
    """Profile should accept agents dict configuration."""
    from amelia.core.types import AgentConfig, Profile

    profile = Profile(
        name="test",
        tracker=TrackerType.NOOP,
        repo_root="/tmp/test",
        agents={
            "architect": AgentConfig(driver="claude", model="opus"),
            "developer": AgentConfig(driver="claude", model="sonnet"),
        },
    )
    assert profile.agents["architect"].model == "opus"
    assert profile.agents["developer"].model == "sonnet"


def test_profile_get_agent_config() -> None:
    """Profile.get_agent_config should return config or raise if missing."""
    from amelia.core.types import AgentConfig, Profile

    profile = Profile(
        name="test",
        tracker=TrackerType.NOOP,
        repo_root="/tmp/test",
        agents={
            "architect": AgentConfig(driver="claude", model="opus"),
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


def test_agent_config_sandbox_default() -> None:
    """AgentConfig should default sandbox to SandboxConfig() with mode='none'."""
    from amelia.core.types import AgentConfig, SandboxConfig

    config = AgentConfig(driver="claude", model="sonnet")
    assert config.sandbox == SandboxConfig()
    assert config.sandbox.mode == "none"


def test_agent_config_profile_name_default() -> None:
    """AgentConfig should default profile_name to 'default'."""
    from amelia.core.types import AgentConfig

    config = AgentConfig(driver="claude", model="sonnet")
    assert config.profile_name == "default"


def test_agent_config_with_sandbox_config() -> None:
    """AgentConfig should accept explicit SandboxConfig."""
    from amelia.core.types import AgentConfig, SandboxConfig

    sandbox = SandboxConfig(mode=SandboxMode.CONTAINER, image="custom:latest")
    config = AgentConfig(
        driver=DriverType.API, model="test-model",
        sandbox=sandbox, profile_name="work",
    )
    assert config.sandbox.mode == SandboxMode.CONTAINER
    assert config.sandbox.image == "custom:latest"
    assert config.profile_name == "work"


def test_get_agent_config_injects_sandbox() -> None:
    """get_agent_config should inject profile's sandbox config into AgentConfig."""
    from amelia.core.types import AgentConfig, Profile, SandboxConfig

    sandbox = SandboxConfig(mode=SandboxMode.CONTAINER, image="custom:latest")
    profile = Profile(
        name="work",
        tracker=TrackerType.NOOP,
        repo_root="/tmp/test",
        sandbox=sandbox,
        agents={"architect": AgentConfig(driver=DriverType.API, model="opus")},
    )

    config = profile.get_agent_config("architect")
    assert config.sandbox.mode == SandboxMode.CONTAINER
    assert config.sandbox.image == "custom:latest"
    assert config.profile_name == "work"


def test_get_agent_config_injects_profile_name() -> None:
    """get_agent_config should set profile_name to profile.name."""
    from amelia.core.types import AgentConfig, Profile

    profile = Profile(
        name="personal",
        tracker=TrackerType.NOOP,
        repo_root="/tmp/test",
        agents={"developer": AgentConfig(driver="claude", model="sonnet")},
    )

    config = profile.get_agent_config("developer")
    assert config.profile_name == "personal"


def test_get_agent_config_preserves_original() -> None:
    """get_agent_config should not mutate the stored AgentConfig."""
    from amelia.core.types import AgentConfig, Profile, SandboxConfig

    sandbox = SandboxConfig(mode=SandboxMode.CONTAINER)
    original = AgentConfig(driver=DriverType.API, model="opus")
    profile = Profile(
        name="work",
        tracker=TrackerType.NOOP,
        repo_root="/tmp/test",
        sandbox=sandbox,
        agents={"architect": original},
    )

    injected = profile.get_agent_config("architect")
    assert injected is not original
    assert original.sandbox.mode == SandboxMode.NONE  # Original unchanged
    assert original.profile_name == "default"  # Original unchanged
    assert injected.sandbox.mode == SandboxMode.CONTAINER  # Injected has profile's sandbox


class TestPlanValidationResult:
    """Tests for PlanValidationResult model."""

    def test_valid_result(self) -> None:
        result = PlanValidationResult(valid=True, issues=[], severity=Severity.NONE)
        assert result.valid is True
        assert result.issues == []
        assert result.severity == Severity.NONE

    def test_invalid_result(self) -> None:
        result = PlanValidationResult(
            valid=False,
            issues=["Missing ### Task headers", "Goal section not found"],
            severity=Severity.MAJOR,
        )
        assert result.valid is False
        assert len(result.issues) == 2
        assert result.severity == Severity.MAJOR

    def test_is_frozen(self) -> None:
        result = PlanValidationResult(valid=True, issues=[], severity=Severity.NONE)
        with pytest.raises(ValidationError):
            result.valid = False  # type: ignore[misc]


class TestAskUserQuestionPayload:
    """Tests for AskUser* models."""

    def test_valid_payload(self) -> None:
        payload = AskUserQuestionPayload(
            questions=[
                AskUserQuestionItem(
                    question="Which approach?",
                    header="Approach",
                    options=[
                        AskUserOption(label="A", description="First"),
                        AskUserOption(label="B"),
                    ],
                    multi_select=True,
                )
            ]
        )
        assert len(payload.questions) == 1
        assert payload.questions[0].question == "Which approach?"
        assert payload.questions[0].header == "Approach"
        assert payload.questions[0].multi_select is True
        assert len(payload.questions[0].options) == 2
        assert payload.questions[0].options[0].description == "First"
        assert payload.questions[0].options[1].description is None

    def test_minimal_payload(self) -> None:
        payload = AskUserQuestionPayload(
            questions=[AskUserQuestionItem(question="Ready?")]
        )
        assert payload.questions[0].header is None
        assert payload.questions[0].options == []
        assert payload.questions[0].multi_select is False

    def test_from_dict(self) -> None:
        data = {
            "questions": [
                {
                    "question": "Pick one?",
                    "options": [{"label": "Yes"}, {"label": "No"}],
                }
            ]
        }
        payload = AskUserQuestionPayload(**data)  # type: ignore[arg-type]
        assert payload.questions[0].options[1].label == "No"

    def test_invalid_questions_type(self) -> None:
        with pytest.raises(ValidationError):
            AskUserQuestionPayload(questions="not-a-list")  # type: ignore[arg-type]

    def test_invalid_options_type(self) -> None:
        with pytest.raises(ValidationError):
            AskUserQuestionPayload(
                questions=[
                    AskUserQuestionItem(
                        question="Q?",
                        options="not-a-list",  # type: ignore[arg-type]
                    )
                ]
            )
