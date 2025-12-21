# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Unit tests for ArchitectContextStrategy."""
import pytest

from amelia.agents.architect import ArchitectContextStrategy
from amelia.core.context import ContextSection


class TestArchitectContextStrategy:
    """Test ArchitectContextStrategy context compilation."""

    @pytest.fixture
    def strategy(self):
        """Create an ArchitectContextStrategy instance for testing."""
        return ArchitectContextStrategy()

    def test_compile_with_issue_only(
        self, strategy, mock_execution_state_factory, mock_issue_factory
    ):
        """Test compile with issue only (current implementation)."""
        issue = mock_issue_factory(
            id="ARCH-100",
            title="Implement authentication system",
            description="Build a secure authentication system with JWT tokens",
        )
        state = mock_execution_state_factory(issue=issue)

        context = strategy.compile(state)

        # Should have system prompt
        assert context.system_prompt == ArchitectContextStrategy.SYSTEM_PROMPT

        # Should have exactly one section: issue
        assert len(context.sections) == 1
        assert context.sections[0].name == "issue"
        assert "Implement authentication system" in context.sections[0].content
        assert "Build a secure authentication system" in context.sections[0].content
        assert context.sections[0].source == "state.issue"

        # Should not have messages override
        assert context.messages is None

    def test_to_messages_produces_valid_agent_message_list(
        self, strategy, mock_execution_state_factory, mock_issue_factory
    ):
        """Test to_messages produces valid AgentMessage list."""
        issue = mock_issue_factory(
            title="Implement feature X", description="Feature description"
        )
        state = mock_execution_state_factory(issue=issue)

        context = strategy.compile(state)
        messages = strategy.to_messages(context)

        # System prompt is passed separately - to_messages only returns user messages
        assert len(messages) == 1

        # User message with formatted sections
        assert messages[0].role == "user"
        assert "## Issue" in messages[0].content
        assert "Implement feature X" in messages[0].content
        assert "Feature description" in messages[0].content

    def test_system_prompt_is_stable_and_constant(
        self, strategy, mock_execution_state_factory, mock_issue_factory
    ):
        """Test that SYSTEM_PROMPT is a stable class constant across instances and calls."""
        # Verify it's a class attribute
        assert hasattr(ArchitectContextStrategy, "SYSTEM_PROMPT")
        assert len(ArchitectContextStrategy.SYSTEM_PROMPT) > 0

        # Test stability across different compiles
        issue1 = mock_issue_factory(title="Issue 1", description="Description 1")
        issue2 = mock_issue_factory(title="Issue 2", description="Description 2")
        state1 = mock_execution_state_factory(issue=issue1)
        state2 = mock_execution_state_factory(issue=issue2)

        context1 = strategy.compile(state1)
        context2 = strategy.compile(state2)

        # System prompts should be identical
        assert context1.system_prompt == context2.system_prompt
        assert context1.system_prompt == ArchitectContextStrategy.SYSTEM_PROMPT

    def test_only_issue_design_and_codebase_sections_allowed(self, strategy):
        """Test that only 'issue', 'design', and 'codebase' sections are allowed."""
        # Verify ALLOWED_SECTIONS is defined correctly
        assert hasattr(ArchitectContextStrategy, "ALLOWED_SECTIONS")
        assert {"issue", "design", "codebase"} == ArchitectContextStrategy.ALLOWED_SECTIONS

        # Valid sections should pass validation
        valid_sections = [
            ContextSection(name="issue", content="Issue content"),
        ]
        strategy.validate_sections(valid_sections)  # Should not raise

    def test_compile_raises_for_disallowed_sections(self, strategy):
        """Test compile raises ValueError when attempting to add disallowed section."""
        # Invalid section name should raise ValueError
        invalid_sections = [
            ContextSection(name="issue", content="Valid"),
            ContextSection(name="task", content="Not allowed for Architect"),
        ]

        with pytest.raises(ValueError) as exc_info:
            strategy.validate_sections(invalid_sections)

        assert "Section 'task' not allowed" in str(exc_info.value)
        assert "Allowed sections: ['codebase', 'design', 'issue']" in str(exc_info.value)

    def test_compile_formats_issue_with_title_and_description(
        self, strategy, mock_execution_state_factory, mock_issue_factory
    ):
        """Test compile formats issue section with title and description."""
        issue = mock_issue_factory(
            title="Refactor authentication module",
            description="The current auth module needs refactoring to support OAuth2",
        )
        state = mock_execution_state_factory(issue=issue)

        context = strategy.compile(state)

        issue_section = context.sections[0]
        assert issue_section.name == "issue"

        # Should contain both title and description
        content = issue_section.content
        assert "Refactor authentication module" in content
        assert "The current auth module needs refactoring to support OAuth2" in content

    def test_section_content_is_non_empty(
        self,
        strategy,
        mock_execution_state_factory,
        mock_issue_factory,
    ):
        """Test that all sections have non-empty content."""
        issue = mock_issue_factory(title="Test Issue", description="Test description")
        state = mock_execution_state_factory(issue=issue)

        context = strategy.compile(state)

        for section in context.sections:
            assert len(section.content.strip()) > 0

    def test_compile_raises_when_issue_missing(
        self, strategy, mock_profile_factory
    ):
        """Test compile raises ValueError when issue is missing."""
        from amelia.core.state import ExecutionState

        # Create state without issue
        profile = mock_profile_factory()
        state = ExecutionState(profile=profile, issue=None)

        with pytest.raises(ValueError) as exc_info:
            strategy.compile(state)

        assert "Issue context is required for planning" in str(exc_info.value)

    def test_compile_raises_when_issue_has_no_title_or_description(
        self, strategy, mock_execution_state_factory, mock_issue_factory
    ):
        """Test compile raises ValueError when issue has no title or description."""
        issue = mock_issue_factory(title="", description="")
        state = mock_execution_state_factory(issue=issue)

        with pytest.raises(ValueError) as exc_info:
            strategy.compile(state)

        assert "Issue context is required for planning" in str(exc_info.value)

    @pytest.mark.parametrize(
        "title,description",
        [
            ("Test Issue", ""),
            ("", "Test description"),
        ],
        ids=["only_title", "only_description"],
    )
    def test_compile_works_with_partial_issue(
        self, strategy, mock_execution_state_factory, mock_issue_factory, title, description
    ):
        """Test compile works when issue has only title or only description."""
        issue = mock_issue_factory(title=title, description=description)
        state = mock_execution_state_factory(issue=issue)

        context = strategy.compile(state)

        assert len(context.sections) == 1
        expected_content = title if title else description
        assert expected_content in context.sections[0].content

    def test_format_design_section_structures_design_fields(
        self, strategy, mock_design_factory
    ):
        """Test _format_design_section formats design as structured markdown."""
        design = mock_design_factory(
            title="Authentication System",
            goal="Build secure JWT-based authentication",
            architecture="Layered architecture with service and repository patterns",
            tech_stack=["FastAPI", "PostgreSQL", "Redis"],
            components=["AuthService", "TokenManager", "UserRepository"],
            data_flow="Request -> AuthService -> TokenManager -> Response",
            testing_strategy="Unit tests for services, integration for API",
        )

        result = strategy._format_design_section(design)

        assert "## Goal" in result
        assert "Build secure JWT-based authentication" in result
        assert "## Architecture" in result
        assert "Layered architecture" in result
        assert "## Tech Stack" in result
        assert "- FastAPI" in result
        assert "- PostgreSQL" in result
        assert "## Components" in result
        assert "- AuthService" in result
        assert "## Data Flow" in result
        assert "Request -> AuthService" in result
        assert "## Testing Strategy" in result
        assert "Unit tests for services" in result

    def test_compile_includes_design_section_when_present(
        self, strategy, mock_execution_state_factory, mock_issue_factory, mock_design_factory
    ):
        """Test compile includes design section when state.design is set."""
        issue = mock_issue_factory(title="Build auth", description="Auth system")
        design = mock_design_factory(
            title="Auth Design",
            goal="Secure authentication",
            architecture="JWT-based",
        )
        state = mock_execution_state_factory(issue=issue, design=design)

        context = strategy.compile(state)

        # Should have two sections: issue and design
        assert len(context.sections) == 2
        section_names = [s.name for s in context.sections]
        assert "issue" in section_names
        assert "design" in section_names

        # Find design section
        design_section = next(s for s in context.sections if s.name == "design")
        assert "Secure authentication" in design_section.content
        assert "JWT-based" in design_section.content
        assert design_section.source == "state.design"

    def test_compile_excludes_design_section_when_none(
        self, strategy, mock_execution_state_factory, mock_issue_factory
    ):
        """Test compile excludes design section when state.design is None."""
        issue = mock_issue_factory(title="Build feature", description="Feature desc")
        state = mock_execution_state_factory(issue=issue, design=None)

        context = strategy.compile(state)

        # Should have only issue section
        assert len(context.sections) == 1
        assert context.sections[0].name == "issue"

    def test_compile_includes_codebase_section_when_working_dir_set(
        self, strategy, mock_execution_state_factory, mock_issue_factory, mock_profile_factory, tmp_path
    ):
        """Test compile includes codebase section when profile.working_dir is set."""
        # Create a test directory structure
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("print('hello')")
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "test_main.py").write_text("def test_main(): pass")
        (tmp_path / "README.md").write_text("# Project")

        issue = mock_issue_factory(title="Add feature", description="Feature desc")
        profile = mock_profile_factory(working_dir=str(tmp_path))
        state = mock_execution_state_factory(issue=issue, profile=profile)

        context = strategy.compile(state)

        # Should have two sections: issue and codebase
        section_names = [s.name for s in context.sections]
        assert "issue" in section_names
        assert "codebase" in section_names

        # Codebase section should contain file structure
        codebase_section = next(s for s in context.sections if s.name == "codebase")
        assert "src/main.py" in codebase_section.content or "src\\main.py" in codebase_section.content
        assert "tests/test_main.py" in codebase_section.content or "tests\\test_main.py" in codebase_section.content
        assert "README.md" in codebase_section.content

    def test_compile_excludes_codebase_section_when_working_dir_not_set(
        self, strategy, mock_execution_state_factory, mock_issue_factory, mock_profile_factory
    ):
        """Test compile excludes codebase section when profile.working_dir is None."""
        issue = mock_issue_factory(title="Add feature", description="Feature desc")
        # Create profile with working_dir=None explicitly
        profile = mock_profile_factory(working_dir=None)
        state = mock_execution_state_factory(issue=issue, profile=profile)

        context = strategy.compile(state)

        # Should have only issue section, no codebase
        section_names = [s.name for s in context.sections]
        assert "issue" in section_names
        assert "codebase" not in section_names

    def test_codebase_section_allowed_in_allowed_sections(self, strategy):
        """Test that 'codebase' is in ALLOWED_SECTIONS."""
        assert "codebase" in ArchitectContextStrategy.ALLOWED_SECTIONS

    def test_execution_plan_system_prompt_includes_risk_level_definitions(self, strategy):
        """Test that execution plan system prompt includes risk level definitions."""
        prompt = strategy.get_execution_plan_system_prompt()

        # Should define all three risk levels with examples
        assert "low" in prompt.lower()
        assert "medium" in prompt.lower()
        assert "high" in prompt.lower()

        # Should mention characteristics of each risk level
        assert "file writes" in prompt.lower() or "reversible" in prompt.lower()
        assert "database" in prompt.lower() or "config" in prompt.lower()
        assert "destructive" in prompt.lower() or "irreversible" in prompt.lower()

    def test_execution_plan_system_prompt_includes_batch_size_limits(self, strategy):
        """Test that execution plan system prompt mentions batch size limits."""
        prompt = strategy.get_execution_plan_system_prompt()

        # Should mention max batch sizes for different risk levels
        # low=5, medium=3, high=1
        assert "5" in prompt or "five" in prompt.lower()
        assert "3" in prompt or "three" in prompt.lower()
        # Should mention batching concept
        assert "batch" in prompt.lower()

    def test_execution_plan_system_prompt_includes_tdd_guidance(self, strategy):
        """Test that execution plan system prompt includes TDD approach guidance."""
        prompt = strategy.get_execution_plan_system_prompt()

        # Should mention TDD concepts
        assert "tdd" in prompt.lower() or "test-driven" in prompt.lower() or "test first" in prompt.lower()
        # Should mention the typical TDD flow
        assert "test" in prompt.lower()
        assert "fail" in prompt.lower() or "failing" in prompt.lower()
        assert "implement" in prompt.lower()
        assert "pass" in prompt.lower()

    def test_execution_plan_system_prompt_includes_step_granularity_guidance(self, strategy):
        """Test that execution plan system prompt includes step granularity guidance."""
        prompt = strategy.get_execution_plan_system_prompt()

        # Should mention 2-5 minute step granularity
        assert "2" in prompt
        assert "5" in prompt
        assert "minute" in prompt.lower() or "min" in prompt.lower()

    def test_execution_plan_system_prompt_includes_fallback_command_guidance(self, strategy):
        """Test that execution plan system prompt includes fallback command guidance."""
        prompt = strategy.get_execution_plan_system_prompt()

        # Should mention fallback commands or alternatives
        assert "fallback" in prompt.lower() or "alternative" in prompt.lower()

    def test_execution_plan_user_prompt_is_concise_instruction(self, strategy):
        """Test that execution plan user prompt is a concise instruction."""
        prompt = strategy.get_execution_plan_user_prompt()

        # Should be a clear instruction to create an execution plan
        assert len(prompt) > 0
        assert "execution plan" in prompt.lower() or "plan" in prompt.lower()


class TestArchitectSessionId:
    """Tests for Architect session_id handling."""

    async def test_architect_passes_session_id_to_driver(
        self,
        mock_execution_state_factory,
        mock_async_driver_factory,
        mock_execution_plan_factory,
    ):
        """Test that Architect passes session_id from state to driver."""
        from amelia.agents.architect import Architect, ExecutionPlanOutput

        # Create mock plan output
        mock_plan = mock_execution_plan_factory()
        mock_output = ExecutionPlanOutput(plan=mock_plan, reasoning="test")

        # Driver returns (output, new_session_id)
        mock_driver = mock_async_driver_factory(generate_return=(mock_output, "new-sess-456"))

        state = mock_execution_state_factory(driver_session_id="existing-sess-123")

        architect = Architect(mock_driver)
        result_plan, result_session_id = await architect.generate_execution_plan(state.issue, state)

        # Verify driver was called with session_id from state
        mock_driver.generate.assert_called_once()
        call_kwargs = mock_driver.generate.call_args.kwargs
        assert call_kwargs.get("session_id") == "existing-sess-123"

        # Verify return value includes session_id
        assert result_session_id == "new-sess-456"
        assert result_plan is not None
