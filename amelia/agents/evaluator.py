"""Evaluator agent for the review-fix workflow.

This module provides the Evaluator agent that evaluates review feedback
against the actual codebase, applying a decision matrix to determine
which items to implement, reject, defer, or clarify.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from loguru import logger

from amelia.agents.schemas.evaluator import (
    Disposition,
    EvaluatedItem,
    EvaluationOutput,
    EvaluationResult,
)
from amelia.core.types import AgentConfig, Profile, collect_all_comments
from amelia.drivers.base import AgenticMessageType, SubmitToolDef
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

You are running inside the actual working tree at the current working directory.
Use the Read, Grep, and Bash tools to fetch file contents and diffs on demand
as you verify each review item. The user prompt provides only a manifest of
changed files; do not expect an inlined diff in the prompt itself.

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

    @staticmethod
    def _parse_changed_files(diff_text: str | None) -> list[str]:
        """Extract post-change file paths from `diff --git` headers.

        Returns paths in order of first appearance, deduplicated. Handles
        rename headers (`a/old.py b/new.py`) by returning the `b/` path.
        """
        if not diff_text:
            return []
        seen: set[str] = set()
        out: list[str] = []
        for line in diff_text.splitlines():
            if not line.startswith("diff --git "):
                continue
            parts = line.split()
            # Expected: ["diff", "--git", "a/<path>", "b/<path>"]
            if len(parts) < 4:
                continue
            b_token = parts[3]
            if not b_token.startswith("b/"):
                continue
            path = b_token[2:]
            if path and path not in seen:
                seen.add(path)
                out.append(path)
        return out

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

        # Code changes context — emit a manifest, not an inlined diff. The
        # agent fetches actual file contents/diffs on demand via Read/Grep/Bash.
        if state.code_changes_for_review:
            changed = self._parse_changed_files(state.code_changes_for_review)
            if changed:
                manifest_lines = ["## Changed Files", ""]
                manifest_lines += [f"- {p}" for p in changed]
                base = getattr(state, "base_commit", None)
                if base:
                    manifest_lines.append("")
                    manifest_lines.append(
                        f"To inspect changes for a specific file, run: "
                        f"`git diff {base} -- <path>` from the repo root."
                    )
                manifest_lines.append("")
                manifest_lines.append(
                    "Use Read/Grep/Bash to fetch file contents or diffs on demand "
                    "as you verify each review item."
                )
                parts.append("\n".join(manifest_lines))

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

        # Build driver-agnostic submit tool.  The on_call callback captures the
        # result directly; stream interception is kept as a fallback for drivers
        # that surface tool calls in the message stream (e.g. mocked in tests).
        captured: list[EvaluationOutput] = []

        async def _on_submit(args: Any) -> None:
            if not captured:
                captured.append(EvaluationOutput.model_validate(args))
            else:
                logger.warning(
                    "submit_evaluation called more than once; ignoring duplicate",
                    agent="evaluator",
                    workflow_id=workflow_id,
                )

        submit_tool = SubmitToolDef(
            name="submit_evaluation",
            description="Submit the evaluation results for all review items. Call this exactly once.",
            schema=EvaluationOutput,
            on_call=_on_submit,
        )

        # Execute agentic evaluation with submit_evaluation tool (per D-05, D-06)
        new_session_id: str | None = None
        stream_result_input: Any | None = None  # fallback for drivers/tests that don't invoke on_call
        driver_error: str | None = None

        async for msg in self.driver.execute_agentic(
            prompt=prompt,
            cwd=profile.repo_root,
            session_id=None,  # Fresh session to avoid bias from prior agent context
            instructions=self.system_prompt,
            submit_tools=[submit_tool],
        ):
            if msg.type == AgenticMessageType.RESULT:
                new_session_id = msg.session_id
                if msg.is_error:
                    driver_error = msg.content or "(no error detail from driver)"
                    logger.error(
                        "Agentic evaluation failed at driver level",
                        agent="evaluator",
                        error=driver_error,
                        workflow_id=workflow_id,
                    )
            elif (
                msg.type == AgenticMessageType.TOOL_CALL
                and msg.tool_name == "submit_evaluation"
                and stream_result_input is None
            ):
                stream_result_input = msg.tool_input

        # on_call callback captures result directly (primary); stream interception is fallback
        result_data = captured[0] if captured else (
            EvaluationOutput.model_validate(stream_result_input)
            if stream_result_input is not None
            else None
        )

        if driver_error is not None:
            raise RuntimeError(
                f"Evaluator driver error (Claude CLI): {driver_error}"
            )

        if result_data is None:
            raise RuntimeError("Evaluator did not call submit_evaluation")
        expected_numbers = set(range(1, len(all_comments) + 1))
        actual_numbers = {item.number for item in result_data.evaluated_items}
        if actual_numbers != expected_numbers:
            raise RuntimeError(
                "submit_evaluation must cover every review item exactly once"
            )

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
