# Develop Page Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace QuickShotModal with a full `/develop` page that supports creating workflows from GitHub issues via a searchable combobox.

**Architecture:** New backend endpoint (`GET /api/github/issues`) uses `gh` CLI to list issues for a profile's repo. New frontend page with GitHubIssueCombobox (shadcn/ui Popover + Command) conditionally shown when profile uses `github` tracker. QuickShotModal is deleted entirely.

**Tech Stack:** Python/FastAPI (backend), React/TypeScript with shadcn/ui (frontend), `gh` CLI for GitHub API access.

---

### Task 1: Backend — GitHub Issues Endpoint

**Files:**
- Create: `amelia/server/routes/github.py`
- Create: `tests/unit/server/routes/test_github.py`
- Modify: `amelia/server/routes/__init__.py`
- Modify: `amelia/server/main.py`

**Step 1: Write the failing test**

Create `tests/unit/server/routes/test_github.py`:

```python
"""Tests for GitHub issues endpoint."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from amelia.core.types import Profile, TrackerType
from amelia.server.routes.github import router


@pytest.fixture
def app() -> FastAPI:
    application = FastAPI()
    application.include_router(router, prefix="/api")
    return application


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


@pytest.fixture
def github_profile() -> Profile:
    return Profile(name="test", tracker=TrackerType.GITHUB, repo_root="/tmp/repo")


@pytest.fixture
def noop_profile() -> Profile:
    return Profile(name="test", tracker=TrackerType.NOOP, repo_root="/tmp/repo")


@pytest.fixture
def mock_gh_output() -> str:
    import json

    return json.dumps([
        {
            "number": 42,
            "title": "Fix login bug",
            "labels": [{"name": "bug", "color": "d73a4a"}],
            "assignees": [{"login": "alice"}],
            "createdAt": "2026-03-01T10:00:00Z",
            "state": "OPEN",
        },
        {
            "number": 17,
            "title": "Add dark mode",
            "labels": [],
            "assignees": [],
            "createdAt": "2026-02-15T08:00:00Z",
            "state": "OPEN",
        },
    ])


class TestListGitHubIssues:
    def test_returns_issues_for_github_profile(
        self, client: TestClient, github_profile: Profile, mock_gh_output: str
    ) -> None:
        with (
            patch(
                "amelia.server.routes.github._get_profile",
                new_callable=AsyncMock,
                return_value=github_profile,
            ),
            patch("amelia.server.routes.github.subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(
                returncode=0, stdout=mock_gh_output, stderr=""
            )
            response = client.get("/api/github/issues?profile=test")

        assert response.status_code == 200
        data = response.json()
        assert len(data["issues"]) == 2
        assert data["issues"][0]["number"] == 42
        assert data["issues"][0]["title"] == "Fix login bug"
        assert data["issues"][0]["labels"] == [{"name": "bug", "color": "d73a4a"}]
        assert data["issues"][0]["assignee"] == "alice"
        assert data["issues"][1]["assignee"] is None

    def test_returns_400_for_non_github_profile(
        self, client: TestClient, noop_profile: Profile
    ) -> None:
        with patch(
            "amelia.server.routes.github._get_profile",
            new_callable=AsyncMock,
            return_value=noop_profile,
        ):
            response = client.get("/api/github/issues?profile=test")

        assert response.status_code == 400
        assert "github" in response.json()["detail"].lower()

    def test_returns_404_for_unknown_profile(self, client: TestClient) -> None:
        with patch(
            "amelia.server.routes.github._get_profile",
            new_callable=AsyncMock,
            return_value=None,
        ):
            response = client.get("/api/github/issues?profile=nonexistent")

        assert response.status_code == 404

    def test_passes_search_to_gh_cli(
        self, client: TestClient, github_profile: Profile
    ) -> None:
        with (
            patch(
                "amelia.server.routes.github._get_profile",
                new_callable=AsyncMock,
                return_value=github_profile,
            ),
            patch("amelia.server.routes.github.subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(
                returncode=0, stdout="[]", stderr=""
            )
            client.get("/api/github/issues?profile=test&search=login")

        cmd = mock_run.call_args[0][0]
        assert "--search" in cmd
        assert "login" in cmd

    def test_returns_500_on_gh_cli_failure(
        self, client: TestClient, github_profile: Profile
    ) -> None:
        with (
            patch(
                "amelia.server.routes.github._get_profile",
                new_callable=AsyncMock,
                return_value=github_profile,
            ),
            patch("amelia.server.routes.github.subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(
                returncode=1, stdout="", stderr="auth required"
            )
            response = client.get("/api/github/issues?profile=test")

        assert response.status_code == 500

    def test_profile_param_required(self, client: TestClient) -> None:
        response = client.get("/api/github/issues")
        assert response.status_code == 422
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/routes/test_github.py -v`
Expected: FAIL — cannot import `amelia.server.routes.github`

**Step 3: Write the route implementation**

Create `amelia/server/routes/github.py`:

```python
"""GitHub integration endpoints."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
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
    profile_repo: ProfileRepository,
) -> Profile | None:
    """Fetch a profile by name from the repository."""
    return await profile_repo.get_profile(profile_name)


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
    resolved = await _get_profile(profile, profile_repo)
    if resolved is None:
        raise HTTPException(status_code=404, detail=f"Profile '{profile}' not found")

    if resolved.tracker != TrackerType.GITHUB:
        raise HTTPException(
            status_code=400,
            detail=f"Profile '{profile}' uses tracker '{resolved.tracker}', not GitHub",
        )

    cmd = [
        "gh", "issue", "list",
        "--json", "number,title,labels,assignees,createdAt,state",
        "--limit", "50",
        "--state", "open",
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
                    GitHubIssueLabel(name=l["name"], color=l.get("color", ""))
                    for l in (item.get("labels") or [])
                ],
                assignee=assignees[0]["login"] if assignees else None,
                created_at=item["createdAt"],
                state=item["state"],
            )
        )

    return GitHubIssuesResponse(issues=issues)
```

**Step 4: Register the route**

In `amelia/server/routes/__init__.py`, add:

```python
from amelia.server.routes.github import router as github_router
```

And add `"github_router"` to `__all__`.

In `amelia/server/main.py`, add the import and router registration:

```python
# In the imports (around line 89-98):
from amelia.server.routes import (
    config_router,
    files_router,
    github_router,  # ADD THIS
    health_router,
    ...
)

# In create_app() (around line 354):
application.include_router(github_router, prefix="/api")
```

**Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/unit/server/routes/test_github.py -v`
Expected: All 6 tests PASS

**Step 6: Run full backend checks**

Run: `uv run ruff check amelia/server/routes/github.py && uv run mypy amelia/server/routes/github.py`
Expected: No errors

**Step 7: Commit**

```bash
git add amelia/server/routes/github.py tests/unit/server/routes/test_github.py amelia/server/routes/__init__.py amelia/server/main.py
git commit -m "feat: add GET /api/github/issues endpoint for listing repo issues"
```

---

### Task 2: Frontend — TypeScript Types and API Client

**Files:**
- Modify: `dashboard/src/types/index.ts`
- Modify: `dashboard/src/api/client.ts`
- Modify: `dashboard/src/api/__tests__/client.test.ts`

**Step 1: Add TypeScript types**

In `dashboard/src/types/index.ts`, add near the GitHub/issue-related types:

```typescript
// ---------------------------------------------------------------------------
// GitHub Issues (for Develop page combobox)
// ---------------------------------------------------------------------------

/** Label on a GitHub issue. */
export interface GitHubIssueLabel {
  name: string;
  color: string;
}

/** Summary of a GitHub issue for the issue picker. */
export interface GitHubIssueSummary {
  number: number;
  title: string;
  labels: GitHubIssueLabel[];
  assignee: string | null;
  created_at: string;
  state: string;
}

/** Response from GET /api/github/issues. */
export interface GitHubIssuesResponse {
  issues: GitHubIssueSummary[];
}
```

Also update the "Quick Shot" comment on `CreateWorkflowRequest` to just say "Request payload for creating a new workflow."

**Step 2: Add API client method**

In `dashboard/src/api/client.ts`, add after the existing methods (and remove `getWorkflowDefaults`):

```typescript
/**
 * Fetches open GitHub issues for a profile's repository.
 *
 * @param profile - Profile name to resolve repo context.
 * @param search - Optional search query for filtering.
 * @param signal - Optional AbortSignal for cancellation.
 * @returns List of GitHub issue summaries.
 */
async getGitHubIssues(
  profile: string,
  search?: string,
  signal?: AbortSignal,
): Promise<GitHubIssuesResponse> {
  const params = new URLSearchParams({ profile });
  if (search) params.set('search', search);
  const response = await fetchWithTimeout(
    `${API_BASE_URL}/github/issues?${params}`,
    { signal },
  );
  return handleResponse<GitHubIssuesResponse>(response);
},
```

Add `GitHubIssuesResponse` to the imports from `@/types`.

Remove the `getWorkflowDefaults()` method entirely (lines ~527-559).

**Step 3: Write API client test**

In `dashboard/src/api/__tests__/client.test.ts`, remove the `getWorkflowDefaults` describe block and add:

```typescript
describe('getGitHubIssues', () => {
  it('should fetch issues for a profile', async () => {
    const mockResponse: GitHubIssuesResponse = {
      issues: [
        {
          number: 42,
          title: 'Fix login bug',
          labels: [{ name: 'bug', color: 'd73a4a' }],
          assignee: 'alice',
          created_at: '2026-03-01T10:00:00Z',
          state: 'OPEN',
        },
      ],
    };
    mockFetchSuccess(mockResponse);

    const result = await api.getGitHubIssues('my-profile');

    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/github/issues?profile=my-profile'),
      expect.any(Object),
    );
    expect(result.issues).toHaveLength(1);
    expect(result.issues[0].number).toBe(42);
  });

  it('should pass search param when provided', async () => {
    mockFetchSuccess({ issues: [] });

    await api.getGitHubIssues('my-profile', 'login');

    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('search=login'),
      expect.any(Object),
    );
  });

  it('should throw on API error', async () => {
    mockFetchError(400, 'Not a GitHub profile', 'INVALID_TRACKER');

    await expect(api.getGitHubIssues('noop-profile')).rejects.toThrow();
  });
});
```

Add `GitHubIssuesResponse` to the type import at the top.

**Step 4: Run tests**

Run: `cd dashboard && pnpm test:run -- --grep "getGitHubIssues"`
Expected: All 3 tests PASS

**Step 5: Commit**

```bash
git add dashboard/src/types/index.ts dashboard/src/api/client.ts dashboard/src/api/__tests__/client.test.ts
git commit -m "feat: add getGitHubIssues API client method, remove getWorkflowDefaults"
```

---

### Task 3: Frontend — GitHubIssueCombobox Component

**Files:**
- Create: `dashboard/src/components/GitHubIssueCombobox.tsx`
- Create: `dashboard/src/components/__tests__/GitHubIssueCombobox.test.tsx`

**Step 1: Write the test**

Create `dashboard/src/components/__tests__/GitHubIssueCombobox.test.tsx`:

```typescript
/**
 * @fileoverview Tests for GitHubIssueCombobox component.
 */

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';

import { api } from '@/api/client';
import { GitHubIssueCombobox } from '../GitHubIssueCombobox';
import type { GitHubIssueSummary } from '@/types';

vi.mock('@/api/client', () => ({
  api: {
    getGitHubIssues: vi.fn(),
  },
}));

const mockIssues: GitHubIssueSummary[] = [
  {
    number: 42,
    title: 'Fix login bug',
    labels: [{ name: 'bug', color: 'd73a4a' }],
    assignee: 'alice',
    created_at: '2026-03-01T10:00:00Z',
    state: 'OPEN',
  },
  {
    number: 17,
    title: 'Add dark mode',
    labels: [],
    assignee: null,
    created_at: '2026-02-15T08:00:00Z',
    state: 'OPEN',
  },
];

describe('GitHubIssueCombobox', () => {
  const onSelect = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.getGitHubIssues).mockResolvedValue({ issues: mockIssues });
  });

  it('renders trigger button', () => {
    render(<GitHubIssueCombobox profile="test" onSelect={onSelect} />);
    expect(screen.getByRole('button', { name: /select issue/i })).toBeInTheDocument();
  });

  it('fetches and displays issues when opened', async () => {
    const user = userEvent.setup();
    render(<GitHubIssueCombobox profile="test" onSelect={onSelect} />);

    await user.click(screen.getByRole('button', { name: /select issue/i }));

    await waitFor(() => {
      expect(screen.getByText('#42')).toBeInTheDocument();
      expect(screen.getByText('Fix login bug')).toBeInTheDocument();
      expect(screen.getByText('#17')).toBeInTheDocument();
    });
  });

  it('calls onSelect with issue data when item clicked', async () => {
    const user = userEvent.setup();
    render(<GitHubIssueCombobox profile="test" onSelect={onSelect} />);

    await user.click(screen.getByRole('button', { name: /select issue/i }));
    await waitFor(() => expect(screen.getByText('#42')).toBeInTheDocument());

    await user.click(screen.getByText('Fix login bug'));

    expect(onSelect).toHaveBeenCalledWith(mockIssues[0]);
  });

  it('shows empty state when no issues found', async () => {
    vi.mocked(api.getGitHubIssues).mockResolvedValue({ issues: [] });
    const user = userEvent.setup();
    render(<GitHubIssueCombobox profile="test" onSelect={onSelect} />);

    await user.click(screen.getByRole('button', { name: /select issue/i }));

    await waitFor(() => {
      expect(screen.getByText(/no issues found/i)).toBeInTheDocument();
    });
  });

  it('refetches when profile changes', async () => {
    const { rerender } = render(
      <GitHubIssueCombobox profile="first" onSelect={onSelect} />
    );
    expect(api.getGitHubIssues).toHaveBeenCalledWith('first', undefined, expect.any(AbortSignal));

    rerender(<GitHubIssueCombobox profile="second" onSelect={onSelect} />);
    expect(api.getGitHubIssues).toHaveBeenCalledWith('second', undefined, expect.any(AbortSignal));
  });

  it('displays label badges', async () => {
    const user = userEvent.setup();
    render(<GitHubIssueCombobox profile="test" onSelect={onSelect} />);

    await user.click(screen.getByRole('button', { name: /select issue/i }));

    await waitFor(() => {
      expect(screen.getByText('bug')).toBeInTheDocument();
    });
  });
});
```

**Step 2: Run test to verify it fails**

Run: `cd dashboard && pnpm test:run -- --grep "GitHubIssueCombobox"`
Expected: FAIL — cannot find module `../GitHubIssueCombobox`

**Step 3: Implement the component**

Create `dashboard/src/components/GitHubIssueCombobox.tsx`:

```tsx
/**
 * @fileoverview Combobox for selecting GitHub issues from a profile's repository.
 *
 * Uses shadcn/ui Popover + Command for a searchable dropdown.
 * Fetches issues via GET /api/github/issues and supports debounced search.
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import { ChevronsUpDown } from 'lucide-react';

import { api } from '@/api/client';
import type { GitHubIssueSummary } from '@/types';
import { Button } from '@/components/ui/button';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '@/components/ui/command';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';

interface GitHubIssueComboboxProps {
  profile: string;
  onSelect: (issue: GitHubIssueSummary) => void;
}

function formatRelativeTime(dateStr: string): string {
  const now = Date.now();
  const then = new Date(dateStr).getTime();
  const diffMs = now - then;
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffDays === 0) return 'today';
  if (diffDays === 1) return '1d ago';
  if (diffDays < 30) return `${diffDays}d ago`;
  if (diffDays < 365) return `${Math.floor(diffDays / 30)}mo ago`;
  return `${Math.floor(diffDays / 365)}y ago`;
}

export function GitHubIssueCombobox({ profile, onSelect }: GitHubIssueComboboxProps) {
  const [open, setOpen] = useState(false);
  const [issues, setIssues] = useState<GitHubIssueSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState('');
  const debounceRef = useRef<ReturnType<typeof setTimeout>>();
  const abortRef = useRef<AbortController>();

  const fetchIssues = useCallback(
    async (query?: string) => {
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      setLoading(true);
      try {
        const response = await api.getGitHubIssues(
          profile,
          query || undefined,
          controller.signal,
        );
        setIssues(response.issues);
      } catch {
        if (!controller.signal.aborted) {
          setIssues([]);
        }
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      }
    },
    [profile],
  );

  // Fetch on mount and when profile changes
  useEffect(() => {
    fetchIssues();
    return () => abortRef.current?.abort();
  }, [fetchIssues]);

  const handleSearchChange = (value: string) => {
    setSearch(value);
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      fetchIssues(value);
    }, 300);
  };

  const handleSelect = (issue: GitHubIssueSummary) => {
    onSelect(issue);
    setOpen(false);
    setSearch('');
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          role="combobox"
          aria-expanded={open}
          aria-label="Select issue"
          className="w-full justify-between"
        >
          Select GitHub issue...
          <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[--radix-popover-trigger-width] p-0" align="start">
        <Command shouldFilter={false}>
          <CommandInput
            placeholder="Search issues..."
            value={search}
            onValueChange={handleSearchChange}
          />
          <CommandList>
            {loading ? (
              <div className="p-2 space-y-2">
                <Skeleton className="h-8 w-full" />
                <Skeleton className="h-8 w-full" />
                <Skeleton className="h-8 w-full" />
              </div>
            ) : (
              <>
                <CommandEmpty>No issues found</CommandEmpty>
                <CommandGroup>
                  {issues.map((issue) => (
                    <CommandItem
                      key={issue.number}
                      value={String(issue.number)}
                      onSelect={() => handleSelect(issue)}
                      className="flex items-center gap-2"
                    >
                      <span className="text-muted-foreground text-xs font-mono shrink-0">
                        #{issue.number}
                      </span>
                      <span className="truncate">{issue.title}</span>
                      <div className="ml-auto flex items-center gap-2 shrink-0">
                        {issue.labels.map((label) => (
                          <Badge
                            key={label.name}
                            variant="outline"
                            className="text-xs px-1 py-0"
                            style={{
                              borderColor: `#${label.color}`,
                              color: `#${label.color}`,
                            }}
                          >
                            {label.name}
                          </Badge>
                        ))}
                        {issue.assignee && (
                          <span className="text-muted-foreground text-xs">
                            {issue.assignee}
                          </span>
                        )}
                        <span className="text-muted-foreground text-xs">
                          {formatRelativeTime(issue.created_at)}
                        </span>
                      </div>
                    </CommandItem>
                  ))}
                </CommandGroup>
              </>
            )}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
```

**Step 4: Run tests to verify they pass**

Run: `cd dashboard && pnpm test:run -- --grep "GitHubIssueCombobox"`
Expected: All 6 tests PASS

**Step 5: Commit**

```bash
git add dashboard/src/components/GitHubIssueCombobox.tsx dashboard/src/components/__tests__/GitHubIssueCombobox.test.tsx
git commit -m "feat: add GitHubIssueCombobox component with search and metadata"
```

---

### Task 4: Frontend — DevelopPage Component

**Files:**
- Create: `dashboard/src/pages/DevelopPage.tsx`
- Create: `dashboard/src/pages/__tests__/DevelopPage.test.tsx`

**Step 1: Write the test**

Create `dashboard/src/pages/__tests__/DevelopPage.test.tsx`:

```typescript
/**
 * @fileoverview Tests for DevelopPage.
 */

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router';

import { api } from '@/api/client';
import DevelopPage from '../DevelopPage';

// Mock api client
vi.mock('@/api/client', () => ({
  api: {
    getConfig: vi.fn(),
    createWorkflow: vi.fn(),
    validatePath: vi.fn(),
    getGitHubIssues: vi.fn(),
  },
}));

// Mock ProfileSelect to simplify - it fetches its own data
vi.mock('@/components/ProfileSelect', () => ({
  ProfileSelect: ({
    value,
    onChange,
  }: {
    value: string;
    onChange: (v: string, tracker?: string) => void;
  }) => (
    <select
      data-testid="profile-select"
      value={value}
      onChange={(e) => onChange(e.target.value, 'github')}
    >
      <option value="">None</option>
      <option value="test">test</option>
    </select>
  ),
}));

// Mock PlanImportSection
vi.mock('@/components/PlanImportSection', () => ({
  PlanImportSection: () => <div data-testid="plan-import-section" />,
}));

// Mock GitHubIssueCombobox
vi.mock('@/components/GitHubIssueCombobox', () => ({
  GitHubIssueCombobox: ({
    onSelect,
  }: {
    profile: string;
    onSelect: (issue: { number: number; title: string }) => void;
  }) => (
    <button
      data-testid="issue-combobox"
      onClick={() => onSelect({ number: 42, title: 'Fix login bug' })}
    >
      mock combobox
    </button>
  ),
}));

// Mock toast
vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

function renderPage() {
  return render(
    <MemoryRouter>
      <DevelopPage />
    </MemoryRouter>,
  );
}

describe('DevelopPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.getConfig).mockResolvedValue({
      repo_root: '/tmp/repo',
      active_profile: 'test',
      max_concurrent: 3,
      active_profile_info: { driver: 'cli:claude', model: 'opus' },
    });
    vi.mocked(api.validatePath).mockResolvedValue({
      exists: true,
      is_git_repo: true,
      branch: 'main',
      message: 'Valid',
    });
    vi.mocked(api.createWorkflow).mockResolvedValue({
      id: 'wf-1',
      status: 'pending',
      message: 'Created',
    });
  });

  it('renders the page title', async () => {
    renderPage();
    expect(screen.getByText(/develop/i)).toBeInTheDocument();
  });

  it('renders form fields', async () => {
    renderPage();
    expect(screen.getByTestId('profile-select')).toBeInTheDocument();
    expect(screen.getByLabelText(/task id/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/task title/i)).toBeInTheDocument();
  });

  it('shows issue combobox when github profile selected', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.selectOptions(screen.getByTestId('profile-select'), 'test');

    await waitFor(() => {
      expect(screen.getByTestId('issue-combobox')).toBeInTheDocument();
    });
  });

  it('pre-fills form when issue selected', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.selectOptions(screen.getByTestId('profile-select'), 'test');
    await waitFor(() => expect(screen.getByTestId('issue-combobox')).toBeInTheDocument());

    await user.click(screen.getByTestId('issue-combobox'));

    await waitFor(() => {
      expect(screen.getByLabelText(/task id/i)).toHaveValue('42');
      expect(screen.getByLabelText(/task title/i)).toHaveValue('Fix login bug');
    });
  });

  it('renders Start and Queue buttons', () => {
    renderPage();
    expect(screen.getByRole('button', { name: /start/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /queue/i })).toBeInTheDocument();
  });
});
```

**Step 2: Run test to verify it fails**

Run: `cd dashboard && pnpm test:run -- --grep "DevelopPage"`
Expected: FAIL — cannot find module `../DevelopPage`

**Step 3: Implement DevelopPage**

Create `dashboard/src/pages/DevelopPage.tsx`. This migrates the form logic from QuickShotModal into a full page:

- Profile select at top
- GitHubIssueCombobox conditionally shown when profile tracker is `github`
- Task ID, Worktree Path, Title, Description fields
- PlanImportSection (collapsible)
- Design document import zone (drag/drop markdown)
- Submit buttons: Start (always), Queue (always), Plan & Queue (only when design doc present AND no external plan)
- Form validation with react-hook-form + zod (same schema as QuickShotModal)
- Submits to `api.createWorkflow()` with `CreateWorkflowRequest`
- Toast notifications on success/error

The component should:
- Fetch config on mount for defaults (repo_root, active_profile)
- Track the selected profile's tracker type to show/hide combobox
- Pass `onSelect` handler to combobox that calls `form.setValue()` for issue_id, task_title, task_description
- Track `hasDesignDoc` and `hasExternalPlan` state for Plan & Queue visibility

Reference `QuickShotModal.tsx` for the exact form logic, validation schema, submission handlers, and design doc import zone — migrate all of that to page layout.

**Step 4: Run tests to verify they pass**

Run: `cd dashboard && pnpm test:run -- --grep "DevelopPage"`
Expected: All 5 tests PASS

**Step 5: Commit**

```bash
git add dashboard/src/pages/DevelopPage.tsx dashboard/src/pages/__tests__/DevelopPage.test.tsx
git commit -m "feat: add DevelopPage with GitHub issue selection and form"
```

---

### Task 5: Frontend — Router and Sidebar Integration

**Files:**
- Modify: `dashboard/src/router.tsx`
- Modify: `dashboard/src/components/DashboardSidebar.tsx`
- Modify: `dashboard/src/components/DashboardSidebar.test.tsx`

**Step 1: Add route to router.tsx**

In `dashboard/src/router.tsx`, add the `/develop` route alongside the other top-level routes (after `/logs`, before `/prompts`):

```typescript
{
  path: 'develop',
  async lazy() {
    const { default: Component } = await import('@/pages/DevelopPage');
    return { Component };
  },
},
```

**Step 2: Update DashboardSidebar.tsx**

Remove:
- `import { QuickShotModal } from './QuickShotModal';` (line ~42)
- `Bolt` from lucide-react imports (line ~36) — actually keep `Bolt`, it's the icon for "Develop"
- `quickShotOpen` and `quickShotDefaults` state (lines ~142-146)
- `useEffect` fetching workflow defaults (lines ~149-162)
- Quick Shot `<SidebarMenuItem>` button JSX (lines ~230-248) — replace with NavLink
- `<QuickShotModal .../>` at end of component (line ~372)

Add:
- In the TOOLS section, replace the Quick Shot button with a `SidebarNavLink` to `/develop`:

```tsx
<SidebarNavLink to="/develop" icon={Bolt} label="Develop" />
```

Use the same `SidebarNavLink` component pattern used by the other nav items (Active Jobs, Past Runs, etc.).

**Step 3: Update DashboardSidebar.test.tsx**

Remove the test "renders Quick Shot button that opens modal" (lines ~79-89).

Add a new test:

```typescript
it('renders Develop nav link', () => {
  renderSidebar();
  const developLink = screen.getByRole('link', { name: /develop/i });
  expect(developLink).toBeInTheDocument();
  expect(developLink).toHaveAttribute('href', '/develop');
});
```

**Step 4: Run tests**

Run: `cd dashboard && pnpm test:run -- --grep "DashboardSidebar"`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add dashboard/src/router.tsx dashboard/src/components/DashboardSidebar.tsx dashboard/src/components/DashboardSidebar.test.tsx
git commit -m "feat: add /develop route and sidebar nav link, wire up DevelopPage"
```

---

### Task 6: Cleanup — Remove QuickShotModal and Related Code

**Files:**
- Delete: `dashboard/src/components/QuickShotModal.tsx`
- Delete: `dashboard/src/components/__tests__/QuickShotModal.test.tsx`
- Modify: `dashboard/src/styles/globals.css`
- Modify: `dashboard/src/api/client.ts` (if not already done in Task 2)
- Modify: `dashboard/src/api/__tests__/client.test.ts` (if not already done in Task 2)

**Step 1: Delete QuickShotModal files**

```bash
rm dashboard/src/components/QuickShotModal.tsx
rm dashboard/src/components/__tests__/QuickShotModal.test.tsx
```

**Step 2: Remove Quick Shot animations from globals.css**

In `dashboard/src/styles/globals.css`, remove the entire section (~lines 373-423):

- `@keyframes quick-shot-field-reveal { ... }`
- `@keyframes quick-shot-charge-pulse { ... }`
- `@keyframes quick-shot-scan-line { ... }`
- `.animate-quick-shot-field { ... }`
- `.animate-quick-shot-charge { ... }`
- `.animate-quick-shot-scan { ... }`

Including the `/* Quick Shot modal animations */` comment.

**Step 3: Run full frontend test suite**

Run: `cd dashboard && pnpm test:run`
Expected: All tests PASS, no broken imports or references

**Step 4: Run type check and lint**

Run: `cd dashboard && pnpm type-check && pnpm lint:fix`
Expected: No errors

**Step 5: Commit**

```bash
git add -A dashboard/
git commit -m "chore: remove QuickShotModal and related animations/tests"
```

---

### Task 7: Verification — Full Stack Checks

**Step 1: Run full backend test suite**

Run: `uv run pytest`
Expected: All tests PASS

**Step 2: Run backend lint and type checks**

Run: `uv run ruff check amelia tests && uv run mypy amelia`
Expected: No errors

**Step 3: Run full frontend test suite**

Run: `cd dashboard && pnpm test:run`
Expected: All tests PASS

**Step 4: Run frontend build**

Run: `cd dashboard && pnpm build`
Expected: Build succeeds with no errors

**Step 5: Search for any remaining QuickShot references**

Run: `grep -ri "quickshot\|quick.shot\|quick_shot" dashboard/src/ amelia/ --include="*.ts" --include="*.tsx" --include="*.py" --include="*.css"`
Expected: No results (all references removed)

**Step 6: Commit any final fixes if needed**

If any issues were found in steps 1-5, fix them and commit.
