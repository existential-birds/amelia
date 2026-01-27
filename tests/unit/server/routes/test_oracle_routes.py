"""Tests for Oracle API routes."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from amelia.agents.oracle import OracleConsultResult
from amelia.core.types import OracleConsultation
from amelia.server.routes.oracle import router


@pytest.fixture
def app() -> FastAPI:
    """Create test FastAPI app with oracle router."""
    test_app = FastAPI()
    test_app.include_router(router, prefix="/api/oracle")
    return test_app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """Create test client."""
    return TestClient(app)


class TestOracleConsultRoute:
    """Tests for POST /api/oracle/consult."""

    def test_consult_returns_202(self, client: TestClient):
        """Consult endpoint should return 202 Accepted."""
        with (
            patch("amelia.server.routes.oracle._get_profile", new_callable=AsyncMock) as mock_get_profile,
            patch("amelia.server.routes.oracle._get_event_bus") as mock_get_bus,
            patch("amelia.server.routes.oracle.Oracle") as mock_oracle_cls,
        ):
            mock_profile = MagicMock()
            mock_profile.working_dir = "/tmp/work"
            mock_profile.get_agent_config.return_value = MagicMock(
                driver="cli", model="sonnet"
            )
            mock_get_profile.return_value = mock_profile
            mock_get_bus.return_value = MagicMock()

            consultation = OracleConsultation(
                timestamp=datetime.now(UTC),
                problem="How to refactor auth?",
                advice="Use DI.",
                model="sonnet",
                session_id="abc",
                tokens={},
                files_consulted=[],
                outcome="success",
            )
            mock_result = OracleConsultResult(
                advice="Use DI.",
                consultation=consultation,
            )

            mock_oracle = MagicMock()
            mock_oracle.consult = AsyncMock(return_value=mock_result)
            mock_oracle_cls.return_value = mock_oracle

            response = client.post("/api/oracle/consult", json={
                "problem": "How to refactor auth?",
                "working_dir": "/tmp/work",
            })

        assert response.status_code == 202

    def test_consult_validates_working_dir(self, client: TestClient):
        """Consult should reject working_dir outside profile root."""
        with (
            patch("amelia.server.routes.oracle._get_profile", new_callable=AsyncMock) as mock_get_profile,
        ):
            mock_profile = MagicMock()
            mock_profile.working_dir = "/home/user/projects"
            mock_get_profile.return_value = mock_profile

            response = client.post("/api/oracle/consult", json={
                "problem": "Analyze",
                "working_dir": "/etc/passwd",
            })

        assert response.status_code == 400

    def test_consult_missing_oracle_config(self, client: TestClient):
        """Consult should return 400 if profile lacks oracle agent config."""
        with (
            patch("amelia.server.routes.oracle._get_profile", new_callable=AsyncMock) as mock_get_profile,
        ):
            mock_profile = MagicMock()
            mock_profile.working_dir = "/tmp/work"
            mock_profile.get_agent_config.side_effect = ValueError(
                "Agent 'oracle' not configured"
            )
            mock_get_profile.return_value = mock_profile

            response = client.post("/api/oracle/consult", json={
                "problem": "Analyze",
                "working_dir": "/tmp/work",
            })

        assert response.status_code == 400
