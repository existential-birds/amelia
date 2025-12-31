# Usage Guide

Complete reference for using Amelia in your projects.

## Installation

```bash
# Install amelia as a global tool
uv tool install git+https://github.com/existential-birds/amelia.git

# Set your API key
export OPENROUTER_API_KEY="sk-..."
```

## Project Setup

Create `settings.amelia.yaml` in your project root:

```yaml
active_profile: dev
profiles:
  dev:
    name: dev
    driver: api:openrouter
    model: "anthropic/claude-3.5-sonnet"
    tracker: github
    strategy: single
```

## Configuration

Amelia uses profile-based configuration in `settings.amelia.yaml`. See [Configuration Reference](/guide/configuration) for complete details.

### Profile Parameters

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `name` | Yes | - | Profile identifier (should match the key) |
| `driver` | Yes | - | LLM driver: `api:openrouter`, `api`, `cli:claude`, or `cli` |
| `model` | API only | - | LLM model identifier (required for API drivers) |
| `tracker` | No | `none` | Issue source: `github`, `jira`, `none`, or `noop` |
| `strategy` | No | `single` | Review strategy: `single` or `competitive` |
| `plan_output_dir` | No | `docs/plans` | Directory for generated plans |
| `working_dir` | No | `null` | Working directory for agentic execution |
| `max_review_iterations` | No | `3` | Maximum review-fix loop iterations |
| `retry` | No | see below | Retry configuration for transient failures |

### Retry Configuration

The `retry` parameter accepts these sub-fields:

| Field | Default | Range | Description |
|-------|---------|-------|-------------|
| `max_retries` | `3` | 0-10 | Maximum retry attempts |
| `base_delay` | `1.0` | 0.1-30.0 | Base delay (seconds) for exponential backoff |
| `max_delay` | `60.0` | 1.0-300.0 | Maximum delay cap (seconds) |

### Driver Options

| Driver | Description | Requirements |
|--------|-------------|--------------|
| `api:openrouter` | Direct OpenRouter API calls | `OPENROUTER_API_KEY` env var, `model` field |
| `api` | Alias for `api:openrouter` | Same as above |
| `cli:claude` | Wraps Claude CLI tool | `claude` CLI installed and authenticated |
| `cli` | Alias for `cli:claude` | Same as above |

### Tracker Options

| Tracker | Description | Requirements |
|---------|-------------|--------------|
| `github` | GitHub Issues | `gh` CLI authenticated (`gh auth login`) |
| `jira` | Jira issues | `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN` |
| `none` | No tracker (manual input) | None |
| `noop` | Alias for `none` | None |

### Full Configuration Example

```yaml
active_profile: dev

profiles:
  dev:
    name: dev
    driver: api:openrouter
    model: "anthropic/claude-3.5-sonnet"
    tracker: github
    strategy: single
    plan_output_dir: "docs/plans"
    max_review_iterations: 3
    retry:
      max_retries: 3
      base_delay: 1.0
      max_delay: 60.0

  enterprise:
    name: enterprise
    driver: cli:claude
    tracker: jira
    strategy: competitive
    max_review_iterations: 5
    retry:
      max_retries: 5
      base_delay: 2.0
      max_delay: 120.0
```

## CLI Reference

### Workflow Commands

These commands require the Amelia server to be running (`amelia dev` or `amelia server`).

#### `amelia start <ISSUE_ID>`

Start a new workflow for an issue in the current worktree.

```bash
# Start workflow for GitHub issue #123
amelia start 123

# Start workflow with specific profile
amelia start 123 --profile work
```

Options:
- `--profile, -p` - Profile name from settings.amelia.yaml

The command auto-detects your git worktree and creates a workflow via the API server.

#### `amelia status`

Show status of active workflows.

```bash
# Show workflow in current worktree
amelia status

# Show all workflows across all worktrees
amelia status --all
```

Options:
- `--all, -a` - Show workflows from all worktrees

#### `amelia approve`

Approve the workflow plan in the current worktree.

```bash
amelia approve
```

Use this after reviewing the Architect's generated plan. The workflow will proceed to the Developer phase.

#### `amelia reject <REASON>`

Reject the workflow plan with feedback.

```bash
amelia reject "Please add error handling for the API calls"
```

The Architect will replan based on your feedback.

#### `amelia cancel`

Cancel the active workflow in the current worktree.

```bash
# With confirmation prompt
amelia cancel

# Skip confirmation
amelia cancel --force
```

Options:
- `--force, -f` - Skip confirmation prompt

### Server Commands

#### `amelia dev`

Start the development environment (API server + dashboard).

```bash
# Default: localhost:8420
amelia dev

# Custom port
amelia dev --port 9000

# Server only (no dashboard)
amelia dev --no-dashboard

# Bind to all interfaces (for network access)
amelia dev --bind-all
```

Options:
- `--port, -p` - Server port (default: 8420)
- `--no-dashboard` - Skip starting the dashboard
- `--bind-all` - Bind to 0.0.0.0 (exposes to network)

The dashboard is served from bundled static files at `localhost:8420`. For frontend development with hot module replacement (HMR), run `pnpm dev` in `dashboard/` separately.

#### `amelia server`

Start the API server only (no dashboard dev server).

```bash
# Default: localhost:8420
amelia server

# Custom port and host
amelia server --port 9000 --bind-all

# With auto-reload for development
amelia server --reload
```

Options:
- `--port, -p` - Port to listen on
- `--bind-all` - Bind to all interfaces (0.0.0.0)
- `--reload` - Enable auto-reload for development

### Local Commands (No Server Required)

#### `amelia plan <ISSUE_ID>`

Generate a plan without executing it. Calls the Architect directly without going through the server.

```bash
# Generate plan for issue
amelia plan 123

# With specific profile
amelia plan 123 --profile home
```

Options:
- `--profile, -p` - Profile name from settings.amelia.yaml

Saves the plan to a markdown file in `docs/plans/` for review before execution.

#### `amelia review --local`

Review uncommitted changes in the current repository.

```bash
# Review local changes
amelia review --local

# With specific profile
amelia review --local --profile work
```

Options:
- `--local, -l` - Review local uncommitted changes (required)
- `--profile, -p` - Profile name from settings.amelia.yaml

Runs the Reviewer agent on your `git diff` output.

---

## REST API Reference

Base URL: `http://localhost:8420/api`

API documentation available at: `http://localhost:8420/api/docs`

### Workflows

#### Create Workflow

```bash
POST /api/workflows
```

```bash
curl -X POST http://localhost:8420/api/workflows \
  -H "Content-Type: application/json" \
  -d '{
    "issue_id": "123",
    "worktree_path": "/path/to/your/project",
    "worktree_name": "my-project",
    "profile": "dev"
  }'
```

**Request Body:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `issue_id` | string | Yes | Issue identifier (alphanumeric, dashes, underscores) |
| `worktree_path` | string | Yes | Absolute path to worktree directory |
| `worktree_name` | string | No | Custom worktree display name |
| `profile` | string | No | Profile name from settings |
| `driver` | string | No | Driver override (e.g., `api:openrouter`) |

**Response:** `201 Created`
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "message": "Workflow created for issue 123"
}
```

#### List Workflows

```bash
GET /api/workflows
```

```bash
# List all workflows
curl http://localhost:8420/api/workflows

# Filter by status
curl "http://localhost:8420/api/workflows?status=in_progress"

# Filter by worktree
curl "http://localhost:8420/api/workflows?worktree=/path/to/project"

# Pagination
curl "http://localhost:8420/api/workflows?limit=10&cursor=abc123"
```

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `status` | string | Filter by status: `pending`, `in_progress`, `blocked`, `completed`, `failed`, `cancelled` |
| `worktree` | string | Filter by worktree path |
| `limit` | int | Max results per page (1-100, default: 20) |
| `cursor` | string | Pagination cursor from previous response |

**Response:** `200 OK`
```json
{
  "workflows": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "issue_id": "123",
      "worktree_name": "my-project",
      "status": "in_progress",
      "started_at": "2025-01-15T10:30:00Z",
      "current_stage": "developer"
    }
  ],
  "total": 1,
  "cursor": null,
  "has_more": false
}
```

#### List Active Workflows

```bash
GET /api/workflows/active
```

```bash
# All active workflows
curl http://localhost:8420/api/workflows/active

# Active in specific worktree
curl "http://localhost:8420/api/workflows/active?worktree=/path/to/project"
```

Returns workflows in `pending`, `in_progress`, or `blocked` status.

#### Get Workflow Details

```bash
GET /api/workflows/{workflow_id}
```

```bash
curl http://localhost:8420/api/workflows/550e8400-e29b-41d4-a716-446655440000
```

**Response:** `200 OK`
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "issue_id": "123",
  "worktree_path": "/path/to/project",
  "worktree_name": "my-project",
  "status": "blocked",
  "started_at": "2025-01-15T10:30:00Z",
  "completed_at": null,
  "failure_reason": null,
  "current_stage": "architect",
  "plan": null,
  "token_usage": null,
  "recent_events": []
}
```

#### Approve Workflow

```bash
POST /api/workflows/{workflow_id}/approve
```

```bash
curl -X POST http://localhost:8420/api/workflows/550e8400-e29b-41d4-a716-446655440000/approve
```

Approves a workflow that is blocked waiting for plan approval.

**Response:** `200 OK`
```json
{
  "status": "approved",
  "workflow_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

#### Reject Workflow

```bash
POST /api/workflows/{workflow_id}/reject
```

```bash
curl -X POST http://localhost:8420/api/workflows/550e8400-e29b-41d4-a716-446655440000/reject \
  -H "Content-Type: application/json" \
  -d '{"feedback": "Please add unit tests for the new functions"}'
```

**Request Body:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `feedback` | string | Yes | Rejection reason for the Architect |

**Response:** `200 OK`
```json
{
  "status": "rejected",
  "workflow_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

#### Cancel Workflow

```bash
POST /api/workflows/{workflow_id}/cancel
```

```bash
curl -X POST http://localhost:8420/api/workflows/550e8400-e29b-41d4-a716-446655440000/cancel
```

**Response:** `200 OK`
```json
{
  "status": "cancelled",
  "workflow_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

### Health Checks

#### Liveness Probe

```bash
GET /api/health/live
```

```bash
curl http://localhost:8420/api/health/live
```

**Response:** `200 OK`
```json
{"status": "alive"}
```

#### Readiness Probe

```bash
GET /api/health/ready
```

```bash
curl http://localhost:8420/api/health/ready
```

**Response:** `200 OK`
```json
{"status": "ready"}
```

#### Detailed Health

```bash
GET /api/health
```

```bash
curl http://localhost:8420/api/health
```

**Response:** `200 OK`
```json
{
  "status": "healthy",
  "version": "0.1.0",
  "uptime_seconds": 3600.5,
  "active_workflows": 2,
  "websocket_connections": 1,
  "memory_mb": 128.5,
  "cpu_percent": 2.3,
  "database": {
    "status": "healthy",
    "mode": "wal"
  }
}
```

### WebSocket Events

```
WebSocket /api/ws/events
```

Connect for real-time workflow updates.

```javascript
const ws = new WebSocket('ws://localhost:8420/api/ws/events');

// Subscribe to specific workflow
ws.send(JSON.stringify({ type: 'subscribe', workflow_id: 'uuid' }));

// Subscribe to all workflows
ws.send(JSON.stringify({ type: 'subscribe_all' }));

// Unsubscribe
ws.send(JSON.stringify({ type: 'unsubscribe', workflow_id: 'uuid' }));

// Handle events
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  if (data.type === 'event') {
    console.log('Workflow event:', data.payload);
  } else if (data.type === 'ping') {
    ws.send(JSON.stringify({ type: 'pong' }));
  }
};
```

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `since` | string | Event ID for backfill on reconnect |

**Server Messages:**
- `{"type": "event", "payload": WorkflowEvent}` - Workflow event
- `{"type": "ping"}` - Heartbeat (respond with pong)
- `{"type": "backfill_complete", "count": 15}` - Replay complete
- `{"type": "backfill_expired", "message": "..."}` - Event too old

### Error Responses

All errors follow this format:

```json
{
  "code": "ERROR_CODE",
  "error": "Human-readable message",
  "details": { ... }
}
```

| HTTP Status | Code | Description |
|-------------|------|-------------|
| 400 | `INVALID_WORKTREE` | Worktree path is invalid |
| 400 | `VALIDATION_ERROR` | Request validation failed |
| 404 | `NOT_FOUND` | Workflow not found |
| 409 | `WORKFLOW_CONFLICT` | Worktree already has active workflow |
| 422 | `INVALID_STATE` | Workflow not in expected state |
| 429 | `CONCURRENCY_LIMIT` | Too many concurrent workflows |
| 500 | `INTERNAL_ERROR` | Server error |

---

## Example Workflows

### Basic Issue Implementation

```bash
# 1. Start the server
amelia dev

# 2. In another terminal, navigate to your project
cd /path/to/your/project

# 3. Start a workflow for an issue
amelia start ISSUE-123

# 4. Wait for the Architect to generate a plan
#    The workflow will be blocked, waiting for approval

# 5. Review the plan in the dashboard (http://localhost:8420)
#    Or check status:
amelia status

# 6. Approve or reject the plan
amelia approve
# or
amelia reject "Please break task 3 into smaller steps"

# 7. Monitor progress in the dashboard
#    Developer will execute code changes agentically
#    Reviewer will check changes and provide feedback
```

### Review Local Changes

```bash
# Make some code changes
git diff  # verify you have changes

# Run the reviewer
amelia review --local

# Review output for approval status and comments
```

### Generate Plan Only (Dry Run)

```bash
# Generate plan without executing (no server required)
amelia plan ISSUE-123

# Review the generated markdown file
cat docs/plans/ISSUE-123-plan.md

# If satisfied, start the full workflow
amelia start ISSUE-123
```

### Multiple Worktrees

Use git worktrees to work on multiple issues simultaneously:

```bash
# Create worktrees for different issues
git worktree add ../project-issue-123 -b feature/issue-123
git worktree add ../project-issue-456 -b feature/issue-456

# Start workflows in each
cd ../project-issue-123 && amelia start 123
cd ../project-issue-456 && amelia start 456

# Monitor all workflows
amelia status --all
```

### CI/CD Integration

```bash
# Health check before deployment
curl -f http://localhost:8420/api/health/ready || exit 1

# Create workflow via API
WORKFLOW_ID=$(curl -s -X POST http://localhost:8420/api/workflows \
  -H "Content-Type: application/json" \
  -d '{"issue_id": "'$ISSUE_ID'", "worktree_path": "'$PWD'"}' \
  | jq -r '.id')

# Poll for completion
while true; do
  STATUS=$(curl -s http://localhost:8420/api/workflows/$WORKFLOW_ID | jq -r '.status')
  case $STATUS in
    completed) echo "Success!"; break ;;
    failed|cancelled) echo "Failed!"; exit 1 ;;
    blocked) echo "Waiting for approval..."; sleep 10 ;;
    *) sleep 5 ;;
  esac
done
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENROUTER_API_KEY` | - | OpenRouter API key (required for `api:openrouter` driver) |
| `AMELIA_SETTINGS` | `./settings.amelia.yaml` | Path to settings file |
| `AMELIA_PORT` | `8420` | Server port |
| `AMELIA_HOST` | `127.0.0.1` | Server host |

---

## Troubleshooting

### Server won't start

```
Error: Port 8420 is already in use
```

Another process is using the port. Either:
- Stop the existing process: `lsof -i :8420` then `kill <PID>`
- Use a different port: `amelia dev --port 9000`

### No active workflow

```
Error: No workflow active in /path/to/project
```

Ensure you:
1. Started the server: `amelia dev`
2. Started a workflow: `amelia start ISSUE-123`
3. Are in the correct directory

### Server unreachable

```
Error: Cannot connect to server at http://127.0.0.1:8420
```

Start the server first:
```bash
amelia dev
# or
amelia server
```

### Workflow conflict

```
Error: Workflow already active in /path/to/project
```

Each worktree can only have one active workflow. Either:
- Cancel the existing workflow: `amelia cancel --force`
- Use a different worktree: `git worktree add ../project-new`

See [Troubleshooting](/guide/troubleshooting) for more solutions.
