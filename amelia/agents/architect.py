from datetime import date
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from amelia.core.state import AgentMessage, Task, TaskDAG
from amelia.core.types import Design, Issue
from amelia.drivers.base import DriverInterface


class TaskListResponse(BaseModel):
    """Schema for LLM-generated list of tasks."""
    tasks: list[Task] = Field(description="A list of actionable development tasks.")


class PlanOutput(BaseModel):
    """Output from architect planning."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    task_dag: TaskDAG
    markdown_path: Path


def _slugify(text: str) -> str:
    """Convert text to URL-friendly slug."""
    return text.lower().replace(" ", "-").replace("_", "-")[:50]


class Architect:
    """Agent responsible for creating implementation plans from issues and designs.

    Attributes:
        driver: LLM driver interface for generating plans.
    """

    def __init__(self, driver: DriverInterface):
        """Initialize the Architect agent.

        Args:
            driver: LLM driver interface for generating plans.
        """
        self.driver = driver

    async def plan(
        self,
        issue: Issue,
        design: Design | None = None,
        output_dir: str = "docs/plans"
    ) -> PlanOutput:
        """
        Generates a development plan from an issue and optional design.

        Returns both structured TaskDAG and saves markdown for human review.
        """
        context = self._build_context(issue, design)
        task_dag = await self._generate_task_dag(context, issue)
        markdown_path = self._save_markdown(task_dag, issue, design, output_dir)

        return PlanOutput(task_dag=task_dag, markdown_path=markdown_path)

    def _build_context(self, issue: Issue, design: Design | None) -> str:
        """Build context string from issue and optional design."""
        context = f"Issue: {issue.title}\nDescription: {issue.description}\n"

        if design:
            context += "\nDesign Context:\n"
            context += f"Title: {design.title}\n"
            context += f"Goal: {design.goal}\n"
            context += f"Architecture: {design.architecture}\n"
            context += f"Tech Stack: {', '.join(design.tech_stack)}\n"
            context += f"Components: {', '.join(design.components)}\n"
            if design.data_flow:
                context += f"Data Flow: {design.data_flow}\n"
            if design.error_handling:
                context += f"Error Handling: {design.error_handling}\n"
            if design.testing_strategy:
                context += f"Testing Strategy: {design.testing_strategy}\n"
            if design.relevant_files:
                context += f"Relevant Files: {', '.join(design.relevant_files)}\n"
            if design.conventions:
                context += f"Conventions: {design.conventions}\n"

        return context

    async def _generate_task_dag(self, context: str, issue: Issue) -> TaskDAG:
        """Generate TaskDAG using LLM.

        Args:
            context: Formatted context string containing issue and design information.
            issue: Original issue being planned.

        Returns:
            TaskDAG containing structured tasks with TDD steps.
        """
        system_prompt = """You are an expert software architect creating implementation plans.

Your role is to break down the given context into a sequence of actionable development tasks.
Each task MUST follow TDD (Test-Driven Development) principles.

For each task, provide:
- id: Unique identifier (e.g., "1", "2", "3")
- description: Clear, concise description of what to build
- dependencies: List of task IDs this task depends on
- files: List of FileOperation objects with:
  - operation: "create", "modify", or "test"
  - path: Exact file path (e.g., "src/auth/middleware.py")
  - line_range: Optional, for modify operations (e.g., "10-25")
- steps: List of TaskStep objects following TDD:
  1. Write the failing test (include actual code)
  2. Run test to verify it fails (include command and expected output)
  3. Write minimal implementation (include actual code)
  4. Run test to verify it passes (include command and expected output)
  5. Commit (include commit message)
- commit_message: Conventional commit message (e.g., "feat: add auth middleware")

Each step should be 2-5 minutes of work. Include complete code, not placeholders."""

        user_prompt = f"""Given the following context:

{context}

Create a detailed implementation plan with bite-sized TDD tasks.
Ensure exact file paths, complete code in steps, and commands with expected output."""

        prompt_messages = [
            AgentMessage(role="system", content=system_prompt),
            AgentMessage(role="user", content=user_prompt)
        ]

        response = await self.driver.generate(messages=prompt_messages, schema=TaskListResponse)

        return TaskDAG(tasks=response.tasks, original_issue=issue.id)

    def _save_markdown(
        self,
        task_dag: TaskDAG,
        issue: Issue,
        design: Design | None,
        output_dir: str
    ) -> Path:
        """Save plan as markdown file.

        Args:
            task_dag: Structured task DAG to render.
            issue: Original issue being planned.
            design: Optional design context.
            output_dir: Directory path for saving the markdown file.

        Returns:
            Path to the saved markdown file.
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        title = design.title if design else issue.title
        filename = f"{date.today().isoformat()}-{_slugify(title)}.md"
        file_path = output_path / filename

        md_content = self._render_markdown(task_dag, issue, design)
        file_path.write_text(md_content)

        return file_path

    def _render_markdown(
        self,
        task_dag: TaskDAG,
        issue: Issue,
        design: Design | None
    ) -> str:
        """Render TaskDAG as markdown following writing-plans format.

        Args:
            task_dag: Structured task DAG to render.
            issue: Original issue being planned.
            design: Optional design context.

        Returns:
            Markdown-formatted string representation of the plan.
        """
        title = design.title if design else issue.title
        goal = design.goal if design else issue.description
        architecture = design.architecture if design else "See task descriptions below."
        tech_stack = ", ".join(design.tech_stack) if design else "See implementation details."

        lines = [
            f"# {title} Implementation Plan",
            "",
            "> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.",
            "",
            f"**Goal:** {goal}",
            "",
            f"**Architecture:** {architecture}",
            "",
            f"**Tech Stack:** {tech_stack}",
            "",
            "---",
            "",
        ]

        for i, task in enumerate(task_dag.tasks, 1):
            lines.append(f"### Task {i}: {task.description}")
            lines.append("")

            if task.files:
                lines.append("**Files:**")
                for f in task.files:
                    if f.line_range:
                        lines.append(f"- {f.operation.capitalize()}: `{f.path}:{f.line_range}`")
                    else:
                        lines.append(f"- {f.operation.capitalize()}: `{f.path}`")
                lines.append("")

            for j, step in enumerate(task.steps, 1):
                lines.append(f"**Step {j}: {step.description}**")
                lines.append("")
                if step.code:
                    lines.append("```python")
                    lines.append(step.code)
                    lines.append("```")
                    lines.append("")
                if step.command:
                    lines.append(f"Run: `{step.command}`")
                if step.expected_output:
                    lines.append(f"Expected: {step.expected_output}")
                lines.append("")

            if task.commit_message:
                lines.append("**Commit:**")
                lines.append("```bash")
                if task.files:
                    file_paths = " ".join(f.path for f in task.files)
                    lines.append(f"git add {file_paths}")
                lines.append(f'git commit -m "{task.commit_message}"')
                lines.append("```")
                lines.append("")

            lines.append("---")
            lines.append("")

        return "\n".join(lines)
