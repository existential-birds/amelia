"""Unit tests for amelia.core.types module."""

from amelia.core.types import Profile


def test_profile_max_task_review_iterations_default():
    """Profile should have max_task_review_iterations with default value."""
    profile = Profile(
        name="test",
        driver="cli:claude",
        model="sonnet",
        validator_model="sonnet",
        working_dir="/tmp/test",
    )

    assert profile.max_task_review_iterations == 5


def test_profile_max_task_review_iterations_override():
    """Profile max_task_review_iterations should be configurable."""
    profile = Profile(
        name="test",
        driver="cli:claude",
        model="sonnet",
        validator_model="sonnet",
        working_dir="/tmp/test",
        max_task_review_iterations=10,
    )

    assert profile.max_task_review_iterations == 10
