"""PR auto-fix pipeline package.

Provides the pipeline for automatically fixing PR review comments.
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
