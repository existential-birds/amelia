import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SessionListItem } from "../SessionListItem";
import type { BrainstormingSession } from "@/types/api";

const mockSession: BrainstormingSession = {
  id: "s1",
  profile_id: "p1",
  driver_session_id: null,
  status: "active",
  topic: "Test Session",
  created_at: "2026-01-18T10:00:00Z",
  updated_at: "2026-01-18T10:05:00Z",
};

describe("SessionListItem", () => {
  it("renders session topic", () => {
    render(
      <SessionListItem
        session={mockSession}
        isSelected={false}
        onSelect={vi.fn()}
        onDelete={vi.fn()}
      />
    );

    expect(screen.getByText("Test Session")).toBeInTheDocument();
  });

  it("renders 'Untitled' for sessions without topic", () => {
    render(
      <SessionListItem
        session={{ ...mockSession, topic: null }}
        isSelected={false}
        onSelect={vi.fn()}
        onDelete={vi.fn()}
      />
    );

    expect(screen.getByText("Untitled")).toBeInTheDocument();
  });

  it("shows status indicator based on session status", () => {
    const { rerender } = render(
      <SessionListItem
        session={{ ...mockSession, status: "active" }}
        isSelected={false}
        onSelect={vi.fn()}
        onDelete={vi.fn()}
      />
    );

    expect(screen.getByTestId("status-indicator")).toHaveClass(
      "bg-status-running"
    );

    rerender(
      <SessionListItem
        session={{ ...mockSession, status: "completed" }}
        isSelected={false}
        onSelect={vi.fn()}
        onDelete={vi.fn()}
      />
    );

    expect(screen.getByTestId("status-indicator")).toHaveClass(
      "bg-status-completed"
    );
  });

  it("calls onSelect when clicked", async () => {
    const onSelect = vi.fn();
    render(
      <SessionListItem
        session={mockSession}
        isSelected={false}
        onSelect={onSelect}
        onDelete={vi.fn()}
      />
    );

    await userEvent.click(screen.getByRole("button", { name: /test session/i }));

    expect(onSelect).toHaveBeenCalledWith("s1");
  });

  it("shows selected state", () => {
    render(
      <SessionListItem
        session={mockSession}
        isSelected={true}
        onSelect={vi.fn()}
        onDelete={vi.fn()}
      />
    );

    const button = screen.getByRole("button", { name: /test session/i });
    expect(button).toHaveClass("bg-session-selected");
    expect(button).toHaveClass("border-l-2");
    expect(button).toHaveClass("border-session-active-border");
  });

  it("calls onDelete when delete button is clicked", async () => {
    const onDelete = vi.fn();
    render(
      <SessionListItem
        session={mockSession}
        isSelected={false}
        onSelect={vi.fn()}
        onDelete={onDelete}
      />
    );

    // Click delete button
    await userEvent.click(screen.getByRole("button", { name: /delete session/i }));

    expect(onDelete).toHaveBeenCalledWith("s1");
  });
});
