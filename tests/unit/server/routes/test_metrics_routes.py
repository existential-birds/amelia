"""Tests for PR auto-fix metrics API routes."""

from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from amelia.server.models.metrics import (
    AggressivenessBreakdown,
    ClassificationRecord,
    ClassificationsResponse,
    PRAutoFixDailyBucket,
    PRAutoFixMetricsResponse,
    PRAutoFixMetricsSummary,
)


def _make_metrics_response(
    total_runs: int = 5,
    total_fixed: int = 3,
) -> PRAutoFixMetricsResponse:
    """Build a realistic PRAutoFixMetricsResponse for mocking."""
    return PRAutoFixMetricsResponse(
        summary=PRAutoFixMetricsSummary(
            total_runs=total_runs,
            total_comments_processed=10,
            total_fixed=total_fixed,
            total_failed=1,
            total_skipped=1,
            avg_latency_seconds=4.2,
            fix_rate=0.6,
        ),
        daily=[
            PRAutoFixDailyBucket(
                date="2026-03-10",
                total_runs=2,
                fixed=1,
                failed=0,
                skipped=1,
                avg_latency_s=3.5,
            ),
            PRAutoFixDailyBucket(
                date="2026-03-11",
                total_runs=3,
                fixed=2,
                failed=1,
                skipped=0,
                avg_latency_s=4.8,
            ),
        ],
        by_aggressiveness=[
            AggressivenessBreakdown(
                level="cautious",
                runs=3,
                fixed=2,
                failed=0,
                skipped=1,
                fix_rate=0.67,
            ),
            AggressivenessBreakdown(
                level="aggressive",
                runs=2,
                fixed=1,
                failed=1,
                skipped=0,
                fix_rate=0.5,
            ),
        ],
    )


def _make_classifications_response() -> ClassificationsResponse:
    """Build a realistic ClassificationsResponse for mocking."""
    return ClassificationsResponse(
        classifications=[
            ClassificationRecord(
                comment_id=101,
                body_snippet="Please fix the typo",
                category="bug_fix",
                confidence=0.92,
                actionable=True,
                aggressiveness_level="cautious",
                prompt_hash="abc123",
                created_at="2026-03-10T12:00:00",
            ),
        ],
        total=1,
    )


@pytest.fixture
def mock_metrics_repo() -> MagicMock:
    """Create mock MetricsRepository."""
    repo = MagicMock()
    repo.get_metrics_summary = AsyncMock(return_value=_make_metrics_response())
    repo.get_classifications = AsyncMock(return_value=_make_classifications_response())
    return repo


@pytest.fixture
def client(mock_metrics_repo: MagicMock) -> TestClient:
    """Create test client with mocked dependencies."""
    from amelia.server.dependencies import get_metrics_repository
    from amelia.server.routes.metrics import router

    app = FastAPI()
    app.include_router(router, prefix="/api")

    app.dependency_overrides[get_metrics_repository] = lambda: mock_metrics_repo

    return TestClient(app)


# ---- Metrics endpoint tests ----


def test_get_metrics_default_30d(client: TestClient, mock_metrics_repo: MagicMock) -> None:
    """GET /api/github/pr-autofix/metrics with no params defaults to 30d."""
    response = client.get("/api/github/pr-autofix/metrics")

    assert response.status_code == 200
    data = response.json()
    assert data["summary"]["total_runs"] == 5
    assert len(data["daily"]) == 2
    assert len(data["by_aggressiveness"]) == 2

    # Verify 30-day range
    call_args = mock_metrics_repo.get_metrics_summary.call_args
    start = call_args[1]["start"]
    end = call_args[1]["end"]
    assert (end - start).days == 29


def test_get_metrics_with_preset(client: TestClient, mock_metrics_repo: MagicMock) -> None:
    """GET /api/github/pr-autofix/metrics?preset=7d uses 7-day range."""
    response = client.get("/api/github/pr-autofix/metrics?preset=7d")

    assert response.status_code == 200

    call_args = mock_metrics_repo.get_metrics_summary.call_args
    start = call_args[1]["start"]
    end = call_args[1]["end"]
    assert (end - start).days == 6


def test_get_metrics_with_date_range(client: TestClient, mock_metrics_repo: MagicMock) -> None:
    """GET /api/github/pr-autofix/metrics with start/end dates."""
    response = client.get(
        "/api/github/pr-autofix/metrics?start=2026-01-01&end=2026-01-15"
    )

    assert response.status_code == 200

    call_args = mock_metrics_repo.get_metrics_summary.call_args
    assert call_args[1]["start"] == date(2026, 1, 1)
    assert call_args[1]["end"] == date(2026, 1, 15)


def test_get_metrics_preset_and_dates_returns_400(client: TestClient) -> None:
    """Providing both preset and start/end returns 400."""
    response = client.get(
        "/api/github/pr-autofix/metrics?preset=7d&start=2026-01-01&end=2026-01-15"
    )

    assert response.status_code == 400


def test_get_metrics_start_without_end_returns_400(client: TestClient) -> None:
    """Providing start without end returns 400."""
    response = client.get("/api/github/pr-autofix/metrics?start=2026-01-01")

    assert response.status_code == 400


def test_get_metrics_with_profile_filter(
    client: TestClient, mock_metrics_repo: MagicMock
) -> None:
    """Profile param is passed through to repository."""
    response = client.get(
        "/api/github/pr-autofix/metrics?preset=30d&profile=my-profile"
    )

    assert response.status_code == 200

    call_args = mock_metrics_repo.get_metrics_summary.call_args
    assert call_args[1]["profile_id"] == "my-profile"


def test_get_metrics_with_aggressiveness_filter(
    client: TestClient, mock_metrics_repo: MagicMock
) -> None:
    """Aggressiveness param is passed through to repository."""
    response = client.get(
        "/api/github/pr-autofix/metrics?preset=30d&aggressiveness=cautious"
    )

    assert response.status_code == 200

    call_args = mock_metrics_repo.get_metrics_summary.call_args
    assert call_args[1]["aggressiveness"] == "cautious"


def test_get_metrics_invalid_preset(client: TestClient) -> None:
    """Invalid preset returns 400."""
    response = client.get("/api/github/pr-autofix/metrics?preset=invalid")

    assert response.status_code == 400


# ---- Classifications endpoint tests ----


def test_get_classifications_default(
    client: TestClient, mock_metrics_repo: MagicMock
) -> None:
    """GET /api/github/pr-autofix/classifications with defaults."""
    response = client.get("/api/github/pr-autofix/classifications")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert len(data["classifications"]) == 1
    assert data["classifications"][0]["comment_id"] == 101


def test_get_classifications_with_limit_offset(
    client: TestClient, mock_metrics_repo: MagicMock
) -> None:
    """Limit and offset are passed through to repository."""
    response = client.get(
        "/api/github/pr-autofix/classifications?preset=30d&limit=10&offset=20"
    )

    assert response.status_code == 200

    call_args = mock_metrics_repo.get_classifications.call_args
    assert call_args[1]["limit"] == 10
    assert call_args[1]["offset"] == 20


def test_get_classifications_with_date_range(
    client: TestClient, mock_metrics_repo: MagicMock
) -> None:
    """Date range params are resolved correctly for classifications."""
    response = client.get(
        "/api/github/pr-autofix/classifications?start=2026-02-01&end=2026-02-28"
    )

    assert response.status_code == 200

    call_args = mock_metrics_repo.get_classifications.call_args
    assert call_args[1]["start"] == date(2026, 2, 1)
    assert call_args[1]["end"] == date(2026, 2, 28)


def test_get_classifications_preset_and_dates_returns_400(client: TestClient) -> None:
    """Providing both preset and start/end returns 400."""
    response = client.get(
        "/api/github/pr-autofix/classifications?preset=7d&start=2026-01-01&end=2026-01-15"
    )

    assert response.status_code == 400


def test_get_metrics_empty_response(
    client: TestClient, mock_metrics_repo: MagicMock
) -> None:
    """Empty results return valid response structure."""
    mock_metrics_repo.get_metrics_summary.return_value = PRAutoFixMetricsResponse(
        summary=PRAutoFixMetricsSummary(
            total_runs=0,
            total_comments_processed=0,
            total_fixed=0,
            total_failed=0,
            total_skipped=0,
            avg_latency_seconds=0.0,
            fix_rate=0.0,
        ),
        daily=[],
        by_aggressiveness=[],
    )

    response = client.get("/api/github/pr-autofix/metrics")

    assert response.status_code == 200
    data = response.json()
    assert data["summary"]["total_runs"] == 0
    assert data["daily"] == []
    assert data["by_aggressiveness"] == []
