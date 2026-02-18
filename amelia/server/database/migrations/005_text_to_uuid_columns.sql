-- Migration 005: Convert TEXT columns to UUID type
-- Affects: brainstorm_sessions, brainstorm_messages, brainstorm_artifacts,
--          prompt_versions, prompts, workflow_prompt_versions

-- 1. brainstorm tables: drop FKs, alter columns, re-add FKs

ALTER TABLE brainstorm_messages DROP CONSTRAINT IF EXISTS brainstorm_messages_session_id_fkey;
ALTER TABLE brainstorm_artifacts DROP CONSTRAINT IF EXISTS brainstorm_artifacts_session_id_fkey;

ALTER TABLE brainstorm_sessions ALTER COLUMN id TYPE UUID USING id::uuid;
ALTER TABLE brainstorm_messages ALTER COLUMN id TYPE UUID USING id::uuid;
ALTER TABLE brainstorm_messages ALTER COLUMN session_id TYPE UUID USING session_id::uuid;
ALTER TABLE brainstorm_artifacts ALTER COLUMN id TYPE UUID USING id::uuid;
ALTER TABLE brainstorm_artifacts ALTER COLUMN session_id TYPE UUID USING session_id::uuid;

ALTER TABLE brainstorm_messages
    ADD CONSTRAINT brainstorm_messages_session_id_fkey
    FOREIGN KEY (session_id) REFERENCES brainstorm_sessions(id) ON DELETE CASCADE;

ALTER TABLE brainstorm_artifacts
    ADD CONSTRAINT brainstorm_artifacts_session_id_fkey
    FOREIGN KEY (session_id) REFERENCES brainstorm_sessions(id) ON DELETE CASCADE;

-- 2. prompt tables: drop FK, alter columns, re-add FK

ALTER TABLE workflow_prompt_versions DROP CONSTRAINT IF EXISTS workflow_prompt_versions_version_id_fkey;

ALTER TABLE prompt_versions ALTER COLUMN id TYPE UUID USING id::uuid;
ALTER TABLE prompts ALTER COLUMN current_version_id TYPE UUID USING current_version_id::uuid;
ALTER TABLE workflow_prompt_versions ALTER COLUMN version_id TYPE UUID USING version_id::uuid;

ALTER TABLE workflow_prompt_versions
    ADD CONSTRAINT workflow_prompt_versions_version_id_fkey
    FOREIGN KEY (version_id) REFERENCES prompt_versions(id);
