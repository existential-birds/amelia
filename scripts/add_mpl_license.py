#!/usr/bin/env python3
"""Add MPL 2.0 license headers to source files."""

import argparse
import sys
from pathlib import Path

# License headers for different file types
PYTHON_HEADER = """\
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""

JS_HEADER = """\
/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/.
 */
"""

HTML_HEADER = """\
<!-- This Source Code Form is subject to the terms of the Mozilla Public
   - License, v. 2.0. If a copy of the MPL was not distributed with this
   - file, You can obtain one at https://mozilla.org/MPL/2.0/. -->
"""

PLAIN_HEADER = """\
This Source Code Form is subject to the terms of the Mozilla Public
License, v. 2.0. If a copy of the MPL was not distributed with this
file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""

# File extension to header mapping
EXTENSION_MAP = {
    # Python/hash-comment files
    ".py": PYTHON_HEADER,
    ".yaml": PYTHON_HEADER,
    ".yml": PYTHON_HEADER,
    ".toml": PYTHON_HEADER,
    ".sh": PYTHON_HEADER,
    # JavaScript/CSS block-comment files
    ".js": JS_HEADER,
    ".jsx": JS_HEADER,
    ".ts": JS_HEADER,
    ".tsx": JS_HEADER,
    ".css": JS_HEADER,
    ".scss": JS_HEADER,
    # HTML-style comment files
    ".html": HTML_HEADER,
    ".md": HTML_HEADER,
    ".xml": HTML_HEADER,
}

# Files/directories to skip
SKIP_PATTERNS = {
    "LICENSE",
    "LICENSE.md",
    ".gitignore",
    ".gitkeep",
    "uv.lock",
    "pnpm-lock.yaml",
    "package-lock.json",
    "yarn.lock",
    "vite-env.d.ts",
}

SKIP_DIRS = {
    ".git",
    ".ruff_cache",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    ".mypy_cache",
    ".pytest_cache",
    "dist",
    "build",
    ".next",
}

# Extensions that cannot have comments (need LICENSE file in directory)
NO_COMMENT_EXTENSIONS = {".json", ".jpg", ".jpeg", ".png", ".gif", ".ico", ".svg"}


def has_mpl_license(content: str) -> bool:
    """Check if content already has MPL 2.0 license header."""
    return "mozilla.org/MPL/2.0" in content.lower() or "Mozilla Public" in content


def get_header_for_file(file_path: Path) -> str | None:
    """Get the appropriate header for a file based on extension."""
    ext = file_path.suffix.lower()
    return EXTENSION_MAP.get(ext)


def should_skip_file(file_path: Path) -> bool:
    """Check if file should be skipped."""
    # Skip by name
    if file_path.name in SKIP_PATTERNS:
        return True

    # Skip by extension (no-comment files)
    if file_path.suffix.lower() in NO_COMMENT_EXTENSIONS:
        return True

    # Skip if parent is a skip directory
    for parent in file_path.parents:
        if parent.name in SKIP_DIRS:
            return True

    return False


def add_license_to_python(content: str, header: str) -> str:
    """Add license to Python file, preserving shebang and encoding."""
    lines = content.split("\n")
    insert_at = 0

    # Preserve shebang
    if lines and lines[0].startswith("#!"):
        insert_at = 1

    # Preserve encoding declaration
    if len(lines) > insert_at and lines[insert_at].startswith("# -*-"):
        insert_at += 1
    elif len(lines) > insert_at and lines[insert_at].startswith("# coding"):
        insert_at += 1

    # Insert header
    lines.insert(insert_at, header.rstrip())
    if insert_at > 0:
        lines.insert(insert_at, "")  # Blank line after shebang/encoding

    return "\n".join(lines)


def add_license_to_file(content: str, header: str, ext: str) -> str:
    """Add license header to file content."""
    if ext == ".py":
        return add_license_to_python(content, header)

    # For other files, just prepend
    return header + "\n" + content


def process_file(file_path: Path, dry_run: bool = False) -> tuple[bool, str]:
    """Process a single file. Returns (modified, message)."""
    if should_skip_file(file_path):
        return False, f"SKIP (excluded): {file_path}"

    header = get_header_for_file(file_path)
    if header is None:
        return False, f"SKIP (no header defined): {file_path}"

    try:
        content = file_path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, PermissionError) as e:
        return False, f"ERROR: {file_path}: {e}"

    # Skip empty files
    if not content.strip():
        return False, f"SKIP (empty): {file_path}"

    # Skip if already has license
    if has_mpl_license(content):
        return False, f"SKIP (has license): {file_path}"

    # Add license
    new_content = add_license_to_file(content, header, file_path.suffix.lower())

    if not dry_run:
        file_path.write_text(new_content, encoding="utf-8")
        return True, f"UPDATED: {file_path}"
    else:
        return True, f"WOULD UPDATE: {file_path}"


def process_directory(
    directory: Path, dry_run: bool = False, verbose: bool = False
) -> tuple[int, int, int]:
    """Process all files in directory. Returns (updated, skipped, errors)."""
    updated = 0
    skipped = 0
    errors = 0

    for file_path in directory.rglob("*"):
        if file_path.is_dir():
            continue

        # Skip if in excluded directory
        skip = False
        for parent in file_path.relative_to(directory).parents:
            if parent.name in SKIP_DIRS:
                skip = True
                break
        if skip:
            continue

        modified, message = process_file(file_path, dry_run)

        if verbose or modified or "ERROR" in message:
            print(message)

        if "ERROR" in message:
            errors += 1
        elif modified:
            updated += 1
        else:
            skipped += 1

    return updated, skipped, errors


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Add MPL 2.0 license headers to source files"
    )
    parser.add_argument(
        "paths", nargs="+", type=Path, help="Files or directories to process"
    )
    parser.add_argument(
        "--dry-run", "-n", action="store_true", help="Show what would be done"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Show all files processed"
    )

    args = parser.parse_args()

    total_updated = 0
    total_skipped = 0
    total_errors = 0

    for path in args.paths:
        if not path.exists():
            print(f"ERROR: Path does not exist: {path}")
            total_errors += 1
            continue

        if path.is_file():
            modified, message = process_file(path, args.dry_run)
            print(message)
            if "ERROR" in message:
                total_errors += 1
            elif modified:
                total_updated += 1
            else:
                total_skipped += 1
        else:
            print(f"\nProcessing directory: {path}")
            updated, skipped, errors = process_directory(path, args.dry_run, args.verbose)
            total_updated += updated
            total_skipped += skipped
            total_errors += errors

    print(f"\nSummary: {total_updated} updated, {total_skipped} skipped, {total_errors} errors")
    return 1 if total_errors > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
