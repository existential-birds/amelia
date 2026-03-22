-- Backfill fixes_skipped column if migration 009 was applied before it was added
ALTER TABLE pr_autofix_runs ADD COLUMN IF NOT EXISTS fixes_skipped INTEGER NOT NULL DEFAULT 0;
