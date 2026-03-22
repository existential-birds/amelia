"""PR Auto-Fix Pipeline.

Nodes: classify -> develop -> commit_push -> reply_resolve -> END

Note: PIPE-08 (review pipeline composition -- invoking PR_AUTO_FIX from
the existing review pipeline) is deferred. PR creation capability must
exist before composition can be wired. See Phase 5 CONTEXT.md for details.
"""

from amelia.pipelines.pr_auto_fix.pipeline import PRAutoFixPipeline
from amelia.pipelines.pr_auto_fix.state import (
    GroupFixResult,
    GroupFixStatus,
    PRAutoFixState,
)


__all__ = [
    "GroupFixResult",
    "GroupFixStatus",
    "PRAutoFixPipeline",
    "PRAutoFixState",
]
