"""Evaluator agent for the review-fix workflow.

This module provides the Evaluator agent that evaluates review feedback
against the actual codebase, applying a decision matrix to determine
which items to implement, reject, defer, or clarify.
"""
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING

from loguru import logger
from pydantic import BaseModel, ConfigDict, Field

from amelia.core.types import Profile, StreamEmitter, StreamEvent, StreamEventType
from amelia.drivers.base import DriverInterface


if TYPE_CHECKING:
    from amelia.core.state import ExecutionState


class Disposition(str, Enum):
    """Disposition for evaluated feedback items.

    Attributes:
        IMPLEMENT: Correct and in scope - will fix.
        REJECT: Technically incorrect - won't fix.
        DEFER: Out of scope - backlog.
        CLARIFY: Ambiguous - needs clarification.

    """

    IMPLEMENT = "implement"
    REJECT = "reject"
    DEFER = "defer"
    CLARIFY = "clarify"


class EvaluatedItem(BaseModel):
    """Single evaluated feedback item.

    Attributes:
        number: Original issue number from review.
        title: Brief title describing the issue.
        file_path: Path to the file containing the issue.
        line: Line number where the issue occurs.
        disposition: The evaluation decision for this item.
        reason: Evidence supporting the disposition decision.
        original_issue: The issue description from review.
        suggested_fix: The suggested fix from review.

    """

    model_config = ConfigDict(frozen=True)

    number: int
    title: str
    file_path: str
    line: int
    disposition: Disposition
    reason: str
    original_issue: str
    suggested_fix: str


class EvaluationResult(BaseModel):
    """Result of evaluating review feedback.

    Attributes:
        items_to_implement: Items marked for implementation.
        items_rejected: Items rejected as technically incorrect.
        items_deferred: Items deferred as out of scope.
        items_needing_clarification: Items requiring clarification.
        summary: Brief summary of evaluation decisions.

    """

    model_config = ConfigDict(frozen=True)

    items_to_implement: list[EvaluatedItem] = Field(default_factory=list)
    items_rejected: list[EvaluatedItem] = Field(default_factory=list)
    items_deferred: list[EvaluatedItem] = Field(default_factory=list)
    items_needing_clarification: list[EvaluatedItem] = Field(default_factory=list)
    summary: str


class EvaluationOutput(BaseModel):
    """Schema for LLM-generated evaluation output.

    This is the schema the LLM uses to generate evaluation results.

    Attributes:
        evaluated_items: All evaluated items with their dispositions.
        summary: Brief summary of the evaluation decisions.

    """

    evaluated_items: list[EvaluatedItem]
    summary: str


class Evaluator:
    """Evaluates review feedback against codebase.

    Applies decision matrix from beagle:receive-feedback pattern:
    - Correct & In Scope -> implement
    - Technically Incorrect -> reject with evidence
    - Out of Scope -> defer
    - Ambiguous -> clarify

    Attributes:
        driver: LLM driver interface for generating evaluations.

    """

    SYSTEM_PROMPT = """You are an expert code evaluation agent. Your task is to evaluate
code review feedback items against the actual codebase.

For each review item, you must:
1. VERIFY the issue exists by checking the referenced file and line
2. VERIFY the technical accuracy of the claim
3. Determine if the fix is in scope for the current task
4. Apply the decision matrix:
   - Correct & In Scope -> IMPLEMENT (will be fixed)
   - Technically Incorrect -> REJECT with evidence
   - Correct but Out of Scope -> DEFER to backlog
   - Ambiguous/Unclear -> CLARIFY with specific question

VERIFICATION METHODS:
- "Unused code" claims -> grep for actual usage
- "Bug/Error" claims -> verify with test or reproduction
- "Missing import" claims -> check file imports
- "Style/Convention" claims -> check existing codebase patterns

Never trust review feedback blindly. Always verify against the code.
Provide clear evidence for each disposition decision."""

    def __init__(
        self,
        driver: DriverInterface,
        stream_emitter: StreamEmitter | None = None,
        prompts: dict[str, str] | None = None,
    ):
        """Initialize the Evaluator agent.

        Args:
            driver: LLM driver interface for generating evaluations.
            stream_emitter: Optional callback for streaming events.
            prompts: Optional dict of prompt_id -> content for customization.

        """
        self.driver = driver
        self._stream_emitter = stream_emitter
        self._prompts = prompts or {}

    @property
    def system_prompt(self) -> str:
        """Get the system prompt for evaluation.

        Returns the custom prompt if configured, otherwise falls back
        to the hardcoded default.

        Returns:
            The system prompt string.

        """
        return self._prompts.get("evaluator.system", self.SYSTEM_PROMPT)

    def _build_prompt(self, state: "ExecutionState") -> str:
        """Build the user prompt for evaluation from state.

        Args:
            state: Current execution state containing review feedback.

        Returns:
            Formatted user prompt string for the evaluator.

        Raises:
            ValueError: If no review feedback is found in state.

        """
        parts: list[str] = []

        # Task context (if available)
        if state.goal:
            parts.append(f"## Current Task\n\n{state.goal}")
        elif state.issue:
            issue_parts = []
            if state.issue.title:
                issue_parts.append(f"**{state.issue.title}**")
            if state.issue.description:
                issue_parts.append(state.issue.description)
            if issue_parts:
                parts.append("## Issue Context\n\n" + "\n\n".join(issue_parts))

        # Review feedback to evaluate
        if not state.last_review:
            raise ValueError("No review feedback found in state")

        parts.append("## Review Feedback to Evaluate\n")
        for i, comment in enumerate(state.last_review.comments, start=1):
            parts.append(f"### Item {i}\n\n{comment}\n")

        # Code changes context (if available)
        if state.code_changes_for_review:
            parts.append(f"## Code Changes\n\n```diff\n{state.code_changes_for_review}\n```")

        parts.append("""
---

For each review item above, evaluate it against the codebase and assign a disposition:
- IMPLEMENT: The issue is valid and in scope for the current task
- REJECT: The issue is technically incorrect (provide evidence)
- DEFER: The issue is valid but out of scope for this task
- CLARIFY: The issue is ambiguous and needs clarification

Return your evaluation as an EvaluationOutput with all items and a summary.""")

        return "\n\n".join(parts)

    async def evaluate(
        self,
        state: "ExecutionState",
        profile: Profile,
        *,
        workflow_id: str,
    ) -> tuple[EvaluationResult, str | None]:
        """Evaluate review feedback items.

        Analyzes each review comment, verifies it against the codebase,
        and assigns a disposition based on the decision matrix.

        Args:
            state: Current execution state with last_review containing feedback.
            profile: Active profile with driver settings.
            workflow_id: Workflow identifier for streaming events.

        Returns:
            Tuple of (EvaluationResult, session_id from driver).

        Raises:
            ValueError: If no last_review in state.

        """
        if not state.last_review:
            raise ValueError("ExecutionState must have last_review set for evaluation")

        # Handle empty review comments
        if not state.last_review.comments:
            logger.warning(
                "No review comments to evaluate, returning empty result",
                agent="evaluator",
                workflow_id=workflow_id,
            )
            if self._stream_emitter is not None:
                event = StreamEvent(
                    type=StreamEventType.AGENT_OUTPUT,
                    content="No review comments to evaluate",
                    timestamp=datetime.now(UTC),
                    agent="evaluator",
                    workflow_id=workflow_id,
                )
                await self._stream_emitter(event)

            result = EvaluationResult(
                items_to_implement=[],
                items_rejected=[],
                items_deferred=[],
                items_needing_clarification=[],
                summary="No review comments to evaluate.",
            )
            return result, state.driver_session_id

        # Build prompt and call driver
        prompt = self._build_prompt(state)

        logger.debug(
            "Built evaluation prompt",
            agent="evaluator",
            prompt_length=len(prompt),
            comments_count=len(state.last_review.comments),
        )

        response, new_session_id = await self.driver.generate(
            prompt=prompt,
            system_prompt=self.system_prompt,
            schema=EvaluationOutput,
            cwd=profile.working_dir,
            session_id=state.driver_session_id,
        )

        # Partition items by disposition
        items_to_implement: list[EvaluatedItem] = []
        items_rejected: list[EvaluatedItem] = []
        items_deferred: list[EvaluatedItem] = []
        items_needing_clarification: list[EvaluatedItem] = []

        for item in response.evaluated_items:
            if item.disposition == Disposition.IMPLEMENT:
                items_to_implement.append(item)
            elif item.disposition == Disposition.REJECT:
                items_rejected.append(item)
            elif item.disposition == Disposition.DEFER:
                items_deferred.append(item)
            elif item.disposition == Disposition.CLARIFY:
                items_needing_clarification.append(item)

        logger.info(
            "Evaluation complete",
            agent="evaluator",
            to_implement=len(items_to_implement),
            rejected=len(items_rejected),
            deferred=len(items_deferred),
            needs_clarification=len(items_needing_clarification),
        )

        # Emit completion event
        if self._stream_emitter is not None:
            summary_parts = []
            if items_to_implement:
                summary_parts.append(f"{len(items_to_implement)} to implement")
            if items_rejected:
                summary_parts.append(f"{len(items_rejected)} rejected")
            if items_deferred:
                summary_parts.append(f"{len(items_deferred)} deferred")
            if items_needing_clarification:
                summary_parts.append(f"{len(items_needing_clarification)} need clarification")

            content = f"Evaluation complete: {', '.join(summary_parts)}" if summary_parts else "Evaluation complete: no items"

            event = StreamEvent(
                type=StreamEventType.AGENT_OUTPUT,
                content=content,
                timestamp=datetime.now(UTC),
                agent="evaluator",
                workflow_id=workflow_id,
            )
            await self._stream_emitter(event)

        result = EvaluationResult(
            items_to_implement=items_to_implement,
            items_rejected=items_rejected,
            items_deferred=items_deferred,
            items_needing_clarification=items_needing_clarification,
            summary=response.summary,
        )

        return result, new_session_id
