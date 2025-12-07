import asyncio

from pydantic import BaseModel, Field

from amelia.core.state import AgentMessage, ExecutionState, ReviewResult, Severity
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

class Reviewer:
    """Agent responsible for reviewing code changes against requirements.

    Attributes:
        driver: LLM driver interface for generating reviews.
    """

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
        system_prompt = (
            f"You are an expert code reviewer with a focus on {persona} aspects. "
            "Analyze the provided code changes in the context of the given issue and "
            "provide a comprehensive review."
        )

        issue_title = state.issue.title if state.issue else "No Issue Title"
        issue_description = state.issue.description if state.issue else "No Issue Description"

        user_prompt = (
            f"Given the following issue:\n\n"
            f"Title: {issue_title}\n"
            f"Description: {issue_description}\n\n"
            f"And the following code changes to review:\n"
            f"```diff\n{code_changes}\n```\n\n"
            f"Provide your review indicating approval status, comments, and overall severity."
        )
        
        prompt_messages = [
            AgentMessage(role="system", content=system_prompt),
            AgentMessage(role="user", content=user_prompt)
        ]

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
