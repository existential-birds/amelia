import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AskUserQuestionCard } from "../AskUserQuestionCard";
import type { AskUserQuestionPayload } from "@/types/api";

const singleSelectPayload: AskUserQuestionPayload = {
  questions: [
    {
      question: "Which approach do you prefer?",
      header: "Approach",
      options: [
        { label: "Option A", description: "First approach" },
        { label: "Option B", description: "Second approach" },
      ],
      multi_select: false,
    },
  ],
};

const multiSelectPayload: AskUserQuestionPayload = {
  questions: [
    {
      question: "Which features do you want?",
      header: "Features",
      options: [
        { label: "Auth" },
        { label: "Caching" },
        { label: "Logging" },
      ],
      multi_select: true,
    },
  ],
};

describe("AskUserQuestionCard", () => {
  it("renders question text and header", () => {
    render(
      <AskUserQuestionCard payload={singleSelectPayload} onAnswer={vi.fn()} />
    );
    expect(screen.getByText("Which approach do you prefer?")).toBeInTheDocument();
    expect(screen.getByText("Approach")).toBeInTheDocument();
  });

  it("renders options with descriptions", () => {
    render(
      <AskUserQuestionCard payload={singleSelectPayload} onAnswer={vi.fn()} />
    );
    expect(screen.getByText("Option A")).toBeInTheDocument();
    expect(screen.getByText("First approach")).toBeInTheDocument();
    expect(screen.getByText("Option B")).toBeInTheDocument();
  });

  it("handles single-select: clicking replaces selection", async () => {
    const user = userEvent.setup();
    const onAnswer = vi.fn();
    render(
      <AskUserQuestionCard payload={singleSelectPayload} onAnswer={onAnswer} />
    );

    await user.click(screen.getByText("Option A"));
    await user.click(screen.getByText("Option B"));
    await user.click(screen.getByRole("button", { name: /submit/i }));

    expect(onAnswer).toHaveBeenCalledWith({
      "Which approach do you prefer?": "Option B",
    });
  });

  it("handles multi-select: clicking toggles selection", async () => {
    const user = userEvent.setup();
    const onAnswer = vi.fn();
    render(
      <AskUserQuestionCard payload={multiSelectPayload} onAnswer={onAnswer} />
    );

    await user.click(screen.getByText("Auth"));
    await user.click(screen.getByText("Caching"));
    await user.click(screen.getByRole("button", { name: /submit/i }));

    expect(onAnswer).toHaveBeenCalled();
    const call = onAnswer.mock.calls[0]![0] as Record<string, string | string[]>;
    expect(call["Which features do you want?"]).toEqual(
      expect.arrayContaining(["Auth", "Caching"])
    );
    expect(call["Which features do you want?"]).toHaveLength(2);
  });

  it("handles 'Other' text input", async () => {
    const user = userEvent.setup();
    const onAnswer = vi.fn();
    render(
      <AskUserQuestionCard payload={singleSelectPayload} onAnswer={onAnswer} />
    );

    const otherInput = screen.getByPlaceholderText("Other...");
    await user.type(otherInput, "Custom answer");
    await user.click(screen.getByRole("button", { name: /submit/i }));

    expect(onAnswer).toHaveBeenCalledWith({
      "Which approach do you prefer?": "Custom answer",
    });
  });

  it("shows answered state", () => {
    render(
      <AskUserQuestionCard
        payload={singleSelectPayload}
        onAnswer={vi.fn()}
        answered
      />
    );
    expect(screen.getByText("Answered")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /submit/i })).not.toBeInTheDocument();
  });

  it("disables interactions when disabled", () => {
    render(
      <AskUserQuestionCard
        payload={singleSelectPayload}
        onAnswer={vi.fn()}
        disabled
      />
    );
    const buttons = screen.getAllByRole("button");
    for (const btn of buttons) {
      expect(btn).toBeDisabled();
    }
    expect(screen.getByPlaceholderText("Other...")).toBeDisabled();
  });

  it("disables submit button when no selection made", () => {
    render(
      <AskUserQuestionCard payload={singleSelectPayload} onAnswer={vi.fn()} />
    );
    expect(screen.getByRole("button", { name: /submit/i })).toBeDisabled();
  });
});
