-- ATIF trajectory logging: thin trajectory index on workflows.
-- Written once at workflow finalize; the trajectory file is the source of truth.
ALTER TABLE workflows
    ADD COLUMN trajectory_path TEXT,
    ADD COLUMN total_cost_usd DOUBLE PRECISION,
    ADD COLUMN total_tokens BIGINT,
    ADD COLUMN total_duration_ms BIGINT;

-- Trajectory files are the only run history — drop the dead stores.
DROP TABLE workflow_log;
DROP TABLE token_usage;
