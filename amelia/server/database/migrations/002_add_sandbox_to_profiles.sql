-- Add sandbox configuration column to profiles table.
-- Stores SandboxConfig as JSONB with fields: mode ('none'|'container'),
-- image (Docker image name), network_allowlist_enabled, network_allowed_hosts.
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS sandbox JSONB NOT NULL DEFAULT '{}';
