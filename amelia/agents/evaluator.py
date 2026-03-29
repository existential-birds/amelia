"""Evaluator agent for the review-fix workflow.

This module provides the Evaluator agent that evaluates review feedback
against the actual codebase, applying a decision matrix to determine
which items to implement, reject, defer, or clarify.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from loguru import logger

from amelia.agents.schemas.evaluator import (
    Disposition,
    EvaluatedItem,
    EvaluationOutput,
    EvaluationResult,
)
from amelia.core.types import AgentConfig, Profile, collect_all_comments
from amelia.drivers.base import AgenticMessageType
from amelia.drivers.factory import get_driver
from amelia.server.models.events import (
    EPHEMERAL_SEQUENCE,
    EventLevel,
    EventType,
    WorkflowEvent,
)


if TYPE_CHECKING:
    from amelia.pipelines.implementation.state import ImplementationState
    from amelia.sandbox.provider import SandboxProvider
    from amelia.server.events.bus import EventBus



class Evaluator:
    """Evaluates review feedback against codebase.

    Applies decision matrix:
    - Correct & In Scope -> implement
    - Technically Incorrect -> reject with evidence
    - Out of Scope -> defer
    - Ambiguous -> clarify

    Attributes:
        driver: LLM driver interface for generating evaluations.

    """

    PROMPT_KEY_SYSTEM = "evaluator.system"

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
        config: AgentConfig,
        event_bus: EventBus | None = None,
        prompts: dict[str, str] | None = None,
        sandbox_provider: SandboxProvider | None = None,
    ):
        """Initialize the Evaluator agent.

        Args:
            config: Agent configuration with driver, model, and options.
            event_bus: Optional EventBus for emitting workflow events.
            prompts: Optional dict of prompt_id -> content for customization.
            sandbox_provider: Optional shared sandbox provider for sandbox reuse.

        """
        self.driver = get_driver(
            config.driver,
            model=config.model,
            sandbox_config=config.sandbox,
            sandbox_provider=sandbox_provider,
            profile_name=config.profile_name,
            options=config.options,
        )
        self.options = config.options
        self._event_bus = event_bus
        self._prompts = prompts or {}

        if self.PROMPT_KEY_SYSTEM not in self._prompts:
            logger.debug(
                "Custom prompt key not found, using default",
                agent="evaluator",
                prompt_key=self.PROMPT_KEY_SYSTEM,
            )

    @property
    def system_prompt(self) -> str:
        """Get the system prompt for evaluation.

        Returns the custom prompt if configured, otherwise falls back
        to the hardcoded default.

        Returns:
            The system prompt string.

        """
        return self._prompts.get(self.PROMPT_KEY_SYSTEM, self.SYSTEM_PROMPT)

    def _build_prompt(self, state: ImplementationState) -> str:
        """Build the user prompt for evaluation from state.

        Args:
            state: Current implementation state containing review feedback.

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

        # Review feedback to evaluate — aggregate comments from all reviews
        if not state.last_reviews:
            raise ValueError("No review feedback found in state")

        all_comments = collect_all_comments(state.last_reviews)

        parts.append("## Review Feedback to Evaluate\n")
        for i, comment in enumerate(all_comments, start=1):
            parts.append(f"### Item {i}\n\n{comment}\n")

        # Code changes context (if available)
        if state.code_changes_for_review:
            parts.append(f"## Code Changes\n\n```diff\n{state.code_changes_for_review}\n```")

        parts.append("""
---

For each review item above, evaluate it against the codebase and assign a disposition.

When you have completed your evaluation, call the `submit_evaluation` tool with your results. The tool expects:
- `evaluated_items`: list of objects, each with: number (int), title (str), file_path (str), line (int), disposition ("implement"|"reject"|"defer"|"clarify"), reason (str), original_issue (str), suggested_fix (str)
- `summary`: a brief summary string of your evaluation decisions

You MUST call `submit_evaluation` exactly once with all items.""")

        return "\n\n".join(parts)

    async def evaluate(
        self,
        state: ImplementationState,
        profile: Profile,
        *,
        workflow_id: uuid.UUID,
    ) -> tuple[EvaluationResult, str | None]:
        """Evaluate review feedback items.

        Analyzes each review comment, verifies it against the codebase,
        and assigns a disposition based on the decision matrix.

        Args:
            state: Current implementation state with last_reviews containing feedback.
            profile: Active profile with driver settings.
            workflow_id: Workflow identifier for streaming events.

        Returns:
            Tuple of (EvaluationResult, session_id from driver).

        Raises:
            ValueError: If no last_reviews in state.

        """
        if not state.last_reviews:
            raise ValueError("ImplementationState must have last_reviews set for evaluation")

        # Handle empty review comments — aggregate from all reviews
        all_comments = collect_all_comments(state.last_reviews)
        if not all_comments:
            logger.warning(
                "No review comments to evaluate, returning empty result",
                agent="evaluator",
                workflow_id=workflow_id,
            )
            if self._event_bus is not None:
                event = WorkflowEvent(
                    id=uuid4(),
                    workflow_id=workflow_id,
                    sequence=EPHEMERAL_SEQUENCE,
                    timestamp=datetime.now(UTC),
                    agent="evaluator",
                    event_type=EventType.AGENT_OUTPUT,
                    level=EventLevel.DEBUG,
                    message="No review comments to evaluate",
                )
                self._event_bus.emit(event)

            result = EvaluationResult(
                items_to_implement=[],
                items_rejected=[],
                items_deferred=[],
                items_needing_clarification=[],
                summary="No review comments to evaluate.",
            )
            return result, None

        # Build prompt and call driver
        prompt = self._build_prompt(state)

        logger.debug(
            "Built evaluation prompt",
            agent="evaluator",
            prompt_length=len(prompt),
            comments_count=len(all_comments),
        )

        # Execute agentic evaluation with submit_evaluation tool (per D-05, D-06)
        result_data: EvaluationOutput | None = None
        already_submitted = False
        new_session_id: str | None = None

        async for msg in self.driver.execute_agentic(
            prompt=prompt,
            cwd=profile.repo_root,
            session_id=None,  # Fresh session to avoid bias from prior agent context
            instructions=self.system_prompt,
            allowed_tools=["submit_evaluation"],
        ):
            if msg.type == AgenticMessageType.RESULT:
                new_session_id = msg.session_id

            if msg.type == AgenticMessageType.TOOL_CALL and msg.tool_name == "submit_evaluation":
                if already_submitted:
                    # First call wins (per D-07)
                    logger.warning(
                        "submit_evaluation called more than once; ignoring duplicate",
                        agent="evaluator",
                        workflow_id=workflow_id,
                    )
                    continue
                already_submitted = True
                result_data = EvaluationOutput.model_validate(msg.tool_input)

        if result_data is None:
            raise RuntimeError("Evaluator did not call submit_evaluation")

        # Partition items by disposition
        items_to_implement: list[EvaluatedItem] = []
        items_rejected: list[EvaluatedItem] = []
        items_deferred: list[EvaluatedItem] = []
        items_needing_clarification: list[EvaluatedItem] = []

        disposition_map: dict[Disposition, list[EvaluatedItem]] = {
            Disposition.IMPLEMENT: items_to_implement,
            Disposition.REJECT: items_rejected,
            Disposition.DEFER: items_deferred,
            Disposition.CLARIFY: items_needing_clarification,
        }

        for item in result_data.evaluated_items:
            disposition_map[item.disposition].append(item)

        logger.info(
            "Evaluation complete",
            agent="evaluator",
            to_implement=len(items_to_implement),
            rejected=len(items_rejected),
            deferred=len(items_deferred),
            needs_clarification=len(items_needing_clarification),
        )

        # Emit completion event
        if self._event_bus is not None:
            summary_parts = []
            if items_to_implement:
                summary_parts.append(f"{len(items_to_implement)} to implement")
            if items_rejected:
                summary_parts.append(f"{len(items_rejected)} rejected")
            if items_deferred:
                summary_parts.append(f"{len(items_deferred)} deferred")
            if items_needing_clarification:
                summary_parts.append(f"{len(items_needing_clarification)} need clarification")

            message = f"Evaluation complete: {', '.join(summary_parts)}" if summary_parts else "Evaluation complete: no items"

            event = WorkflowEvent(
                id=uuid4(),
                workflow_id=workflow_id,
                sequence=EPHEMERAL_SEQUENCE,
                timestamp=datetime.now(UTC),
                agent="evaluator",
                event_type=EventType.AGENT_OUTPUT,
                level=EventLevel.DEBUG,
                message=message,
            )
            self._event_bus.emit(event)

        result = EvaluationResult(
            items_to_implement=items_to_implement,
            items_rejected=items_rejected,
            items_deferred=items_deferred,
            items_needing_clarification=items_needing_clarification,
            summary=result_data.summary,
        )

        return result, new_session_id
