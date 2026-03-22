-- Make parent foreign keys mandatory in PR auto-fix metrics tables.
-- Backfill any NULL values before adding constraints.

-- Backfill pr_autofix_runs: remove orphans with NULL workflow_id
DELETE FROM pr_autofix_classifications
WHERE run_id IN (SELECT id FROM pr_autofix_runs WHERE workflow_id IS NULL);

DELETE FROM pr_autofix_runs WHERE workflow_id IS NULL;

ALTER TABLE pr_autofix_runs
    ALTER COLUMN workflow_id SET NOT NULL;

-- Backfill pr_autofix_classifications: remove orphans with NULL run_id
DELETE FROM pr_autofix_classifications WHERE run_id IS NULL;

ALTER TABLE pr_autofix_classifications
    ALTER COLUMN run_id SET NOT NULL;
