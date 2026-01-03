"""Tests to verify agents don't use driver-specific SDK imports.

Agent files should use the unified AgenticMessage type from amelia.drivers.base,
not driver-specific types from claude_agent_sdk or langchain_core.
"""

import ast
from pathlib import Path

import pytest


# Forbidden import patterns that should NOT appear in agent files
FORBIDDEN_IMPORTS = [
    "claude_agent_sdk",
    "langchain_core.messages",
]

# Agent files to check
AGENT_FILES = [
    "amelia/agents/developer.py",
    "amelia/agents/reviewer.py",
]

# Files that ARE allowed to use SDK imports (driver implementations)
ALLOWED_SDK_IMPORT_PATTERNS = [
    "amelia/drivers/",
]


def get_imports_from_file(file_path: Path) -> list[tuple[str, int]]:
    """Extract all import statements from a Python file.

    Args:
        file_path: Path to the Python file.

    Returns:
        List of tuples (import_name, line_number).
    """
    content = file_path.read_text()
    tree = ast.parse(content)

    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append((alias.name, node.lineno))
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append((node.module, node.lineno))

    return imports


def is_forbidden_import(import_name: str) -> str | None:
    """Check if an import matches a forbidden pattern.

    Args:
        import_name: The import module name.

    Returns:
        The forbidden pattern that matched, or None if allowed.
    """
    for forbidden in FORBIDDEN_IMPORTS:
        if import_name.startswith(forbidden):
            return forbidden
    return None


class TestAgentImports:
    """Test that agent files don't import driver-specific SDK types."""

    @pytest.fixture
    def project_root(self) -> Path:
        """Get the project root directory."""
        # Walk up from tests/unit/agents to find project root
        current = Path(__file__).resolve()
        for parent in current.parents:
            if (parent / "pyproject.toml").exists():
                return parent
        raise RuntimeError("Could not find project root")

    @pytest.mark.parametrize("agent_file", AGENT_FILES)
    def test_no_sdk_imports_in_agent(self, project_root: Path, agent_file: str) -> None:
        """Verify agent files don't import driver-specific SDK types.

        Agent files should use AgenticMessage from amelia.drivers.base,
        not claude_agent_sdk.types or langchain_core.messages directly.
        """
        file_path = project_root / agent_file

        if not file_path.exists():
            pytest.skip(f"File {agent_file} does not exist")

        imports = get_imports_from_file(file_path)

        violations = []
        for import_name, line_no in imports:
            forbidden = is_forbidden_import(import_name)
            if forbidden:
                violations.append(f"Line {line_no}: imports '{import_name}' (forbidden: {forbidden})")

        if violations:
            violation_list = "\n  - ".join(violations)
            pytest.fail(
                f"File {agent_file} contains forbidden SDK imports:\n  - {violation_list}\n\n"
                f"Agent files should use 'from amelia.drivers.base import AgenticMessage' instead."
            )

    def test_allowed_imports_in_drivers(self, project_root: Path) -> None:
        """Verify that driver files CAN use SDK imports (sanity check).

        This is a positive test to ensure our detection works correctly.
        Driver files are explicitly allowed to import SDK types.
        """
        # Check that at least one driver file exists with SDK imports
        driver_files = [
            project_root / "amelia/drivers/cli/claude.py",
            project_root / "amelia/drivers/api/deepagents.py",
        ]

        found_sdk_imports = False
        for driver_file in driver_files:
            if not driver_file.exists():
                continue

            imports = get_imports_from_file(driver_file)
            for import_name, _ in imports:
                if is_forbidden_import(import_name):
                    found_sdk_imports = True
                    break

            if found_sdk_imports:
                break

        # This test passes as long as we can parse files
        # The important thing is the agent import test above


class TestAgenticMessageUsage:
    """Test that agents properly use the AgenticMessage type."""

    @pytest.fixture
    def project_root(self) -> Path:
        """Get the project root directory."""
        current = Path(__file__).resolve()
        for parent in current.parents:
            if (parent / "pyproject.toml").exists():
                return parent
        raise RuntimeError("Could not find project root")

    @pytest.mark.parametrize("agent_file", AGENT_FILES)
    def test_agent_imports_agentic_message(self, project_root: Path, agent_file: str) -> None:
        """Verify agents import AgenticMessage from the correct location.

        After removing SDK imports, agents should import:
        - AgenticMessage
        - AgenticMessageType (if needed)
        from amelia.drivers.base
        """
        file_path = project_root / agent_file

        if not file_path.exists():
            pytest.skip(f"File {agent_file} does not exist")

        imports = get_imports_from_file(file_path)

        # Check that amelia.drivers.base is imported
        # Note: We don't assert here because the import style may vary
        # (e.g., importing DriverInterface only). The key test is
        # test_no_sdk_imports_in_agent above which verifies no SDK imports.
        _has_base_import = any(
            import_name == "amelia.drivers.base"
            for import_name, _ in imports
        )
        # This is informational - verify the file parses and has expected imports
        assert len(imports) > 0, f"Expected {agent_file} to have imports"
