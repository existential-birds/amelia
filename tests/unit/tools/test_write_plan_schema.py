import pytest
from pydantic import ValidationError

from amelia.tools.write_plan_schema import PlanTask, WritePlanInput


class TestPlanTask:
    """Tests for PlanTask model."""

    def test_minimal_task(self):
        """Task with required fields only."""
        task = PlanTask(
            number="1",
            title="Create the module",
            steps=["**Step 1:** Write the code\n```python\npass\n```"],
        )
        assert task.number == "1"
        assert task.title == "Create the module"
        assert task.files_to_create == []
        assert task.files_to_modify == []

    def test_hierarchical_number(self):
        """Task with hierarchical numbering (e.g., 1.1)."""
        task = PlanTask(
            number="2.3",
            title="Sub-task",
            steps=["Do something"],
        )
        assert task.number == "2.3"

    def test_task_with_files(self):
        """Task with file lists populated."""
        task = PlanTask(
            number="1",
            title="Setup",
            files_to_create=["src/new.py"],
            files_to_modify=["src/existing.py:10-20"],
            steps=["Write the code"],
        )
        assert task.files_to_create == ["src/new.py"]
        assert task.files_to_modify == ["src/existing.py:10-20"]

    def test_task_requires_title(self):
        """Task without title should fail validation."""
        with pytest.raises(ValidationError):
            PlanTask(number="1", title="", steps=["step"])

    def test_task_requires_steps(self):
        """Task with empty steps should fail validation."""
        with pytest.raises(ValidationError):
            PlanTask(number="1", title="Do thing", steps=[])

    def test_invalid_number_format(self):
        """Task number must match N or N.M pattern."""
        with pytest.raises(ValidationError):
            PlanTask(number="abc", title="Bad", steps=["step"])

    def test_number_zero_not_allowed(self):
        """Task number 0 is not allowed (tasks start at 1)."""
        with pytest.raises(ValidationError):
            PlanTask(number="0", title="Bad", steps=["step"])

    def test_hierarchical_zero_subpart_not_allowed(self):
        """Hierarchical number like 1.0 is not allowed (sub-parts start at 1)."""
        with pytest.raises(ValidationError):
            PlanTask(number="1.0", title="Bad", steps=["step"])

    def test_hierarchical_number_valid_range(self):
        """Various valid hierarchical numbers."""
        for num in ("1.1", "3.9", "10.1", "1.12"):
            task = PlanTask(number=num, title="Ok", steps=["step"])
            assert task.number == num


class TestWritePlanInput:
    """Tests for WritePlanInput model."""

    def _make_task(self, number: str = "1", title: str = "Task") -> PlanTask:
        return PlanTask(number=number, title=title, steps=["Do something"])

    def test_minimal_valid_input(self):
        """Valid input with required fields."""
        plan = WritePlanInput(
            goal="Build user auth",
            architecture_summary="JWT-based auth with middleware",
            tasks=[self._make_task()],
            file_path="/docs/plans/test.md",
        )
        assert plan.goal == "Build user auth"
        assert plan.tech_stack == []
        assert len(plan.tasks) == 1

    def test_full_input(self):
        """Valid input with all fields populated."""
        plan = WritePlanInput(
            goal="Build user auth",
            architecture_summary="JWT-based auth",
            tech_stack=["Python", "FastAPI", "JWT"],
            tasks=[self._make_task("1"), self._make_task("2")],
            file_path="/docs/plans/test.md",
        )
        assert len(plan.tasks) == 2
        assert plan.tech_stack == ["Python", "FastAPI", "JWT"]

    def test_empty_goal_rejected(self):
        """Empty goal should fail validation."""
        with pytest.raises(ValidationError):
            WritePlanInput(
                goal="",
                architecture_summary="arch",
                tasks=[self._make_task()],
                file_path="/docs/plans/test.md",
            )

    def test_no_tasks_rejected(self):
        """Empty tasks list should fail validation."""
        with pytest.raises(ValidationError):
            WritePlanInput(
                goal="Build something",
                architecture_summary="arch",
                tasks=[],
                file_path="/docs/plans/test.md",
            )

    def test_empty_file_path_rejected(self):
        """Empty file_path should fail validation."""
        with pytest.raises(ValidationError):
            WritePlanInput(
                goal="Build something",
                architecture_summary="arch",
                tasks=[self._make_task()],
                file_path="",
            )

    def test_empty_architecture_summary_rejected(self):
        """Empty architecture_summary should fail validation."""
        with pytest.raises(ValidationError):
            WritePlanInput(
                goal="Build something",
                architecture_summary="",
                tasks=[self._make_task()],
                file_path="/docs/plans/test.md",
            )
