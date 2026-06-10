"""Tests for usage API routes serving aggregates from trajectory files."""

import uuid
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from harbor.models.trajectories import Agent, FinalMetrics, Step, Trajectory

import amelia
from amelia.server.dependencies import get_repository
from amelia.trajectory import trajectory_path, write_atomic


def make_trajectory(model: str, cost: float, tokens: tuple[int, int], status: str) -> Trajectory:
    """Build a minimal finalized workflow trajectory with one subagent."""
    prompt, completion = tokens
    metrics = FinalMetrics(
        total_prompt_tokens=prompt,
        total_completion_tokens=completion,
        total_cost_usd=cost,
        total_steps=1,
    )
    sub = Trajectory(
        trajectory_id="developer-inv-1",
        agent=Agent(name="developer", version=amelia.__version__, model_name=model),
        steps=[Step(step_id=1, source="agent", message="done")],
        final_metrics=metrics,
    )
    return Trajectory(
        session_id=str(uuid.uuid4()),
        agent=Agent(name="amelia", version=amelia.__version__, model_name="orchestrator"),
        steps=[Step(step_id=1, source="agent", message="Invoked developer")],
        final_metrics=metrics,
        extra={"outcome": {"status": status}},
        subagent_trajectories=[sub],
    )


def seed_trajectory_file(
    trajectory_dir: Path,
    *,
    model: str = "claude-x",
    cost: float = 1.0,
    tokens: tuple[int, int] = (10, 5),
    status: str = "completed",
) -> Path:
    """Write a trajectory file to disk and return its path."""
    path = trajectory_path(trajectory_dir, uuid.uuid4())
    write_atomic(path, make_trajectory(model, cost, tokens, status))
    return path


@pytest.fixture
def mock_repo(tmp_path: Path) -> MagicMock:
    """Mock repository whose list_trajectory_paths filters seeded rows by date.

    ``repo.rows`` holds ``(path_str, completed_date, duration_ms)`` tuples;
    the side effect mimics the SQL ``completed_at::date`` range filter.
    """
    repo = MagicMock()
    repo.rows = []

    async def list_trajectory_paths(start_date: date, end_date: date) -> list[tuple]:
        return [r for r in repo.rows if start_date <= r[1] <= end_date]

    repo.list_trajectory_paths = AsyncMock(side_effect=list_trajectory_paths)
    return repo


@pytest.fixture
def client(mock_repo: MagicMock) -> TestClient:
    """Create test client with mocked dependencies."""
    from amelia.server.routes.usage import router

    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.dependency_overrides[get_repository] = lambda: mock_repo

    return TestClient(app)


def test_get_usage_aggregates_seeded_trajectory_files(
    client: TestClient, mock_repo: MagicMock, tmp_path: Path
) -> None:
    """GET /api/usage sums totals across the trajectory files in range."""
    p1 = seed_trajectory_file(tmp_path, cost=1.0, tokens=(100, 50), status="completed")
    p2 = seed_trajectory_file(tmp_path, cost=2.0, tokens=(200, 100), status="failed")
    mock_repo.rows = [
        (str(p1), date(2026, 6, 1), 1000),
        (str(p2), date(2026, 6, 2), 2000),
    ]

    response = client.get("/api/usage?start=2026-06-01&end=2026-06-03")

    assert response.status_code == 200
    data = response.json()
    assert data["summary"]["total_cost_usd"] == 3.0
    assert data["summary"]["total_workflows"] == 2
    assert data["summary"]["total_tokens"] == 450
    assert data["summary"]["total_duration_ms"] == 3000
    assert data["summary"]["successful_workflows"] == 1
    assert data["summary"]["success_rate"] == 0.5
    assert [p["date"] for p in data["trend"]] == ["2026-06-01", "2026-06-02"]
    assert [m["model"] for m in data["by_model"]] == ["claude-x"]
    assert data["by_model"][0]["cost_usd"] == 3.0
    assert data["by_model"][0]["workflows"] == 2


def test_get_usage_date_filter_excludes_out_of_range_workflow(
    client: TestClient, mock_repo: MagicMock, tmp_path: Path
) -> None:
    """A workflow completed outside the requested range contributes nothing."""
    p1 = seed_trajectory_file(tmp_path, cost=1.0)
    p2 = seed_trajectory_file(tmp_path, cost=2.0)
    p3 = seed_trajectory_file(tmp_path, cost=8.0)
    mock_repo.rows = [
        (str(p1), date(2026, 6, 1), 1000),
        (str(p2), date(2026, 6, 2), 1000),
        (str(p3), date(2026, 7, 20), 1000),  # outside range and previous window
    ]

    response = client.get("/api/usage?start=2026-06-01&end=2026-06-05")

    assert response.status_code == 200
    data = response.json()
    assert data["summary"]["total_cost_usd"] == 3.0
    assert data["summary"]["total_workflows"] == 2


def test_get_usage_previous_period_cost_from_pre_window_files(
    client: TestClient, mock_repo: MagicMock, tmp_path: Path
) -> None:
    """Files completed in the immediately preceding window feed the comparison."""
    prev = seed_trajectory_file(tmp_path, cost=4.0)
    current = seed_trajectory_file(tmp_path, cost=1.0)
    mock_repo.rows = [
        (str(prev), date(2026, 5, 29), 1000),
        (str(current), date(2026, 6, 2), 1000),
    ]

    response = client.get("/api/usage?start=2026-06-01&end=2026-06-05")

    assert response.status_code == 200
    data = response.json()
    assert data["summary"]["total_cost_usd"] == 1.0
    assert data["summary"]["previous_period_cost_usd"] == 4.0


def test_get_usage_skips_unreadable_trajectory_file(
    client: TestClient, mock_repo: MagicMock, tmp_path: Path
) -> None:
    """A missing or corrupt file is skipped; the endpoint still answers."""
    good = seed_trajectory_file(tmp_path, cost=1.0)
    missing = tmp_path / "gone" / "trajectory.json"
    corrupt = tmp_path / "corrupt" / "trajectory.json"
    corrupt.parent.mkdir(parents=True)
    corrupt.write_text("not json{")
    mock_repo.rows = [
        (str(good), date(2026, 6, 1), 1000),
        (str(missing), date(2026, 6, 2), 1000),
        (str(corrupt), date(2026, 6, 2), 1000),
    ]

    response = client.get("/api/usage?start=2026-06-01&end=2026-06-03")

    assert response.status_code == 200
    data = response.json()
    assert data["summary"]["total_cost_usd"] == 1.0
    assert data["summary"]["total_workflows"] == 1


def test_get_usage_with_date_range_queries_previous_window_too(
    client: TestClient, mock_repo: MagicMock
) -> None:
    """The single SQL query spans the requested range plus the previous period."""
    response = client.get("/api/usage?start=2026-01-01&end=2026-01-15")

    assert response.status_code == 200
    call_args = mock_repo.list_trajectory_paths.call_args
    # 15-day range → query extends 15 days back for previous-period cost.
    assert call_args[0] == (date(2025, 12, 17), date(2026, 1, 15))


def test_get_usage_preset_7d(client: TestClient, mock_repo: MagicMock) -> None:
    """preset=7d queries a 7-day range plus the 7-day previous window."""
    response = client.get("/api/usage?preset=7d")

    assert response.status_code == 200
    query_start, query_end = mock_repo.list_trajectory_paths.call_args[0]
    assert (query_end - query_start).days == 13  # 7 current + 7 previous, inclusive


def test_get_usage_invalid_preset(client: TestClient) -> None:
    """Invalid preset returns 400."""
    response = client.get("/api/usage?preset=invalid")

    assert response.status_code == 400


def test_get_usage_preset_and_dates_is_400(client: TestClient) -> None:
    """Providing both preset and explicit dates is rejected."""
    response = client.get("/api/usage?preset=7d&start=2026-01-01&end=2026-01-15")

    assert response.status_code == 400


def test_get_usage_missing_params_uses_30d(
    client: TestClient, mock_repo: MagicMock
) -> None:
    """No params defaults to preset=30d (plus the 30-day previous window)."""
    response = client.get("/api/usage")

    assert response.status_code == 200
    query_start, query_end = mock_repo.list_trajectory_paths.call_args[0]
    assert (query_end - query_start).days == 59  # 30 current + 30 previous, inclusive
