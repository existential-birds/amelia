# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
import asyncio

from loguru import logger
from pydantic import BaseModel, Field

from amelia.core.context import CompiledContext, ContextSection, ContextStrategy
from amelia.core.state import ExecutionState, ReviewResult, Severity
from amelia.drivers.base import DriverInterface


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


class ReviewerContextStrategy(ContextStrategy):
    """Context compilation strategy for code review.

    Compiles minimal context for reviewing code changes against task requirements.
    Uses a templated system prompt with {persona} placeholder to maximize cache hits
    across same-persona reviews.
    """

    SYSTEM_PROMPT_TEMPLATE = """You are an expert code reviewer with a focus on {persona} aspects.
Analyze the provided code changes and provide a comprehensive review."""

    ALLOWED_SECTIONS = {"task", "issue", "diff", "criteria"}

    def __init__(self, persona: str = "General"):
        """Initialize the strategy with a review persona.

        Args:
            persona: Review perspective (e.g., "Security", "Performance", "General").
        """
        self.persona = persona

    def compile(self, state: ExecutionState) -> CompiledContext:
        """Compile ExecutionState into review context.

        Args:
            state: Current execution state containing task and code changes.

        Returns:
            CompiledContext with system prompt and relevant sections.

        Raises:
            ValueError: If code_changes_for_review is missing or sections are invalid.
        """
        # Format system prompt with persona
        system_prompt = self.SYSTEM_PROMPT_TEMPLATE.format(persona=self.persona)

        # Get current task or fall back to issue summary
        current_task = self.get_current_task(state)
        issue_summary = self.get_issue_summary(state)
        if not current_task and not issue_summary:
            raise ValueError("No task or issue context found for review")

        # Get code changes
        code_changes = state.code_changes_for_review
        if not code_changes:
            raise ValueError("No code changes provided for review")

        # Build sections
        sections: list[ContextSection] = []

        # Task or issue section - what was supposed to be done
        if current_task:
            sections.append(
                ContextSection(
                    name="task",
                    content=current_task.description,
                    source="state.current_task.description"
                )
            )
        elif issue_summary:
            # issue_summary is guaranteed non-None here due to check on line 67
            sections.append(
                ContextSection(
                    name="issue",
                    content=issue_summary,
                    source="state.issue"
                )
            )

        # Diff section - code changes to review (required)
        sections.append(
            ContextSection(
                name="diff",
                content=f"```diff\n{code_changes}\n```",
                source="state.code_changes_for_review"
            )
        )

        # Criteria section - acceptance criteria (optional, if available)
        # Note: Current Task model doesn't have acceptance_criteria field
        # This is a placeholder for when it's added to the schema
        # For now, we'll skip this section since it's optional

        # Validate sections before returning
        self.validate_sections(sections)

        return CompiledContext(
            system_prompt=system_prompt,
            sections=sections
        )


class Reviewer:
    """Agent responsible for reviewing code changes against requirements.

    Attributes:
        driver: LLM driver interface for generating reviews.
        context_strategy: Strategy for compiling review context.
    """

    context_strategy: type[ReviewerContextStrategy] = ReviewerContextStrategy

    def __init__(self, driver: DriverInterface):
        """Initialize the Reviewer agent.

        Args:
            driver: LLM driver interface for generating reviews.
        """
        self.driver = driver

    async def review(self, state: ExecutionState, code_changes: str) -> ReviewResult:
        """Review code changes in context of execution state and issue.

        Selects single or competitive review strategy based on profile settings.

        Args:
            state: Current execution state containing issue and profile context.
            code_changes: Diff or description of code changes to review.

        Returns:
            ReviewResult with approval status, comments, and severity level.
        """
        if state.profile.strategy == "competitive":
            return await self._competitive_review(state, code_changes)
        else: # Default to single review
            return await self._single_review(state, code_changes, persona="General")

    async def _single_review(self, state: ExecutionState, code_changes: str, persona: str) -> ReviewResult:
        """Performs a single review with a specified persona.

        Args:
            state: Current execution state containing issue context.
            code_changes: Diff or description of code changes to review.
            persona: Review perspective (e.g., "Security", "Performance").

        Returns:
            ReviewResult with approval status, comments, and severity.
        """
        # Validate state: if plan has tasks, current_task_id must be set
        # State preparation is the orchestrator's responsibility, not the agent's
        if state.plan and state.plan.tasks and not state.current_task_id:
            raise ValueError(
                "current_task_id is required when plan has tasks. "
                "The orchestrator must set current_task_id before calling review."
            )

        # Prepare state for context strategy
        # Set code_changes_for_review if not already set (passed as parameter)
        review_state = state
        if not state.code_changes_for_review:
            review_state = state.model_copy(update={"code_changes_for_review": code_changes})

        # Use context strategy to compile review context
        strategy = self.context_strategy(persona=persona)
        compiled_context = strategy.compile(review_state)

        logger.debug(
            "Compiled context",
            agent="reviewer",
            sections=[s.name for s in compiled_context.sections],
            system_prompt_length=len(compiled_context.system_prompt) if compiled_context.system_prompt else 0
        )

        # Convert to messages
        prompt_messages = strategy.to_messages(compiled_context)

        response = await self.driver.generate(messages=prompt_messages, schema=ReviewResponse)

        return ReviewResult(
            reviewer_persona=persona,
            approved=response.approved,
            comments=response.comments,
            severity=response.severity
        )

    async def _competitive_review(self, state: ExecutionState, code_changes: str) -> ReviewResult:
        """Performs competitive review using multiple personas in parallel.

        Args:
            state: Current execution state containing issue context.
            code_changes: Diff or description of code changes to review.

        Returns:
            Aggregated ReviewResult combining feedback from all personas.
        """
        personas = ["Security", "Performance", "Usability"] # Example personas
        
        # Run reviews in parallel
        review_tasks = [self._single_review(state, code_changes, persona) for persona in personas]
        results = await asyncio.gather(*review_tasks)

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

        return ReviewResult(
            reviewer_persona="Competitive-Aggregated",
            approved=overall_approved,
            comments=all_comments,
            severity=overall_severity
        )
