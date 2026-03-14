"""Stub node functions for the PR auto-fix pipeline.

These will be implemented in Plan 02. For now they return empty dicts
so the graph can compile and the pipeline structure can be tested.
"""

from typing import Any

from langchain_core.runnables import RunnableConfig

from amelia.pipelines.pr_auto_fix.state import PRAutoFixState


async def classify_node(
    state: PRAutoFixState,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """Classify PR review comments into actionable categories.

    Stub implementation -- returns empty dict.
    """
    return {}


async def develop_node(
    state: PRAutoFixState,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """Fix code for each file group based on classified comments.

    Stub implementation -- returns empty dict.
    """
    return {}


async def commit_push_node(
    state: PRAutoFixState,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """Commit and push fixes to the PR branch.

    Stub implementation -- returns empty dict.
    """
    return {}
