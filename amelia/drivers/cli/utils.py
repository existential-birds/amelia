"""Shared utilities for CLI drivers."""


def strip_markdown_fences(text: str) -> str:
    """Strip markdown code fences from text if present.

    Handles common patterns like:
    - ```json\n{...}\n```
    - ```\n{...}\n```

    Args:
        text: Text that may contain markdown code fences.

    Returns:
        Text with code fences stripped, or original text if no fences found.
    """
    stripped = text.strip()

    # Check for fenced code block pattern
    if stripped.startswith("```"):
        lines = stripped.split("\n")

        # Find the opening fence (first line starting with ```)
        if lines and lines[0].startswith("```"):
            # Find the closing fence
            end_idx = -1
            for i in range(len(lines) - 1, 0, -1):
                if lines[i].strip() == "```":
                    end_idx = i
                    break

            if end_idx > 0:
                # Extract content between fences
                content_lines = lines[1:end_idx]
                return "\n".join(content_lines).strip()

    return text
