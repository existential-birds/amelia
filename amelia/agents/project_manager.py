from amelia.trackers.base import BaseTracker
from amelia.core.types import Issue, Profile
from amelia.trackers.noop import NoopTracker
from amelia.trackers.github import GithubTracker
from amelia.trackers.jira import JiraTracker

class ProjectManager:
    def __init__(self, tracker: BaseTracker):
        self.tracker = tracker

    def get_issue(self, issue_id: str) -> Issue:
        """
        Retrieves an issue from the configured tracker.
        """
        return self.tracker.get_issue(issue_id)

def create_project_manager(profile: Profile) -> ProjectManager:
    """
    Factory to create a ProjectManager based on the profile settings.
    """
    if profile.tracker == "jira":
        tracker: BaseTracker = JiraTracker()
    elif profile.tracker == "github":
        tracker = GithubTracker()
    elif profile.tracker == "none" or profile.tracker == "noop":
        tracker = NoopTracker()
    else:
        raise ValueError(f"Unknown tracker type: {profile.tracker}")
    
    return ProjectManager(tracker=tracker)

