-- Initial database schema for Amelia server

-- Workflows table with indexed columns for common queries
CREATE TABLE workflows (
    id TEXT PRIMARY KEY,
    issue_id TEXT NOT NULL,
    worktree_path TEXT NOT NULL,
    worktree_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    failure_reason TEXT,
    state_json TEXT NOT NULL
);

-- Indexes for efficient querying
CREATE INDEX idx_workflows_issue_id ON workflows(issue_id);
CREATE INDEX idx_workflows_status ON workflows(status);
CREATE INDEX idx_workflows_worktree ON workflows(worktree_path);
CREATE INDEX idx_workflows_started_at ON workflows(started_at DESC);

-- Unique constraint: one active workflow per worktree
-- Active statuses: pending, in_progress, blocked
CREATE UNIQUE INDEX idx_workflows_active_worktree
    ON workflows(worktree_path)
    WHERE status IN ('pending', 'in_progress', 'blocked');

-- Events table with monotonic sequence for ordering
CREATE TABLE events (
    id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
    sequence INTEGER NOT NULL,
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    agent TEXT NOT NULL,
    event_type TEXT NOT NULL,
    message TEXT NOT NULL,
    data_json TEXT,
    correlation_id TEXT
);

-- Unique constraint ensures no duplicate sequences per workflow
CREATE UNIQUE INDEX idx_events_workflow_sequence ON events(workflow_id, sequence);
CREATE INDEX idx_events_workflow ON events(workflow_id, timestamp);
CREATE INDEX idx_events_type ON events(event_type);

-- Token usage table
CREATE TABLE token_usage (
    id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
    agent TEXT NOT NULL,
    model TEXT NOT NULL DEFAULT 'claude-sonnet-4-20250514',
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    cache_read_tokens INTEGER DEFAULT 0,
    cache_creation_tokens INTEGER DEFAULT 0,
    cost_usd REAL,
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_tokens_workflow ON token_usage(workflow_id);
CREATE INDEX idx_tokens_agent ON token_usage(agent);

-- Health check table (for write capability verification)
CREATE TABLE health_check (
    id TEXT PRIMARY KEY,
    checked_at TIMESTAMP NOT NULL
);
