import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { toast } from "sonner";
import SpecBuilderPage from "../SpecBuilderPage";
import { useBrainstormStore } from "@/store/brainstormStore";
import { brainstormApi } from "@/api/brainstorm";

vi.mock("@/api/brainstorm");
vi.mock("sonner", () => ({
  toast: {
    error: vi.fn(),
  },
}));
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

  it("shows input area when session is active", () => {
    useBrainstormStore.setState({
      activeSessionId: "s1",
      sessions: [{ id: "s1", profile_id: "test", driver_session_id: null, status: "active" as const, topic: "Test", created_at: "2026-01-18T00:00:00Z", updated_at: "2026-01-18T00:00:00Z" }],
      messages: [{ id: "m1", session_id: "s1", sequence: 1, role: "user" as const, content: "Hello", parts: null, created_at: "2026-01-18T00:00:00Z" }],
    });

    renderPage();

    expect(
      screen.getByPlaceholderText(/what would you like to design/i)
    ).toBeInTheDocument();
  });

  it("hides input area when no active session", () => {
    renderPage();

    expect(
      screen.queryByPlaceholderText(/what would you like to design/i)
    ).not.toBeInTheDocument();
  });

  it("sends message in active session", async () => {
    useBrainstormStore.setState({
      activeSessionId: "s1",
      sessions: [{ id: "s1", profile_id: "test", driver_session_id: null, status: "active" as const, topic: "Test", created_at: "2026-01-18T00:00:00Z", updated_at: "2026-01-18T00:00:00Z" }],
      messages: [{ id: "m1", session_id: "s1", sequence: 1, role: "user" as const, content: "Hello", parts: null, created_at: "2026-01-18T00:00:00Z" }],
    });
    vi.mocked(brainstormApi.sendMessage).mockResolvedValue({ message_id: "m2" });

    renderPage();

    const input = screen.getByPlaceholderText(/what would you like to design/i);
    await userEvent.type(input, "Design a caching layer{enter}");

    await waitFor(() => {
      expect(brainstormApi.sendMessage).toHaveBeenCalledWith(
        "s1",
        "Design a caching layer"
      );
    });
  });

  it("creates session when Start Brainstorming is clicked", async () => {
    const mockSession = {
      id: "s1",
      profile_id: "test",
      driver_session_id: null,
      status: "active" as const,
      topic: null,
      created_at: "2026-01-18T00:00:00Z",
      updated_at: "2026-01-18T00:00:00Z",
    };
    const mockProfile = {
      name: "test",
      driver: "cli:claude",
      model: "sonnet",
    };
    vi.mocked(brainstormApi.createSession).mockResolvedValue({
      session: mockSession,
      profile: mockProfile,
    });
    vi.mocked(brainstormApi.primeSession).mockResolvedValue({ message_id: "m1" });

    renderPage();

    // Wait for the button to be present (handles any async rendering)
    const startButton = await screen.findByRole("button", { name: /start brainstorming/i });
    await userEvent.click(startButton);

    await waitFor(() => {
      expect(brainstormApi.createSession).toHaveBeenCalledWith("test");
    });

    await waitFor(() => {
      expect(brainstormApi.primeSession).toHaveBeenCalledWith("s1");
    });
  });

  it("opens drawer when hamburger is clicked", async () => {
    renderPage();

    await userEvent.click(screen.getByRole("button", { name: /open sessions/i }));

    expect(useBrainstormStore.getState().drawerOpen).toBe(true);
  });

  it("shows expandable reasoning when message has reasoning field (streaming)", async () => {
    // When reasoning comes in via WebSocket streaming, it's stored in message.reasoning
    useBrainstormStore.setState({
      activeSessionId: "s1",
      sessions: [{ id: "s1", profile_id: "test", driver_session_id: null, status: "active" as const, topic: "Test", created_at: "2026-01-18T00:00:00Z", updated_at: "2026-01-18T00:00:00Z" }],
      messages: [
        {
          id: "m1",
          session_id: "s1",
          sequence: 1,
          role: "assistant" as const,
          content: "",
          reasoning: "Thinking about the design...",
          parts: null,
          created_at: "2026-01-18T00:00:00Z",
          status: "streaming" as const,
        },
      ],
      isStreaming: true,
    });

    renderPage();

    // Should show the expandable Reasoning component (not just plain Shimmer)
    // The Reasoning component uses a Collapsible with data-slot="collapsible"
    await waitFor(() => {
      const collapsible = document.querySelector('[data-slot="collapsible"]');
      expect(collapsible).toBeInTheDocument();
    });
  });

  it("shows expandable reasoning when message has parts with reasoning type", async () => {
    // After streaming completes, reasoning is stored in message.parts
    useBrainstormStore.setState({
      activeSessionId: "s1",
      sessions: [{ id: "s1", profile_id: "test", driver_session_id: null, status: "active" as const, topic: "Test", created_at: "2026-01-18T00:00:00Z", updated_at: "2026-01-18T00:00:00Z" }],
      messages: [
        {
          id: "m1",
          session_id: "s1",
          sequence: 1,
          role: "assistant" as const,
          content: "Here is my response",
          parts: [{ type: "reasoning" as const, text: "I thought about this carefully" }],
          created_at: "2026-01-18T00:00:00Z",
        },
      ],
      isStreaming: false,
    });

    renderPage();

    // Should show the message content
    await waitFor(() => {
      expect(screen.getByText(/Here is my response/)).toBeInTheDocument();
    });
    // Should have the expandable Reasoning component
    const collapsible = document.querySelector('[data-slot="collapsible"]');
    expect(collapsible).toBeInTheDocument();
  });

  it("shows error toast when session creation fails", async () => {
    vi.mocked(brainstormApi.createSession).mockRejectedValue(new Error("Network error"));

    renderPage();

    const startButton = await screen.findByRole("button", { name: /start brainstorming/i });
    await userEvent.click(startButton);

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith("Failed to start session");
    });
  });

  it("shows error toast when handoff fails", async () => {
    const mockArtifact = {
      id: "a1",
      session_id: "s1",
      type: "design",
      path: "/path/to/design.md",
      title: "Design Doc",
      created_at: "2026-01-18T00:00:00Z",
    };

    useBrainstormStore.setState({
      activeSessionId: "s1",
      sessions: [
        {
          id: "s1",
          profile_id: "test",
          driver_session_id: null,
          status: "active" as const,
          topic: "Test",
          created_at: "2026-01-18T00:00:00Z",
          updated_at: "2026-01-18T00:00:00Z",
        },
      ],
      messages: [
        {
          id: "m1",
          session_id: "s1",
          sequence: 1,
          role: "assistant" as const,
          content: "Response",
          parts: null,
          created_at: "2026-01-18T00:00:00Z",
        },
      ],
      artifacts: [mockArtifact],
    });

    vi.mocked(brainstormApi.handoff).mockRejectedValue(
      new Error("Handoff failed")
    );

    renderPage();

    // Click the handoff button on the artifact card
    const handoffButton = await screen.findByRole("button", {
      name: /hand off to implementation/i,
    });
    await userEvent.click(handoffButton);

    // Fill in the dialog and confirm
    const titleInput = await screen.findByLabelText(/issue title/i);
    await userEvent.clear(titleInput);
    await userEvent.type(titleInput, "Implement design");
    const confirmButton = screen.getByRole("button", {
      name: /create workflow/i,
    });
    await userEvent.click(confirmButton);

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith(
        expect.stringContaining("Handoff failed")
      );
    });
  });

  it("shows error indicator when message has error status", async () => {
    useBrainstormStore.setState({
      activeSessionId: "s1",
      sessions: [{ id: "s1", profile_id: "test", driver_session_id: null, status: "active" as const, topic: "Test", created_at: "2026-01-18T00:00:00Z", updated_at: "2026-01-18T00:00:00Z" }],
      messages: [
        {
          id: "m1",
          session_id: "s1",
          sequence: 1,
          role: "assistant" as const,
          content: "Partial response",
          parts: null,
          created_at: "2026-01-18T00:00:00Z",
          status: "error" as const,
          errorMessage: "Connection lost. Please retry.",
        },
      ],
    });

    renderPage();

    await waitFor(() => {
      expect(screen.getByText(/connection lost/i)).toBeInTheDocument();
    });
  });

  it("has aria-live region for screen reader announcements", async () => {
    useBrainstormStore.setState({
      activeSessionId: "s1",
      sessions: [{ id: "s1", profile_id: "test", driver_session_id: null, status: "active" as const, topic: "Test", created_at: "2026-01-18T00:00:00Z", updated_at: "2026-01-18T00:00:00Z" }],
      messages: [{ id: "m1", session_id: "s1", sequence: 1, role: "user" as const, content: "Hello", parts: null, created_at: "2026-01-18T00:00:00Z" }],
    });

    renderPage();

    const logRegion = await screen.findByRole("log");
    expect(logRegion).toHaveAttribute("aria-live", "polite");
  });

  it("sets aria-busy during streaming", async () => {
    useBrainstormStore.setState({
      activeSessionId: "s1",
      sessions: [{ id: "s1", profile_id: "test", driver_session_id: null, status: "active" as const, topic: "Test", created_at: "2026-01-18T00:00:00Z", updated_at: "2026-01-18T00:00:00Z" }],
      messages: [{ id: "m1", session_id: "s1", sequence: 1, role: "assistant" as const, content: "", parts: null, created_at: "2026-01-18T00:00:00Z", status: "streaming" as const }],
      isStreaming: true,
    });

    renderPage();

    const logRegion = await screen.findByRole("log");
    expect(logRegion).toHaveAttribute("aria-busy", "true");
  });

  it("returns focus to input after submit", async () => {
    useBrainstormStore.setState({
      activeSessionId: "s1",
      sessions: [{ id: "s1", profile_id: "test", driver_session_id: null, status: "active" as const, topic: "Test", created_at: "2026-01-18T00:00:00Z", updated_at: "2026-01-18T00:00:00Z" }],
      messages: [],
    });

    vi.mocked(brainstormApi.sendMessage).mockResolvedValue({ message_id: "m1" });

    renderPage();

    const textarea = screen.getByPlaceholderText(/what would you like to design/i);
    await userEvent.type(textarea, "Test message");
    await userEvent.keyboard("{Enter}");

    // Verify message was sent
    await waitFor(() => {
      expect(brainstormApi.sendMessage).toHaveBeenCalledWith("s1", "Test message");
    });

    // Verify input was cleared and focus is maintained
    await waitFor(() => {
      expect(textarea).toHaveValue("");
      expect(document.activeElement).toBe(textarea);
    });
  });
});
