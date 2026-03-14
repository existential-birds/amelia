"""Unit tests for the classifier service.

Tests pre-filtering, iteration detection, LLM classification,
confidence/aggressiveness filtering, and file grouping.
"""

from datetime import UTC, datetime

import pytest

from amelia.core.types import PRReviewComment
from amelia.services.classifier import (
    count_amelia_replies,
    filter_comments,
    filter_top_level,
    has_new_feedback_after_amelia,
    should_skip_thread,
)
from amelia.services.github_pr import AMELIA_FOOTER


def _comment(
    id: int,
    body: str = "Fix this bug",
    author: str = "reviewer1",
    in_reply_to_id: int | None = None,
    thread_id: str | None = None,
    path: str | None = "src/app.py",
    line: int | None = 42,
    diff_hunk: str | None = "@@ -1,3 +1,4 @@",
    created_at: datetime | None = None,
) -> PRReviewComment:
    """Helper to build a PRReviewComment for tests."""
    return PRReviewComment(
        id=id,
        body=body,
        author=author,
        created_at=created_at or datetime(2026, 3, 13, 12, 0, 0, tzinfo=UTC),
        path=path,
        line=line,
        diff_hunk=diff_hunk,
        in_reply_to_id=in_reply_to_id,
        thread_id=thread_id,
    )


class TestFilterTopLevel:
    """Tests for filter_top_level: only comments with in_reply_to_id=None."""

    def test_filter_top_level_only(self) -> None:
        comments = [
            _comment(1),  # top-level
            _comment(2, in_reply_to_id=1),  # reply
            _comment(3),  # top-level
            _comment(4, in_reply_to_id=3),  # reply
        ]
        result = filter_top_level(comments)
        assert len(result) == 2
        assert [c.id for c in result] == [1, 3]

    def test_filter_top_level_all_top_level(self) -> None:
        comments = [_comment(1), _comment(2)]
        result = filter_top_level(comments)
        assert len(result) == 2

    def test_filter_top_level_empty(self) -> None:
        assert filter_top_level([]) == []


class TestCountAmeliaReplies:
    """Tests for count_amelia_replies: counts AMELIA_FOOTER in thread."""

    def test_count_amelia_replies(self) -> None:
        thread = [
            _comment(1, body="Please fix this"),
            _comment(2, body=f"Fixed the issue.\n\n{AMELIA_FOOTER}", author="amelia[bot]"),
            _comment(3, body="Still broken"),
            _comment(4, body=f"Fixed again.\n\n{AMELIA_FOOTER}", author="amelia[bot]"),
        ]
        assert count_amelia_replies(thread) == 2

    def test_count_amelia_replies_none(self) -> None:
        thread = [
            _comment(1, body="Please fix this"),
            _comment(2, body="I agree"),
        ]
        assert count_amelia_replies(thread) == 0

    def test_count_amelia_replies_empty(self) -> None:
        assert count_amelia_replies([]) == 0


class TestHasNewFeedbackAfterAmelia:
    """Tests for has_new_feedback_after_amelia."""

    def test_has_new_feedback_after_amelia(self) -> None:
        thread = [
            _comment(1, body="Fix this", created_at=datetime(2026, 3, 13, 10, 0, 0, tzinfo=UTC)),
            _comment(2, body=f"Done.\n\n{AMELIA_FOOTER}", created_at=datetime(2026, 3, 13, 11, 0, 0, tzinfo=UTC)),
            _comment(3, body="Still not right", created_at=datetime(2026, 3, 13, 12, 0, 0, tzinfo=UTC)),
        ]
        assert has_new_feedback_after_amelia(thread) is True

    def test_no_feedback_after_amelia(self) -> None:
        thread = [
            _comment(1, body="Fix this", created_at=datetime(2026, 3, 13, 10, 0, 0, tzinfo=UTC)),
            _comment(2, body=f"Done.\n\n{AMELIA_FOOTER}", created_at=datetime(2026, 3, 13, 11, 0, 0, tzinfo=UTC)),
        ]
        assert has_new_feedback_after_amelia(thread) is False

    def test_no_amelia_replies_at_all(self) -> None:
        thread = [
            _comment(1, body="Fix this", created_at=datetime(2026, 3, 13, 10, 0, 0, tzinfo=UTC)),
        ]
        assert has_new_feedback_after_amelia(thread) is False


class TestShouldSkipThread:
    """Tests for should_skip_thread: iteration limit + fresh feedback logic."""

    def test_skip_comments_with_amelia_reply(self) -> None:
        """Comment with Amelia reply and no new feedback is skipped."""
        thread = [
            _comment(1, body="Fix this", created_at=datetime(2026, 3, 13, 10, 0, 0, tzinfo=UTC)),
            _comment(2, body=f"Done.\n\n{AMELIA_FOOTER}", created_at=datetime(2026, 3, 13, 11, 0, 0, tzinfo=UTC)),
        ]
        assert should_skip_thread(thread, max_iterations=3) is True

    def test_fresh_feedback_after_amelia_not_skipped(self) -> None:
        """Comment with new reviewer feedback after Amelia is NOT skipped."""
        thread = [
            _comment(1, body="Fix this", created_at=datetime(2026, 3, 13, 10, 0, 0, tzinfo=UTC)),
            _comment(2, body=f"Done.\n\n{AMELIA_FOOTER}", created_at=datetime(2026, 3, 13, 11, 0, 0, tzinfo=UTC)),
            _comment(3, body="Still broken", created_at=datetime(2026, 3, 13, 12, 0, 0, tzinfo=UTC)),
        ]
        assert should_skip_thread(thread, max_iterations=3) is False

    def test_max_iterations_enforcement(self) -> None:
        """Comment at iteration limit with no new feedback is skipped."""
        thread = [
            _comment(1, body="Fix this", created_at=datetime(2026, 3, 13, 10, 0, 0, tzinfo=UTC)),
            _comment(2, body=f"Done.\n\n{AMELIA_FOOTER}", created_at=datetime(2026, 3, 13, 11, 0, 0, tzinfo=UTC)),
            _comment(3, body="Try again", created_at=datetime(2026, 3, 13, 12, 0, 0, tzinfo=UTC)),
            _comment(4, body=f"Done again.\n\n{AMELIA_FOOTER}", created_at=datetime(2026, 3, 13, 13, 0, 0, tzinfo=UTC)),
            _comment(5, body="One more time", created_at=datetime(2026, 3, 13, 14, 0, 0, tzinfo=UTC)),
            _comment(6, body=f"Third fix.\n\n{AMELIA_FOOTER}", created_at=datetime(2026, 3, 13, 15, 0, 0, tzinfo=UTC)),
        ]
        # 3 Amelia replies, max_iterations=3, no new feedback after last Amelia reply
        assert should_skip_thread(thread, max_iterations=3) is True

    def test_iteration_count_resets_on_new_feedback(self) -> None:
        """Comment at iteration limit WITH new feedback is not skipped."""
        thread = [
            _comment(1, body="Fix this", created_at=datetime(2026, 3, 13, 10, 0, 0, tzinfo=UTC)),
            _comment(2, body=f"Done.\n\n{AMELIA_FOOTER}", created_at=datetime(2026, 3, 13, 11, 0, 0, tzinfo=UTC)),
            _comment(3, body="Try again", created_at=datetime(2026, 3, 13, 12, 0, 0, tzinfo=UTC)),
            _comment(4, body=f"Done again.\n\n{AMELIA_FOOTER}", created_at=datetime(2026, 3, 13, 13, 0, 0, tzinfo=UTC)),
            _comment(5, body="One more time", created_at=datetime(2026, 3, 13, 14, 0, 0, tzinfo=UTC)),
            _comment(6, body=f"Third fix.\n\n{AMELIA_FOOTER}", created_at=datetime(2026, 3, 13, 15, 0, 0, tzinfo=UTC)),
            _comment(7, body="Actually this needs more work", created_at=datetime(2026, 3, 13, 16, 0, 0, tzinfo=UTC)),
        ]
        # 3 Amelia replies, max_iterations=3, BUT new feedback exists -> not skipped
        assert should_skip_thread(thread, max_iterations=3) is False

    def test_no_amelia_replies_not_skipped(self) -> None:
        """Thread with no Amelia replies is not skipped."""
        thread = [
            _comment(1, body="Fix this"),
        ]
        assert should_skip_thread(thread, max_iterations=3) is False


class TestFilterComments:
    """Tests for filter_comments: combines top-level + skip logic."""

    def test_filter_comments_basic(self) -> None:
        """Filters reply comments and Amelia-replied threads."""
        top_level = _comment(1, thread_id="t1")
        reply = _comment(2, in_reply_to_id=1, thread_id="t1")
        amelia_replied = _comment(3, thread_id="t2")

        comments = [top_level, reply, amelia_replied]
        all_threads: dict[str, list[PRReviewComment]] = {
            "t1": [top_level, reply],
            "t2": [
                amelia_replied,
                _comment(
                    4,
                    body=f"Fixed.\n\n{AMELIA_FOOTER}",
                    thread_id="t2",
                    created_at=datetime(2026, 3, 13, 13, 0, 0, tzinfo=UTC),
                ),
            ],
        }

        result = filter_comments(comments, all_threads, max_iterations=3)
        # Only top_level (id=1) should pass; amelia_replied (id=3) skipped
        assert len(result) == 1
        assert result[0].id == 1

    def test_filter_comments_fresh_feedback_passes(self) -> None:
        """Comment with fresh feedback after Amelia passes through."""
        comment = _comment(1, thread_id="t1", created_at=datetime(2026, 3, 13, 10, 0, 0, tzinfo=UTC))
        all_threads: dict[str, list[PRReviewComment]] = {
            "t1": [
                comment,
                _comment(
                    2,
                    body=f"Fixed.\n\n{AMELIA_FOOTER}",
                    thread_id="t1",
                    created_at=datetime(2026, 3, 13, 11, 0, 0, tzinfo=UTC),
                ),
                _comment(
                    3,
                    body="Still wrong",
                    thread_id="t1",
                    created_at=datetime(2026, 3, 13, 12, 0, 0, tzinfo=UTC),
                ),
            ],
        }

        result = filter_comments([comment], all_threads, max_iterations=3)
        assert len(result) == 1
        assert result[0].id == 1

    def test_filter_comments_no_thread_id_passes(self) -> None:
        """Comments without thread_id pass through (no thread lookup)."""
        comment = _comment(1, thread_id=None)
        result = filter_comments([comment], {}, max_iterations=3)
        assert len(result) == 1
