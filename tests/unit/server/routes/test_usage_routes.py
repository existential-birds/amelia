"""Tests for usage API routes."""

from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from amelia.server.dependencies import get_repository


@pytest.fixture
def mock_repo() -> MagicMock:
    """Create mock repository."""
    repo = MagicMock()
    repo.get_usage_summary = AsyncMock(return_value={
        "total_cost_usd": 127.43,
        "total_workflows": 24,
        "total_tokens": 1_200_000,
        "total_duration_ms": 2_820_000,
        "previous_period_cost_usd": 98.12,
        "successful_workflows": 22,
        "success_rate": 0.9167,
    })
    repo.get_usage_trend = AsyncMock(return_value=[
        {"date": "2026-01-15", "cost_usd": 12.34, "workflows": 3, "by_model": {"claude-sonnet-4": 12.34}},
        {"date": "2026-01-16", "cost_usd": 15.67, "workflows": 4, "by_model": {"claude-opus-4": 15.67}},
    ])
    repo.get_usage_by_model = AsyncMock(return_value=[
        {"model": "claude-sonnet-4", "workflows": 18, "tokens": 892_000, "cost_usd": 42.17, "trend": [12.34, 0.0], "successful_workflows": 17, "success_rate": 0.9444},
        {"model": "claude-opus-4", "workflows": 6, "tokens": 340_000, "cost_usd": 85.26, "trend": [0.0, 15.67], "successful_workflows": 5, "success_rate": 0.8333},
    ])
    return repo


@pytest.fixture
def client(mock_repo: MagicMock) -> TestClient:
    """Create test client with mocked dependencies."""
    from amelia.server.routes.usage import router

    app = FastAPI()
    app.include_router(router, prefix="/api")

    # Override dependencies
    app.dependency_overrides[get_repository] = lambda: mock_repo

    return TestClient(app)


def test_get_usage_with_preset(client: TestClient, mock_repo: MagicMock) -> None:
    """GET /api/usage?preset=30d returns usage data."""
    response = client.get("/api/usage?preset=30d")

    assert response.status_code == 200
    data = response.json()

    assert data["summary"]["total_cost_usd"] == 127.43
    assert data["summary"]["total_workflows"] == 24
    assert len(data["trend"]) == 2
    assert len(data["by_model"]) == 2


def test_get_usage_with_date_range(client: TestClient, mock_repo: MagicMock) -> None:
    """GET /api/usage with start/end dates uses those dates."""
    response = client.get("/api/usage?start=2026-01-01&end=2026-01-15")

    assert response.status_code == 200

    # Verify repo was called with correct dates
    call_args = mock_repo.get_usage_summary.call_args
    assert call_args[1]["start_date"] == date(2026, 1, 1)
    assert call_args[1]["end_date"] == date(2026, 1, 15)


def test_get_usage_preset_7d(client: TestClient, mock_repo: MagicMock) -> None:
    """preset=7d calculates correct date range."""
    response = client.get("/api/usage?preset=7d")

    assert response.status_code == 200

    # Verify dates are within 7 days of today
    call_args = mock_repo.get_usage_summary.call_args
    end_date = call_args[1]["end_date"]
    start_date = call_args[1]["start_date"]
    assert (end_date - start_date).days == 6  # 7 days inclusive


def test_get_usage_invalid_preset(client: TestClient) -> None:
    """Invalid preset returns 400."""
    response = client.get("/api/usage?preset=invalid")

    assert response.status_code == 400


def test_get_usage_missing_params_uses_30d(client: TestClient, mock_repo: MagicMock) -> None:
    """No params defaults to preset=30d."""
    response = client.get("/api/usage")

    assert response.status_code == 200

    # Should use 30 day range
    call_args = mock_repo.get_usage_summary.call_args
    end_date = call_args[1]["end_date"]
    start_date = call_args[1]["start_date"]
    assert (end_date - start_date).days == 29  # 30 days inclusive
