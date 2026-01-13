"""File bundler utility for Oracle consulting system.

Bundles files matching glob patterns into formatted markdown.
"""

import asyncio
import glob
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

try:
    import tiktoken
except ImportError:
    tiktoken = None


@dataclass
class FileSection:
    """Represents a file section in the bundle."""
    path: str
    content: str
    token_count: int


async def bundle_files(
    root_dir: str,
    patterns: list[str],
    exclude_patterns: Optional[list[str]] = None,
    max_tokens: int = 8000,
) -> tuple[str, int]:
    """Bundle files matching glob patterns into formatted markdown.

    Args:
        root_dir: Root directory to search from
        patterns: List of glob patterns (e.g., ['src/**/*.py'])
        exclude_patterns: List of patterns to exclude
        max_tokens: Maximum tokens to include in bundle

    Returns:
        Tuple of (formatted_content, total_tokens_used)
    """
    sections: list[FileSection] = []
    total_tokens = 0
    exclude_patterns = exclude_patterns or []

    encoder = None
    if tiktoken is not None:
        encoder = tiktoken.get_encoding("cl100k_base")

    root_path = Path(root_dir)

    for pattern in patterns:
        matching_files = glob.glob(pattern, root_dir=root_dir, recursive=True)

        for file_path in matching_files:
            file_path_obj = root_path / file_path

            if not file_path_obj.is_file():
                continue

            if any(part.startswith(".") for part in file_path_obj.parts):
                continue

            skip = False
            for exclude_pattern in exclude_patterns:
                if glob.fnmatch.fnmatch(file_path, exclude_pattern):
                    skip = True
                    break
            if skip:
                continue

            try:
                content = file_path_obj.read_text(encoding="utf-8")

                if encoder:
                    tokens = len(encoder.encode(content))
                else:
                    tokens = len(content) // 4

                if total_tokens + tokens > max_tokens:
                    continue

                sections.append(
                    FileSection(
                        path=str(file_path),
                        content=content,
                        token_count=tokens,
                    )
                )
                total_tokens += tokens
            except (UnicodeDecodeError, IOError):
                continue

    output = "# File Context\n\n"
    output += f"Total files: {len(sections)} | Tokens: {total_tokens}\n\n"

    for section in sections:
        output += f"## {section.path}\n```\n{section.content}\n```\n\n"

    return output, total_tokens
