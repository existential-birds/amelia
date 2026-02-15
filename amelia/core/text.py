"""Text utilities for generating safe identifiers."""

import re


def slugify(text: str, max_length: int = 15) -> str:
    """Convert text to a URL-safe slug.

    Args:
        text: Input text to slugify.
        max_length: Maximum length of the result.

    Returns:
        Lowercase slug with only alphanumeric chars and dashes.
    """
    # Lowercase and replace non-alphanumeric with dashes
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower())
    # Strip leading/trailing dashes
    slug = slug.strip("-")
    # Truncate at dash boundary if possible
    if len(slug) > max_length:
        truncated = slug[:max_length]
        # Try to break at last dash within limit
        last_dash = truncated.rfind("-")
        slug = truncated[:last_dash] if last_dash > 0 else truncated
    return slug
