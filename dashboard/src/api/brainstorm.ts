import type {
  BrainstormingSession,
  CreateSessionResponse,
  SessionWithHistory,
  SessionStatus,
} from "@/types/api";
import { request } from './utils';

interface ListSessionsFilters {
  profileId?: string;
  status?: SessionStatus;
  limit?: number;
}

export const brainstormApi = {
  async listSessions(
    filters?: ListSessionsFilters
  ): Promise<BrainstormingSession[]> {
    return request<BrainstormingSession[]>("/brainstorm/sessions", {
      params: {
        profile_id: filters?.profileId,
        status: filters?.status,
        limit: filters?.limit,
      },
    });
  },

  async createSession(
    profileId: string,
    topic?: string
  ): Promise<CreateSessionResponse> {
    return request<CreateSessionResponse>("/brainstorm/sessions", {
      method: "POST",
      body: { profile_id: profileId, topic },
    });
  },

  async getSession(sessionId: string): Promise<SessionWithHistory> {
    return request<SessionWithHistory>(
      `/brainstorm/sessions/${encodeURIComponent(sessionId)}`
    );
  },

  async sendMessage(
    sessionId: string,
    content: string
  ): Promise<{ message_id: string }> {
    return request<{ message_id: string }>(
      `/brainstorm/sessions/${encodeURIComponent(sessionId)}/message`,
      { method: "POST", body: { content } }
    );
  },

  async deleteSession(sessionId: string): Promise<void> {
    await request(`/brainstorm/sessions/${encodeURIComponent(sessionId)}`, {
      method: "DELETE",
    });
  },

  async handoff(
    sessionId: string,
    artifactPath: string,
    issueTitle?: string
  ): Promise<{ workflow_id: string; status: string }> {
    return request<{ workflow_id: string; status: string }>(
      `/brainstorm/sessions/${encodeURIComponent(sessionId)}/handoff`,
      {
        method: "POST",
        body: { artifact_path: artifactPath, issue_title: issueTitle },
      }
    );
  },
};
