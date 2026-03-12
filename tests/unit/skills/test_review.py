"""Tests for review skill detection and loading."""
from amelia.skills.review import detect_stack, load_skills


class TestDetectStack:
    """Tests for detect_stack()."""

    def test_python_files(self) -> None:
        tags = detect_stack(["src/app.py", "src/utils.py"], "")
        assert "python" in tags

    def test_pytest_from_test_files(self) -> None:
        tags = detect_stack(["tests/test_app.py", "conftest.py"], "")
        assert "pytest" in tags
        assert "python" in tags

    def test_react_tsx(self) -> None:
        tags = detect_stack(["src/App.tsx", "src/Component.tsx"], "")
        assert "react" in tags

    def test_typescript_ts(self) -> None:
        tags = detect_stack(["src/utils.ts"], "")
        assert "typescript" in tags

    def test_go_files(self) -> None:
        tags = detect_stack(["main.go", "handler.go"], "")
        assert "go" in tags

    def test_elixir_files(self) -> None:
        tags = detect_stack(["lib/app.ex", "test/app_test.exs"], "")
        assert "elixir" in tags

    def test_swift_files(self) -> None:
        tags = detect_stack(["Sources/App.swift"], "")
        assert "swift" in tags

    def test_fastapi_from_imports(self) -> None:
        diff = "+from fastapi import APIRouter"
        tags = detect_stack(["src/routes.py"], diff)
        assert "fastapi" in tags
        assert "python" in tags

    def test_sqlalchemy_from_imports(self) -> None:
        diff = "+from sqlalchemy import Column"
        tags = detect_stack(["src/models.py"], diff)
        assert "sqlalchemy" in tags

    def test_shadcn_from_imports(self) -> None:
        diff = "+import { Button } from '@/components/ui/button'"
        tags = detect_stack(["src/App.tsx"], diff)
        assert "shadcn" in tags

    def test_react_router_from_imports(self) -> None:
        diff = "+import { useLoaderData } from 'react-router-dom'"
        tags = detect_stack(["src/Page.tsx"], diff)
        assert "react-router" in tags

    def test_react_flow_from_imports(self) -> None:
        diff = "+import { ReactFlow } from '@xyflow/react'"
        tags = detect_stack(["src/Flow.tsx"], diff)
        assert "react-flow" in tags

    def test_phoenix_from_imports(self) -> None:
        diff = "+use Phoenix.Router"
        tags = detect_stack(["lib/router.ex"], diff)
        assert "phoenix" in tags

    def test_empty_input(self) -> None:
        tags = detect_stack([], "")
        assert tags == set()

    def test_mixed_stack(self) -> None:
        tags = detect_stack(
            ["backend/app.py", "frontend/App.tsx"],
            "+from fastapi import FastAPI",
        )
        assert "python" in tags
        assert "fastapi" in tags
        assert "react" in tags


class TestLoadSkills:
    """Tests for load_skills()."""

    def test_load_general_skills(self) -> None:
        content = load_skills(set(), ["general"])
        assert "General Code Review" in content
        assert "verification" in content.lower()

    def test_load_python_skills(self) -> None:
        content = load_skills({"python"}, ["general"])
        assert "Python Code Review" in content

    def test_load_multiple_tags(self) -> None:
        content = load_skills({"python", "fastapi"}, ["general"])
        assert "Python Code Review" in content
        assert "FastAPI" in content

    def test_load_security_type(self) -> None:
        content = load_skills(set(), ["security"])
        assert "Security" in content

    def test_load_unknown_tag_ignored(self) -> None:
        content = load_skills({"nonexistent_lang"}, ["general"])
        # Should still include general skills, just no language-specific ones
        assert "General Code Review" in content

    def test_deduplication(self) -> None:
        """Loading same skills twice should not duplicate content."""
        content = load_skills({"python"}, ["general"])
        # Count occurrences of a unique header
        assert content.count("# Python Code Review") == 1
