"""Server lifecycle management.

Provide services for server startup, shutdown, and ongoing maintenance tasks.
Include health checking for git worktrees, log retention cleanup, and
graceful shutdown coordination.

Exports:
    CleanupResult: Result of a log retention cleanup operation.
    LogRetentionService: Service for cleaning up old workflow logs.
    ServerLifecycle: Coordinator for server startup and shutdown.
    WorktreeHealthChecker: Health checker for git worktree status.
"""

from amelia.server.lifecycle.health_checker import WorktreeHealthChecker
from amelia.server.lifecycle.retention import CleanupResult, LogRetentionService
from amelia.server.lifecycle.server import ServerLifecycle


__all__ = [
    "CleanupResult",
    "LogRetentionService",
    "ServerLifecycle",
    "WorktreeHealthChecker",
]
