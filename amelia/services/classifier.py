"""Classifier service for PR review comment classification.

Provides pre-filtering (top-level only, iteration limits, Amelia reply detection),
LLM-based batch classification, post-filtering (confidence threshold, aggressiveness),
and file-based grouping.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from typing import TYPE_CHECKING

from loguru import logger

from amelia.agents.prompts.defaults import PROMPT_DEFAULTS
from amelia.agents.schemas.classifier import (
    ClassificationOutput,
    CommentClassification,
    is_actionable,
)
from amelia.core.types import PRAutoFixConfig, PRReviewComment
from amelia.services.github_pr import AMELIA_FOOTER


if TYPE_CHECKING:
    from amelia.drivers.base import DriverInterface


def filter_top_level(comments: list[PRReviewComment]) -> list[PRReviewComment]:
    """Return only top-level comments (in_reply_to_id is None).

    Args:
        comments: List of PR review comments.

    Returns:
        Filtered list containing only top-level comments.
    """
    return [c for c in comments if c.in_reply_to_id is None]


def count_amelia_replies(thread_comments: list[PRReviewComment]) -> int:
    """Count comments containing AMELIA_FOOTER in a thread.

    Args:
        thread_comments: All comments in a review thread.

    Returns:
        Number of comments with the Amelia footer signature.
    """
    return sum(1 for c in thread_comments if AMELIA_FOOTER in c.body)


def has_new_feedback_after_amelia(thread_comments: list[PRReviewComment]) -> bool:
    """Check if a non-Amelia comment exists after the last Amelia comment.

    Args:
        thread_comments: All comments in a review thread.

    Returns:
        True if a reviewer commented after Amelia's last reply.
    """
    sorted_comments = sorted(thread_comments, key=lambda c: c.created_at)

    last_amelia_at = None
    for c in sorted_comments:
        if AMELIA_FOOTER in c.body:
            last_amelia_at = c.created_at

    if last_amelia_at is None:
        return False

    for c in sorted_comments:
        if c.created_at > last_amelia_at and AMELIA_FOOTER not in c.body:
            return True

    return False


def should_skip_thread(
    thread_comments: list[PRReviewComment],
    max_iterations: int,
) -> bool:
    """Determine whether a thread should be skipped.

    A thread is skipped when:
    - Amelia has replied AND no new reviewer feedback exists after the last reply
    - OR Amelia reply count >= max_iterations AND no new feedback (iteration limit)

    A thread is NOT skipped when:
    - No Amelia replies exist
    - New reviewer feedback exists after Amelia's last reply (fresh feedback resets)

    Args:
        thread_comments: All comments in a review thread.
        max_iterations: Maximum fix attempts per thread.

    Returns:
        True if the thread should be skipped.
    """
    amelia_count = count_amelia_replies(thread_comments)

    if amelia_count == 0:
        return False

    # Fresh feedback resets iteration tracking; otherwise skip
    return not has_new_feedback_after_amelia(thread_comments)


def filter_comments(
    comments: list[PRReviewComment],
    all_thread_comments: dict[str, list[PRReviewComment]],
    max_iterations: int,
) -> list[PRReviewComment]:
    """Apply pre-filtering to comments before classification.

    Filters out:
    - Reply comments (in_reply_to_id is not None)
    - Comments in threads where Amelia already replied (unless fresh feedback)
    - Comments in threads exceeding max_iterations (unless fresh feedback)

    Args:
        comments: All review comments to filter.
        all_thread_comments: Mapping of thread_id to all comments in that thread.
        max_iterations: Maximum fix attempts per thread.

    Returns:
        Filtered list of comments ready for classification.
    """
    top_level = filter_top_level(comments)

    result: list[PRReviewComment] = []
    for comment in top_level:
        if comment.thread_id is None:
            # No thread context -- cannot check for Amelia replies
            result.append(comment)
            continue

        thread = all_thread_comments.get(comment.thread_id, [])
        if should_skip_thread(thread, max_iterations):
            logger.debug(
                "Skipping comment in already-handled thread",
                comment_id=comment.id,
                thread_id=comment.thread_id,
                reason="amelia_replied_no_new_feedback",
            )
            continue

        result.append(comment)

    return result


def _build_user_prompt(comments: list[PRReviewComment]) -> str:
    """Build the user prompt listing each comment for classification.

    Args:
        comments: Comments to include in the prompt.

    Returns:
        Formatted prompt string with comment details.
    """
    lines: list[str] = ["Classify the following PR review comments:\n"]
    for c in comments:
        lines.append(f"---\nComment ID: {c.id}")
        lines.append(f"Body: {c.body}")
        if c.path is not None:
            lines.append(f"Path: {c.path}")
        # Prefer current line, fall back to original_line (survives force-pushes)
        effective_line = c.line or c.original_line
        if c.start_line is not None or c.original_start_line is not None:
            effective_start = c.start_line or c.original_start_line
            if effective_line is not None:
                lines.append(f"Lines: {effective_start}-{effective_line}")
            elif effective_start is not None:
                lines.append(f"Line: {effective_start}")
        elif effective_line is not None:
            lines.append(f"Line: {effective_line}")
        if c.side is not None:
            lines.append(f"Side: {c.side}")
        if c.subject_type == "file":
            lines.append("Scope: file-level comment")
        if c.diff_hunk is not None:
            lines.append(f"Diff hunk:\n{c.diff_hunk}")
        lines.append("")
    return "\n".join(lines)


async def classify_comments(
    comments: list[PRReviewComment],
    driver: DriverInterface,
    config: PRAutoFixConfig,
) -> dict[int, CommentClassification]:
    """Classify PR review comments using LLM with post-filtering.

    1. Loads system prompt from PROMPT_DEFAULTS, formatted with aggressiveness level
    2. Builds user prompt with comment details
    3. Calls driver.generate with schema=ClassificationOutput
    4. Applies confidence threshold filter
    5. Applies aggressiveness filter via is_actionable

    Args:
        comments: Pre-filtered list of comments to classify.
        driver: LLM driver implementing DriverInterface.
        config: PR auto-fix configuration with aggressiveness and thresholds.

    Returns:
        Mapping of comment_id to final CommentClassification.
    """
    if len(comments) > 50:
        logger.warning(
            "Large batch of comments for classification",
            count=len(comments),
        )

    # Build prompts
    system_prompt_template = PROMPT_DEFAULTS["classifier.system"].content
    system_prompt = system_prompt_template.format(
        aggressiveness_level=config.aggressiveness.name,
    )
    user_prompt = _build_user_prompt(comments)

    # Call LLM
    output, _session_id = await driver.generate(
        prompt=user_prompt,
        system_prompt=system_prompt,
        schema=ClassificationOutput,
    )

    # Process classifications
    result: dict[int, CommentClassification] = {}
    classification_output: ClassificationOutput = output

    for classification in classification_output.classifications:
        final = classification

        # Apply confidence threshold
        if classification.confidence < config.confidence_threshold:
            logger.debug(
                "Classification below confidence threshold",
                comment_id=classification.comment_id,
                confidence=classification.confidence,
                threshold=config.confidence_threshold,
            )
            if final.actionable:
                final = final.model_copy(update={"actionable": False})

        # Apply aggressiveness filter
        if final.actionable and not is_actionable(
            final.category, config.aggressiveness
        ):
            logger.debug(
                "Classification filtered by aggressiveness level",
                comment_id=final.comment_id,
                category=str(final.category),
                aggressiveness=config.aggressiveness.name,
            )
            final = final.model_copy(update={"actionable": False})

        logger.debug(
            "Classification result",
            comment_id=final.comment_id,
            category=str(final.category),
            confidence=final.confidence,
            actionable=final.actionable,
        )

        result[final.comment_id] = final

    return result


def group_comments_by_file(
    comments: list[PRReviewComment],
    classifications: dict[int, CommentClassification],
) -> dict[str | None, list[PRReviewComment]]:
    """Group actionable comments by file path.

    Only includes comments whose classification is actionable.
    Comments with path=None form a separate group under the None key.

    Args:
        comments: All comments to group.
        classifications: Classification results mapping comment_id to classification.

    Returns:
        Mapping of file path (or None) to list of actionable comments.
    """
    groups: dict[str | None, list[PRReviewComment]] = defaultdict(list)

    for comment in comments:
        classification = classifications.get(comment.id)
        if classification is None or not classification.actionable:
            continue
        groups[comment.path].append(comment)

    return dict(groups)


def get_prompt_hash(aggressiveness_level: str) -> str:
    """Compute SHA-256 hash prefix of the classification system prompt.

    Builds the same prompt that classify_comments uses, normalizes
    whitespace, and returns the first 16 hex characters of the SHA-256.

    Args:
        aggressiveness_level: The aggressiveness level name to format into the prompt.

    Returns:
        16-character hex digest string.
    """
    system_prompt_template = PROMPT_DEFAULTS["classifier.system"].content
    system_prompt = system_prompt_template.format(
        aggressiveness_level=aggressiveness_level,
    )
    return hashlib.sha256(system_prompt.strip().encode()).hexdigest()[:16]
