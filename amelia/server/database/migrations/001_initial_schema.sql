-- Profiles
CREATE TABLE profiles (
    id TEXT PRIMARY KEY,
    tracker TEXT NOT NULL DEFAULT 'noop',
    working_dir TEXT NOT NULL,
    plan_output_dir TEXT NOT NULL DEFAULT 'docs/plans',
    plan_path_pattern TEXT NOT NULL DEFAULT 'docs/plans/{date}-{issue_key}.md',
    agents JSONB NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX idx_profiles_active ON profiles(is_active) WHERE is_active = TRUE;

-- Workflows
CREATE TABLE workflows (
    id UUID PRIMARY KEY,
    issue_id TEXT NOT NULL,
    worktree_path TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    failure_reason TEXT,
    workflow_type TEXT NOT NULL DEFAULT 'full',
    profile_id TEXT,
    plan_cache JSONB,
    issue_cache JSONB
);
CREATE INDEX idx_workflows_issue_id ON workflows(issue_id);
CREATE INDEX idx_workflows_status ON workflows(status);
CREATE INDEX idx_workflows_worktree ON workflows(worktree_path);
CREATE INDEX idx_workflows_started_at ON workflows(started_at DESC);
CREATE UNIQUE INDEX idx_workflows_active_worktree
    ON workflows(worktree_path) WHERE status IN ('in_progress', 'blocked');

-- Workflow log
CREATE TABLE workflow_log (
    id UUID PRIMARY KEY,
    workflow_id UUID NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
    sequence INTEGER NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    level TEXT NOT NULL CHECK (level IN ('info', 'warning', 'error', 'debug')),
    event_type TEXT NOT NULL,
    agent TEXT,
    message TEXT NOT NULL,
    data JSONB,
    is_error BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (workflow_id, sequence)
);
CREATE INDEX idx_workflow_log_workflow ON workflow_log(workflow_id, sequence);
CREATE INDEX idx_workflow_log_errors ON workflow_log(workflow_id) WHERE is_error = TRUE;

-- Token usage
CREATE TABLE token_usage (
    id UUID PRIMARY KEY,
    workflow_id UUID NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
    agent TEXT NOT NULL,
    model TEXT NOT NULL,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    cache_read_tokens INTEGER DEFAULT 0,
    cache_creation_tokens INTEGER DEFAULT 0,
    cost_usd NUMERIC(10,6) NOT NULL,
    duration_ms INTEGER NOT NULL DEFAULT 0,
    num_turns INTEGER NOT NULL DEFAULT 1,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_token_usage_workflow ON token_usage(workflow_id);
CREATE INDEX idx_token_usage_timestamp ON token_usage(timestamp);

-- Prompts
CREATE TABLE prompts (
    id TEXT PRIMARY KEY,
    agent TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    current_version_id TEXT
);

CREATE TABLE prompt_versions (
    id TEXT PRIMARY KEY,
    prompt_id TEXT NOT NULL REFERENCES prompts(id),
    version_number INTEGER NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    change_note TEXT,
    UNIQUE(prompt_id, version_number)
);

CREATE TABLE workflow_prompt_versions (
    workflow_id UUID NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
    prompt_id TEXT NOT NULL REFERENCES prompts(id),
    version_id TEXT NOT NULL REFERENCES prompt_versions(id),
    PRIMARY KEY (workflow_id, prompt_id)
);

-- Server settings (singleton)
CREATE TABLE server_settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    log_retention_days INTEGER NOT NULL DEFAULT 30,
    checkpoint_retention_days INTEGER NOT NULL DEFAULT 0,
    websocket_idle_timeout_seconds NUMERIC NOT NULL DEFAULT 300.0,
    workflow_start_timeout_seconds NUMERIC NOT NULL DEFAULT 60.0,
    max_concurrent INTEGER NOT NULL DEFAULT 5,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Brainstorm sessions
CREATE TABLE brainstorm_sessions (
    id TEXT PRIMARY KEY,
    profile_id TEXT NOT NULL,
    driver_session_id TEXT,
    driver_type TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    topic TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX idx_brainstorm_sessions_profile ON brainstorm_sessions(profile_id);
CREATE INDEX idx_brainstorm_sessions_status ON brainstorm_sessions(status);

-- Brainstorm messages
CREATE TABLE brainstorm_messages (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES brainstorm_sessions(id) ON DELETE CASCADE,
    sequence INTEGER NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    parts JSONB,
    created_at TIMESTAMPTZ NOT NULL,
    input_tokens INTEGER,
    output_tokens INTEGER,
    cost_usd NUMERIC(10,6),
    is_system BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE(session_id, sequence)
);
CREATE INDEX idx_brainstorm_messages_session ON brainstorm_messages(session_id, sequence);

-- Brainstorm artifacts
CREATE TABLE brainstorm_artifacts (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES brainstorm_sessions(id) ON DELETE CASCADE,
    type TEXT NOT NULL,
    path TEXT NOT NULL,
    title TEXT,
    created_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX idx_brainstorm_artifacts_session ON brainstorm_artifacts(session_id);

-- Prompt indexes
CREATE INDEX idx_prompt_versions_prompt ON prompt_versions(prompt_id);
CREATE INDEX idx_workflow_prompts_workflow ON workflow_prompt_versions(workflow_id);
