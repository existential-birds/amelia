/**
 * GitHub issue types for the Develop page combobox.
 */

/** Label on a GitHub issue. */
export interface GitHubIssueLabel {
  name: string;
  color: string;
}

/** Summary of a GitHub issue for the issue picker. */
export interface GitHubIssueSummary {
  number: number;
  title: string;
  body: string;
  labels: GitHubIssueLabel[];
  assignee: string | null;
  created_at: string;
  state: string;
}

/** Response from GET /api/github/issues. */
export interface GitHubIssuesResponse {
  issues: GitHubIssueSummary[];
}
