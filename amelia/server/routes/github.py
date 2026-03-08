"""GitHub integration endpoints."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from loguru import logger
from pydantic import BaseModel

from amelia.core.types import Profile, TrackerType
from amelia.server.database import ProfileRepository
from amelia.server.dependencies import get_profile_repository


router = APIRouter(prefix="/github", tags=["github"])


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


async def _get_profile(
    profile_name: str,
    profile_repo: ProfileRepository | None = None,
) -> Profile | None:
    """Fetch a profile by name from the repository."""
    if profile_repo is None:
        profile_repo = get_profile_repository()
    return await profile_repo.get_profile(profile_name)


@router.get("/issues", response_model=GitHubIssuesResponse)
async def list_github_issues(
    profile: str = Query(..., description="Profile name to resolve repo context"),
    search: str | None = Query(None, description="Search query for filtering issues"),
) -> GitHubIssuesResponse:
    """List open GitHub issues for a profile's repository.

    Args:
        profile: Profile name used to resolve repo_root and validate tracker type.
        search: Optional search query passed to gh issue list --search.

    Returns:
        GitHubIssuesResponse with up to 50 open issues.

    Raises:
        HTTPException: 400 if profile doesn't use github tracker,
            404 if profile not found, 500 if gh CLI fails.
    """
    resolved = await _get_profile(profile)
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
        "number,title,labels,assignees,createdAt,state",
        "--limit",
        "50",
        "--state",
        "open",
    ]
    if search:
        cmd.extend(["--search", search])

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
        cwd=resolved.repo_root,
    )

    if result.returncode != 0:
        logger.error("gh issue list failed", stderr=result.stderr, profile=profile)
        raise HTTPException(
            status_code=500,
            detail=f"GitHub CLI failed: {result.stderr.strip()}",
        )

    try:
        raw_issues = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        logger.error("Failed to parse gh output", error=str(e), profile=profile)
        raise HTTPException(
            status_code=500,
            detail="Failed to parse GitHub CLI output",
        ) from e

    issues = []
    for item in raw_issues:
        assignees = item.get("assignees") or []
        issues.append(
            GitHubIssueSummary(
                number=item["number"],
                title=item["title"],
                labels=[
                    GitHubIssueLabel(name=label["name"], color=label.get("color", ""))
                    for label in (item.get("labels") or [])
                ],
                assignee=assignees[0]["login"] if assignees else None,
                created_at=item["createdAt"],
                state=item["state"],
            )
        )

    return GitHubIssuesResponse(issues=issues)
