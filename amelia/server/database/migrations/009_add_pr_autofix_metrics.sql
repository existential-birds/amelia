-- Per-run aggregate metrics for PR auto-fix pipeline
CREATE TABLE IF NOT EXISTS pr_autofix_runs (
    id UUID PRIMARY KEY,
    workflow_id UUID REFERENCES workflows(id),
    profile_id TEXT NOT NULL,
    pr_number INTEGER NOT NULL,
    aggressiveness_level TEXT NOT NULL,
    comments_processed INTEGER NOT NULL DEFAULT 0,
    fixes_applied INTEGER NOT NULL DEFAULT 0,
    fixes_failed INTEGER NOT NULL DEFAULT 0,
    fixes_skipped INTEGER NOT NULL DEFAULT 0,
    commits_pushed INTEGER NOT NULL DEFAULT 0,
    threads_resolved INTEGER NOT NULL DEFAULT 0,
    duration_seconds REAL NOT NULL DEFAULT 0.0,
    prompt_hash TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pr_autofix_runs_created_at
    ON pr_autofix_runs(created_at);
CREATE INDEX IF NOT EXISTS idx_pr_autofix_runs_profile
    ON pr_autofix_runs(profile_id);
CREATE INDEX IF NOT EXISTS idx_pr_autofix_runs_aggressiveness
    ON pr_autofix_runs(aggressiveness_level);

-- Per-classification audit log
CREATE TABLE IF NOT EXISTS pr_autofix_classifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID REFERENCES pr_autofix_runs(id),
    comment_id BIGINT NOT NULL,
    body_snippet TEXT NOT NULL,
    category TEXT NOT NULL,
    confidence REAL NOT NULL,
    actionable BOOLEAN NOT NULL,
    aggressiveness_level TEXT NOT NULL,
    prompt_hash TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pr_autofix_classifications_run
    ON pr_autofix_classifications(run_id);
CREATE INDEX IF NOT EXISTS idx_pr_autofix_classifications_created_at
    ON pr_autofix_classifications(created_at);
