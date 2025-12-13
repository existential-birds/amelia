# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Unit tests for amelia.core.context module."""
import pytest

from amelia.core.context import CompiledContext, ContextSection, ContextStrategy
from amelia.core.state import AgentMessage, ExecutionState


class TestCompiledContext:
    """Test CompiledContext behavior and message conversion."""

    def test_to_messages_with_sections_single_section(self):
        """Test to_messages formats a single section with markdown header."""
        section = ContextSection(name="issue", content="Fix bug in auth module")
        context = CompiledContext(
            system_prompt="You are a developer agent.",
            sections=[section]
        )

        strategy = ConcreteTestStrategy()
        messages = strategy.to_messages(context)

        # System prompt is passed separately - to_messages only returns user messages
        assert len(messages) == 1
        assert messages[0].role == "user"
        assert messages[0].content == "## Issue\n\nFix bug in auth module"

    def test_to_messages_with_sections_multiple_sections(self):
        """Test to_messages formats multiple sections with markdown headers."""
        sections = [
            ContextSection(name="issue", content="Implement feature X"),
            ContextSection(name="current_task", content="Write tests first"),
            ContextSection(name="plan", content="3 tasks in sequence")
        ]
        context = CompiledContext(
            system_prompt="You are an architect.",
            sections=sections
        )

        strategy = ConcreteTestStrategy()
        messages = strategy.to_messages(context)

        # System prompt is passed separately - to_messages only returns user messages
        assert len(messages) == 1
        assert messages[0].role == "user"

        # Check sections are formatted with headers and separated by double newlines
        expected_content = (
            "## Issue\n\nImplement feature X\n\n"
            "## Current_Task\n\nWrite tests first\n\n"
            "## Plan\n\n3 tasks in sequence"
        )
        assert messages[0].content == expected_content

    def test_to_messages_with_sections_no_system_prompt(self):
        """Test to_messages without system prompt, only sections."""
        section = ContextSection(name="task", content="Complete unit tests")
        context = CompiledContext(sections=[section])

        strategy = ConcreteTestStrategy()
        messages = strategy.to_messages(context)

        # Should only have user message
        assert len(messages) == 1
        assert messages[0].role == "user"
        assert messages[0].content == "## Task\n\nComplete unit tests"

    def test_to_messages_with_messages_override(self):
        """Test that messages override bypasses section-based generation."""
        sections = [
            ContextSection(name="issue", content="Should be ignored"),
            ContextSection(name="task", content="Also ignored")
        ]
        override_messages = [
            AgentMessage(role="system", content="Override system message"),
            AgentMessage(role="user", content="Override user message"),
            AgentMessage(role="assistant", content="Override assistant message")
        ]
        context = CompiledContext(
            system_prompt="Should be ignored",
            sections=sections,
            messages=override_messages
        )

        strategy = ConcreteTestStrategy()
        messages = strategy.to_messages(context)

        # Should return override messages directly, ignoring sections and system_prompt
        assert messages == override_messages
        assert len(messages) == 3
        assert messages[0].content == "Override system message"
        assert messages[1].content == "Override user message"
        assert messages[2].content == "Override assistant message"

    def test_to_messages_empty_context(self):
        """Test to_messages with empty context returns empty list."""
        context = CompiledContext()

        strategy = ConcreteTestStrategy()
        messages = strategy.to_messages(context)

        assert messages == []

    def test_to_messages_only_system_prompt(self):
        """Test to_messages with only system prompt, no sections."""
        context = CompiledContext(system_prompt="System instruction")

        strategy = ConcreteTestStrategy()
        messages = strategy.to_messages(context)

        # System prompt is passed separately - to_messages returns empty when no sections
        assert len(messages) == 0


class TestContextStrategy:
    """Test ContextStrategy base class behavior."""

    @pytest.fixture
    def strategy(self):
        """Fixture providing a ConcreteTestStrategy instance."""
        return ConcreteTestStrategy()

    def test_validate_sections_passes_for_allowed_sections(self, strategy):
        """Test validate_sections passes when all sections are allowed."""
        sections = [
            ContextSection(name="issue", content="Content 1"),
            ContextSection(name="current_task", content="Content 2"),
            ContextSection(name="plan", content="Content 3")
        ]

        # Should not raise
        strategy.validate_sections(sections)

    def test_validate_sections_raises_for_disallowed_sections(self, strategy):
        """Test validate_sections raises ValueError for disallowed section names."""
        sections = [
            ContextSection(name="issue", content="Valid"),
            ContextSection(name="invalid_section", content="Not allowed"),
        ]

        with pytest.raises(ValueError) as exc_info:
            strategy.validate_sections(sections)

        assert "Section 'invalid_section' not allowed" in str(exc_info.value)
        assert "Allowed sections: ['current_task', 'issue', 'plan']" in str(exc_info.value)

    def test_validate_sections_skips_validation_when_allowed_sections_empty(self):
        """Test validate_sections skips validation when ALLOWED_SECTIONS is empty."""
        # Base ContextStrategy has empty ALLOWED_SECTIONS
        strategy = EmptyAllowedSectionsStrategy()
        sections = [
            ContextSection(name="any_name", content="Content 1"),
            ContextSection(name="another_name", content="Content 2"),
        ]

        # Should not raise even though sections aren't in ALLOWED_SECTIONS
        strategy.validate_sections(sections)

    @pytest.mark.parametrize(
        "test_id, setup_state, expected_task_id, expected_description",
        [
            (
                "task_found",
                lambda factories: factories["state"](
                    plan=factories["dag"](tasks=[
                        factories["task"](id="1", description="First task"),
                        factories["task"](id="2", description="Second task"),
                        factories["task"](id="3", description="Third task")
                    ]),
                    current_task_id="2"
                ),
                "2",
                "Second task"
            ),
            (
                "no_plan",
                lambda factories: factories["state"](plan=None, current_task_id="1"),
                None,
                None
            ),
            (
                "no_current_task_id",
                lambda factories: factories["state"](
                    plan=factories["dag"](num_tasks=3),
                    current_task_id=None
                ),
                None,
                None
            ),
            (
                "task_not_found",
                lambda factories: factories["state"](
                    plan=factories["dag"](tasks=[
                        factories["task"](id="1", description="First task"),
                        factories["task"](id="2", description="Second task")
                    ]),
                    current_task_id="999"
                ),
                None,
                None
            ),
        ],
        ids=["task_found", "no_plan", "no_current_task_id", "task_not_found"]
    )
    def test_get_current_task(
        self,
        strategy,
        mock_execution_state_factory,
        mock_task_dag_factory,
        mock_task_factory,
        test_id,
        setup_state,
        expected_task_id,
        expected_description
    ):
        """Test get_current_task with various state configurations."""
        factories = {
            "state": mock_execution_state_factory,
            "dag": mock_task_dag_factory,
            "task": mock_task_factory
        }
        state = setup_state(factories)

        current_task = strategy.get_current_task(state)

        if expected_task_id is None:
            assert current_task is None
        else:
            assert current_task is not None
            assert current_task.id == expected_task_id
            assert current_task.description == expected_description

    @pytest.mark.parametrize(
        "title, description, expected_summary",
        [
            (
                "Implement user authentication",
                "Add login and logout endpoints with JWT tokens",
                "**Implement user authentication**\n\nAdd login and logout endpoints with JWT tokens"
            ),
            (
                "Fix bug in auth module",
                "",
                "**Fix bug in auth module**"
            ),
            (
                "",
                "Add comprehensive error handling to API endpoints",
                "Add comprehensive error handling to API endpoints"
            ),
            (
                "",
                "",
                None
            ),
        ],
        ids=["title_and_description", "only_title", "only_description", "both_empty"]
    )
    def test_get_issue_summary(
        self,
        strategy,
        mock_execution_state_factory,
        mock_issue_factory,
        title,
        description,
        expected_summary
    ):
        """Test get_issue_summary with various title and description combinations."""
        issue = mock_issue_factory(title=title, description=description)
        state = mock_execution_state_factory(issue=issue)

        summary = strategy.get_issue_summary(state)

        assert summary == expected_summary

    def test_get_issue_summary_returns_none_when_no_issue(self, strategy, mock_profile_factory):
        """Test get_issue_summary returns None when issue is not present."""
        # Create state directly with issue=None (factory always creates default issue)
        profile = mock_profile_factory()
        state = ExecutionState(profile=profile, issue=None)

        summary = strategy.get_issue_summary(state)

        assert summary is None


# Concrete test strategy for testing base class functionality
class ConcreteTestStrategy(ContextStrategy):
    """Concrete strategy implementation for testing base class behavior."""

    SYSTEM_PROMPT = "Test system prompt"
    ALLOWED_SECTIONS = {"issue", "current_task", "plan"}

    def compile(self, state: ExecutionState) -> CompiledContext:
        """Simple compile implementation for testing."""
        return CompiledContext(
            system_prompt=self.SYSTEM_PROMPT,
            sections=[
                ContextSection(name="issue", content="Test content")
            ]
        )


class EmptyAllowedSectionsStrategy(ContextStrategy):
    """Strategy with empty ALLOWED_SECTIONS for testing validation skip."""

    SYSTEM_PROMPT = "Empty allowed sections"
    ALLOWED_SECTIONS = set()

    def compile(self, state: ExecutionState) -> CompiledContext:
        """Simple compile implementation for testing."""
        return CompiledContext()
