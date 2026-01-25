"""Factory module for creating issue tracker instances.

Provide a factory function that instantiates the appropriate tracker
implementation based on profile configuration. Supports Jira, GitHub,
and no-op trackers for different workflow integrations.
"""

from amelia.core.types import Profile
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
