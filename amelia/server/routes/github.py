"""GitHub integration endpoints."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger
from pydantic import BaseModel
from starlette.requests import Request
from starlette.responses import JSONResponse

from amelia.core.types import (
    AggressivenessLevel,
    PRAutoFixConfig,
    Profile,
    PRReviewComment,
    PRSummary,
    TrackerType,
)
from amelia.pipelines.pr_auto_fix.orchestrator import PRAutoFixOrchestrator
from amelia.server.database import ProfileRepository, WorkflowRepository
from amelia.server.dependencies import get_profile_repository, get_repository
from amelia.services.github_pr import GitHubPRService


router = APIRouter(prefix="/github", tags=["github"])

_GH_ISSUE_FIELDS = "number,title,labels,assignees,createdAt,state"
_GH_ISSUE_LIMIT = "50"


# ---------------------------------------------------------------------------
# Issue models and endpoint
# ---------------------------------------------------------------------------


class GitHubIssueLabel(BaseModel):
    """Label on a GitHub issue."""

    name: str
    color: str


class GitHubIssueSummary(BaseModel):
    """Summary of a GitHub issue for the combobox."""

    number: int
    title: str
    labels: list[GitHubIssueLabel]
    assignee: str | None
    created_at: datetime
    state: str


class GitHubIssuesResponse(BaseModel):
    """Response containing a list of GitHub issues."""

    issues: list[GitHubIssueSummary]


def _parse_issue(item: dict[str, Any]) -> GitHubIssueSummary:
    """Parse a single raw gh JSON issue into a GitHubIssueSummary."""
    assignees = item.get("assignees") or []
    raw_labels = item.get("labels") or []
    return GitHubIssueSummary(
        number=item["number"],
        title=item["title"],
        labels=[
            GitHubIssueLabel(name=label["name"], color=label.get("color", ""))
            for label in raw_labels
        ],
        assignee=assignees[0]["login"] if assignees else None,
        created_at=item["createdAt"],
        state=item["state"],
    )


@router.get("/issues", response_model=GitHubIssuesResponse)
async def list_github_issues(
    profile: str = Query(..., description="Profile name to resolve repo context"),
    search: str | None = Query(None, description="Search query for filtering issues"),
    profile_repo: ProfileRepository = Depends(get_profile_repository),
) -> GitHubIssuesResponse:
    """List open GitHub issues for a profile's repository.

    Args:
        profile: Profile name used to resolve repo_root and validate tracker type.
        search: Optional search query passed to gh issue list --search.
        profile_repo: Profile repository dependency.

    Returns:
        GitHubIssuesResponse with up to 50 open issues.

    Raises:
        HTTPException: 400 if profile doesn't use github tracker,
            404 if profile not found, 500 if gh CLI fails.
    """
    resolved = await profile_repo.get_profile(profile)
    if resolved is None:
        raise HTTPException(status_code=404, detail=f"Profile '{profile}' not found")

    if resolved.tracker != TrackerType.GITHUB:
        raise HTTPException(
            status_code=400,
            detail=f"Profile '{profile}' uses tracker '{resolved.tracker}', not GitHub",
        )

    cmd = [
        "gh",
        "issue",
        "list",
        "--json",
        _GH_ISSUE_FIELDS,
        "--limit",
        _GH_ISSUE_LIMIT,
        "--state",
        "open",
    ]
    if search:
        cmd.extend(["--search", search])

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=resolved.repo_root,
    )
    stdout_bytes, stderr_bytes = await proc.communicate()
    stdout = stdout_bytes.decode()
    stderr = stderr_bytes.decode()

    if proc.returncode != 0:
        logger.error("gh issue list failed", stderr=stderr, profile=profile)
        raise HTTPException(
            status_code=500,
            detail=f"GitHub CLI failed: {stderr.strip()}",
        )

    try:
        raw_issues = json.loads(stdout)
    except json.JSONDecodeError as e:
        logger.error("Failed to parse gh output", error=str(e), profile=profile)
        raise HTTPException(
            status_code=500,
            detail="Failed to parse GitHub CLI output",
        ) from e

    return GitHubIssuesResponse(
        issues=[_parse_issue(item) for item in raw_issues],
    )


# ---------------------------------------------------------------------------
# PR models
# ---------------------------------------------------------------------------


class TriggerPRAutoFixRequest(BaseModel):
    """Request body for triggering PR auto-fix."""

    aggressiveness: str | None = None


class TriggerPRAutoFixResponse(BaseModel):
    """Response from triggering PR auto-fix."""

    workflow_id: str
    message: str


class PRListResponse(BaseModel):
    """Response containing a list of open PRs."""

    prs: list[PRSummary]


class PRCommentsResponse(BaseModel):
    """Response containing PR review comments."""

    comments: list[PRReviewComment]


class PRAutoFixStatusResponse(BaseModel):
    """Response with PR auto-fix configuration status."""

    enabled: bool
    config: PRAutoFixConfig | None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _resolve_github_profile(
    profile_name: str,
    profile_repo: ProfileRepository,
) -> Profile:
    """Resolve and validate a GitHub profile.

    Args:
        profile_name: Profile name to resolve.
        profile_repo: Profile repository for lookup.

    Returns:
        Resolved Profile instance.

    Raises:
        HTTPException: 404 if not found, 400 if not GitHub tracker.
    """
    resolved = await profile_repo.get_profile(profile_name)
    if resolved is None:
        raise HTTPException(status_code=404, detail=f"Profile '{profile_name}' not found")

    if resolved.tracker != TrackerType.GITHUB:
        raise HTTPException(
            status_code=400,
            detail=f"Profile '{profile_name}' uses tracker '{resolved.tracker}', not GitHub",
        )
    return resolved


async def _get_repo_name(repo_root: str) -> str:
    """Get repository name in 'owner/repo' format via gh CLI.

    Args:
        repo_root: Path to the repository root.

    Returns:
        Repository name in 'owner/repo' format.

    Raises:
        HTTPException: 500 if gh CLI fails.
    """
    proc = await asyncio.create_subprocess_exec(
        "gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=repo_root,
    )
    stdout_bytes, stderr_bytes = await proc.communicate()
    if proc.returncode != 0:
        logger.error("gh repo view failed", stderr=stderr_bytes.decode(), repo_root=repo_root)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to resolve repository name: {stderr_bytes.decode().strip()}",
        )
    return stdout_bytes.decode().strip()


# ---------------------------------------------------------------------------
# PR endpoints
# ---------------------------------------------------------------------------


@router.get("/prs/config", response_model=PRAutoFixStatusResponse)
async def get_pr_autofix_config(
    profile: str = Query(..., description="Profile name"),
    profile_repo: ProfileRepository = Depends(get_profile_repository),
) -> PRAutoFixStatusResponse:
    """Get PR auto-fix configuration status for a profile.

    Args:
        profile: Profile name to check.
        profile_repo: Profile repository dependency.

    Returns:
        PRAutoFixStatusResponse with enabled flag and config (if set).
    """
    resolved = await _resolve_github_profile(profile, profile_repo)
    return PRAutoFixStatusResponse(
        enabled=resolved.pr_autofix is not None,
        config=resolved.pr_autofix,
    )


@router.get("/prs/{number}/comments", response_model=PRCommentsResponse)
async def get_pr_comments(
    number: int,
    profile: str = Query(..., description="Profile name"),
    profile_repo: ProfileRepository = Depends(get_profile_repository),
) -> PRCommentsResponse:
    """Get unresolved review comments for a PR.

    Args:
        number: PR number.
        profile: Profile name to resolve repo context.
        profile_repo: Profile repository dependency.

    Returns:
        PRCommentsResponse with list of unresolved review comments.
    """
    resolved = await _resolve_github_profile(profile, profile_repo)
    service = GitHubPRService(resolved.repo_root)
    comments = await service.fetch_review_comments(number)
    return PRCommentsResponse(comments=comments)


@router.get("/prs", response_model=PRListResponse)
async def list_prs(
    profile: str = Query(..., description="Profile name"),
    profile_repo: ProfileRepository = Depends(get_profile_repository),
) -> PRListResponse:
    """List open PRs for a profile's repository.

    Args:
        profile: Profile name to resolve repo context.
        profile_repo: Profile repository dependency.

    Returns:
        PRListResponse with list of open PRs.
    """
    resolved = await _resolve_github_profile(profile, profile_repo)
    service = GitHubPRService(resolved.repo_root)
    prs = await service.list_open_prs()
    return PRListResponse(prs=prs)


@router.post("/prs/{number}/auto-fix", status_code=202)
async def trigger_pr_autofix(
    request: Request,
    number: int,
    profile: str = Query(..., description="Profile name"),
    body: TriggerPRAutoFixRequest | None = None,
    profile_repo: ProfileRepository = Depends(get_profile_repository),
    workflow_repo: WorkflowRepository = Depends(get_repository),
) -> JSONResponse:
    """Trigger a PR auto-fix cycle.

    Fetches PR metadata (head_branch) then spawns an async fix cycle via
    the PRAutoFixOrchestrator. Returns 202 immediately with a workflow_id.

    Args:
        request: Starlette request (for app.state.event_bus access).
        number: PR number to fix.
        profile: Profile name to resolve repo context.
        body: Optional request body with aggressiveness override.
        profile_repo: Profile repository dependency.

    Returns:
        202 JSONResponse with workflow_id and message.

    Raises:
        HTTPException: 400 if pr_autofix not configured, 404 if profile not found.
    """
    resolved = await _resolve_github_profile(profile, profile_repo)

    if resolved.pr_autofix is None:
        raise HTTPException(
            status_code=400,
            detail=f"Profile '{profile}' has pr_autofix=None. Enable PR auto-fix first.",
        )

    service = GitHubPRService(resolved.repo_root)
    pr_summary = await service.get_pr_summary(number)

    repo = await _get_repo_name(resolved.repo_root)

    # Determine config override
    effective_config: PRAutoFixConfig | None = None
    if body and body.aggressiveness:
        effective_config = resolved.pr_autofix.model_copy(
            update={"aggressiveness": AggressivenessLevel[body.aggressiveness.upper()]},
        )

    orchestrator = PRAutoFixOrchestrator(
        event_bus=request.app.state.event_bus,
        github_pr_service=service,
        workflow_repo=workflow_repo,
    )
    workflow_id = orchestrator._get_workflow_id(number)

    asyncio.create_task(
        orchestrator.trigger_fix_cycle(
            pr_number=number,
            repo=repo,
            profile=resolved,
            head_branch=pr_summary.head_branch,
            config=effective_config,
        )
    )

    return JSONResponse(
        status_code=202,
        content=TriggerPRAutoFixResponse(
            workflow_id=str(workflow_id),
            message=f"Auto-fix cycle triggered for PR #{number}",
        ).model_dump(),
    )
