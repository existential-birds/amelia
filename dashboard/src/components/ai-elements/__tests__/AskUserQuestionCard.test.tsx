import { describe, it, expect, vi, beforeEach } from "vitest";
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
  beforeEach(() => {
    vi.clearAllMocks();
  });

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
    const [call] = onAnswer.mock.calls[0]!;
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

  it("disables interactions when isSubmitting", () => {
    render(
      <AskUserQuestionCard
        payload={singleSelectPayload}
        onAnswer={vi.fn()}
        isSubmitting
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

  it("in single-select mode, Other text takes precedence over selected option", async () => {
    const user = userEvent.setup();
    const onAnswer = vi.fn();
    render(
      <AskUserQuestionCard payload={singleSelectPayload} onAnswer={onAnswer} />
    );

    // Select an option first
    await user.click(screen.getByText("Option A"));
    // Then also type in Other
    const otherInput = screen.getByPlaceholderText("Other...");
    await user.type(otherInput, "Custom answer");
    await user.click(screen.getByRole("button", { name: /submit/i }));

    // Other text should take precedence, ignoring the selected option
    expect(onAnswer).toHaveBeenCalledWith({
      "Which approach do you prefer?": "Custom answer",
    });
  });

  it("multi-select: Other text is appended to selected options", async () => {
    const user = userEvent.setup();
    const onAnswer = vi.fn();
    render(
      <AskUserQuestionCard payload={multiSelectPayload} onAnswer={onAnswer} />
    );

    await user.click(screen.getByText("Auth"));
    await user.click(screen.getByText("Caching"));
    const otherInput = screen.getByPlaceholderText("Other...");
    await user.type(otherInput, "Custom feature");
    await user.click(screen.getByRole("button", { name: /submit/i }));

    expect(onAnswer).toHaveBeenCalled();
    const [call] = onAnswer.mock.calls[0]!;
    expect(call["Which features do you want?"]).toEqual(
      expect.arrayContaining(["Auth", "Caching", "Custom feature"])
    );
    expect(call["Which features do you want?"]).toHaveLength(3);
  });

  it("multi-select: toggling option off removes it from selection", async () => {
    const user = userEvent.setup();
    const onAnswer = vi.fn();
    render(
      <AskUserQuestionCard payload={multiSelectPayload} onAnswer={onAnswer} />
    );

    await user.click(screen.getByText("Auth"));
    await user.click(screen.getByText("Caching"));
    await user.click(screen.getByText("Auth")); // Toggle off
    await user.click(screen.getByRole("button", { name: /submit/i }));

    expect(onAnswer).toHaveBeenCalledWith({
      "Which features do you want?": ["Caching"],
    });
  });

  it("handles multiple questions", async () => {
    const user = userEvent.setup();
    const onAnswer = vi.fn();
    const payload: AskUserQuestionPayload = {
      questions: [
        {
          question: "Which approach?",
          header: "Approach",
          options: [
            { label: "A" },
            { label: "B" },
          ],
          multi_select: false,
        },
        {
          question: "Which features?",
          header: "Features",
          options: [
            { label: "Auth" },
            { label: "Caching" },
          ],
          multi_select: true,
        },
      ],
    };

    render(<AskUserQuestionCard payload={payload} onAnswer={onAnswer} />);

    await user.click(screen.getByText("A"));
    await user.click(screen.getByText("Auth"));
    await user.click(screen.getByText("Caching"));
    await user.click(screen.getByRole("button", { name: /submit/i }));

    expect(onAnswer).toHaveBeenCalledWith({
      "Which approach?": "A",
      "Which features?": expect.arrayContaining(["Auth", "Caching"]),
    });
  });

  it("handles options without descriptions", () => {
    const payload: AskUserQuestionPayload = {
      questions: [
        {
          question: "Choose one",
          header: "Choice",
          options: [
            { label: "First" },
            { label: "Second" },
          ],
          multi_select: false,
        },
      ],
    };

    render(<AskUserQuestionCard payload={payload} onAnswer={vi.fn()} />);

    expect(screen.getByText("First")).toBeInTheDocument();
    expect(screen.getByText("Second")).toBeInTheDocument();
    // Ensure no description elements are rendered
    expect(screen.queryByText(/approach/i)).not.toBeInTheDocument();
  });
});
