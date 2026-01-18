import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SessionDrawer } from "../SessionDrawer";
import { useBrainstormStore } from "@/store/brainstormStore";
import type { BrainstormingSession } from "@/types/api";

const mockSessions: BrainstormingSession[] = [
  {
    id: "s1",
    profile_id: "p1",
    driver_session_id: null,
    status: "active",
    topic: "Active Session",
    created_at: "2026-01-18T10:00:00Z",
    updated_at: "2026-01-18T10:05:00Z",
  },
  {
    id: "s2",
    profile_id: "p1",
    driver_session_id: null,
    status: "completed",
    topic: "Completed Session",
    created_at: "2026-01-17T10:00:00Z",
    updated_at: "2026-01-17T10:05:00Z",
  },
];

describe("SessionDrawer", () => {
  beforeEach(() => {
    useBrainstormStore.setState({
      sessions: mockSessions,
      activeSessionId: "s1",
      drawerOpen: true,
    });
  });

  it("renders session list grouped by status", () => {
    render(
      <SessionDrawer onSelectSession={vi.fn()} onDeleteSession={vi.fn()} onNewSession={vi.fn()} />
    );

    expect(screen.getByText("Active")).toBeInTheDocument();
    expect(screen.getByText("Active Session")).toBeInTheDocument();
    expect(screen.getByText("Completed")).toBeInTheDocument();
    expect(screen.getByText("Completed Session")).toBeInTheDocument();
  });

  it("calls onSelectSession when session is clicked", async () => {
    const onSelectSession = vi.fn();
    render(
      <SessionDrawer
        onSelectSession={onSelectSession}
        onDeleteSession={vi.fn()}
        onNewSession={vi.fn()}
      />
    );

    await userEvent.click(screen.getByRole("button", { name: /completed session/i }));

    expect(onSelectSession).toHaveBeenCalledWith("s2");
  });

  it("calls onNewSession when new session button is clicked", async () => {
    const onNewSession = vi.fn();
    render(
      <SessionDrawer
        onSelectSession={vi.fn()}
        onDeleteSession={vi.fn()}
        onNewSession={onNewSession}
      />
    );

    await userEvent.click(screen.getByRole("button", { name: /new session/i }));

    expect(onNewSession).toHaveBeenCalled();
  });

  it("shows empty state when no sessions", () => {
    useBrainstormStore.setState({ sessions: [] });

    render(
      <SessionDrawer onSelectSession={vi.fn()} onDeleteSession={vi.fn()} onNewSession={vi.fn()} />
    );

    expect(screen.getByText(/no sessions yet/i)).toBeInTheDocument();
  });
});
