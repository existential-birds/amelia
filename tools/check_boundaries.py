#!/usr/bin/env python3
"""Check import boundaries between Core and Enterprise packages.

This script validates that Core code (amelia/*) does not import from
enterprise packages. This ensures Core remains fully usable without
any enterprise dependencies.

Forbidden patterns:
- amelia/* importing from "amelia_enterprise"
- amelia/* importing from "enterprise"

The only allowed cross-boundary imports are through amelia.ext interfaces.

Usage:
    python tools/check_boundaries.py

Exit codes:
    0: All checks passed
    1: Boundary violations found
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import NamedTuple


# Packages that Core should never import from
FORBIDDEN_PACKAGES = [
    "amelia_enterprise",
    "enterprise",
]


class Violation(NamedTuple):
    """A boundary violation."""

    file: Path
    line: int
    imported: str
    message: str


def find_imports(file_path: Path) -> list[tuple[int, str]]:
    """Find all imports in a Python file.

    Args:
        file_path: Path to the Python file.

    Returns:
        List of (line_number, module_name) tuples.
    """
    imports: list[tuple[int, str]] = []

    try:
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(file_path))
    except (SyntaxError, UnicodeDecodeError) as e:
        print(f"Warning: Could not parse {file_path}: {e}", file=sys.stderr)
        return imports

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append((node.lineno, alias.name))
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append((node.lineno, node.module))

    return imports


def check_file(file_path: Path) -> list[Violation]:
    """Check a single file for boundary violations.

    Args:
        file_path: Path to the Python file.

    Returns:
        List of violations found.
    """
    violations: list[Violation] = []
    imports = find_imports(file_path)

    for line, module in imports:
        for forbidden in FORBIDDEN_PACKAGES:
            if module == forbidden or module.startswith(f"{forbidden}."):
                violations.append(
                    Violation(
                        file=file_path,
                        line=line,
                        imported=module,
                        message=f"Core module imports from forbidden package '{forbidden}'",
                    )
                )

    return violations


def check_directory(directory: Path) -> list[Violation]:
    """Check all Python files in a directory for boundary violations.

    Args:
        directory: Path to the directory to check.

    Returns:
        List of violations found.
    """
    violations: list[Violation] = []

    for py_file in directory.rglob("*.py"):
        # Skip __pycache__ directories
        if "__pycache__" in py_file.parts:
            continue
        violations.extend(check_file(py_file))

    return violations


def main() -> int:
    """Run boundary checks.

    Returns:
        0 if all checks pass, 1 if violations found.
    """
    # Find the project root (where this script is in tools/)
    script_dir = Path(__file__).parent
    project_root = script_dir.parent

    # Check the amelia package
    amelia_dir = project_root / "amelia"
    if not amelia_dir.exists():
        print(f"Error: amelia directory not found at {amelia_dir}", file=sys.stderr)
        return 1

    print(f"Checking import boundaries in {amelia_dir}...")
    print(f"Forbidden packages: {FORBIDDEN_PACKAGES}")
    print()

    violations = check_directory(amelia_dir)

    if violations:
        print(f"Found {len(violations)} boundary violation(s):")
        print()
        for v in violations:
            print(f"  {v.file}:{v.line}")
            print(f"    Import: {v.imported}")
            print(f"    {v.message}")
            print()
        return 1

    print("✓ No boundary violations found")
    return 0


if __name__ == "__main__":
    sys.exit(main())
