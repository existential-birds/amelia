# Develop Page — Create Workflows from GitHub Issues

## Overview

Replace the QuickShotModal with a full "Develop" page at `/develop`. Add a GitHub issue combobox that lets users select an open issue to pre-fill the workflow creation form. The page becomes a top-level sidebar nav item.

## Backend

### New endpoint: `GET /api/github/issues`

New route file: `amelia/server/routes/github.py`, mounted at `/api/github`.

**Query parameters**:
- `profile` (required) — profile name, used to resolve `repo_root` and validate tracker type
- `search` (optional) — passed to `gh issue list --search` for server-side filtering

**Behavior**:
- Returns up to 50 open issues
- Uses `gh issue list --json number,title,labels,assignees,createdAt,state --limit 50` with profile's `repo_root` as `cwd`
- Returns 400 if the profile doesn't use the `github` tracker
- Returns 500 if `gh` CLI fails

**Response models** (in `amelia/server/models/requests.py` or a new `github.py` models file):

```python
class GitHubIssueLabel(BaseModel):
    name: str
    color: str  # hex without #

class GitHubIssueSummary(BaseModel):
    number: int
    title: str
    labels: list[GitHubIssueLabel]
    assignee: str | None  # login username
    created_at: datetime
    state: str

class GitHubIssuesResponse(BaseModel):
    issues: list[GitHubIssueSummary]
```

## Frontend

### New route: `/develop` → `DevelopPage`

Added to `dashboard/src/router.tsx` as a lazy-loaded route.

### Page layout

```
DevelopPage
├── ProfileSelect (existing component)
├── GitHubIssueCombobox (new) — shown when profile uses github tracker
├── Issue ID field (manual fallback, always visible)
├── WorktreePathField (existing component)
├── Task Title
├── Task Description
├── External Plan section (collapsible, existing PlanImportSection)
└── Submit buttons
```

### GitHubIssueCombobox (new component)

- Uses shadcn/ui `Popover` + `Command` (both already installed)
- Fetches `GET /api/github/issues?profile={name}` when a GitHub profile is selected
- `CommandInput` for search — debounced 300ms, calls endpoint with `&search={query}`
- Each `CommandItem` displays:
  - `#123` issue number (muted)
  - Issue title (primary text)
  - Label badges (colored)
  - Assignee username (right-aligned, muted)
  - Relative time e.g. "3d ago" (right-aligned, muted)
- Loading state: skeleton items
- Empty state: "No issues found"
- On select: pre-fills `issue_id`, `task_title`, `task_description` — fields remain editable

### Sidebar changes

- Replace "Quick Shot" (modal trigger) with "Develop" (`NavLink` to `/develop`)
- Keep `Bolt` icon
- Remove QuickShotModal import, state, and rendering from DashboardSidebar

### Submit button logic

| Button | Visible | Behavior |
|--------|---------|----------|
| Start | Always | Creates and immediately executes workflow |
| Queue | Always | Creates workflow in pending state |
| Plan & Queue | Design doc provided AND no external plan | Runs Architect planning, then queues |

### Form behavior

- Profile field at top (controls combobox visibility and worktree path default)
- Worktree path auto-fills from profile's `repo_root`
- GitHub issue selection pre-fills issue_id, task_title, task_description
- Manual Task ID entry always available as fallback
- Submits to existing `POST /api/workflows` with `CreateWorkflowRequest`

## Removal

### Files to delete

- `dashboard/src/components/QuickShotModal.tsx`
- `dashboard/src/components/__tests__/QuickShotModal.test.tsx`

### Files to modify

| File | Changes |
|------|---------|
| `DashboardSidebar.tsx` | Remove QuickShotModal import, state, useEffect, button JSX, modal rendering. Add "Develop" NavLink |
| `DashboardSidebar.test.tsx` | Remove Quick Shot modal test, add Develop link test |
| `globals.css` | Remove `quick-shot-*` keyframes and `.animate-quick-shot-*` utilities |
| `api/client.ts` | Remove `getWorkflowDefaults()` method. Add `getGitHubIssues(profile, search?)` method |
| `api/__tests__/client.test.ts` | Remove `getWorkflowDefaults` tests. Add `getGitHubIssues` tests |
| `types/index.ts` | Update "Quick Shot" comment. Add `GitHubIssueSummary` and related types |
| `router.tsx` | Add `/develop` route |

### Unchanged

- `WorktreePathField.tsx`, `ProfileSelect.tsx`, `PlanImportSection.tsx` — reused as-is
- `WorkflowEmptyState.tsx` — no QuickShot references
- `CreateWorkflowRequest` / `POST /api/workflows` — unchanged
- All backend Python files — no QuickShot references
