"""Node functions for the PR auto-fix pipeline.

Implements classify_node (classification orchestration), develop_node
(Developer agent bridge with per-group execution), and commit_push_node
(git commit and push).
"""

from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig
from loguru import logger

from amelia.agents.developer import Developer
from amelia.agents.prompts.defaults import PROMPT_DEFAULTS
from amelia.agents.schemas.classifier import CommentClassification
from amelia.core.agentic_state import AgenticStatus
from amelia.core.types import AgentConfig, PRReviewComment
from amelia.drivers.factory import get_driver
from amelia.pipelines.implementation.state import ImplementationState
from amelia.pipelines.pr_auto_fix.state import (
    GroupFixResult,
    GroupFixStatus,
    PRAutoFixState,
)
from amelia.pipelines.utils import extract_config_params
from amelia.services.classifier import (
    classify_comments,
    filter_comments,
    group_comments_by_file,
)
from amelia.tools.git_utils import GitOperations


async def classify_node(
    state: PRAutoFixState,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """Classify PR review comments into actionable categories.

    Orchestrates filter -> classify -> group flow:
    1. Pre-filters comments (top-level only, iteration limits)
    2. Classifies via LLM
    3. Groups actionable comments by file path

    Returns dict with classified_comments and file_groups for state update.
    """
    if not state.comments:
        return {"classified_comments": [], "file_groups": {}}

    _event_bus, _workflow_id, profile = extract_config_params(config or {})

    # Create driver for classification
    agent_config = AgentConfig(
        driver=profile.agents["developer"].driver,
        model=profile.agents["developer"].model,
    )
    driver = get_driver(agent_config.driver, model=agent_config.model)

    # Pre-filter: top-level only, skip already-handled threads
    filtered = filter_comments(
        state.comments,
        {},  # Empty thread context -- threads pre-filtered by caller
        state.autofix_config.max_iterations,
    )

    if not filtered:
        return {"classified_comments": [], "file_groups": {}}

    # LLM classification
    classifications = await classify_comments(
        filtered, driver, state.autofix_config,
    )

    # Group by file path
    file_group_comments = group_comments_by_file(state.comments, classifications)

    # Convert from dict[path, list[PRReviewComment]] to dict[path, list[int]]
    file_groups: dict[str | None, list[int]] = {
        path: [c.id for c in comments]
        for path, comments in file_group_comments.items()
    }

    return {
        "classified_comments": list(classifications.values()),
        "file_groups": file_groups,
    }


def _build_developer_goal(
    file_path: str | None,
    comments: list[PRReviewComment],
    classifications: dict[int, CommentClassification],
    pr_number: int,
    head_branch: str,
) -> str:
    """Build a Developer goal string with full context for a file group.

    Args:
        file_path: File path for the group (None for cross-file).
        comments: Comments in this group.
        classifications: Classification results for looking up category/reason.
        pr_number: PR number for context.
        head_branch: PR head branch name.

    Returns:
        Goal string with comment body, file path, line, diff hunk,
        PR metadata, classification reasoning, and constraints.
    """
    parts: list[str] = []
    parts.append(f"Fix code based on PR #{pr_number} review comments (branch: {head_branch}).")
    parts.append("")

    for comment in comments:
        cls = classifications.get(comment.id)
        parts.append(f"## Comment (ID: {comment.id})")
        parts.append(f"**Body:** {comment.body}")
        if comment.path:
            parts.append(f"**File:** {comment.path}")
        if comment.line is not None:
            parts.append(f"**Line:** {comment.line}")
        if comment.diff_hunk:
            parts.append(f"**Diff hunk:**\n```\n{comment.diff_hunk}\n```")
        if cls:
            parts.append(f"**Category:** {cls.category}")
            parts.append(f"**Reason:** {cls.reason}")
        parts.append("")

    # Constraints
    parts.append("## Constraints")
    if file_path:
        parts.append(f"- Only modify files related to {file_path}")
    parts.append("- Fix root causes, not symptoms")
    parts.append("- Make minimal, targeted changes")
    parts.append("- Preserve existing behavior unless the review explicitly asks for a change")

    return "\n".join(parts)


async def develop_node(
    state: PRAutoFixState,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """Fix code for each file group based on classified comments.

    Iterates over file_groups, creates a Developer agent per group,
    builds a goal with full context, and runs the Developer.
    Handles per-group failures gracefully.

    Returns dict with group_results and agentic_status for state update.
    """
    if not state.file_groups:
        return {
            "group_results": [],
            "agentic_status": AgenticStatus.COMPLETED,
        }

    _event_bus, workflow_id, profile = extract_config_params(config or {})

    # Build classification lookup from state
    classifications: dict[int, CommentClassification] = {
        cls.comment_id: cls for cls in state.classified_comments
    }

    # Build comment lookup from state
    comments_by_id: dict[int, PRReviewComment] = {
        c.id: c for c in state.comments
    }

    group_results: list[GroupFixResult] = []

    for file_path, comment_ids in state.file_groups.items():
        comments = [comments_by_id[cid] for cid in comment_ids if cid in comments_by_id]

        # Build goal with full context
        goal_text = _build_developer_goal(
            file_path, comments, classifications,
            state.pr_number, state.head_branch,
        )

        try:
            # Create Developer with PR-fix system prompt
            agent_config = profile.get_agent_config("developer")
            dev = Developer(
                config=agent_config,
                prompts={
                    "developer.system": PROMPT_DEFAULTS["developer.pr_fix.system"].content,
                },
            )

            # Create temporary ImplementationState for Developer.run()
            impl_state = ImplementationState(
                workflow_id=state.workflow_id,
                pipeline_type="implementation",
                profile_id=state.profile_id,
                created_at=state.created_at,
                status="running",
                goal=goal_text,
                plan_markdown=goal_text,  # Required by Developer._build_prompt
            )

            # Run Developer and iterate to completion
            final_state = impl_state
            async for updated_state, _event in dev.run(
                final_state, profile=profile, workflow_id=workflow_id,
            ):
                final_state = updated_state

            group_results.append(GroupFixResult(
                file_path=file_path,
                status=GroupFixStatus.FIXED,
                comment_ids=comment_ids,
            ))
            logger.info(
                "Group fix completed",
                file_path=file_path,
                comment_count=len(comment_ids),
            )

        except Exception as e:
            logger.error(
                "Group fix failed",
                file_path=file_path,
                error=str(e),
            )
            group_results.append(GroupFixResult(
                file_path=file_path,
                status=GroupFixStatus.FAILED,
                error=str(e),
                comment_ids=comment_ids,
            ))

    # Determine overall status
    any_fixed = any(r.status == GroupFixStatus.FIXED for r in group_results)
    all_no_changes = all(r.status == GroupFixStatus.NO_CHANGES for r in group_results)
    agentic_status = (
        AgenticStatus.COMPLETED
        if any_fixed or all_no_changes
        else AgenticStatus.FAILED
    )

    return {
        "group_results": group_results,
        "agentic_status": agentic_status,
    }


def _build_commit_message(
    prefix: str,
    group_results: list[GroupFixResult],
    comments: list[PRReviewComment],
) -> str:
    """Build commit message with prefix and addressed comment listing.

    Args:
        prefix: Commit message prefix (e.g. "fix(review):").
        group_results: Results of group fixes.
        comments: All PR review comments for context.

    Returns:
        Formatted commit message.
    """
    comments_by_id = {c.id: c for c in comments}

    lines: list[str] = [f"{prefix} address PR review comments", ""]
    lines.append("Addressed:")

    for result in group_results:
        if result.status != GroupFixStatus.FIXED:
            continue
        for cid in result.comment_ids:
            comment = comments_by_id.get(cid)
            if comment:
                body_truncated = comment.body[:80]
                path_line = f"{comment.path or 'general'}"
                if comment.line is not None:
                    path_line += f":{comment.line}"
                lines.append(f"- {path_line} '{body_truncated}'")

    return "\n".join(lines)


async def commit_push_node(
    state: PRAutoFixState,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """Commit and push fixes to the PR branch.

    Checks for changes before committing. Builds commit message with
    configurable prefix and lists addressed comments. Pushes to head_branch.

    Returns dict with commit_sha and status for state update.
    """
    _event_bus, _workflow_id, profile = extract_config_params(config or {})

    try:
        git_ops = GitOperations(profile.repo_root)

        # Check if there are changes to commit
        porcelain = await git_ops._run_git("status", "--porcelain")
        if not porcelain.strip():
            logger.info("No changes to commit, skipping")
            return {"status": "completed", "commit_sha": None}

        # Build commit message
        message = _build_commit_message(
            state.autofix_config.commit_prefix,
            state.group_results,
            state.comments,
        )

        # Commit and push
        sha = await git_ops.stage_and_commit(message)
        await git_ops.safe_push(state.head_branch)

        logger.info(
            "Committed and pushed fixes",
            sha=sha[:8],
            branch=state.head_branch,
        )
        return {"status": "completed", "commit_sha": sha}

    except ValueError as e:
        logger.error("Git operation failed", error=str(e))
        return {"status": "failed", "error": str(e)}
