"""Reviewer agent for code review in the Amelia orchestrator."""

import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import uuid4

from loguru import logger
from pydantic import BaseModel, ConfigDict, Field

from amelia.core.types import AgentConfig, Profile, ReviewResult, Severity
from amelia.drivers.factory import get_driver
from amelia.server.models.events import EventLevel, EventType, WorkflowEvent


if TYPE_CHECKING:
    from amelia.pipelines.implementation.state import ImplementationState
    from amelia.server.events.bus import EventBus


class ReviewItemSeverity(StrEnum):
    """Severity level for individual review items (beagle format)."""

    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"


class ReviewVerdict(StrEnum):
    """Verdict for structured review results."""

    APPROVED = "approved"
    NEEDS_FIXES = "needs_fixes"
    BLOCKED = "blocked"


def normalize_severity(value: str | None, default: Severity = Severity.MEDIUM) -> Severity:
    """Normalize a severity value to a valid Severity enum.

    LLMs may return invalid severity values like "none" or other hallucinated
    values. This function ensures we always get a valid Severity.

    Args:
        value: The severity value to normalize.
        default: The default severity to use if value is invalid.

    Returns:
        A valid Severity enum member.

    """
    if value is not None:
        try:
            return Severity(value)
        except ValueError:
            pass
    return default


class ReviewItem(BaseModel):
    """Single review item with full context.

    Follows beagle review skill format: [FILE:LINE] TITLE

    Note on Severity:
        Uses 'critical/major/minor' to match the beagle review skill format for
        individual items. This differs from ReviewResult.severity which uses
        'low/medium/high/critical' (Severity enum) for orchestrator integration.

    Attributes:
        number: Sequential issue number.
        title: Brief issue title.
        file_path: Path to the file containing the issue.
        line: Line number where the issue occurs.
        severity: Issue severity level (critical/major/minor).
        issue: Description of what's wrong.
        why: Explanation of why it matters.
        fix: Recommended fix.

    """

    model_config = ConfigDict(frozen=True)

    number: int
    title: str
    file_path: str
    line: int
    severity: ReviewItemSeverity
    issue: str  # What's wrong
    why: str  # Why it matters
    fix: str  # Recommended fix


class StructuredReviewResult(BaseModel):
    """Structured review output matching beagle format.

    Attributes:
        summary: 1-2 sentence overview of the review.
        items: List of all review items with full context.
        good_patterns: Things done well that should be preserved.
        verdict: Overall review verdict.

    """

    model_config = ConfigDict(frozen=True)

    summary: str
    items: list[ReviewItem]
    good_patterns: list[str] = Field(default_factory=list)
    verdict: ReviewVerdict


class Reviewer:
    """Agent responsible for reviewing code changes against requirements.

    Review Method:
        agentic_review(): Agentic review that auto-detects technologies, loads review
            skills, and fetches diff via git. Returns ReviewResult with properly
            separated issues (not including observations or praise).

    Attributes:
        driver: LLM driver interface for generating reviews.

    """

    AGENTIC_REVIEW_PROMPT = """You are an expert code reviewer. Your task is to review code changes using the appropriate review skills.

## Process

1. **Identify Changed Files**: Run `git diff --name-only {base_commit}` to see what files changed

2. **Detect Technologies**: Based on file extensions and imports, identify the stack:
   - Python files (.py): Look for FastAPI, Pydantic-AI, SQLAlchemy, pytest
   - Go files (.go): Look for BubbleTea, Wish, Prometheus
   - TypeScript/React (.tsx, .ts): Look for React Router, shadcn/ui, Zustand, React Flow

3. **Load Review Skills**: Use the `Skill` tool to load appropriate review skills:
   - Python: `beagle:review-python` (FastAPI, pytest, Pydantic)
   - Go: `beagle:review-go` (error handling, concurrency, interfaces)
   - Frontend: `beagle:review-frontend` (React, TypeScript, CSS)
   - TUI: `beagle:review-tui` (BubbleTea terminal apps)

4. **Get the Diff**: Run `git diff {base_commit}` to get the full diff

5. **Review**: Follow the loaded skill's instructions to review the code

6. **Output**: Provide your review in the following markdown format:

```markdown
## Review Summary

[1-2 sentence overview of findings]

## Issues

### Critical (Blocking)

1. [FILE:LINE] ISSUE_TITLE
   - Issue: Description of what's wrong
   - Why: Why this matters (bug, type safety, security)
   - Fix: Specific recommended fix

### Major (Should Fix)

2. [FILE:LINE] ISSUE_TITLE
   - Issue: ...
   - Why: ...
   - Fix: ...

### Minor (Nice to Have)

N. [FILE:LINE] ISSUE_TITLE
   - Issue: ...
   - Why: ...
   - Fix: ...

## Good Patterns

- [FILE:LINE] Pattern description (preserve this)

## Verdict

Ready: Yes | No | With fixes 1-N
Rationale: [1-2 sentences]
```

## Rules

- Load skills BEFORE reviewing (not after)
- Number every issue sequentially (1, 2, 3...)
- Include FILE:LINE for each issue
- Separate Issue/Why/Fix clearly
- Categorize by actual severity (Critical/Major/Minor)
- Only flag real issues - check linters first before flagging style issues
- "Ready: Yes" means approved to merge as-is"""

    def __init__(
        self,
        config: AgentConfig,
        event_bus: "EventBus | None" = None,
        prompts: dict[str, str] | None = None,
        agent_name: str = "reviewer",
    ):
        """Initialize the Reviewer agent.

        Args:
            config: Agent configuration with driver, model, and options.
            event_bus: Optional EventBus for emitting workflow events.
            prompts: Optional dict mapping prompt IDs to custom content.
                Supports key: "reviewer.agentic".
            agent_name: Name used in logs/events. Use "task_reviewer" for task-based
                execution to distinguish from final review.

        """
        self.driver = get_driver(config.driver, model=config.model)
        self.options = config.options
        self._event_bus = event_bus
        self._prompts = prompts or {}
        self._agent_name = agent_name

    @property
    def agentic_prompt(self) -> str:
        return self._prompts.get("reviewer.agentic", self.AGENTIC_REVIEW_PROMPT)

    def _extract_task_context(self, state: "ImplementationState") -> str | None:
        """Extract task context from execution state.

        For multi-task execution, extracts only the current task section
        from the full plan.

        Args:
            state: Current execution state containing plan or goal.

        Returns:
            Formatted task context string, or None if no context found.
        """
        if state.plan_markdown:
            from amelia.pipelines.implementation.utils import extract_task_section  # noqa: PLC0415

            total = state.total_tasks
            current = state.current_task_index

            if total == 1:
                return f"**Task:**\n\n{state.plan_markdown}"

            task_section = extract_task_section(state.plan_markdown, current)
            return f"**Current Task ({current + 1}/{total}):**\n\n{task_section}"

        if state.goal:
            return f"**Task Goal:**\n\n{state.goal}"

        if state.issue:
            issue_parts = []
            if state.issue.title:
                issue_parts.append(f"**{state.issue.title}**")
            if state.issue.description:
                issue_parts.append(state.issue.description)
            if issue_parts:
                return "\n\n".join(issue_parts)

        return None

    def _emit_review_completion(
        self,
        workflow_id: str,
        approved: bool,
        severity: Severity,
        comments: list[str],
    ) -> None:
        """Emit event for review completion.

        Args:
            workflow_id: Workflow ID for stream events.
            approved: Whether the review approved the changes.
            severity: The severity level of the review findings.
            comments: List of review comments.

        """
        if self._event_bus is None:
            return

        status = "Approved" if approved else "Changes requested"

        content_parts = [f"**Review completed:** {status} (severity: {severity})"]

        # Comments are already filtered to actionable issues at the source
        if not approved and comments:
            content_parts.append("\n**Issues to fix:**")
            for comment in comments:
                content_parts.append(f"- {comment}")
        elif comments:
            content_parts.append("\n**Comments:**")
            for comment in comments:
                content_parts.append(f"- {comment}")

        event = WorkflowEvent(
            id=str(uuid4()),
            workflow_id=workflow_id,
            sequence=0,
            timestamp=datetime.now(UTC),
            agent=self._agent_name,
            event_type=EventType.AGENT_OUTPUT,
            level=EventLevel.TRACE,
            message="\n".join(content_parts),
        )
        self._event_bus.emit(event)

    async def agentic_review(
        self,
        state: "ImplementationState",
        base_commit: str,
        profile: Profile,
        *,
        workflow_id: str,
    ) -> tuple[ReviewResult, str | None]:
        """Perform agentic code review that fetches diff using git tools.

        This method uses agentic execution to:
        1. Auto-detect technologies in the changed files
        2. Load appropriate review skills (beagle:review-python, etc.)
        3. Fetch the diff using git tools
        4. Review the code following the loaded skills

        This approach avoids passing large diffs via command line arguments,
        which can fail with "Argument list too long" errors.

        Uses the unified AgenticMessage stream from the driver, independent
        of the specific driver implementation (CLI or API).

        Args:
            state: Current execution state containing issue context.
            base_commit: Git commit hash to diff against.
            profile: The profile containing working directory settings.
            workflow_id: Workflow ID for stream events (required).

        Returns:
            Tuple of (ReviewResult, session_id from driver).

        """
        from amelia.drivers.base import AgenticMessageType  # noqa: PLC0415

        # Build the task prompt using shared helper
        task_context = self._extract_task_context(state) or "Review the code changes."

        prompt = f"""Review the code changes for this task:

{task_context}

The changes are in git - diff against commit: {base_commit}"""

        # Build system prompt with base_commit
        system_prompt = self.agentic_prompt.format(base_commit=base_commit)

        if profile.working_dir is None:
            logger.warning(
                "profile.working_dir is None, falling back to current directory",
                agent=self._agent_name,
                workflow_id=workflow_id,
            )
        cwd = profile.working_dir or "."
        session_id = state.driver_session_id
        new_session_id: str | None = None
        final_result: str | None = None
        has_error: bool = False

        logger.info(
            "Starting agentic review",
            agent=self._agent_name,
            base_commit=base_commit,
            workflow_id=workflow_id,
        )

        # Execute agentic review using unified AgenticMessage stream
        async for msg in self.driver.execute_agentic(
            prompt=prompt,
            cwd=cwd,
            session_id=session_id,
            instructions=system_prompt,
        ):
            # Emit stream events for visibility using to_workflow_event()
            if self._event_bus is not None and msg.type != AgenticMessageType.RESULT:
                event = msg.to_workflow_event(workflow_id=workflow_id, agent=self._agent_name)
                self._event_bus.emit(event)

            # Capture final result from RESULT message
            if msg.type == AgenticMessageType.RESULT:
                new_session_id = msg.session_id
                final_result = msg.content
                has_error = msg.is_error
                if msg.is_error:
                    logger.error(
                        "Agentic review failed",
                        agent=self._agent_name,
                        error=msg.content,
                        workflow_id=workflow_id,
                    )

        # Parse the result to extract review
        result = self._parse_review_result(final_result, workflow_id)

        logger.debug(
            "After _parse_review_result",
            approved=result.approved,
            has_error=has_error,
            severity=result.severity,
            comments_count=len(result.comments),
            workflow_id=workflow_id,
        )

        # If there was an error, ensure result is not approved
        if has_error and result.approved:
            logger.warning(
                "Overriding approved=True due to has_error=True",
                original_approved=result.approved,
                workflow_id=workflow_id,
            )
            result = ReviewResult(
                reviewer_persona=result.reviewer_persona,
                approved=False,
                comments=result.comments,
                severity=Severity.HIGH if result.severity in (Severity.LOW, Severity.MEDIUM) else result.severity,
            )

        # Emit completion event
        self._emit_review_completion(
            workflow_id,
            result.approved,
            result.severity,
            result.comments,
        )

        logger.info(
            "Agentic review completed",
            agent=self._agent_name,
            approved=result.approved,
            issue_count=len(result.comments),
            severity=result.severity,
            workflow_id=workflow_id,
        )

        return result, new_session_id

    def _parse_review_result(self, output: str | None, workflow_id: str) -> ReviewResult:
        """Parse the agent's output to extract ReviewResult.

        Parses the beagle review markdown format with sections:
        - Review Summary
        - Issues (Critical/Major/Minor)
        - Good Patterns
        - Verdict

        Args:
            output: The agent's final output text.
            workflow_id: Workflow ID for logging.

        Returns:
            Parsed ReviewResult with issues as comments (not good patterns).

        """
        if not output:
            logger.warning(
                "No output from agentic review, defaulting to not approved",
                agent=self._agent_name,
                workflow_id=workflow_id,
            )
            return ReviewResult(
                reviewer_persona="Agentic",
                approved=False,
                comments=["Review did not produce output"],
                severity=Severity.HIGH,
            )

        # Parse verdict to determine approval
        # Handle markdown formatting like **Ready:** Yes, **Ready**: Yes, or __Ready:__ Yes
        # Pattern allows bold/italic markers before "Ready", between "Ready" and ":", and after ":"
        verdict_match = re.search(
            r"[*_]{0,2}Ready[*_]{0,2}:[*_]{0,2}\s*(Yes|No|With fixes[^\n]*)",
            output,
            re.IGNORECASE,
        )
        logger.debug(
            "Parsing verdict from review output",
            verdict_match_found=verdict_match is not None,
            verdict_text=verdict_match.group(1) if verdict_match else None,
            output_preview=output[:500] if output else None,
            workflow_id=workflow_id,
        )
        if verdict_match:
            verdict_text = verdict_match.group(1).lower()
            approved = verdict_text == "yes"
            logger.debug(
                "Verdict parsed from regex match",
                verdict_text=verdict_text,
                approved=approved,
                workflow_id=workflow_id,
            )
        else:
            # Fallback: check for approval keywords
            output_lower = output.lower()
            approval_keywords_found = [
                word for word in ["ready: yes", "approved", "lgtm", "looks good"]
                if word in output_lower
            ]
            rejection_keywords_found = [
                word for word in ["ready: no", "not approved", "needs fixes", "blocked"]
                if word in output_lower
            ]
            approved = bool(approval_keywords_found)
            if rejection_keywords_found:
                approved = False
            logger.debug(
                "Verdict parsed from fallback keywords",
                approval_keywords_found=approval_keywords_found,
                rejection_keywords_found=rejection_keywords_found,
                approved=approved,
                workflow_id=workflow_id,
            )

        # Parse issues from each severity section
        issues: list[tuple[str, str]] = []  # (severity, issue_text)

        # Match numbered issues: "1. [FILE:LINE] TITLE" or just "1. TITLE"
        issue_pattern = re.compile(
            r"^\s*(\d+)\.\s*(?:\[([^\]]+)\])?\s*(.+?)$",
            re.MULTILINE,
        )

        # Determine current section by tracking headers
        current_severity: str | None = None
        for line in output.split("\n"):
            line_stripped = line.strip().lower()

            # Detect severity section headers
            if "### critical" in line_stripped or "critical (blocking)" in line_stripped:
                current_severity = "critical"
            elif "### major" in line_stripped or "major (should fix)" in line_stripped:
                current_severity = "major"
            elif "### minor" in line_stripped or "minor (nice to have)" in line_stripped:
                current_severity = "minor"
            elif line_stripped.startswith("## good patterns"):
                current_severity = None  # Stop collecting issues
            elif line_stripped.startswith("## verdict"):
                current_severity = None

            # Match issues in current section
            if current_severity:
                issue_match = issue_pattern.match(line)
                if issue_match:
                    file_line = issue_match.group(2) or ""
                    title = issue_match.group(3).strip()
                    if file_line:
                        issue_text = f"[{current_severity}] [{file_line}] {title}"
                    else:
                        issue_text = f"[{current_severity}] {title}"
                    issues.append((current_severity, issue_text))

        # Determine overall severity from highest issue severity
        severity_priority = {"critical": 3, "major": 2, "minor": 1}
        if issues:
            max_severity_value = max(severity_priority.get(sev, 0) for sev, _ in issues)
            severity_map: dict[int, Severity] = {
                3: Severity.CRITICAL,
                2: Severity.HIGH,  # major maps to high
                1: Severity.MEDIUM,  # minor maps to medium
                0: Severity.LOW,
            }
            overall_severity = severity_map[max_severity_value]
        else:
            overall_severity = Severity.LOW if approved else Severity.MEDIUM

        # Extract just the issue text for comments
        comments = [issue_text for _, issue_text in issues]

        # If no structured issues found, try legacy parsing
        if not comments:
            for raw_line in output.split("\n"):
                line = raw_line.strip()
                if line.startswith(("- ", "* ", "• ")) or re.match(r"^\d+\.", line):
                    # Skip good patterns section items
                    if "good pattern" in output.lower():
                        good_patterns_pos = output.lower().find("## good patterns")
                        verdict_pos = output.lower().find("## verdict")
                        line_pos = output.find(line)
                        in_good_patterns = (
                            good_patterns_pos != -1
                            and line_pos > good_patterns_pos
                            and (verdict_pos == -1 or line_pos < verdict_pos)
                        )
                        if in_good_patterns:
                            continue  # Skip good patterns

                    comment = re.sub(r"^[-*•]\s*|\d+\.\s*", "", line).strip()
                    if comment and len(comment) > 10:
                        comments.append(comment)

        if not comments and not approved:
            comments = ["See review output for details"]

        logger.debug(
            "Parsed review result",
            agent=self._agent_name,
            approved=approved,
            issue_count=len(comments),
            severity=overall_severity,
            workflow_id=workflow_id,
        )

        return ReviewResult(
            reviewer_persona="Agentic",
            approved=approved,
            comments=comments[:20],  # Limit to 20 issues
            severity=overall_severity,
        )
