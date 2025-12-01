from amelia.core.types import Profile
from amelia.trackers.base import BaseTracker
from amelia.trackers.github import GithubTracker
from amelia.trackers.jira import JiraTracker
from amelia.trackers.noop import NoopTracker


def create_tracker(profile: Profile) -> BaseTracker:
    """
    Factory to create a tracker based on the profile settings.
    """
    if profile.tracker == "jira":
        return JiraTracker()
    elif profile.tracker == "github":
        return GithubTracker()
    elif profile.tracker == "none" or profile.tracker == "noop":
        return NoopTracker()
    else:
        raise ValueError(f"Unknown tracker type: {profile.tracker}")
