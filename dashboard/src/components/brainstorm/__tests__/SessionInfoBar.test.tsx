import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { SessionInfoBar } from "../SessionInfoBar";
import type { ProfileInfo, SessionUsageSummary } from "@/types/api";

const mockProfile: ProfileInfo = {
  name: "test-profile",
  driver: "cli",
  model: "claude-sonnet-4.5",
};

const mockUsageSummary: SessionUsageSummary = {
  total_input_tokens: 5000,
  total_output_tokens: 3000,
  total_cost_usd: 0.42,
  message_count: 3,
};

describe("SessionInfoBar", () => {
  it("renders without usage summary", () => {
    render(
      <SessionInfoBar
        profile={mockProfile}
        status="active"
        messageCount={5}
      />
    );

    // Should render message count
    expect(screen.getByText("5")).toBeInTheDocument();

    // Should not render cost
    expect(screen.queryByText(/\$\d+\.\d{2}/)).not.toBeInTheDocument();
  });

  it("renders cost when usage summary is provided", () => {
    render(
      <SessionInfoBar
        profile={mockProfile}
        status="active"
        messageCount={5}
        usageSummary={mockUsageSummary}
      />
    );

    // Should render the total cost
    expect(screen.getByText("$0.42")).toBeInTheDocument();
  });

  it("does not render cost section when total_cost_usd is 0", () => {
    render(
      <SessionInfoBar
        profile={mockProfile}
        status="active"
        messageCount={5}
        usageSummary={{
          total_input_tokens: 100,
          total_output_tokens: 50,
          total_cost_usd: 0,
          message_count: 1,
        }}
      />
    );

    // Should not render cost when it's 0
    expect(screen.queryByText(/\$\d+\.\d{2}/)).not.toBeInTheDocument();
  });

  it("renders model and driver info", () => {
    render(
      <SessionInfoBar
        profile={mockProfile}
        status="active"
        messageCount={5}
      />
    );

    // Should render formatted model name (formatModel capitalizes and adds spaces)
    // "claude-sonnet-4.5" -> "Claude Sonnet 4.5"
    expect(screen.getByText("Claude Sonnet 4.5")).toBeInTheDocument();

    // Should render formatted driver (formatDriver returns "CLI" for "cli:" prefix)
    expect(screen.getByText("CLI")).toBeInTheDocument();
  });

  it("renders message count", () => {
    render(
      <SessionInfoBar
        profile={mockProfile}
        status="active"
        messageCount={42}
      />
    );

    expect(screen.getByText("42")).toBeInTheDocument();
  });

  it("renders status indicator for active status", () => {
    render(
      <SessionInfoBar
        profile={mockProfile}
        status="active"
        messageCount={5}
      />
    );

    expect(screen.getByText("Active")).toBeInTheDocument();
  });

  it("renders status indicator for completed status", () => {
    render(
      <SessionInfoBar
        profile={mockProfile}
        status="completed"
        messageCount={5}
      />
    );

    expect(screen.getByText("Done")).toBeInTheDocument();
  });

  it("renders status indicator for ready_for_handoff status", () => {
    render(
      <SessionInfoBar
        profile={mockProfile}
        status="ready_for_handoff"
        messageCount={5}
      />
    );

    expect(screen.getByText("Ready")).toBeInTheDocument();
  });

  it("renders status indicator for failed status", () => {
    render(
      <SessionInfoBar
        profile={mockProfile}
        status="failed"
        messageCount={5}
      />
    );

    expect(screen.getByText("Failed")).toBeInTheDocument();
  });

  it("renders without profile", () => {
    render(
      <SessionInfoBar
        profile={null}
        status="active"
        messageCount={5}
      />
    );

    // Should still render status and message count
    expect(screen.getByText("Active")).toBeInTheDocument();
    expect(screen.getByText("5")).toBeInTheDocument();

    // Should not render model or driver
    expect(screen.queryByText("Claude Sonnet 4.5")).not.toBeInTheDocument();
    // Note: "CLI" might appear elsewhere, so we check for the model specifically
  });

  it("formats cost with two decimal places", () => {
    render(
      <SessionInfoBar
        profile={mockProfile}
        status="active"
        messageCount={5}
        usageSummary={{
          total_input_tokens: 1000,
          total_output_tokens: 500,
          total_cost_usd: 0.1,
          message_count: 2,
        }}
      />
    );

    // Should display as $0.10, not $0.1
    expect(screen.getByText("$0.10")).toBeInTheDocument();
  });
});
