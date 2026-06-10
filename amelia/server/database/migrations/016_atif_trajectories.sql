-- ATIF trajectory logging, part 1: thin trajectory index on workflows.
-- Written once at workflow finalize; the trajectory file is the source of truth.
-- The workflow_log / token_usage DROPs land in a later migration step once all
-- consumers are served from trajectory files.
ALTER TABLE workflows
    ADD COLUMN trajectory_path TEXT,
    ADD COLUMN total_cost_usd DOUBLE PRECISION,
    ADD COLUMN total_tokens BIGINT,
    ADD COLUMN total_duration_ms BIGINT;
