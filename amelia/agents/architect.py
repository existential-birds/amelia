# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Architect agent for generating implementation plans.

This module provides the Architect agent that analyzes issues and produces
rich markdown implementation plans for agentic execution.
"""
import os
from datetime import UTC, date, datetime
from pathlib import Path

from loguru import logger
from pydantic import BaseModel, ConfigDict

from amelia.core.context import CompiledContext, ContextSection, ContextStrategy
from amelia.core.state import AgentMessage, ExecutionState
from amelia.core.types import Design, Issue, Profile, StreamEmitter, StreamEvent, StreamEventType
from amelia.drivers.base import DriverInterface


def _slugify(text: str) -> str:
    """Convert text to URL-friendly slug.

    Args:
        text: Input text to convert to slug format.

    Returns:
        Lowercase, hyphenated string truncated to 50 characters.
    """
    return text.lower().replace(" ", "-").replace("_", "-")[:50]


class PlanOutput(BaseModel):
    """Output from Architect plan generation.

    Attributes:
        markdown_content: The full markdown plan content.
        markdown_path: Path where the plan was saved.
        goal: High-level goal extracted from the plan.
        key_files: Files likely to be modified.
    """

    model_config = ConfigDict(frozen=True)

    markdown_content: str
    markdown_path: Path
    goal: str
    key_files: list[str] = []


class ArchitectOutput(BaseModel):
    """Output from Architect analysis (simplified form).

    Used when only analysis is needed, not full plan generation.

    Attributes:
        goal: Clear description of what needs to be done.
        strategy: High-level approach (not step-by-step).
        key_files: Files likely to be modified.
        risks: Potential risks to watch for.
    """

    model_config = ConfigDict(frozen=True)

    goal: str
    strategy: str
    key_files: list[str] = []
    risks: list[str] = []


class MarkdownPlanOutput(BaseModel):
    """Structured output for markdown plan generation.

    This is the schema the LLM uses to generate the plan content.

    Attributes:
        goal: High-level goal for the implementation.
        plan_markdown: The full markdown plan with phases, tasks, and steps.
        key_files: Files that will likely be modified.
    """

    goal: str
    plan_markdown: str
    key_files: list[str] = []


class ArchitectContextStrategy(ContextStrategy):
    """Context compilation strategy for the Architect agent.

    Compiles context for plan generation by including issue information
    and optional design context.
    """

    SYSTEM_PROMPT = """You are a senior software architect creating implementation plans.
Your role is to analyze issues and produce detailed markdown implementation plans."""

    SYSTEM_PROMPT_PLAN = """You are a senior software architect creating implementation plans.

Generate implementation plans in markdown format that follow this structure:

# [Title] Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** [Clear description of what needs to be accomplished]

**Success Criteria:** [How we know when the task is complete]

---

## Phase 1: [Phase Name]

### Task 1.1: [Task Name]

**Step 1: [Step description]**

```[language]
[code block if applicable]
```

**Run:** `[command to run]`

**Success criteria:** [How to verify this step worked]

### Task 1.2: [Next Task]
...

---

## Phase 2: [Next Phase]
...

---

## Summary

[Brief summary of what was accomplished]

---

Guidelines:
- Each Phase groups related work with ## headers
- Each Task is a discrete unit of work with ### headers
- Each Step has code blocks, commands to run, and success criteria
- Include TDD approach: write test first, run to verify it fails, implement, run to verify it passes
- Be specific about file paths, commands, and expected outputs
- Keep steps granular (2-5 minutes of work each)"""

    ALLOWED_SECTIONS = {"issue", "design", "codebase"}

    def get_plan_generation_prompt(self) -> str:
        """Get user prompt for markdown plan generation.

        Returns:
            User prompt string for plan generation.
        """
        return """Analyze the issue and generate a complete implementation plan in markdown format.

The plan should:
1. Include the Claude skill instruction at the top: > **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans
2. Break work into logical Phases (## headers)
3. Each Phase contains Tasks (### headers)
4. Each Task has Steps with code blocks, commands, and success criteria
5. Follow TDD approach where applicable
6. Be specific about file paths and commands
7. Include success criteria for each step

Return the plan as a MarkdownPlanOutput with:
- goal: A clear 1-2 sentence goal statement
- plan_markdown: The full markdown plan content
- key_files: List of files that will be modified"""

    def _format_design_section(self, design: Design) -> str:
        """Format Design into structured markdown for context.

        Args:
            design: The design to format.

        Returns:
            Formatted markdown string with design fields.
        """
        parts = []

        parts.append(f"## Goal\n\n{design.goal}")
        parts.append(f"## Architecture\n\n{design.architecture}")

        if design.tech_stack:
            tech_list = "\n".join(f"- {tech}" for tech in design.tech_stack)
            parts.append(f"## Tech Stack\n\n{tech_list}")

        if design.components:
            comp_list = "\n".join(f"- {comp}" for comp in design.components)
            parts.append(f"## Components\n\n{comp_list}")

        if design.data_flow:
            parts.append(f"## Data Flow\n\n{design.data_flow}")

        if design.error_handling:
            parts.append(f"## Error Handling\n\n{design.error_handling}")

        if design.testing_strategy:
            parts.append(f"## Testing Strategy\n\n{design.testing_strategy}")

        if design.conventions:
            parts.append(f"## Conventions\n\n{design.conventions}")

        if design.relevant_files:
            files_list = "\n".join(f"- `{f}`" for f in design.relevant_files)
            parts.append(f"## Relevant Files\n\n{files_list}")

        return "\n\n".join(parts)

    def _scan_codebase(self, working_dir: str, max_files: int = 500) -> str:
        """Scan the codebase directory and return a file tree structure.

        Args:
            working_dir: Path to the working directory to scan.
            max_files: Maximum number of files to include (default 500).

        Returns:
            Formatted string with file tree structure.
        """
        # Common directories and files to ignore
        ignore_dirs = {
            ".git", ".svn", ".hg",
            "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
            "node_modules", ".venv", "venv", "env",
            "dist", "build", ".next", ".nuxt",
            "coverage", ".coverage", "htmlcov",
            ".idea", ".vscode",
            "eggs", "*.egg-info",
        }
        ignore_files = {".DS_Store", "Thumbs.db", ".gitignore"}

        files: list[str] = []
        root_path = Path(working_dir)

        try:
            for dirpath, dirnames, filenames in os.walk(root_path):
                # Filter out ignored directories (modifies dirnames in-place)
                dirnames[:] = [d for d in dirnames if d not in ignore_dirs and not d.endswith(".egg-info")]

                rel_dir = Path(dirpath).relative_to(root_path)

                for filename in filenames:
                    if filename in ignore_files:
                        continue
                    if len(files) >= max_files:
                        break

                    rel_path = rel_dir / filename if str(rel_dir) != "." else Path(filename)
                    files.append(str(rel_path))

                if len(files) >= max_files:
                    break
        except OSError as e:
            logger.warning(f"Error scanning codebase: {e}")

        # Sort files for consistent output
        files.sort()

        if not files:
            return "No files found in working directory."

        # Format as a simple file list
        file_list = "\n".join(f"- {f}" for f in files)
        header = f"## File Structure ({len(files)} files)\n\n"

        if len(files) >= max_files:
            header += f"(Truncated to first {max_files} files)\n\n"

        return header + file_list

    def compile(self, state: ExecutionState, profile: Profile) -> CompiledContext:
        """Compile ExecutionState into context for analysis.

        Args:
            state: The current execution state.
            profile: The profile containing working directory settings.

        Returns:
            CompiledContext with system prompt and relevant sections.

        Raises:
            ValueError: If required sections are missing.
        """
        sections: list[ContextSection] = []

        # Issue section (required)
        issue_summary = self.get_issue_summary(state)
        if not issue_summary:
            raise ValueError("Issue context is required for planning")

        sections.append(
            ContextSection(
                name="issue",
                content=issue_summary,
                source="state.issue",
            )
        )

        # Design section (optional)
        if state.design:
            design_content = self._format_design_section(state.design)
            sections.append(
                ContextSection(
                    name="design",
                    content=design_content,
                    source="state.design",
                )
            )

        # Codebase section (optional - when working_dir is set)
        if profile.working_dir:
            codebase_content = self._scan_codebase(profile.working_dir)
            sections.append(
                ContextSection(
                    name="codebase",
                    content=codebase_content,
                    source="profile.working_dir",
                )
            )

        # Validate all sections before returning
        self.validate_sections(sections)

        return CompiledContext(
            system_prompt=self.SYSTEM_PROMPT,
            sections=sections,
        )


class Architect:
    """Agent responsible for creating implementation plans from issues.

    Generates rich markdown plans that the Developer agent can follow
    agentically, or provides simplified analysis when full plans aren't needed.

    Attributes:
        driver: LLM driver interface for plan generation.
        context_strategy: Strategy for compiling context from ExecutionState.
    """

    context_strategy: type[ArchitectContextStrategy] = ArchitectContextStrategy

    def __init__(
        self,
        driver: DriverInterface,
        stream_emitter: StreamEmitter | None = None,
    ):
        """Initialize the Architect agent.

        Args:
            driver: LLM driver interface for plan generation.
            stream_emitter: Optional callback for streaming events.
        """
        self.driver = driver
        self._stream_emitter = stream_emitter

    async def plan(
        self,
        state: ExecutionState,
        profile: Profile,
        output_dir: str | None = None,
        *,
        workflow_id: str,
    ) -> PlanOutput:
        """Generate a markdown implementation plan from an issue.

        Creates a rich markdown plan and saves it to docs/plans/. The plan
        follows the superpowers:executing-plans format with phases, tasks,
        and steps that the Developer agent can follow agentically.

        Args:
            state: The execution state containing the issue and optional design.
            profile: The profile containing working directory settings.
            output_dir: Directory path where the markdown plan will be saved.
                If None, uses profile's plan_output_dir (defaults to docs/plans).
            workflow_id: Workflow ID for stream events (required).

        Returns:
            PlanOutput containing the markdown plan content and path.

        Raises:
            ValueError: If no issue is present in the state.
        """
        if not state.issue:
            raise ValueError("Cannot generate plan: no issue in ExecutionState")

        # Use profile's output directory if not specified
        if output_dir is None:
            output_dir = profile.plan_output_dir

        # Resolve relative paths to working_dir (not server CWD)
        output_path = Path(output_dir)
        if not output_path.is_absolute() and profile.working_dir:
            output_dir = str(Path(profile.working_dir) / output_path)

        # Compile context using strategy
        strategy = self.context_strategy()
        compiled_context = strategy.compile(state, profile)

        # Build messages with plan generation system prompt
        system_message = AgentMessage(role="system", content=strategy.SYSTEM_PROMPT_PLAN)
        context_messages = strategy.to_messages(compiled_context)
        user_message = AgentMessage(role="user", content=strategy.get_plan_generation_prompt())

        messages = [system_message, *context_messages, user_message]

        # Call driver with MarkdownPlanOutput schema
        raw_response, _session_id = await self.driver.generate(
            messages=messages,
            schema=MarkdownPlanOutput,
            cwd=profile.working_dir,
            session_id=state.driver_session_id,
        )
        response = MarkdownPlanOutput.model_validate(raw_response)

        # Save markdown to file
        markdown_path = self._save_markdown(
            response.plan_markdown,
            state.issue,
            state.design,
            output_dir,
        )

        logger.info(
            "Architect plan generated",
            agent="architect",
            goal=response.goal[:100] + "..." if len(response.goal) > 100 else response.goal,
            key_files_count=len(response.key_files),
            markdown_path=str(markdown_path),
        )

        # Emit completion event
        if self._stream_emitter is not None:
            event = StreamEvent(
                type=StreamEventType.AGENT_OUTPUT,
                content=f"Plan generated: {response.goal[:100]}...",
                timestamp=datetime.now(UTC),
                agent="architect",
                workflow_id=workflow_id,
            )
            await self._stream_emitter(event)

        return PlanOutput(
            markdown_content=response.plan_markdown,
            markdown_path=markdown_path,
            goal=response.goal,
            key_files=response.key_files,
        )

    def _save_markdown(
        self,
        markdown_content: str,
        issue: Issue,
        design: Design | None,
        output_dir: str,
    ) -> Path:
        """Save plan as markdown file.

        Args:
            markdown_content: The markdown plan content to save.
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

        file_path.write_text(markdown_content)

        return file_path

    async def analyze(
        self,
        state: ExecutionState,
        profile: Profile,
        *,
        workflow_id: str,
    ) -> ArchitectOutput:
        """Analyze an issue and generate goal/strategy (simplified form).

        Creates an ArchitectOutput with high-level goal and strategy
        for quick analysis without full plan generation.

        Args:
            state: The execution state containing the issue and optional design.
            profile: The profile containing working directory settings.
            workflow_id: Workflow ID for stream events (required).

        Returns:
            ArchitectOutput containing goal, strategy, key files, and risks.

        Raises:
            ValueError: If no issue is present in the state.
        """
        if not state.issue:
            raise ValueError("Cannot analyze: no issue in ExecutionState")

        # Compile context using strategy
        strategy = self.context_strategy()
        compiled_context = strategy.compile(state, profile)

        # Convert compiled context to messages
        base_messages = strategy.to_messages(compiled_context)

        # Add user prompt requesting analysis
        user_prompt = """Analyze this issue and provide:
1. A clear goal statement describing what needs to be accomplished
2. A high-level strategy for how to approach the implementation
3. Key files that will likely need to be modified
4. Any potential risks or considerations

Respond with a structured ArchitectOutput."""

        messages = [
            *base_messages,
            AgentMessage(role="user", content=user_prompt),
        ]

        # Call driver with ArchitectOutput schema
        raw_response, new_session_id = await self.driver.generate(
            messages=messages,
            schema=ArchitectOutput,
            cwd=profile.working_dir,
            session_id=state.driver_session_id,
        )
        response = ArchitectOutput.model_validate(raw_response)

        logger.info(
            "Architect analysis complete",
            agent="architect",
            goal=response.goal[:100] + "..." if len(response.goal) > 100 else response.goal,
            key_files_count=len(response.key_files),
            risks_count=len(response.risks),
        )

        # Emit completion event
        if self._stream_emitter is not None:
            event = StreamEvent(
                type=StreamEventType.AGENT_OUTPUT,
                content=f"Analysis complete: {response.goal[:100]}...",
                timestamp=datetime.now(UTC),
                agent="architect",
                workflow_id=workflow_id,
            )
            await self._stream_emitter(event)

        return response
