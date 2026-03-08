"""GitHub integration endpoints."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger
from pydantic import BaseModel

from amelia.core.types import TrackerType
from amelia.server.database import ProfileRepository
from amelia.server.dependencies import get_profile_repository


router = APIRouter(prefix="/github", tags=["github"])

_GH_ISSUE_FIELDS = "number,title,labels,assignees,createdAt,state"
_GH_ISSUE_LIMIT = "50"


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
