import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MessageMetadata } from "../MessageMetadata";
import type { MessageUsage } from "@/types/api";

vi.mock("@/lib/utils", async () => {
  const actual = await vi.importActual("@/lib/utils");
  return {
    ...actual,
    copyToClipboard: vi.fn(() => Promise.resolve(true)),
  };
});

import { copyToClipboard } from "@/lib/utils";

beforeEach(() => {
  vi.clearAllMocks();
});

const mockUsage: MessageUsage = {
  input_tokens: 10000,
  output_tokens: 2400,
  cost_usd: 0.05,
};

describe("MessageMetadata", () => {
  it("renders timestamp without usage data", () => {
    render(
      <MessageMetadata
        timestamp="2026-01-18T10:00:00Z"
        content="Test message content"
      />
    );

    expect(
      screen.getByRole("button", { name: /copy message/i })
    ).toBeInTheDocument();

    expect(screen.queryByText(/tok$/)).not.toBeInTheDocument();
    expect(screen.queryByText(/\$\d+\.\d+/)).not.toBeInTheDocument();
  });

  it("renders token count and cost when usage is provided", () => {
    render(
      <MessageMetadata
        timestamp="2026-01-18T10:00:00Z"
        content="Test message content"
        usage={mockUsage}
      />
    );

    expect(screen.getByText("12.4K tok")).toBeInTheDocument();

    expect(screen.getByText("$0.05")).toBeInTheDocument();
  });

  it("formats tokens with K notation for thousands", () => {
    const { rerender } = render(
      <MessageMetadata
        timestamp="2026-01-18T10:00:00Z"
        content="Test message content"
        usage={{ input_tokens: 1000, output_tokens: 500, cost_usd: 0.01 }}
      />
    );
    expect(screen.getByText("1.5K tok")).toBeInTheDocument();

    // Test 500 tokens -> "500 tok" (no K notation for < 1000)
    rerender(
      <MessageMetadata
        timestamp="2026-01-18T10:00:00Z"
        content="Test message content"
        usage={{ input_tokens: 300, output_tokens: 200, cost_usd: 0.005 }}
      />
    );
    expect(screen.getByText("500 tok")).toBeInTheDocument();

    rerender(
      <MessageMetadata
        timestamp="2026-01-18T10:00:00Z"
        content="Test message content"
        usage={{ input_tokens: 600, output_tokens: 400, cost_usd: 0.01 }}
      />
    );
    expect(screen.getByText("1.0K tok")).toBeInTheDocument();
  });

  it("does not show usage section when usage is undefined", () => {
    render(
      <MessageMetadata
        timestamp="2026-01-18T10:00:00Z"
        content="Test message content"
        usage={undefined}
      />
    );

    expect(screen.queryByText("◈")).not.toBeInTheDocument();

    expect(screen.queryByText(/tok$/)).not.toBeInTheDocument();
    expect(screen.queryByText(/\$/)).not.toBeInTheDocument();
  });

  it("renders copy button", () => {
    render(
      <MessageMetadata
        timestamp="2026-01-18T10:00:00Z"
        content="Test message content"
      />
    );

    const copyButton = screen.getByRole("button", { name: /copy message/i });
    expect(copyButton).toBeInTheDocument();
  });

  it("copies content to clipboard when copy button is clicked", async () => {
    const user = userEvent.setup();
    const testContent = "Test message content to copy";

    render(
      <MessageMetadata timestamp="2026-01-18T10:00:00Z" content={testContent} />
    );

    const copyButton = screen.getByRole("button", { name: /copy message/i });
    await user.click(copyButton);

    expect(copyToClipboard).toHaveBeenCalledWith(testContent);
  });

  it("shows copied state after clicking copy button", async () => {
    const user = userEvent.setup();

    render(
      <MessageMetadata
        timestamp="2026-01-18T10:00:00Z"
        content="Test message content"
      />
    );

    const copyButton = screen.getByRole("button", { name: /copy message/i });
    await user.click(copyButton);

    expect(
      screen.getByRole("button", { name: /copied/i })
    ).toBeInTheDocument();
  });

  it("formats cost with two decimal places", () => {
    render(
      <MessageMetadata
        timestamp="2026-01-18T10:00:00Z"
        content="Test message content"
        usage={{ input_tokens: 100, output_tokens: 100, cost_usd: 0.1 }}
      />
    );

    // Should display as $0.10, not $0.1
    expect(screen.getByText("$0.10")).toBeInTheDocument();
  });
});
