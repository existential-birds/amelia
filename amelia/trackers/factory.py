"""Factory module for creating issue tracker instances.

Provide a factory function that instantiates the appropriate tracker
implementation based on profile configuration. Supports Jira, GitHub,
and no-op trackers for different workflow integrations.
"""

import asyncio

from amelia.core.types import Issue, Profile
from amelia.trackers.base import BaseTracker
from amelia.trackers.github import GithubTracker
from amelia.trackers.jira import JiraTracker
from amelia.trackers.noop import NoopTracker


def create_tracker(profile: Profile) -> BaseTracker:
    """Factory to create a tracker based on the profile settings.

    Args:
        profile: The profile containing tracker configuration.

    Returns:
        A tracker instance implementing the BaseTracker protocol.

    Raises:
        ValueError: If the tracker type in the profile is unknown.
        ConfigurationError: If the selected tracker is not properly configured.
    """
    if profile.tracker == "jira":
        return JiraTracker()
    elif profile.tracker == "github":
        return GithubTracker()
    elif profile.tracker == "noop":
        return NoopTracker()
    else:
        raise ValueError(f"Unknown tracker type: {profile.tracker}")


async def fetch_issue(
    profile: Profile, issue_id: str, *, cwd: str | None = None
) -> Issue:
    """Create the tracker for ``profile`` and fetch ``issue_id`` off the loop.

    Wraps the blocking tracker fetch in :func:`asyncio.to_thread` so a slow
    subprocess/HTTP tracker does not freeze the event loop. Prefer this over
    ``create_tracker(profile)`` followed by a synchronous ``get_issue`` call:
    off-loading is baked in, so the missing-await bug class cannot recur at
    future call sites.

    Args:
        profile: The profile describing which tracker to use.
        issue_id: The tracker issue identifier to fetch.
        cwd: Optional working directory forwarded to ``get_issue``.

    Returns:
        The fetched issue.

    Raises:
        ValueError: If the tracker type in the profile is unknown.
        ConfigurationError: If the selected tracker is not properly configured.
        Any exception raised by the underlying tracker fetch propagates.
    """
    tracker = create_tracker(profile)
    return await asyncio.to_thread(tracker.get_issue, issue_id, cwd=cwd)
