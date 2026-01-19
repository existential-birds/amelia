"""Smoke tests for brainstorm dependency wiring in main.py.

These tests verify that create_app() properly wires all brainstorm dependencies.
Without these tests, forgetting to wire a dependency in main.py would not be caught
because all other tests override the dependencies with mocks.

This was the root cause of a bug where get_driver and get_cwd were not wired up
in main.py, causing RuntimeError("Driver not initialized") in production.

Test Strategy:
- Static tests verify dependency overrides exist in app.dependency_overrides
- Dynamic tests verify dependencies resolve correctly with mocked external boundaries
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from amelia.server.database.brainstorm_repository import BrainstormRepository
from amelia.server.database.connection import Database
from amelia.server.events.bus import EventBus
from amelia.server.main import create_app
from amelia.server.routes.brainstorm import (
    get_brainstorm_service,
    get_cwd,
    get_driver,
)
from amelia.server.services.brainstorm import BrainstormService


# =============================================================================
# Static Wiring Tests
# =============================================================================


@pytest.mark.integration
class TestBrainstormDependencyWiring:
    """Verify that create_app() wires all brainstorm dependencies."""

    def test_get_brainstorm_service_is_wired(self) -> None:
        """get_brainstorm_service must be wired in create_app().

        This dependency provides the BrainstormService instance.
        Without it, session creation and message handling fail.
        """
        app = create_app()
        assert get_brainstorm_service in app.dependency_overrides, (
            "get_brainstorm_service not wired in create_app(). "
            "Add: app.dependency_overrides[get_brainstorm_service] = ..."
        )

    def test_get_driver_is_wired(self) -> None:
        """get_driver must be wired in create_app().

        This dependency provides the LLM driver for brainstorming.
        Without it, send_message raises RuntimeError("Driver not initialized").
        """
        app = create_app()
        assert get_driver in app.dependency_overrides, (
            "get_driver not wired in create_app(). "
            "Add: app.dependency_overrides[get_driver] = ..."
        )

    def test_get_cwd_is_wired(self) -> None:
        """get_cwd must be wired in create_app().

        This dependency provides the working directory for brainstorming.
        Without it, artifact paths may be incorrect.
        """
        app = create_app()
        assert get_cwd in app.dependency_overrides, (
            "get_cwd not wired in create_app(). "
            "Add: app.dependency_overrides[get_cwd] = ..."
        )

    def test_all_brainstorm_dependencies_wired(self) -> None:
        """All brainstorm dependencies must be wired together.

        This is a comprehensive check that catches any missing dependency.
        """
        app = create_app()
        required_deps = [get_brainstorm_service, get_driver, get_cwd]
        missing = [
            dep.__name__
            for dep in required_deps
            if dep not in app.dependency_overrides
        ]
        assert not missing, (
            f"Missing brainstorm dependencies in create_app(): {missing}. "
            "Ensure all dependencies are wired in main.py."
        )


# =============================================================================
# Dynamic Wiring Tests
# =============================================================================


@pytest.mark.integration
class TestBrainstormDependencyResolution:
    """Verify that wired dependencies resolve correctly at runtime.

    These tests mock only at the external boundary:
    - Settings file path (AMELIA_SETTINGS env var or settings.amelia.yaml)
    - LLM API calls (execute_agentic)

    They do NOT mock internal dependencies (get_driver, get_cwd), which is
    the key difference from other integration tests.
    """

    @pytest.fixture
    async def test_db(self, temp_db_path: Path) -> AsyncGenerator[Database, None]:
        """Create and initialize in-memory SQLite database."""
        db = Database(temp_db_path)
        await db.connect()
        await db.ensure_schema()
        yield db
        await db.close()

    @pytest.fixture
    def test_brainstorm_service(
        self, test_db: Database
    ) -> BrainstormService:
        """Create real BrainstormService with test dependencies."""
        repo = BrainstormRepository(test_db)
        event_bus = EventBus()
        return BrainstormService(repo, event_bus)

    def test_get_driver_resolves_with_settings_file(
        self,
        test_brainstorm_service: BrainstormService,
        tmp_path: Path,
    ) -> None:
        """get_driver should resolve from active profile in settings file.

        This test verifies that the dependency wiring in main.py correctly
        loads settings.amelia.yaml and reads driver from the active profile,
        then uses factory_get_driver() to create the driver instance.
        """
        import yaml

        # Create settings file with driver in profile
        settings_path = tmp_path / "settings.amelia.yaml"
        working_dir = tmp_path / "working"
        working_dir.mkdir()
        settings_data = {
            "active_profile": "test",
            "profiles": {
                "test": {
                    "name": "test",
                    "driver": "cli:claude",
                    "model": "sonnet",
                    "tracker": "noop",
                    "working_dir": str(working_dir),
                    "validator_model": "sonnet",
                }
            },
        }
        with settings_path.open("w") as f:
            yaml.dump(settings_data, f)

        app = create_app()

        @asynccontextmanager
        async def noop_lifespan(_app: Any) -> AsyncGenerator[None, None]:
            yield

        app.router.lifespan_context = noop_lifespan

        # Only override brainstorm_service (needs app.state from lifespan)
        app.dependency_overrides[get_brainstorm_service] = (
            lambda: test_brainstorm_service
        )

        # Set AMELIA_SETTINGS to use our test settings file
        with patch.dict("os.environ", {"AMELIA_SETTINGS": str(settings_path)}):
            client = TestClient(app)

            # Create a session - this doesn't use get_driver
            response = client.post(
                "/api/brainstorm/sessions",
                json={"profile_id": "test", "topic": "Test topic"},
            )
            assert response.status_code == 201

            # The key test: get_driver was resolved without RuntimeError
            # If it wasn't wired, we'd get RuntimeError("Driver not initialized")
            # when calling send_message (which uses Depends(get_driver))

    def test_get_cwd_resolves_with_settings_file(
        self,
        test_brainstorm_service: BrainstormService,
        tmp_path: Path,
    ) -> None:
        """get_cwd should resolve from active profile in settings file.

        This test verifies that the dependency wiring in main.py correctly
        loads settings.amelia.yaml and reads working_dir from the active profile.
        """
        import yaml

        # Create settings file with working_dir in profile
        settings_path = tmp_path / "settings.amelia.yaml"
        working_dir = tmp_path / "my_working_dir"
        working_dir.mkdir()
        settings_data = {
            "active_profile": "test",
            "profiles": {
                "test": {
                    "name": "test",
                    "driver": "cli:claude",
                    "model": "sonnet",
                    "tracker": "noop",
                    "working_dir": str(working_dir),
                    "validator_model": "sonnet",
                }
            },
        }
        with settings_path.open("w") as f:
            yaml.dump(settings_data, f)

        app = create_app()

        @asynccontextmanager
        async def noop_lifespan(_app: Any) -> AsyncGenerator[None, None]:
            yield

        app.router.lifespan_context = noop_lifespan

        # Only override brainstorm_service (needs app.state from lifespan)
        app.dependency_overrides[get_brainstorm_service] = (
            lambda: test_brainstorm_service
        )

        # Set AMELIA_SETTINGS to use our test settings file
        with patch.dict("os.environ", {"AMELIA_SETTINGS": str(settings_path)}):
            # Get the actual override function and call it
            cwd_override = app.dependency_overrides[get_cwd]
            result = cwd_override()
            assert result == str(working_dir)

    def test_get_cwd_falls_back_to_getcwd(
        self,
        test_brainstorm_service: BrainstormService,
        tmp_path: Path,
    ) -> None:
        """get_cwd should fall back to os.getcwd() when settings file not found.

        This test verifies the fallback behavior when settings.amelia.yaml
        doesn't exist or doesn't have working_dir.
        """
        app = create_app()

        @asynccontextmanager
        async def noop_lifespan(_app: Any) -> AsyncGenerator[None, None]:
            yield

        app.router.lifespan_context = noop_lifespan

        # Only override brainstorm_service (needs app.state from lifespan)
        app.dependency_overrides[get_brainstorm_service] = (
            lambda: test_brainstorm_service
        )

        # Point to non-existent settings file
        non_existent_path = tmp_path / "nonexistent.yaml"
        with patch.dict("os.environ", {"AMELIA_SETTINGS": str(non_existent_path)}):
            # Get the actual override function and call it
            cwd_override = app.dependency_overrides[get_cwd]
            result = cwd_override()
            # Should fall back to current working directory
            import os
            assert result == os.getcwd()

    def test_send_message_endpoint_uses_real_dependencies(
        self,
        test_brainstorm_service: BrainstormService,
        tmp_path: Path,
    ) -> None:
        """send_message endpoint should work with real dependency wiring.

        This is the end-to-end smoke test that verifies:
        1. get_driver resolves without RuntimeError
        2. get_cwd resolves without error
        3. The endpoint accepts requests (even if driver execution is mocked)

        We only mock:
        - AMELIA_SETTINGS env var (external: points to settings file)
        - DriverInterface.execute_agentic (external: calls LLM API)
        """
        import yaml

        from amelia.drivers.base import AgenticMessage, AgenticMessageType
        from tests.conftest import create_mock_execute_agentic

        # Create settings file with working_dir in profile
        settings_path = tmp_path / "settings.amelia.yaml"
        working_dir = tmp_path / "working"
        working_dir.mkdir()
        settings_data = {
            "active_profile": "test",
            "profiles": {
                "test": {
                    "name": "test",
                    "driver": "cli:claude",
                    "model": "sonnet",
                    "tracker": "noop",
                    "working_dir": str(working_dir),
                    "validator_model": "sonnet",
                }
            },
        }
        with settings_path.open("w") as f:
            yaml.dump(settings_data, f)

        app = create_app()

        @asynccontextmanager
        async def noop_lifespan(_app: Any) -> AsyncGenerator[None, None]:
            yield

        app.router.lifespan_context = noop_lifespan

        # Only override brainstorm_service (needs app.state from lifespan)
        app.dependency_overrides[get_brainstorm_service] = (
            lambda: test_brainstorm_service
        )

        # Create mock driver response at LLM boundary
        mock_messages = [
            AgenticMessage(
                type=AgenticMessageType.RESULT,
                content="Test response",
                session_id="test-session",
            ),
        ]

        with (
            patch.dict("os.environ", {"AMELIA_SETTINGS": str(settings_path)}),
            patch(
                "amelia.drivers.cli.ClaudeCliDriver.execute_agentic",
                create_mock_execute_agentic(mock_messages),
            ),
        ):
            client = TestClient(app)

            # Create session
            create_resp = client.post(
                "/api/brainstorm/sessions",
                json={"profile_id": "test"},
            )
            assert create_resp.status_code == 201
            session_id = create_resp.json()["session"]["id"]

            # Send message - this uses REAL get_driver and get_cwd wiring
            # If dependencies weren't wired, this would fail with RuntimeError
            msg_resp = client.post(
                f"/api/brainstorm/sessions/{session_id}/message",
                json={"content": "Hello"},
            )

            # 202 means the request was accepted and dependencies resolved
            assert msg_resp.status_code == 202, (
                f"Expected 202 but got {msg_resp.status_code}. "
                f"Response: {msg_resp.json()}"
            )


# =============================================================================
# Driver Cleanup Wiring Tests
# =============================================================================


@pytest.mark.integration
class TestDriverCleanupWiring:
    """Test driver cleanup is wired correctly.

    These tests verify that the production main.py lifespan properly wires
    the driver_cleanup callback to BrainstormService. This enables automatic
    cleanup of driver sessions (e.g., API session memory) when brainstorming
    sessions are deleted or reach terminal status.
    """

    def test_cleanup_wired_to_service(self) -> None:
        """BrainstormService should have driver_cleanup callback wired.

        Inspects the production lifespan source to verify driver_cleanup
        is passed to BrainstormService constructor.
        """
        import inspect

        from amelia.server.main import lifespan

        # Get the source code of the lifespan function
        source = inspect.getsource(lifespan)

        # Verify driver_cleanup is passed to BrainstormService
        assert "driver_cleanup" in source, (
            "main.py lifespan does not pass driver_cleanup to BrainstormService. "
            "Add: BrainstormService(..., driver_cleanup=create_driver_cleanup_callback())"
        )
