import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ArtifactCard } from "../ArtifactCard";
import type { BrainstormArtifact } from "@/types/api";

const mockArtifact: BrainstormArtifact = {
  id: "a1",
  session_id: "s1",
  type: "design",
  path: "docs/plans/2026-01-18-caching-design.md",
  title: "Caching Layer Design",
  created_at: "2026-01-18T10:00:00Z",
};

describe("ArtifactCard", () => {
  it("renders artifact path", () => {
    render(<ArtifactCard artifact={mockArtifact} onHandoff={vi.fn()} />);

    expect(
      screen.getByText("docs/plans/2026-01-18-caching-design.md")
    ).toBeInTheDocument();
  });

  it("renders title if present", () => {
    render(<ArtifactCard artifact={mockArtifact} onHandoff={vi.fn()} />);

    expect(screen.getByText("Caching Layer Design")).toBeInTheDocument();
  });

  it("shows success indicator", () => {
    render(<ArtifactCard artifact={mockArtifact} onHandoff={vi.fn()} />);

    expect(screen.getByText(/design document created/i)).toBeInTheDocument();
  });

  it("calls onHandoff when handoff button is clicked", async () => {
    const onHandoff = vi.fn();
    render(<ArtifactCard artifact={mockArtifact} onHandoff={onHandoff} />);

    await userEvent.click(
      screen.getByRole("button", { name: /hand off to implementation/i })
    );

    expect(onHandoff).toHaveBeenCalledWith(mockArtifact);
  });

  it("disables handoff when isHandingOff is true", () => {
    render(
      <ArtifactCard
        artifact={mockArtifact}
        onHandoff={vi.fn()}
        isHandingOff={true}
      />
    );

    expect(
      screen.getByRole("button", { name: /hand off to implementation/i })
    ).toBeDisabled();
  });
});
