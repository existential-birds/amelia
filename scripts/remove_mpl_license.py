#!/usr/bin/env python3
"""Remove MPL 2.0 license headers from source files.

This script removes Mozilla Public License 2.0 headers from files as part of
the migration to Elastic License 2.0. It handles multiple comment styles:

- Hash comments (Python, YAML, TOML, shell)
- Block comments (JS, TS, CSS)
- HTML comments (HTML, Vue, Markdown)

Usage:
    python scripts/remove_mpl_license.py amelia dashboard tests  # Process directories
    python scripts/remove_mpl_license.py --dry-run .             # Preview changes
    python scripts/remove_mpl_license.py -v amelia               # Verbose output
"""

import argparse
import re
import sys
from pathlib import Path

# Regex patterns for different license header formats
# Each pattern captures the header and any trailing blank line(s)

# Python/hash-style: matches 3 lines starting with # containing MPL text
HASH_COMMENT_PATTERN = re.compile(
    r"^(#![^\n]*\n)?"  # Optional shebang (group 1, preserved)
    r"# This Source Code Form is subject to the terms of the Mozilla Public\n"
    r"# License, v\. 2\.0\. If a copy of the MPL was not distributed with this\n"
    r"# file, You can obtain one at https://mozilla\.org/MPL/2\.0/\.\n"
    r"\n?",  # Optional trailing blank line
    re.MULTILINE,
)

# JS/CSS block comment style
JS_BLOCK_PATTERN = re.compile(
    r"^/\*\n"
    r" \* This Source Code Form is subject to the terms of the Mozilla Public\n"
    r" \* License, v\. 2\.0\. If a copy of the MPL was not distributed with this\n"
    r" \* file, You can obtain one at https://mozilla\.org/MPL/2\.0/\.\n"
    r" \*/\n"
    r"\n?",  # Optional trailing blank line
    re.MULTILINE,
)

# HTML comment style (single-line start, multi-line body with " - " prefix)
HTML_SINGLE_START_PATTERN = re.compile(
    r"^<!-- This Source Code Form is subject to the terms of the Mozilla Public\n"
    r"   - License, v\. 2\.0\. If a copy of the MPL was not distributed with this\n"
    r"   - file, You can obtain one at https://mozilla\.org/MPL/2\.0/\. -->\n"
    r"\n?",
    re.MULTILINE,
)

# HTML/Vue comment style (multi-line with opening on its own line)
HTML_MULTI_LINE_PATTERN = re.compile(
    r"^<!--\n"
    r"  This Source Code Form is subject to the terms of the Mozilla Public\n"
    r"  License, v\. 2\.0\. If a copy of the MPL was not distributed with this\n"
    r"  file, You can obtain one at https://mozilla\.org/MPL/2\.0/\.\n"
    r"-->\n"
    r"\n?",
    re.MULTILINE,
)

# Vue component hybrid style (HTML comment with * prefix like JS)
VUE_HYBRID_PATTERN = re.compile(
    r"^<!--\n"
    r" \* This Source Code Form is subject to the terms of the Mozilla Public\n"
    r" \* License, v\. 2\.0\. If a copy of the MPL was not distributed with this\n"
    r" \* file, You can obtain one at https://mozilla\.org/MPL/2\.0/\.\n"
    r"-->\n"
    r"\n?",
    re.MULTILINE,
)

# Markdown badge pattern (for README.md) - matches the badge line
MD_BADGE_PATTERN = re.compile(
    r"^\[!\[License: MPL 2\.0\]\(https://img\.shields\.io/badge/License-MPL_2\.0-brightgreen\.svg\)\]"
    r"\(https://opensource\.org/licenses/MPL-2\.0\)\n\n?",
    re.MULTILINE,
)

# Markdown license footer section pattern (## License at end of docs)
MD_LICENSE_FOOTER_PATTERN1 = re.compile(
    r"\n## License\n\n"
    r"Mozilla Public License 2\.0 - See component headers for details\.\n*$",
)

MD_LICENSE_FOOTER_PATTERN2 = re.compile(
    r"\n## License\n\n"
    r"This Source Code Form is subject to the terms of the Mozilla Public License, v\. 2\.0\.\n*$",
)

# Extension to pattern mapping
EXTENSION_PATTERNS: dict[str, list[re.Pattern]] = {
    # Hash comment files
    ".py": [HASH_COMMENT_PATTERN],
    ".yaml": [HASH_COMMENT_PATTERN],
    ".yml": [HASH_COMMENT_PATTERN],
    ".toml": [HASH_COMMENT_PATTERN],
    ".sh": [HASH_COMMENT_PATTERN],
    # Block comment files
    ".js": [JS_BLOCK_PATTERN],
    ".jsx": [JS_BLOCK_PATTERN],
    ".ts": [JS_BLOCK_PATTERN],
    ".tsx": [JS_BLOCK_PATTERN],
    ".css": [JS_BLOCK_PATTERN],
    ".scss": [JS_BLOCK_PATTERN],
    # HTML-style comment files (try multiple patterns)
    ".html": [HTML_SINGLE_START_PATTERN, HTML_MULTI_LINE_PATTERN],
    ".vue": [HTML_MULTI_LINE_PATTERN, VUE_HYBRID_PATTERN, HTML_SINGLE_START_PATTERN],
    ".md": [
        HTML_SINGLE_START_PATTERN,
        HTML_MULTI_LINE_PATTERN,
        MD_BADGE_PATTERN,
        MD_LICENSE_FOOTER_PATTERN1,
        MD_LICENSE_FOOTER_PATTERN2,
    ],
    ".xml": [HTML_SINGLE_START_PATTERN, HTML_MULTI_LINE_PATTERN],
}

# Files to skip
SKIP_PATTERNS = {
    "LICENSE",
    "LICENSE.md",
    "NOTICE",
    ".gitignore",
    ".gitkeep",
    "uv.lock",
    "pnpm-lock.yaml",
    "package-lock.json",
    "yarn.lock",
    "vite-env.d.ts",
    "remove_mpl_license.py",  # This script references MPL in docstring
}

# Directories to skip
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

# Extensions that cannot have comments
NO_COMMENT_EXTENSIONS = {".json", ".jpg", ".jpeg", ".png", ".gif", ".ico", ".svg"}


def has_mpl_license(content: str) -> bool:
    """Check if content contains MPL 2.0 license reference."""
    return "mozilla.org/MPL/2.0" in content.lower() or "Mozilla Public" in content


def get_patterns_for_file(file_path: Path) -> list[re.Pattern] | None:
    """Get regex patterns for removing license from a file based on extension."""
    ext = file_path.suffix.lower()
    return EXTENSION_PATTERNS.get(ext)


def should_skip_file(file_path: Path) -> bool:
    """Check if file should be skipped."""
    if file_path.name in SKIP_PATTERNS:
        return True

    if file_path.suffix.lower() in NO_COMMENT_EXTENSIONS:
        return True

    for parent in file_path.parents:
        if parent.name in SKIP_DIRS:
            return True

    return False


def remove_license_header(content: str, patterns: list[re.Pattern], ext: str) -> str:
    """Remove license header from content using the appropriate patterns."""
    result = content

    for pattern in patterns:
        if ext == ".py":
            # For Python, preserve shebang if present (captured in group 1)
            match = pattern.match(result)
            if match:
                # Replace match with just the shebang (group 1) if present
                result = pattern.sub(lambda m: m.group(1) or "", result, count=1)
                break
        else:
            new_result = pattern.sub("", result, count=1)
            if new_result != result:
                result = new_result
                break

    return result


def process_file(file_path: Path, dry_run: bool = False) -> tuple[bool, str]:
    """Process a single file. Returns (modified, message)."""
    if should_skip_file(file_path):
        return False, f"SKIP (excluded): {file_path}"

    patterns = get_patterns_for_file(file_path)
    if patterns is None:
        return False, f"SKIP (no pattern defined): {file_path}"

    try:
        content = file_path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, PermissionError) as e:
        return False, f"ERROR: {file_path}: {e}"

    if not content.strip():
        return False, f"SKIP (empty): {file_path}"

    if not has_mpl_license(content):
        return False, f"SKIP (no MPL license): {file_path}"

    new_content = remove_license_header(content, patterns, file_path.suffix.lower())

    if new_content == content:
        # Pattern didn't match - might be non-standard format
        return False, f"WARNING: Has MPL reference but pattern didn't match: {file_path}"

    if not dry_run:
        file_path.write_text(new_content, encoding="utf-8")
        return True, f"UPDATED: {file_path}"
    else:
        return True, f"WOULD UPDATE: {file_path}"


def process_directory(
    directory: Path, dry_run: bool = False, verbose: bool = False
) -> tuple[int, int, int, list[str]]:
    """Process all files in directory. Returns (updated, skipped, errors, warnings)."""
    updated = 0
    skipped = 0
    errors = 0
    warnings: list[str] = []

    for file_path in sorted(directory.rglob("*")):
        if file_path.is_dir():
            continue

        # Skip if in excluded directory
        skip = False
        try:
            for parent in file_path.relative_to(directory).parents:
                if parent.name in SKIP_DIRS:
                    skip = True
                    break
        except ValueError:
            pass
        if skip:
            continue

        modified, message = process_file(file_path, dry_run)

        if "WARNING" in message:
            warnings.append(message)
            if verbose:
                print(message)
        elif verbose or modified or "ERROR" in message:
            print(message)

        if "ERROR" in message:
            errors += 1
        elif modified:
            updated += 1
        else:
            skipped += 1

    return updated, skipped, errors, warnings


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Remove MPL 2.0 license headers from source files"
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
    all_warnings: list[str] = []

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
            elif "WARNING" in message:
                all_warnings.append(message)
            elif modified:
                total_updated += 1
            else:
                total_skipped += 1
        else:
            print(f"\nProcessing directory: {path}")
            updated, skipped, errors, warnings = process_directory(
                path, args.dry_run, args.verbose
            )
            total_updated += updated
            total_skipped += skipped
            total_errors += errors
            all_warnings.extend(warnings)

    # Print summary
    print(f"\n{'=' * 60}")
    print(f"Summary: {total_updated} updated, {total_skipped} skipped, {total_errors} errors")

    if all_warnings:
        print(f"\n{len(all_warnings)} files with MPL references but unmatched patterns:")
        for warning in all_warnings:
            print(f"  {warning}")

    return 1 if total_errors > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
