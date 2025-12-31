import asyncio
import json
import re
from datetime import UTC, datetime
from typing import Literal

from loguru import logger
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from amelia.core.state import ExecutionState, ReviewResult, Severity
from amelia.core.types import Profile, StreamEmitter, StreamEvent, StreamEventType
from amelia.drivers.base import DriverInterface


class ReviewItem(BaseModel):
    """Single review item with full context.

    Follows beagle review skill format: [FILE:LINE] TITLE

    Attributes:
        number: Sequential issue number.
        title: Brief issue title.
        file_path: Path to the file containing the issue.
        line: Line number where the issue occurs.
        severity: Issue severity level.
        issue: Description of what's wrong.
        why: Explanation of why it matters.
        fix: Recommended fix.
    """

    model_config = ConfigDict(frozen=True)

    number: int
    title: str
    file_path: str
    line: int
    severity: Literal["critical", "major", "minor"]
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
    verdict: Literal["approved", "needs_fixes", "blocked"]


class ReviewResponse(BaseModel):
    """Schema for LLM-generated review response.

    Attributes:
        approved: Whether the code changes are acceptable and meet requirements.
        comments: List of specific feedback items and suggestions.
        severity: Overall severity of review findings (low, medium, high).
    """

    approved: bool = Field(description="Whether the changes are acceptable.")
    comments: list[str] = Field(description="Specific feedback items.")
    severity: Severity = Field(description="Overall severity of the review findings.")


class Reviewer:
    """Agent responsible for reviewing code changes against requirements.

    Attributes:
        driver: LLM driver interface for generating reviews.
    """

    SYSTEM_PROMPT_TEMPLATE = """You are an expert code reviewer with a focus on {persona} aspects.
Analyze the provided code changes and provide a comprehensive review."""

    STRUCTURED_SYSTEM_PROMPT = """You are an expert code reviewer. Review the provided code changes and produce structured feedback.

OUTPUT FORMAT:
- Summary: 1-2 sentence overview
- Items: Numbered list with format [FILE:LINE] TITLE
  - For each item provide: Issue (what's wrong), Why (why it matters), Fix (recommended solution)
- Good Patterns: List things done well to preserve
- Verdict: "approved" | "needs_fixes" | "blocked"

SEVERITY LEVELS:
- critical: Blocking issues (security, data loss, crashes)
- major: Should fix before merge (bugs, performance, maintainability)
- minor: Nice to have (style, minor improvements)

Be specific with file paths and line numbers. Provide actionable feedback."""

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

6. **Output**: Provide your review in the following JSON format:

```json
{{
  "approved": true|false,
  "comments": ["comment 1", "comment 2"],
  "severity": "low"|"medium"|"high"|"critical"
}}
```

## Rules

- Load skills BEFORE reviewing (not after)
- Include FILE:LINE in your comments
- Be specific about what needs to change
- Only flag real issues - check linters first before flagging style issues
- Approved means the code is ready to merge as-is"""

    def __init__(
        self,
        driver: DriverInterface,
        stream_emitter: StreamEmitter | None = None,
    ):
        """Initialize the Reviewer agent.

        Args:
            driver: LLM driver interface for generating reviews.
            stream_emitter: Optional callback for streaming events.
        """
        self.driver = driver
        self._stream_emitter = stream_emitter

    def _build_prompt(
        self,
        state: ExecutionState,
        base_commit: str | None = None,
        code_changes: str | None = None,
    ) -> str:
        """Build the user prompt for review from state.

        Args:
            state: Current execution state containing task and issue context.
            base_commit: Git commit hash to diff against. If provided, the agent
                will fetch the diff using git tools.
            code_changes: Pre-computed code changes. If provided, these are included
                directly in the prompt (legacy mode for smaller diffs).

        Returns:
            Formatted user prompt string for the reviewer.

        Raises:
            ValueError: If no task or issue context is found for review.
        """
        parts: list[str] = []

        # Get context for what was supposed to be done
        # Priority: goal > issue
        if state.goal:
            parts.append(f"## Task\n\n**Task Goal:**\n\n{state.goal}")
        elif state.issue:
            issue_parts = []
            if state.issue.title:
                issue_parts.append(f"**{state.issue.title}**")
            if state.issue.description:
                issue_parts.append(state.issue.description)
            if issue_parts:
                parts.append("## Issue\n\n" + "\n\n".join(issue_parts))

        if not parts:
            raise ValueError("No task or issue context found for review")

        # Add instructions for getting the diff
        if base_commit:
            parts.append(f"""## Instructions

1. First, run `git diff {base_commit}` to get the code changes to review
2. Analyze the diff carefully against the task requirements
3. Provide your review in the required JSON format""")
        elif code_changes:
            # Legacy mode: code changes provided directly
            parts.append(f"## Diff\n\n```diff\n{code_changes}\n```")

        return "\n\n".join(parts)

    async def review(
        self,
        state: ExecutionState,
        code_changes: str,
        profile: Profile,
        *,
        workflow_id: str,
    ) -> tuple[ReviewResult, str | None]:
        """Review code changes in context of execution state and issue.

        Selects single or competitive review strategy based on profile settings.

        Args:
            state: Current execution state containing issue context.
            code_changes: Diff or description of code changes to review.
            profile: The profile containing review strategy settings.
            workflow_id: Workflow ID for stream events (required).

        Returns:
            Tuple of (ReviewResult, session_id from driver).
        """
        if profile.strategy == "competitive":
            return await self._competitive_review(state, code_changes, profile, workflow_id=workflow_id)
        else: # Default to single review
            return await self._single_review(state, code_changes, profile, persona="General", workflow_id=workflow_id)

    async def _single_review(
        self,
        state: ExecutionState,
        code_changes: str,
        profile: Profile,
        persona: str,
        *,
        workflow_id: str,
    ) -> tuple[ReviewResult, str | None]:
        """Performs a single review with a specified persona.

        Args:
            state: Current execution state containing issue context.
            code_changes: Diff or description of code changes to review.
            profile: The profile containing working directory settings.
            persona: Review perspective (e.g., "Security", "Performance").
            workflow_id: Workflow ID for stream events (required).

        Returns:
            Tuple of (ReviewResult, session_id from driver).
        """
        # Handle empty code changes - warn and auto-approve
        if not code_changes or not code_changes.strip():
            logger.warning(
                "No code changes to review, auto-approving",
                agent="reviewer",
                persona=persona,
                workflow_id=workflow_id,
            )
            if self._stream_emitter is not None:
                event = StreamEvent(
                    type=StreamEventType.AGENT_OUTPUT,
                    content="No code changes to review - auto-approved",
                    timestamp=datetime.now(UTC),
                    agent="reviewer",
                    workflow_id=workflow_id,
                )
                await self._stream_emitter(event)

            result = ReviewResult(
                reviewer_persona=persona,
                approved=True,
                comments=["No code changes to review"],
                severity="low"
            )
            return result, state.driver_session_id

        # Build prompt and system prompt
        prompt = self._build_prompt(state, code_changes=code_changes)
        system_prompt = self.SYSTEM_PROMPT_TEMPLATE.format(persona=persona)

        logger.debug(
            "Built review prompt",
            agent="reviewer",
            persona=persona,
            prompt_length=len(prompt),
            system_prompt_length=len(system_prompt),
        )

        response, new_session_id = await self.driver.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            schema=ReviewResponse,
            cwd=profile.working_dir,
            session_id=state.driver_session_id,
        )

        # Emit completion event before return
        if self._stream_emitter is not None:
            status = "✅ Approved" if response.approved else "⚠️ Changes requested"
            content_parts = [f"**Review completed:** {status} (severity: {response.severity})"]
            if response.comments:
                content_parts.append("\n**Comments:**")
                for comment in response.comments:
                    content_parts.append(f"- {comment}")
            event = StreamEvent(
                type=StreamEventType.AGENT_OUTPUT,
                content="\n".join(content_parts),
                timestamp=datetime.now(UTC),
                agent="reviewer",
                workflow_id=workflow_id,
            )
            await self._stream_emitter(event)

        result = ReviewResult(
            reviewer_persona=persona,
            approved=response.approved,
            comments=response.comments,
            severity=response.severity
        )
        return result, new_session_id

    async def _competitive_review(
        self,
        state: ExecutionState,
        code_changes: str,
        profile: Profile,
        *,
        workflow_id: str,
    ) -> tuple[ReviewResult, str | None]:
        """Performs competitive review using multiple personas in parallel.

        Args:
            state: Current execution state containing issue context.
            code_changes: Diff or description of code changes to review.
            profile: The profile containing working directory settings.
            workflow_id: Workflow ID for stream events (required).

        Returns:
            Tuple of (aggregated ReviewResult, None).
            Note: session_id is always None for competitive reviews since multiple
            parallel sessions are used and returning any single one would be misleading.
        """
        personas = ["Security", "Performance", "Usability"] # Example personas

        # Run reviews in parallel
        review_tasks = [self._single_review(state, code_changes, profile, persona, workflow_id=workflow_id) for persona in personas]
        results_with_sessions = await asyncio.gather(*review_tasks)

        # Unpack results (session_ids discarded for competitive reviews)
        results = [r for r, _ in results_with_sessions]

        # Aggregate results (simple aggregation: if any disapproves, overall disapproves)
        overall_approved = all(res.approved for res in results)

        # Prefix comments with persona name to preserve attribution
        all_comments = [
            f"[{res.reviewer_persona}] {comment}"
            for res in results
            for comment in res.comments
        ]

        # Determine overall severity (e.g., highest severity from any review)
        severity_order: dict[Severity, int] = {"low": 0, "medium": 1, "high": 2, "critical": 3}
        severity_from_value: dict[int, Severity] = {v: k for k, v in severity_order.items()}
        overall_severity_value = max(severity_order.get(res.severity, 0) for res in results)
        overall_severity = severity_from_value[overall_severity_value]

        aggregated_result = ReviewResult(
            reviewer_persona="Competitive-Aggregated",
            approved=overall_approved,
            comments=all_comments,
            severity=overall_severity
        )
        return aggregated_result, None

    async def structured_review(
        self,
        state: ExecutionState,
        code_changes: str,
        profile: Profile,
        *,
        workflow_id: str,
    ) -> tuple[StructuredReviewResult, str | None]:
        """Perform structured code review with beagle format output.

        Args:
            state: Current execution state.
            code_changes: Diff or description of changes to review.
            profile: Active profile with driver settings.
            workflow_id: Workflow identifier for streaming.

        Returns:
            Tuple of StructuredReviewResult and optional session ID.
        """
        # Handle empty code changes - return approved result with no items
        if not code_changes or not code_changes.strip():
            logger.warning(
                "No code changes to review, auto-approving",
                agent="reviewer",
                method="structured_review",
                workflow_id=workflow_id,
            )
            if self._stream_emitter is not None:
                event = StreamEvent(
                    type=StreamEventType.AGENT_OUTPUT,
                    content="No code changes to review - auto-approved",
                    timestamp=datetime.now(UTC),
                    agent="reviewer",
                    workflow_id=workflow_id,
                )
                await self._stream_emitter(event)

            result = StructuredReviewResult(
                summary="No code changes to review.",
                items=[],
                good_patterns=[],
                verdict="approved",
            )
            return result, state.driver_session_id

        # Build prompt using existing method
        prompt = self._build_prompt(state, code_changes=code_changes)

        logger.debug(
            "Built structured review prompt",
            agent="reviewer",
            method="structured_review",
            prompt_length=len(prompt),
            system_prompt_length=len(self.STRUCTURED_SYSTEM_PROMPT),
        )

        response, new_session_id = await self.driver.generate(
            prompt=prompt,
            system_prompt=self.STRUCTURED_SYSTEM_PROMPT,
            schema=StructuredReviewResult,
            cwd=profile.working_dir,
            session_id=state.driver_session_id,
        )

        # Emit completion event before return
        if self._stream_emitter is not None:
            verdict_display = {
                "approved": "✅ Approved",
                "needs_fixes": "⚠️ Needs fixes",
                "blocked": "🛑 Blocked",
            }
            content_parts = [
                f"**Structured review:** {verdict_display.get(response.verdict, response.verdict)}",
                f"\n{response.summary}",
            ]
            if response.items:
                content_parts.append("\n**Issues:**")
                for item in response.items:
                    content_parts.append(
                        f"- **[{item.severity}]** {item.title} ({item.file_path}:{item.line}): {item.issue}"
                    )
            if response.good_patterns:
                content_parts.append("\n**Good patterns:**")
                for pattern in response.good_patterns:
                    content_parts.append(f"- {pattern}")
            event = StreamEvent(
                type=StreamEventType.AGENT_OUTPUT,
                content="\n".join(content_parts),
                timestamp=datetime.now(UTC),
                agent="reviewer",
                workflow_id=workflow_id,
            )
            await self._stream_emitter(event)

        logger.info(
            "Structured review completed",
            agent="reviewer",
            method="structured_review",
            verdict=response.verdict,
            item_count=len(response.items),
            good_pattern_count=len(response.good_patterns),
            workflow_id=workflow_id,
        )

        return response, new_session_id

    async def agentic_review(
        self,
        state: ExecutionState,
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

        Args:
            state: Current execution state containing issue context.
            base_commit: Git commit hash to diff against.
            profile: The profile containing working directory settings.
            workflow_id: Workflow ID for stream events (required).

        Returns:
            Tuple of (ReviewResult, session_id from driver).
        """
        from amelia.drivers.cli.claude import ClaudeCliDriver  # noqa: PLC0415

        # Agentic review requires CLI driver
        if not isinstance(self.driver, ClaudeCliDriver):
            # Fallback to traditional review for non-CLI drivers
            logger.warning(
                "Agentic review requires CLI driver, falling back to git diff",
                agent="reviewer",
                driver_type=type(self.driver).__name__,
            )
            # Get diff the traditional way and use _single_review
            proc = await asyncio.create_subprocess_exec(
                "git", "diff", base_commit,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=profile.working_dir,
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                logger.debug(
                    "git diff failed",
                    agent="reviewer",
                    stderr=stderr.decode(),
                    returncode=proc.returncode,
                )
            code_changes = stdout.decode() if proc.returncode == 0 else ""
            return await self._single_review(
                state, code_changes, profile, persona="General", workflow_id=workflow_id
            )

        # Build the task prompt
        task_parts = []
        if state.goal:
            task_parts.append(f"**Task Goal:**\n{state.goal}")
        elif state.issue:
            if state.issue.title:
                task_parts.append(f"**Issue:** {state.issue.title}")
            if state.issue.description:
                task_parts.append(state.issue.description)

        task_context = "\n\n".join(task_parts) if task_parts else "Review the code changes."

        prompt = f"""Review the code changes for this task:

{task_context}

The changes are in git - diff against commit: {base_commit}"""

        # Build system prompt with base_commit
        system_prompt = self.AGENTIC_REVIEW_PROMPT.format(base_commit=base_commit)

        cwd = profile.working_dir or "."
        session_id = state.driver_session_id
        new_session_id: str | None = None
        final_result: str | None = None

        logger.info(
            "Starting agentic review",
            agent="reviewer",
            base_commit=base_commit,
            workflow_id=workflow_id,
        )

        # Import message types
        from claude_agent_sdk.types import (  # noqa: PLC0415
            AssistantMessage,
            ResultMessage,
            TextBlock,
            ToolUseBlock,
        )

        # Execute agentic review
        async for message in self.driver.execute_agentic(
            prompt=prompt,
            cwd=cwd,
            session_id=session_id,
            instructions=system_prompt,
        ):
            # Emit stream events for visibility
            if self._stream_emitter is not None and isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        event = StreamEvent(
                            type=StreamEventType.CLAUDE_THINKING,
                            content=block.text,
                            timestamp=datetime.now(UTC),
                            agent="reviewer",
                            workflow_id=workflow_id,
                        )
                        await self._stream_emitter(event)
                    elif isinstance(block, ToolUseBlock):
                        event = StreamEvent(
                            type=StreamEventType.CLAUDE_TOOL_CALL,
                            content=None,
                            timestamp=datetime.now(UTC),
                            agent="reviewer",
                            workflow_id=workflow_id,
                            tool_name=block.name,
                            tool_input=block.input if isinstance(block.input, dict) else None,
                        )
                        await self._stream_emitter(event)

            # Capture final result
            if isinstance(message, ResultMessage):
                new_session_id = message.session_id
                final_result = message.result
                if message.is_error:
                    logger.error(
                        "Agentic review failed",
                        agent="reviewer",
                        error=message.result,
                        workflow_id=workflow_id,
                    )

        # Parse the result to extract review
        result = self._parse_review_result(final_result, workflow_id)

        # Emit completion event
        if self._stream_emitter is not None:
            status = "✅ Approved" if result.approved else "⚠️ Changes requested"
            content_parts = [f"**Review completed:** {status} (severity: {result.severity})"]
            if result.comments:
                content_parts.append("\n**Comments:**")
                for comment in result.comments:
                    content_parts.append(f"- {comment}")
            event = StreamEvent(
                type=StreamEventType.AGENT_OUTPUT,
                content="\n".join(content_parts),
                timestamp=datetime.now(UTC),
                agent="reviewer",
                workflow_id=workflow_id,
            )
            await self._stream_emitter(event)

        logger.info(
            "Agentic review completed",
            agent="reviewer",
            approved=result.approved,
            comment_count=len(result.comments),
            workflow_id=workflow_id,
        )

        return result, new_session_id

    def _parse_review_result(self, output: str | None, workflow_id: str) -> ReviewResult:
        """Parse the agent's output to extract ReviewResult.

        Attempts to find and parse JSON from the output. Falls back to
        a basic analysis if JSON parsing fails.

        Args:
            output: The agent's final output text.
            workflow_id: Workflow ID for logging.

        Returns:
            Parsed ReviewResult.
        """
        if not output:
            logger.warning(
                "No output from agentic review, defaulting to not approved",
                agent="reviewer",
                workflow_id=workflow_id,
            )
            return ReviewResult(
                reviewer_persona="Agentic",
                approved=False,
                comments=["Review did not produce output"],
                severity="high",
            )

        # Try to find JSON in the output

        # Look for JSON block in markdown code fence
        json_match = re.search(r"```json\s*\n(.*?)\n```", output, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group(1))
                return ReviewResult(
                    reviewer_persona="Agentic",
                    approved=data.get("approved", False),
                    comments=data.get("comments", []),
                    severity=data.get("severity", "medium"),
                )
            except (json.JSONDecodeError, ValidationError) as e:
                logger.warning(
                    "Failed to parse JSON from review output",
                    agent="reviewer",
                    error=str(e),
                    workflow_id=workflow_id,
                )

        # Try to find raw JSON object
        json_match = re.search(r'\{[^{}]*"approved"[^{}]*\}', output, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group(0))
                return ReviewResult(
                    reviewer_persona="Agentic",
                    approved=data.get("approved", False),
                    comments=data.get("comments", []),
                    severity=data.get("severity", "medium"),
                )
            except (json.JSONDecodeError, ValidationError):
                pass

        # Fallback: analyze text for approval keywords
        output_lower = output.lower()
        approved = any(word in output_lower for word in ["approved", "lgtm", "looks good", "ready to merge"])
        not_approved = any(word in output_lower for word in ["not approved", "needs fixes", "blocked", "changes requested"])

        if not_approved:
            approved = False

        # Extract any bullet points or numbered items as comments
        comments = []
        for line in output.split("\n"):
            line = line.strip()
            if line.startswith(("- ", "* ", "• ")) or re.match(r"^\d+\.", line):
                # Clean up the line
                comment = re.sub(r"^[-*•]\s*|\d+\.\s*", "", line).strip()
                if comment and len(comment) > 10:  # Filter out very short lines
                    comments.append(comment)

        if not comments:
            comments = ["See review output for details"]

        return ReviewResult(
            reviewer_persona="Agentic",
            approved=approved,
            comments=comments[:10],  # Limit to 10 comments
            severity="medium" if approved else "high",
        )
