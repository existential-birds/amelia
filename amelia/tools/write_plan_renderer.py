"""Markdown renderer for structured plan data.

Takes a validated WritePlanInput and produces consistent markdown
with guaranteed ### Task N: headers that downstream consumers expect.
"""

from amelia.tools.write_plan_schema import PlanTask, WritePlanInput


def render_plan_markdown(plan: WritePlanInput) -> str:
    """Render a WritePlanInput into markdown format.

    The output is guaranteed to:
    - Start with # Title, **Goal:**, **Architecture:**, **Tech Stack:**
    - Have --- separator before tasks
    - Use ### Task N: Title format for every task header
    - Include **Files:** sections with Create:/Modify: lists
    - Include all step content verbatim

    Args:
        plan: Validated plan input data.

    Returns:
        Rendered markdown string.
    """
    parts: list[str] = []

    # Header
    parts.append(f"# {plan.goal} Implementation Plan")
    parts.append("")
    parts.append(f"**Goal:** {plan.goal}")
    parts.append("")
    parts.append(f"**Architecture:** {plan.architecture_summary}")
    parts.append("")
    tech = ", ".join(plan.tech_stack) if plan.tech_stack else ""
    parts.append(f"**Tech Stack:** {tech}")
    parts.append("")
    parts.append("---")
    parts.append("")

    # Tasks
    for task in plan.tasks:
        parts.append(_render_task(task))
        parts.append("")

    # Summary
    parts.append("---")
    parts.append("")
    parts.append("## Summary")
    parts.append("")
    parts.append(
        f"This plan contains {len(plan.tasks)} task(s) to accomplish: {plan.goal}"
    )
    parts.append("")

    return "\n".join(parts)


def _render_task(task: PlanTask) -> str:
    """Render a single PlanTask into markdown.

    Args:
        task: The task to render.

    Returns:
        Markdown string for this task section.
    """
    lines: list[str] = []

    # Task header — guaranteed format
    lines.append(f"### Task {task.number}: {task.title}")
    lines.append("")

    # Files section
    has_files = task.files_to_create or task.files_to_modify
    if has_files:
        lines.append("**Files:**")
        for f in task.files_to_create:
            lines.append(f"- Create: `{f}`")
        for f in task.files_to_modify:
            lines.append(f"- Modify: `{f}`")
        lines.append("")

    # Steps
    for step in task.steps:
        lines.append(step)
        lines.append("")

    return "\n".join(lines)
