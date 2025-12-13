# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Unit tests for DeveloperContextStrategy in amelia.agents.developer module."""
import pytest

from amelia.agents.developer import DeveloperContextStrategy
from amelia.core.context import ContextSection
from amelia.core.state import FileOperation, TaskStep


class TestDeveloperContextStrategy:
    """Test DeveloperContextStrategy context compilation."""

    def test_compile_with_minimal_task_description_only(
        self, mock_execution_state_factory, mock_task_dag_factory, mock_task_factory
    ):
        """Test compile with minimal task (description only, no files or steps)."""
        task = mock_task_factory(
            id="1",
            description="Implement login endpoint",
            files=[],
            steps=[]
        )
        plan = mock_task_dag_factory(tasks=[task])
        state = mock_execution_state_factory(plan=plan, current_task_id="1")

        strategy = DeveloperContextStrategy()
        context = strategy.compile(state)

        # Should have system prompt
        assert context.system_prompt == DeveloperContextStrategy.SYSTEM_PROMPT
        assert "TDD principles" in context.system_prompt
        assert "senior developer" in context.system_prompt

        # Should have task section
        assert len(context.sections) >= 1
        task_section = next((s for s in context.sections if s.name == "task"), None)
        assert task_section is not None
        assert "Implement login endpoint" in task_section.content

    def test_compile_with_task_and_files(
        self, mock_execution_state_factory, mock_task_dag_factory, mock_task_factory
    ):
        """Test compile with task + files section."""
        task = mock_task_factory(
            id="1",
            description="Implement user authentication",
            files=[
                FileOperation(operation="create", path="src/auth.py"),
                FileOperation(operation="modify", path="src/main.py"),
                FileOperation(operation="test", path="tests/test_auth.py")
            ],
            steps=[]
        )
        plan = mock_task_dag_factory(tasks=[task])
        state = mock_execution_state_factory(plan=plan, current_task_id="1")

        strategy = DeveloperContextStrategy()
        context = strategy.compile(state)

        # Should have task and files sections
        section_names = {s.name for s in context.sections}
        assert "task" in section_names
        assert "files" in section_names

        # Files section should be formatted as bullet list
        files_section = next((s for s in context.sections if s.name == "files"), None)
        assert files_section is not None
        assert "create" in files_section.content.lower()
        assert "src/auth.py" in files_section.content
        assert "modify" in files_section.content.lower()
        assert "src/main.py" in files_section.content
        assert "test" in files_section.content.lower()
        assert "tests/test_auth.py" in files_section.content

    def test_compile_with_task_files_and_steps(
        self, mock_execution_state_factory, mock_task_dag_factory, mock_task_factory
    ):
        """Test compile with task + files + steps section."""
        task = mock_task_factory(
            id="1",
            description="Create authentication module",
            files=[
                FileOperation(operation="create", path="src/auth.py")
            ],
            steps=[
                TaskStep(
                    description="Create user model",
                    code="class User:\n    pass"
                ),
                TaskStep(
                    description="Run tests",
                    command="pytest tests/test_auth.py"
                )
            ]
        )
        plan = mock_task_dag_factory(tasks=[task])
        state = mock_execution_state_factory(plan=plan, current_task_id="1")

        strategy = DeveloperContextStrategy()
        context = strategy.compile(state)

        # Should have task, files, and steps sections
        section_names = {s.name for s in context.sections}
        assert "task" in section_names
        assert "files" in section_names
        assert "steps" in section_names

    def test_steps_include_code_blocks_when_present(
        self, mock_execution_state_factory, mock_task_dag_factory, mock_task_factory
    ):
        """Test steps section includes code blocks when step.code is present."""
        task = mock_task_factory(
            id="1",
            description="Implement feature",
            files=[],
            steps=[
                TaskStep(
                    description="Write function",
                    code="def authenticate(user, password):\n    return True"
                ),
                TaskStep(
                    description="Add docstring",
                    code='"""Authenticate user with password."""'
                )
            ]
        )
        plan = mock_task_dag_factory(tasks=[task])
        state = mock_execution_state_factory(plan=plan, current_task_id="1")

        strategy = DeveloperContextStrategy()
        context = strategy.compile(state)

        # Steps section should include code blocks
        steps_section = next((s for s in context.sections if s.name == "steps"), None)
        assert steps_section is not None

        # Should contain code from both steps
        assert "def authenticate(user, password):" in steps_section.content
        assert "return True" in steps_section.content
        assert '"""Authenticate user with password."""' in steps_section.content

        # Code should be in markdown code blocks
        content = steps_section.content
        assert "Write function" in content
        assert "Add docstring" in content
        # Verify markdown code block markers
        assert "```" in content

    def test_steps_include_commands_when_present(
        self, mock_execution_state_factory, mock_task_dag_factory, mock_task_factory
    ):
        """Test steps section includes commands when step.command is present."""
        task = mock_task_factory(
            id="1",
            description="Setup and test",
            files=[],
            steps=[
                TaskStep(
                    description="Install dependencies",
                    command="pip install -r requirements.txt"
                ),
                TaskStep(
                    description="Run linter",
                    command="ruff check src/"
                ),
                TaskStep(
                    description="Run tests",
                    command="pytest -v"
                )
            ]
        )
        plan = mock_task_dag_factory(tasks=[task])
        state = mock_execution_state_factory(plan=plan, current_task_id="1")

        strategy = DeveloperContextStrategy()
        context = strategy.compile(state)

        # Steps section should include all commands
        steps_section = next((s for s in context.sections if s.name == "steps"), None)
        assert steps_section is not None

        # Should contain all commands
        assert "pip install -r requirements.txt" in steps_section.content
        assert "ruff check src/" in steps_section.content
        assert "pytest -v" in steps_section.content

        # Should include step descriptions
        assert "Install dependencies" in steps_section.content
        assert "Run linter" in steps_section.content
        assert "Run tests" in steps_section.content

    @pytest.mark.parametrize("setup,error_match", [
        ({"current_task_id": None}, "task"),
        ({"plan": None}, "task"),
    ], ids=["no_current_task", "no_plan"])
    def test_compile_raises_for_missing_task(
        self, mock_execution_state_factory, mock_task_dag_factory, mock_task_factory, setup, error_match
    ):
        """Test compile raises ValueError when current_task_id or plan is missing."""
        # Set up state based on parameters
        if "plan" in setup:
            state = mock_execution_state_factory(plan=setup["plan"], current_task_id="1")
        else:
            task = mock_task_factory(id="1", description="Some task")
            plan = mock_task_dag_factory(tasks=[task])
            state = mock_execution_state_factory(plan=plan, current_task_id=setup["current_task_id"])

        strategy = DeveloperContextStrategy()

        with pytest.raises(ValueError) as exc_info:
            strategy.compile(state)

        # Error message should be clear about missing task
        assert error_match in str(exc_info.value).lower()

    def test_system_prompt_equals_class_constant(
        self, mock_execution_state_factory, mock_task_dag_factory, mock_task_factory
    ):
        """Test SYSTEM_PROMPT is stable and equals class constant (Gap 3)."""
        task = mock_task_factory(id="1", description="Test task")
        plan = mock_task_dag_factory(tasks=[task])
        state = mock_execution_state_factory(plan=plan, current_task_id="1")

        strategy = DeveloperContextStrategy()
        context = strategy.compile(state)

        # System prompt should equal the class constant
        assert context.system_prompt == DeveloperContextStrategy.SYSTEM_PROMPT

    def test_only_allowed_sections_task_files_steps(
        self, mock_execution_state_factory, mock_task_dag_factory, mock_task_factory
    ):
        """Test only 'task', 'files', 'steps' sections are allowed (Gap 5)."""
        task = mock_task_factory(
            id="1",
            description="Test task",
            files=[FileOperation(operation="create", path="test.py")],
            steps=[TaskStep(description="Test step")]
        )
        plan = mock_task_dag_factory(tasks=[task])
        state = mock_execution_state_factory(plan=plan, current_task_id="1")

        strategy = DeveloperContextStrategy()

        # Compile and validate sections
        context = strategy.compile(state)

        # All sections should be in ALLOWED_SECTIONS
        for section in context.sections:
            assert section.name in DeveloperContextStrategy.ALLOWED_SECTIONS

    def test_validate_sections_raises_for_disallowed_section(self):
        """Test validate_sections raises ValueError for disallowed sections (Gap 5)."""
        strategy = DeveloperContextStrategy()

        # Try to validate sections that include a disallowed section
        invalid_sections = [
            ContextSection(name="task", content="Valid task"),
            ContextSection(name="issue", content="Should not be allowed"),  # Not in ALLOWED_SECTIONS
        ]

        with pytest.raises(ValueError) as exc_info:
            strategy.validate_sections(invalid_sections)

        # Error should mention the invalid section name
        assert "issue" in str(exc_info.value).lower()
        assert "not allowed" in str(exc_info.value).lower()

    def test_does_not_include_issue_context(
        self, mock_execution_state_factory, mock_task_dag_factory, mock_task_factory, mock_issue_factory
    ):
        """Test compile does NOT include issue or other agent history (Gap 5)."""
        # Create a state with a full issue
        issue = mock_issue_factory(
            id="TEST-123",
            title="Important Issue Title",
            description="Detailed issue description with requirements"
        )
        task = mock_task_factory(id="1", description="Implement feature")
        plan = mock_task_dag_factory(tasks=[task])
        state = mock_execution_state_factory(
            issue=issue,
            plan=plan,
            current_task_id="1"
        )

        strategy = DeveloperContextStrategy()
        context = strategy.compile(state)

        # Section names should NOT include 'issue'
        section_names = {s.name for s in context.sections}
        assert "issue" not in section_names

        # Content should NOT mention the issue details
        all_content = " ".join(s.content for s in context.sections)
        # The task description might coincidentally match, but issue-specific details should not appear
        assert "Important Issue Title" not in all_content
        assert "Detailed issue description with requirements" not in all_content

    def test_does_not_include_agent_history(
        self, mock_execution_state_factory, mock_task_dag_factory, mock_task_factory
    ):
        """Test compile does NOT include other agent history (Gap 5)."""
        task = mock_task_factory(id="1", description="Test task")
        plan = mock_task_dag_factory(tasks=[task])
        state = mock_execution_state_factory(
            plan=plan,
            current_task_id="1",
            # Add some agent history to the state
            agent_history=["Architect created plan", "Previous developer executed task"]
        )

        strategy = DeveloperContextStrategy()
        context = strategy.compile(state)

        # Should only have task-related sections
        section_names = {s.name for s in context.sections}
        assert "history" not in section_names
        assert "agent_history" not in section_names

        # Content should not include agent history
        all_content = " ".join(s.content for s in context.sections)
        assert "Architect created plan" not in all_content
        assert "Previous developer executed task" not in all_content

    def test_steps_with_both_code_and_command(
        self, mock_execution_state_factory, mock_task_dag_factory, mock_task_factory
    ):
        """Test steps that have both code and command are properly formatted."""
        task = mock_task_factory(
            id="1",
            description="Complex step test",
            files=[],
            steps=[
                TaskStep(
                    description="Write and test function",
                    code="def add(a, b):\n    return a + b",
                    command="pytest tests/test_math.py",
                    expected_output="All tests passed"
                )
            ]
        )
        plan = mock_task_dag_factory(tasks=[task])
        state = mock_execution_state_factory(plan=plan, current_task_id="1")

        strategy = DeveloperContextStrategy()
        context = strategy.compile(state)

        steps_section = next((s for s in context.sections if s.name == "steps"), None)
        assert steps_section is not None

        # Should include both code and command
        assert "def add(a, b):" in steps_section.content
        assert "pytest tests/test_math.py" in steps_section.content
        assert "Write and test function" in steps_section.content

    @pytest.mark.parametrize("files,steps,expected_sections,missing_section", [
        ([], [TaskStep(description="Do something")], {"task", "steps"}, "files"),
        ([FileOperation(operation="create", path="test.py")], [], {"task", "files"}, "steps"),
    ], ids=["empty_files", "empty_steps"])
    def test_empty_list_omits_section(
        self, mock_execution_state_factory, mock_task_dag_factory, mock_task_factory,
        files, steps, expected_sections, missing_section
    ):
        """Test that empty files or steps list omits that section from output."""
        task = mock_task_factory(
            id="1",
            description="Task with empty list",
            files=files,
            steps=steps
        )
        plan = mock_task_dag_factory(tasks=[task])
        state = mock_execution_state_factory(plan=plan, current_task_id="1")

        strategy = DeveloperContextStrategy()
        context = strategy.compile(state)

        section_names = {s.name for s in context.sections}
        # Should have expected sections
        for expected in expected_sections:
            assert expected in section_names
        # Missing section should be omitted when empty
        assert missing_section not in section_names

    def test_to_messages_integration(
        self, mock_execution_state_factory, mock_task_dag_factory, mock_task_factory
    ):
        """Test that compiled context converts to messages correctly."""
        task = mock_task_factory(
            id="1",
            description="Integration test task",
            files=[FileOperation(operation="create", path="src/app.py")],
            steps=[TaskStep(description="Write code", code="print('hello')")]
        )
        plan = mock_task_dag_factory(tasks=[task])
        state = mock_execution_state_factory(plan=plan, current_task_id="1")

        strategy = DeveloperContextStrategy()
        context = strategy.compile(state)
        messages = strategy.to_messages(context)

        # System prompt is passed separately - to_messages only returns user messages
        assert len(messages) == 1
        assert messages[0].role == "user"

        # User message should contain task information
        user_content = messages[0].content
        assert "Integration test task" in user_content
        assert "src/app.py" in user_content

        # Verify system_prompt is still set on the context
        assert context.system_prompt == DeveloperContextStrategy.SYSTEM_PROMPT
