"""Review skill registry, stack detection, and skill loading."""
from __future__ import annotations

import re
from pathlib import Path


_SKILLS_DIR = Path(__file__).parent

# Maps technology tags to skill file paths (relative to _SKILLS_DIR)
REVIEW_SKILLS: dict[str, list[str]] = {
    # Python
    "python": ["python/python.md"],
    "pytest": ["python/pytest.md"],
    "fastapi": ["python/fastapi.md"],
    "sqlalchemy": ["python/sqlalchemy.md"],
    "postgres": ["python/postgres.md"],
    # React / Frontend
    "react": ["react/react.md"],
    "typescript": ["react/typescript.md"],
    "shadcn": ["react/shadcn.md"],
    "vitest": ["react/vitest.md"],
    "react-router": ["react/react-router.md"],
    "react-flow": ["react/react-flow.md"],
    # Go
    "go": ["go/go.md"],
    "go-testing": ["go/go-testing.md"],
    "go-concurrency": ["go/go-concurrency.md"],
    "go-middleware": ["go/go-middleware.md"],
    # Elixir
    "elixir": ["elixir/elixir.md"],
    "phoenix": ["elixir/phoenix.md"],
    "liveview": ["elixir/liveview.md"],
    "exunit": ["elixir/exunit.md"],
    "elixir-security": ["elixir/elixir-security.md"],
    "elixir-performance": ["elixir/elixir-performance.md"],
    # Swift
    "swift": ["swift/swift.md"],
    "swiftui": ["swift/swiftui.md"],
    "combine": ["swift/combine.md"],
}

# Maps review types to always-included skill files
REVIEW_TYPE_SKILLS: dict[str, list[str]] = {
    "general": ["general.md", "verification.md"],
    "security": ["security/general.md"],
}

# File extension -> tag mapping
_EXTENSION_TAGS: dict[str, str] = {
    ".py": "python",
    ".tsx": "react",
    ".jsx": "react",
    ".ts": "typescript",
    ".js": "typescript",
    ".go": "go",
    ".ex": "elixir",
    ".exs": "elixir",
    ".swift": "swift",
}

# Path patterns -> additional tags (checked after extension matching)
_PATH_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(^|/)test_[^/]*\.py$"), "pytest"),
    (re.compile(r"(^|/)conftest\.py$"), "pytest"),
    (re.compile(r"_test\.go$"), "go-testing"),
    (re.compile(r"(^|/)test/.*_test\.exs$"), "exunit"),
    (re.compile(r"\.test\.(ts|tsx|js|jsx)$"), "vitest"),
    (re.compile(r"\.spec\.(ts|tsx|js|jsx)$"), "vitest"),
]

# Import patterns in diff content -> additional tags
_IMPORT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"from fastapi\b|import fastapi\b"), "fastapi"),
    (re.compile(r"from sqlalchemy\b|import sqlalchemy\b"), "sqlalchemy"),
    (re.compile(r"from asyncpg\b|import asyncpg\b|psycopg"), "postgres"),
    (re.compile(r"@/components/ui/|from ['\"]@/components/ui"), "shadcn"),
    (re.compile(r"react-router-dom|@react-router"), "react-router"),
    (re.compile(r"@xyflow/react"), "react-flow"),
    (re.compile(r"use Phoenix\.|Phoenix\.Router|Phoenix\.LiveView"), "phoenix"),
    (re.compile(r"Phoenix\.LiveView|live_render|live_component"), "liveview"),
    (re.compile(r"use SwiftUI\b|import SwiftUI\b"), "swiftui"),
    (re.compile(r"import Combine\b"), "combine"),
]


def detect_stack(file_paths: list[str], diff_content: str) -> set[str]:
    """Detect technology stack from changed file paths and diff content.

    Two-pass detection:
    1. File extensions and path patterns
    2. Import patterns in diff content

    Args:
        file_paths: List of changed file paths from git diff --name-only.
        diff_content: Raw diff content for import scanning.

    Returns:
        Set of technology tags (e.g., {"python", "fastapi", "pytest"}).
    """
    tags: set[str] = set()

    # Pass 1: File extensions and path patterns
    for path in file_paths:
        suffix = Path(path).suffix.lower()
        if suffix in _EXTENSION_TAGS:
            tags.add(_EXTENSION_TAGS[suffix])

        for pattern, tag in _PATH_PATTERNS:
            if pattern.search(path):
                tags.add(tag)

    # Pass 2: Import patterns in diff content
    for pattern, tag in _IMPORT_PATTERNS:
        if pattern.search(diff_content):
            tags.add(tag)

    return tags


def _read_skill_files(rel_paths: list[str], cache: dict[str, str]) -> str:
    """Read and concatenate skill files, reading each file at most once.

    Args:
        rel_paths: Skill file paths to include (order-independent; output is
            sorted for determinism).
        cache: Mutable cache mapping rel_path -> stripped file content. Shared
            across calls so the same base/general skill file is read from disk
            only once even when multiple review types reference it.

    Returns:
        Concatenated markdown content joined with "---" separators.
    """
    sections: list[str] = []
    for rel_path in sorted(set(rel_paths)):
        if rel_path not in cache:
            full_path = _SKILLS_DIR / rel_path
            cache[rel_path] = (
                full_path.read_text(encoding="utf-8").strip() if full_path.exists() else ""
            )
        content = cache[rel_path]
        if content:
            sections.append(content)
    return "\n\n---\n\n".join(sections)


def _collect_paths(tags: set[str], review_types: list[str]) -> list[str]:
    """Collect skill file paths for the given tags and review types."""
    paths: list[str] = []
    for review_type in review_types:
        paths.extend(REVIEW_TYPE_SKILLS.get(review_type, []))
    for tag in tags:
        paths.extend(REVIEW_SKILLS.get(tag, []))
    return paths


def load_skills(tags: set[str], review_types: list[str]) -> str:
    """Load and concatenate review skill files for the given tags and types.

    Args:
        tags: Technology tags from detect_stack().
        review_types: Review types to include (e.g., ["general"], ["security"]).

    Returns:
        Concatenated markdown content from all matched skill files.
    """
    return _read_skill_files(_collect_paths(tags, review_types), cache={})


def load_skills_by_type(tags: set[str], review_types: list[str]) -> dict[str, str]:
    """Load review skills for several review types in a single pass.

    Tag-based skills are shared across review types while each review type has
    its own base skills. This reads every distinct skill file from disk at most
    once (shared tag/base files are cached), so callers can resolve guidelines
    for all configured review types without re-reading shared files per type or
    per retry iteration.

    Args:
        tags: Technology tags from detect_stack() (fixed for the invocation).
        review_types: Review types to resolve (e.g., ["general", "security"]).

    Returns:
        Mapping of review_type -> concatenated markdown guidelines.
    """
    cache: dict[str, str] = {}
    return {
        review_type: _read_skill_files(_collect_paths(tags, [review_type]), cache)
        for review_type in review_types
    }
