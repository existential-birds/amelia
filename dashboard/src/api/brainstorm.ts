import type {
  BrainstormingSession,
  CreateSessionResponse,
  SessionWithHistory,
  SessionStatus,
} from "@/types/api";

const API_BASE_URL = "/api/brainstorm";
const DEFAULT_TIMEOUT_MS = 30000;

function createTimeoutSignal(timeoutMs: number = DEFAULT_TIMEOUT_MS): AbortSignal {
  return AbortSignal.timeout(timeoutMs);
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }
  return response.json();
}

interface ListSessionsFilters {
  profileId?: string;
  status?: SessionStatus;
  limit?: number;
}

export const brainstormApi = {
  async listSessions(
    filters?: ListSessionsFilters
  ): Promise<BrainstormingSession[]> {
    const params = new URLSearchParams();
    if (filters?.profileId) params.set("profile_id", filters.profileId);
    if (filters?.status) params.set("status", filters.status);
    if (filters?.limit) params.set("limit", String(filters.limit));

    const url = `${API_BASE_URL}/sessions${params.toString() ? `?${params}` : ""}`;
    const response = await fetch(url, {
      method: "GET",
      headers: { "Content-Type": "application/json" },
      signal: createTimeoutSignal(DEFAULT_TIMEOUT_MS),
    });
    return handleResponse<BrainstormingSession[]>(response);
  },

  async createSession(
    profileId: string,
    topic?: string
  ): Promise<CreateSessionResponse> {
    const response = await fetch(`${API_BASE_URL}/sessions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ profile_id: profileId, topic }),
      signal: createTimeoutSignal(DEFAULT_TIMEOUT_MS),
    });
    return handleResponse<CreateSessionResponse>(response);
  },

  async getSession(sessionId: string): Promise<SessionWithHistory> {
    const response = await fetch(`${API_BASE_URL}/sessions/${sessionId}`, {
      method: "GET",
      headers: { "Content-Type": "application/json" },
      signal: createTimeoutSignal(DEFAULT_TIMEOUT_MS),
    });
    return handleResponse<SessionWithHistory>(response);
  },

  async sendMessage(
    sessionId: string,
    content: string
  ): Promise<{ message_id: string }> {
    const response = await fetch(
      `${API_BASE_URL}/sessions/${sessionId}/message`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content }),
        signal: createTimeoutSignal(DEFAULT_TIMEOUT_MS),
      }
    );
    return handleResponse<{ message_id: string }>(response);
  },

  async deleteSession(sessionId: string): Promise<void> {
    const response = await fetch(`${API_BASE_URL}/sessions/${sessionId}`, {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      signal: createTimeoutSignal(DEFAULT_TIMEOUT_MS),
    });
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }
  },

  async handoff(
    sessionId: string,
    artifactPath: string,
    issueTitle?: string
  ): Promise<{ workflow_id: string; status: string }> {
    const response = await fetch(
      `${API_BASE_URL}/sessions/${sessionId}/handoff`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          artifact_path: artifactPath,
          issue_title: issueTitle,
        }),
        signal: createTimeoutSignal(DEFAULT_TIMEOUT_MS),
      }
    );
    return handleResponse<{ workflow_id: string; status: string }>(response);
  },

  async primeSession(sessionId: string): Promise<{ message_id: string }> {
    const response = await fetch(
      `${API_BASE_URL}/sessions/${sessionId}/prime`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: createTimeoutSignal(DEFAULT_TIMEOUT_MS),
      }
    );
    return handleResponse<{ message_id: string }>(response);
  },
};
