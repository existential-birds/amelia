/**
 * File listing, file read, and path validation API types.
 */

/**
 * A single file entry returned by the file listing API.
 */
export interface FileEntry {
  /** Filename without path. */
  name: string;

  /** Path relative to the listed directory. */
  relative_path: string;

  /** File size in bytes. */
  size_bytes: number;

  /** ISO 8601 timestamp of last modification. */
  modified_at: string;
}

/**
 * Response from GET /api/files/list endpoint.
 */
export interface FileListResponse {
  /** Array of matching file entries. */
  files: FileEntry[];

  /** The directory that was listed. */
  directory: string;
}

/**
 * Request payload for reading a file.
 * Used by POST /api/files/read endpoint.
 */
export interface FileReadRequest {
  /** Absolute path to the file to read. */
  path: string;
}

/**
 * Response from POST /api/files/read endpoint.
 * Returns file content for design document import.
 */
export interface FileReadResponse {
  /** File content as text. */
  content: string;

  /** Filename without path. */
  filename: string;
}

/**
 * Request payload for validating a worktree path.
 * Used by POST /api/paths/validate endpoint.
 */
export interface PathValidationRequest {
  /** Absolute path to validate. */
  path: string;
}

/**
 * Response from POST /api/paths/validate endpoint.
 * Provides detailed information about a filesystem path.
 */
export interface PathValidationResponse {
  /** Whether the path exists on disk. */
  exists: boolean;

  /** Whether the path is a git repository. */
  is_git_repo: boolean;

  /** Current branch name if git repo. */
  branch?: string;

  /** Repository name (directory name). */
  repo_name?: string;

  /** Whether there are uncommitted changes. */
  has_changes?: boolean;

  /** Human-readable status message. */
  message: string;
}
