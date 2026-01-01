"""Issue tracker integrations for Amelia.

Provide adapters for fetching issue data from various project management
systems. Each tracker implements the BaseTracker protocol to normalize
issue data for the orchestrator.

Exports:
    BaseTracker: Protocol defining the tracker interface.
    GithubTracker: Tracker for GitHub Issues.
    JiraTracker: Tracker for Atlassian Jira.
    NoopTracker: No-op tracker for standalone usage.
    create_tracker: Factory function for tracker instantiation.
"""

from amelia.trackers.base import BaseTracker
from amelia.trackers.factory import create_tracker
from amelia.trackers.github import GithubTracker
from amelia.trackers.jira import JiraTracker
from amelia.trackers.noop import NoopTracker


__all__ = [
    "BaseTracker",
    "GithubTracker",
    "JiraTracker",
    "NoopTracker",
    "create_tracker",
]
