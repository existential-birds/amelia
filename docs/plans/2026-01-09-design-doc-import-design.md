# Design Document Import Design

## Problem

Users cannot use design documents as workflow inputs. The Quick Shot modal only supports manual entry of issue ID, title, and description. There's no way to:
- Import a design doc and have fields auto-populated
- Pre-fill the worktree path from server configuration
- Quickly start workflows from existing planning documents

## Solution

Add design document import to the Quick Shot modal with drag-drop and manual path input. Add server `--working-dir` flag to pre-fill worktree path and scope file access.

## User Flow

```
┌─────────────────────────────────────────────────┐
│  Quick Shot                                  ✕  │
├─────────────────────────────────────────────────┤
│  ┌───────────────────────────────────────────┐  │
│  │  Drop design doc here                     │  │
│  │     or                                    │  │
│  │  [path input_______________] [Import]     │  │
│  └───────────────────────────────────────────┘  │
│                                                 │
│  Task ID:        [design-20260109-143052    ]   │
│  Worktree Path:  [/Users/ka/github/amelia   ]   │ ← pre-filled
│  Profile:        [default                   ]   │
│  Task Title:     [Queue Workflows           ]   │ ← from H1
│  Description:    [Full markdown content...  ]   │ ← full doc
│                                                 │
│         [Cancel]  [Queue]  [Plan & Queue]  [Start] │
└─────────────────────────────────────────────────┘
```

1. User drags `.md` file OR enters path and clicks Import
2. System reads file content
3. Auto-populates: issue_id (`design-{timestamp}`), title (first H1 minus "Design"), description (full content)
4. Worktree path pre-filled from server's `working_dir` config
5. User can edit any field before submitting

## Title Extraction

Parse first H1 heading, strip "Design" suffix:

| Input | Extracted Title |
|-------|-----------------|
| `# Queue Workflows Design` | Queue Workflows |
| `# API Authentication` | API Authentication |
| `# Foo Design Bar` | Foo Design Bar |

Fallback if no H1: use filename without extension and date prefix.

## Issue ID Generation

Auto-generate timestamp-based ID:

```
design-{YYYYMMDDHHmmss}
```

Example: `design-20260109143052`

## API Changes

### New `GET /api/config`

Returns server configuration for dashboard.

**Response:**
```json
{
  "working_dir": "/Users/ka/github/amelia",
  "max_concurrent": 5
}
```

Returns `working_dir: null` if not set.

### New `POST /api/files/read`

Reads file content for manual path import.

**Request:**
```json
{
  "path": "/path/to/design-doc.md"
}
```

**Response:**
```json
{
  "content": "# Queue Workflows Design\n\n## Problem\n...",
  "filename": "2026-01-09-queue-workflows-design.md"
}
```

**Errors:**
- `404` - File not found
- `400` - Path outside allowed directories or invalid

**Security:**
- Path must be absolute
- If `working_dir` set, only allow paths within that subtree
- If `working_dir` not set, allow any readable path

## CLI Changes

### Modify `amelia server`

Add `--working-dir` option:

```bash
amelia server --working-dir /path/to/repo

# or via environment variable
AMELIA_WORKING_DIR=/path/to/repo amelia server
```

**Dual purpose:**
1. Pre-fills worktree path in Quick Shot modal
2. Scopes `POST /api/files/read` to this directory subtree

Default: `None` (no pre-fill, no path restriction)

## Frontend Changes

### QuickShotModal.tsx

Add import area at top of form using shadcn/ui components:
- `Card` with dashed border for drop zone
- `Input` for path field
- `Button` for Import action

On mount, fetch `/api/config` to get `working_dir` for pre-filling worktree path.

On import:
1. Read file (drag-drop via File API, manual path via `/api/files/read`)
2. Extract title from first H1, strip "Design" suffix
3. Generate issue ID (`design-{timestamp}`)
4. Populate form fields

### New utilities (lib/design-doc.ts)

```typescript
function extractTitle(markdown: string): string {
  const match = markdown.match(/^#\s+(.+?)(?:\s+Design)?$/m);
  return match ? match[1].trim() : "Untitled";
}

function generateDesignId(): string {
  const now = new Date();
  const ts = now.toISOString().replace(/[-:T]/g, '').slice(0, 14);
  return `design-${ts}`;
}
```

### API client additions

```typescript
getConfig(): Promise<{ working_dir: string | null; max_concurrent: number }>

readFile(path: string): Promise<{ content: string; filename: string }>
```

## Error Handling

### Drag-drop errors
- Non-markdown file → Toast: "Only .md files supported"
- File read fails → Toast: "Failed to read file"

### Path input errors
- File not found → Toast: "File not found at path"
- Path outside allowed directories → Toast: "Path not accessible"
- Empty content → Toast: "File is empty"

### Title extraction fallback
- No H1 found → Use filename without extension and date prefix
  - `2026-01-09-queue-workflows-design.md` → "queue-workflows-design"

### Form behavior
- All fields editable after import
- Re-importing overwrites issue_id, title, description

## Implementation Files

### Backend

| File | Change |
|------|--------|
| `amelia/server/config.py` | Add `working_dir: str \| None` field |
| `amelia/server/cli.py` | Add `--working-dir` option |
| `amelia/server/routes/config.py` | New - `GET /api/config` |
| `amelia/server/routes/files.py` | New - `POST /api/files/read` |
| `amelia/server/main.py` | Register new routes |

### Frontend

| File | Change |
|------|--------|
| `dashboard/src/api/client.ts` | Add `getConfig()`, `readFile()` |
| `dashboard/src/types/index.ts` | Add config/file types |
| `dashboard/src/components/QuickShotModal.tsx` | Add import area, fetch config |
| `dashboard/src/lib/design-doc.ts` | New - title extraction, ID generation |
