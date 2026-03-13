-- Add PR auto-fix configuration column to profiles table.
-- Stores PRAutoFixConfig as JSONB (NULL means feature disabled).
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS pr_autofix JSONB DEFAULT NULL;

-- Add PR polling toggle to server settings.
ALTER TABLE server_settings ADD COLUMN IF NOT EXISTS pr_polling_enabled BOOLEAN NOT NULL DEFAULT FALSE;
