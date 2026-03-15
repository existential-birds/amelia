-- Add base_commit column to workflows table.
-- Stores the git HEAD SHA at workflow start, used as the diff base for reviews.
ALTER TABLE workflows ADD COLUMN IF NOT EXISTS base_commit TEXT DEFAULT NULL;
