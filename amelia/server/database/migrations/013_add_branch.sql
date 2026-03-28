-- Add branch column to workflows table.
-- Stores the git branch name created or used by the workflow.
ALTER TABLE workflows ADD COLUMN IF NOT EXISTS branch TEXT DEFAULT NULL;
