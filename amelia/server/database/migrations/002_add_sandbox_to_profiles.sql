-- Add sandbox configuration column to profiles table
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS sandbox JSONB NOT NULL DEFAULT '{}';
