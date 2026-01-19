import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import SpecBuilderPage from "../SpecBuilderPage";
import { useBrainstormStore } from "@/store/brainstormStore";
import { brainstormApi } from "@/api/brainstorm";

vi.mock("@/api/brainstorm");
vi.mock("@/api/client", () => ({
  api: {
    getConfig: vi.fn().mockResolvedValue({ working_dir: "", max_concurrent: 5, active_profile: "test" }),
  },
}));

function renderPage() {
  return render(
    <MemoryRouter>
      <SpecBuilderPage />
    </MemoryRouter>
  );
}

describe("SpecBuilderPage", () => {
  beforeEach(() => {
    useBrainstormStore.setState({
      sessions: [],
      activeSessionId: null,
      messages: [],
      artifacts: [],
      isStreaming: false,
      drawerOpen: false,
      streamingMessageId: null,
    });
    vi.clearAllMocks();
    vi.mocked(brainstormApi.listSessions).mockResolvedValue([]);
  });

  it("renders page header", async () => {
    renderPage();

    expect(screen.getByText("Spec Builder")).toBeInTheDocument();
  });

  it("shows empty state when no active session", async () => {
    renderPage();

    await waitFor(() => {
      expect(
        screen.getByText(/start a brainstorming session/i)
      ).toBeInTheDocument();
    });
  });

  it("loads sessions on mount", async () => {
    renderPage();

    await waitFor(() => {
      expect(brainstormApi.listSessions).toHaveBeenCalled();
    });
  });

  it("shows input area", () => {
    renderPage();

    expect(
      screen.getByPlaceholderText(/what would you like to design/i)
    ).toBeInTheDocument();
  });

  it("creates session on first message", async () => {
    const mockSession = {
      id: "s1",
      profile_id: "test",
      driver_session_id: null,
      status: "active" as const,
      topic: "Test",
      created_at: "2026-01-18T00:00:00Z",
      updated_at: "2026-01-18T00:00:00Z",
    };
    vi.mocked(brainstormApi.createSession).mockResolvedValue(mockSession);
    vi.mocked(brainstormApi.sendMessage).mockResolvedValue({ message_id: "m1" });

    renderPage();

    const input = screen.getByPlaceholderText(/what would you like to design/i);
    await userEvent.type(input, "Design a caching layer{enter}");

    await waitFor(() => {
      expect(brainstormApi.createSession).toHaveBeenCalledWith(
        "test",
        "Design a caching layer"
      );
    });
  });

  it("opens drawer when hamburger is clicked", async () => {
    renderPage();

    await userEvent.click(screen.getByRole("button", { name: /open sessions/i }));

    expect(useBrainstormStore.getState().drawerOpen).toBe(true);
  });
});
