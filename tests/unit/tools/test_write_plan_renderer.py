import re

from amelia.tools.write_plan_renderer import render_plan_markdown
from amelia.tools.write_plan_schema import PlanTask, WritePlanInput


class TestRenderPlanMarkdown:
    """Tests for render_plan_markdown function."""

    def _make_plan(self, **overrides) -> WritePlanInput:
        defaults = {
            "goal": "Build user authentication",
            "architecture_summary": "JWT-based auth with FastAPI middleware.",
            "tech_stack": ["Python", "FastAPI"],
            "tasks": [
                PlanTask(
                    number="1",
                    title="Create auth module",
                    files_to_create=["src/auth.py"],
                    files_to_modify=["src/main.py:5-10"],
                    steps=[
                        "**Step 1: Write the failing test**\n\n```python\ndef test_auth():\n    assert False\n```",
                        "**Step 2: Implement**\n\n```python\ndef auth():\n    return True\n```",
                    ],
                ),
            ],
            "file_path": "/docs/plans/test.md",
        }
        defaults.update(overrides)
        return WritePlanInput(**defaults)

    def test_header_contains_goal(self):
        """Rendered markdown must contain **Goal:** with the plan goal."""
        plan = self._make_plan()
        md = render_plan_markdown(plan)
        assert "**Goal:** Build user authentication" in md

    def test_header_contains_architecture(self):
        """Rendered markdown must contain **Architecture:** section."""
        plan = self._make_plan()
        md = render_plan_markdown(plan)
        assert "**Architecture:** JWT-based auth with FastAPI middleware." in md

    def test_header_contains_tech_stack(self):
        """Rendered markdown must contain **Tech Stack:** section."""
        plan = self._make_plan()
        md = render_plan_markdown(plan)
        assert "**Tech Stack:** Python, FastAPI" in md

    def test_task_header_format(self):
        """Task headers must match ### Task N: Title regex exactly."""
        plan = self._make_plan()
        md = render_plan_markdown(plan)
        pattern = r"^### Task 1: Create auth module$"
        assert re.search(pattern, md, re.MULTILINE), f"Pattern not found in:\n{md}"

    def test_task_files_section(self):
        """Tasks should include Create: and Modify: file lists."""
        plan = self._make_plan()
        md = render_plan_markdown(plan)
        assert "- Create: `src/auth.py`" in md
        assert "- Modify: `src/main.py:5-10`" in md

    def test_task_steps_rendered(self):
        """Each step should appear in the rendered output."""
        plan = self._make_plan()
        md = render_plan_markdown(plan)
        assert "**Step 1: Write the failing test**" in md
        assert "**Step 2: Implement**" in md

    def test_hierarchical_task_number(self):
        """Hierarchical task numbers render as ### Task N.M: Title."""
        plan = self._make_plan(
            tasks=[
                PlanTask(number="1.1", title="Sub-task A", steps=["Do A"]),
                PlanTask(number="1.2", title="Sub-task B", steps=["Do B"]),
            ]
        )
        md = render_plan_markdown(plan)
        assert re.search(r"^### Task 1\.1: Sub-task A$", md, re.MULTILINE)
        assert re.search(r"^### Task 1\.2: Sub-task B$", md, re.MULTILINE)

    def test_multiple_tasks(self):
        """Multiple tasks should each have correct headers."""
        plan = self._make_plan(
            tasks=[
                PlanTask(number="1", title="First", steps=["Step A"]),
                PlanTask(number="2", title="Second", steps=["Step B"]),
                PlanTask(number="3", title="Third", steps=["Step C"]),
            ]
        )
        md = render_plan_markdown(plan)
        assert re.search(r"^### Task 1: First$", md, re.MULTILINE)
        assert re.search(r"^### Task 2: Second$", md, re.MULTILINE)
        assert re.search(r"^### Task 3: Third$", md, re.MULTILINE)

    def test_extract_task_count_compatible(self):
        """Rendered output must be parseable by extract_task_count."""
        from amelia.pipelines.implementation.utils import extract_task_count

        plan = self._make_plan(
            tasks=[
                PlanTask(number="1", title="First", steps=["A"]),
                PlanTask(number="2", title="Second", steps=["B"]),
            ]
        )
        md = render_plan_markdown(plan)
        assert extract_task_count(md) == 2

    def test_validate_plan_structure_compatible(self):
        """Rendered output must pass validate_plan_structure."""
        from amelia.pipelines.implementation.utils import validate_plan_structure

        plan = self._make_plan()
        md = render_plan_markdown(plan)
        result = validate_plan_structure(plan.goal, md)
        assert result.valid, f"Validation failed: {result.issues}"

    def test_separator_between_header_and_tasks(self):
        """There must be a --- separator between the header and tasks."""
        plan = self._make_plan()
        md = render_plan_markdown(plan)
        assert "\n---\n" in md

    def test_empty_tech_stack_omitted(self):
        """If tech_stack is empty, still render header but with empty value."""
        plan = self._make_plan(tech_stack=[])
        md = render_plan_markdown(plan)
        # Should still have Tech Stack line but may be empty
        assert "**Tech Stack:**" in md
