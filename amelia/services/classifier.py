"""Classifier service for PR review comment classification.

Provides pre-filtering (top-level only, iteration limits, Amelia reply detection),
LLM-based batch classification, post-filtering (confidence threshold, aggressiveness),
and file-based grouping.
"""

from __future__ import annotations

from collections import defaultdict

from loguru import logger

from amelia.core.types import PRReviewComment
from amelia.services.github_pr import AMELIA_FOOTER


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

    new_feedback = has_new_feedback_after_amelia(thread_comments)

    if new_feedback:
        # Fresh feedback resets iteration tracking
        return False

    # Amelia replied but no new feedback -- skip
    return True


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
