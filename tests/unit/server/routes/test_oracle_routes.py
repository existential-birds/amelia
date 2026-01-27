"""Tests for Oracle API routes."""

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from amelia.agents.oracle import OracleConsultResult
from amelia.core.types import AgentConfig, OracleConsultation, Profile
from amelia.server.database import ProfileRepository
from amelia.server.dependencies import get_profile_repository
from amelia.server.routes.oracle import get_event_bus, router


@pytest.fixture
def mock_profile_repo() -> AsyncMock:
    """Create mock profile repository."""
    return AsyncMock(spec=ProfileRepository)


@pytest.fixture
def mock_event_bus() -> MagicMock:
    """Create mock event bus."""
    return MagicMock()


@pytest.fixture
def app(mock_profile_repo: AsyncMock, mock_event_bus: MagicMock) -> FastAPI:
    """Create test FastAPI app with oracle router and dependency overrides."""
    test_app = FastAPI()
    test_app.include_router(router, prefix="/api/oracle")
    test_app.dependency_overrides[get_profile_repository] = lambda: mock_profile_repo
    test_app.dependency_overrides[get_event_bus] = lambda: mock_event_bus
    return test_app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """Create test client."""
    return TestClient(app)


class TestOracleConsultRoute:
    """Tests for POST /api/oracle/consult."""

    def test_consult_returns_200(
        self, client: TestClient, mock_profile_repo: AsyncMock, tmp_path: Path
    ):
        """Consult endpoint should return 200 OK."""
        work_dir = str(tmp_path)
        mock_profile = Profile(
            name="test",
            working_dir=work_dir,
            agents={"oracle": AgentConfig(driver="cli", model="sonnet")},
        )
        mock_profile_repo.get_active_profile.return_value = mock_profile

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

        with patch("amelia.server.routes.oracle.Oracle") as mock_oracle_cls:
            mock_oracle = MagicMock()
            mock_oracle.consult = AsyncMock(return_value=mock_result)
            mock_oracle_cls.return_value = mock_oracle

            response = client.post("/api/oracle/consult", json={
                "problem": "How to refactor auth?",
                "working_dir": work_dir,
            })

        assert response.status_code == 200

    def test_consult_validates_working_dir(
        self, client: TestClient, mock_profile_repo: AsyncMock
    ):
        """Consult should reject working_dir outside profile root."""
        mock_profile = Profile(
            name="test",
            working_dir="/home/user/projects",
            agents={"oracle": AgentConfig(driver="cli", model="sonnet")},
        )
        mock_profile_repo.get_active_profile.return_value = mock_profile

        response = client.post("/api/oracle/consult", json={
            "problem": "Analyze",
            "working_dir": "/etc/passwd",
        })

        assert response.status_code == 400

    def test_consult_missing_oracle_config(
        self, client: TestClient, mock_profile_repo: AsyncMock, tmp_path: Path
    ):
        """Consult should return 400 if profile lacks oracle agent config."""
        work_dir = str(tmp_path)
        mock_profile = Profile(
            name="test",
            working_dir=work_dir,
            agents={},
        )
        mock_profile_repo.get_active_profile.return_value = mock_profile

        response = client.post("/api/oracle/consult", json={
            "problem": "Analyze",
            "working_dir": work_dir,
        })

        assert response.status_code == 400
