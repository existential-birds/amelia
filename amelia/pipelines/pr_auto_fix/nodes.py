"""Node functions for the PR auto-fix pipeline.

Implements classify_node (classification orchestration), develop_node
(Developer agent bridge with per-group execution), commit_push_node
(git commit and push), and reply_resolve_node (reply to reviewers and
resolve threads).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from langchain_core.runnables import RunnableConfig
from loguru import logger

from amelia.agents.developer import Developer
from amelia.agents.prompts.defaults import PROMPT_DEFAULTS
from amelia.agents.schemas.classifier import CommentClassification
from amelia.core.agentic_state import AgenticStatus
from amelia.core.types import PRReviewComment
from amelia.drivers.factory import get_driver
from amelia.pipelines.implementation.state import ImplementationState
from amelia.pipelines.nodes import _save_token_usage
from amelia.pipelines.pr_auto_fix.state import (
    GroupFixResult,
    GroupFixStatus,
    PRAutoFixState,
    ResolutionResult,
)
from amelia.pipelines.utils import extract_config_params
from amelia.services.classifier import (
    classify_comments,
    filter_comments,
    get_prompt_hash,
    group_comments_by_file,
)
from amelia.services.github_pr import GitHubPRService
from amelia.tools.git_utils import GitOperations


async def classify_node(
    state: PRAutoFixState,
    config: RunnableConfig,
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

    _event_bus, workflow_id, profile = extract_config_params(config)
    configurable = config.get("configurable", {})
    repository = configurable.get("repository")

    # Create driver for classification using full developer agent config
    agent_config = profile.get_agent_config("developer")
    driver = get_driver(
        agent_config.driver,
        model=agent_config.model,
        options=agent_config.options,
        profile_name=agent_config.profile_name,
    )

    # Build thread context by grouping comments by thread_id
    all_thread_comments: dict[str, list[PRReviewComment]] = {}
    for comment in state.comments:
        if comment.thread_id is not None:
            all_thread_comments.setdefault(comment.thread_id, []).append(comment)

    # Pre-filter: top-level only, skip already-handled threads
    filtered = filter_comments(
        state.comments,
        all_thread_comments,
        state.autofix_config.max_iterations,
    )

    if not filtered:
        return {"classified_comments": [], "file_groups": {}}

    # LLM classification
    try:
        classifications = await classify_comments(
            filtered, driver, state.autofix_config,
        )
    finally:
        try:
            await _save_token_usage(driver, workflow_id, "classifier", repository)
        except Exception:
            logger.exception(
                "Failed to persist classifier token usage",
                workflow_id=workflow_id,
            )

    # Build classification audit data for deferred persistence.
    # Stored in state and persisted by the orchestrator after the
    # pr_autofix_runs row exists (avoids FK violation).
    prompt_hash = get_prompt_hash(state.autofix_config.aggressiveness.name)
    classifications_data: list[dict[str, object]] = []
    for comment in filtered:
        cls = classifications.get(comment.id)
        if cls is not None:
            classifications_data.append({
                "comment_id": comment.id,
                "body_snippet": comment.body[:200],
                "category": str(cls.category),
                "confidence": cls.confidence,
                "actionable": cls.actionable,
                "aggressiveness_level": state.autofix_config.aggressiveness.name,
                "prompt_hash": prompt_hash,
            })

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
        "classification_audit_data": classifications_data,
    }


def _build_developer_goal(
    file_path: str | None,
    comments: list[PRReviewComment],
    classifications: dict[int, CommentClassification],
    pr_number: int,
    head_branch: str,
    *,
    cwd: str | None = None,
) -> str:
    """Build a Developer goal string with full context for a file group.

    Args:
        file_path: File path for the group (None for cross-file).
        comments: Comments in this group.
        classifications: Classification results for looking up category/reason.
        pr_number: PR number for context.
        head_branch: PR head branch name.
        cwd: Working directory the agent will run in. When provided, anchors
            all file paths relative to this directory so the agent doesn't
            resolve them against some other location on disk.

    Returns:
        Goal string with comment body, file path, line, diff hunk,
        PR metadata, classification reasoning, and constraints.
    """
    parts: list[str] = []
    parts.append(f"Fix code based on PR #{pr_number} review comments (branch: {head_branch}).")

    # Anchor the agent to its working directory so it doesn't resolve
    # file paths against a different checkout or the original repo.
    if cwd:
        parts.append("")
        parts.append("## Working Directory")
        parts.append(f"You are working in: `{cwd}`")
        parts.append(
            "All file paths in the comments below are **relative to this directory**. "
            "Open files using these relative paths — do NOT construct absolute paths "
            "to other directories on disk."
        )
    parts.append("")

    for comment in comments:
        cls = classifications.get(comment.id)
        parts.append(f"## Comment (ID: {comment.id})")
        parts.append(f"**Body:** {comment.body}")
        if comment.path:
            parts.append(f"**File:** {comment.path}")
        # Prefer line (current), fall back to original_line (survives force-pushes)
        effective_line = comment.line or comment.original_line
        if comment.start_line is not None or comment.original_start_line is not None:
            effective_start = comment.start_line or comment.original_start_line
            if effective_line is not None:
                parts.append(f"**Lines:** {effective_start}-{effective_line}")
            elif effective_start is not None:
                parts.append(f"**Line:** {effective_start}")
        elif effective_line is not None:
            parts.append(f"**Line:** {effective_line}")
        if comment.side:
            side_label = "new code" if comment.side == "RIGHT" else "old code"
            parts.append(f"**Side:** {side_label} ({comment.side})")
        if comment.subject_type == "file":
            parts.append("**Scope:** file-level comment")
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
    config: RunnableConfig,
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

    _event_bus, workflow_id, profile = extract_config_params(config)
    configurable = config.get("configurable", {})
    repository = configurable.get("repository")

    # Build classification lookup from state
    classifications: dict[int, CommentClassification] = {
        cls.comment_id: cls for cls in state.classified_comments
    }

    # Build comment lookup from state
    comments_by_id: dict[int, PRReviewComment] = {
        c.id: c for c in state.comments
    }

    group_results: list[GroupFixResult] = []

    git_ops = GitOperations(profile.repo_root)

    for file_path, comment_ids in state.file_groups.items():
        comments = [comments_by_id[cid] for cid in comment_ids if cid in comments_by_id]

        # Build goal with full context, anchoring paths to the worktree CWD
        goal_text = _build_developer_goal(
            file_path, comments, classifications,
            state.pr_number, state.head_branch,
            cwd=profile.repo_root,
        )

        # Pre-flight: warn if referenced files don't exist in the worktree.
        # This catches misconfigured repo_root early (e.g. worktree created
        # from the wrong repo) instead of letting the agent stumble.
        repo_root = Path(profile.repo_root)
        if file_path:
            target = repo_root / file_path
            if not target.exists():
                logger.warning(
                    "Referenced file not found in worktree — agent may fail",
                    file_path=file_path,
                    repo_root=str(repo_root),
                )

        try:
            # Snapshot changed files before this group runs so we can detect
            # whether THIS group introduced new changes (vs. prior groups).
            baseline_status = await git_ops._run_git(
                "status", "--porcelain", "--", ".", ":!.claude/",
            )
            baseline_files = set(baseline_status.strip().splitlines()) if baseline_status.strip() else set()
            baseline_head = await git_ops._run_git("rev-parse", "HEAD")

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
            try:
                async for updated_state, _event in dev.run(
                    final_state, profile=profile, workflow_id=workflow_id,
                ):
                    final_state = updated_state
            finally:
                try:
                    await _save_token_usage(dev.driver, workflow_id, "developer", repository)
                except Exception:
                    logger.exception(
                        "Failed to persist developer token usage",
                        workflow_id=workflow_id,
                    )

            # Check if THIS group introduced new file changes by comparing
            # the current porcelain status against the pre-group baseline.
            current_status = await git_ops._run_git(
                "status", "--porcelain", "--", ".", ":!.claude/",
            )
            current_files = set(current_status.strip().splitlines()) if current_status.strip() else set()
            current_head = await git_ops._run_git("rev-parse", "HEAD")
            group_introduced_changes = (
                (current_files != baseline_files)
                or (current_head.strip() != baseline_head.strip())
            )

            if group_introduced_changes:
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
            else:
                group_results.append(GroupFixResult(
                    file_path=file_path,
                    status=GroupFixStatus.NO_CHANGES,
                    comment_ids=comment_ids,
                ))
                logger.warning(
                    "Developer completed but produced no file changes",
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
    config: RunnableConfig,
) -> dict[str, Any]:
    """Commit and push fixes to the PR branch.

    Checks for changes before committing. Builds commit message with
    configurable prefix and lists addressed comments. Pushes to head_branch.

    Returns dict with commit_sha and status for state update.
    """
    _event_bus, _workflow_id, profile = extract_config_params(config)

    try:
        git_ops = GitOperations(profile.repo_root)

        # Check if there are changes to commit
        if not await git_ops.has_changes():
            logger.info("No changes to commit, skipping")
            return {"status": "completed", "commit_sha": None}

        # Build commit message
        message = _build_commit_message(
            state.autofix_config.commit_prefix,
            state.group_results,
            state.comments,
        )

        # Commit first — preserve SHA even if push fails
        sha = await git_ops.stage_and_commit(message)

    except ValueError as e:
        logger.error("Git commit failed", error=str(e))
        return {"status": "failed", "error": str(e)}

    # Push separately so commit_sha is always returned on commit success
    try:
        await git_ops.safe_push(state.head_branch, skip_hooks=True)
        logger.info(
            "Committed and pushed fixes",
            sha=sha[:8],
            branch=state.head_branch,
        )
        return {"status": "completed", "commit_sha": sha}

    except ValueError as e:
        logger.error(
            "Git push failed",
            error=str(e),
            sha=sha[:8],
            branch=state.head_branch,
            repo_root=str(profile.repo_root),
        )
        return {"status": "failed", "commit_sha": sha, "error": str(e)}


def _build_reply_body(
    status: GroupFixStatus,
    author: str,
    commit_sha: str | None,
    error: str | None,
) -> str:
    """Build reply body for a comment based on fix status.

    Does NOT include the Amelia footer -- reply_to_comment appends it.

    Args:
        status: The fix outcome status.
        author: Comment author login for @mention.
        commit_sha: Commit SHA for fixed comments.
        error: Error message for failed comments.

    Returns:
        Reply body string.
    """
    short_sha = commit_sha[:7] if commit_sha else "unknown"

    if status == GroupFixStatus.FIXED:
        return f"@{author} Fixed in {short_sha}."
    if status == GroupFixStatus.FAILED:
        return f"@{author} Could not auto-fix: {error or 'Unknown error'}. Flagging for human review."
    # NO_CHANGES
    return f"@{author} Reviewed this comment -- no code changes needed."


async def reply_resolve_node(
    state: PRAutoFixState,
    config: RunnableConfig,
) -> dict[str, Any]:
    """Reply to reviewers and resolve threads after fixes are pushed.

    For each comment addressed by a group result:
    - Posts a per-comment reply with @mention and status info
    - Conditionally resolves the thread (FIXED always, NO_CHANGES if config allows)
    - Isolates errors per-comment so one failure doesn't block others

    Returns dict with status and resolution_results for state update.
    """
    _event_bus, _workflow_id, profile = extract_config_params(config)

    github_service = GitHubPRService(profile.repo_root)

    # Build comment lookup
    comments_by_id: dict[int, PRReviewComment] = {
        c.id: c for c in state.comments
    }

    resolution_results: list[ResolutionResult] = []

    for group_result in state.group_results:
        for comment_id in group_result.comment_ids:
            comment = comments_by_id.get(comment_id)
            if comment is None:
                logger.warning(
                    "Comment not found in state, skipping",
                    comment_id=comment_id,
                )
                continue

            # Guard: skip reply/resolve when commit or push failed.
            if group_result.status == GroupFixStatus.FIXED and not state.commit_sha:
                # Developer "completed" without producing real file changes
                logger.warning(
                    "Group marked FIXED but no commit was made, skipping reply/resolve",
                    comment_id=comment_id,
                    file_path=group_result.file_path,
                )
                resolution_results.append(
                    ResolutionResult(
                        comment_id=comment.id,
                        replied=False,
                        resolved=False,
                        error="No commit was made despite FIXED status",
                    )
                )
                continue

            if group_result.status == GroupFixStatus.FIXED and state.status == "failed":
                # Commit succeeded but push failed — changes aren't on the remote
                logger.warning(
                    "Group marked FIXED but push failed, skipping reply/resolve",
                    comment_id=comment_id,
                    file_path=group_result.file_path,
                    commit_sha=state.commit_sha,
                )
                resolution_results.append(
                    ResolutionResult(
                        comment_id=comment.id,
                        replied=False,
                        resolved=False,
                        error="Fix committed but push to remote failed",
                    )
                )
                continue

            replied = False
            resolved = False
            error_msg: str | None = None

            # Post reply
            body = _build_reply_body(
                group_result.status,
                comment.author,
                state.commit_sha,
                group_result.error,
            )
            try:
                await github_service.reply_to_comment(
                    state.pr_number,
                    comment.id,
                    body,
                    in_reply_to_id=comment.in_reply_to_id,
                )
                replied = True
            except Exception as e:
                logger.error(
                    "Failed to reply to comment",
                    comment_id=comment.id,
                    error=str(e),
                )
                error_msg = str(e)

            # Determine if we should resolve
            should_resolve = (
                group_result.status == GroupFixStatus.FIXED
                or (
                    group_result.status == GroupFixStatus.NO_CHANGES
                    and state.autofix_config.resolve_no_changes
                )
            )

            # Resolve thread (only if reply was successfully posted)
            if should_resolve and replied:
                if comment.thread_id:
                    try:
                        await github_service.resolve_thread(comment.thread_id)
                        resolved = True
                    except Exception as e:
                        logger.error(
                            "Failed to resolve thread",
                            comment_id=comment.id,
                            thread_id=comment.thread_id,
                            error=str(e),
                        )
                        error_msg = str(e)
                else:
                    logger.warning(
                        "No thread_id for comment, skipping resolve",
                        comment_id=comment.id,
                    )
            elif should_resolve and not replied:
                logger.warning(
                    "Skipping thread resolve because reply was not posted",
                    comment_id=comment.id,
                    thread_id=comment.thread_id,
                )

            resolution_results.append(
                ResolutionResult(
                    comment_id=comment.id,
                    replied=replied,
                    resolved=resolved,
                    error=error_msg,
                )
            )

    return {"status": "completed", "resolution_results": resolution_results}
