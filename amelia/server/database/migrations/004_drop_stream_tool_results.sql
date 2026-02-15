-- Drop the stream_tool_results column from server_settings
-- This setting is no longer needed; trace events are always broadcast via WebSocket.
-- The Activity Log filters them client-side.
ALTER TABLE server_settings DROP COLUMN IF EXISTS stream_tool_results;
