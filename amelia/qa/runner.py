"""QA runner — drives scenarios through the full Amelia lifecycle in-process.

The runner is the production version of the e2e test flow
(:mod:`tests.integration.test_trajectory_end_to_end`): it calls
``OrchestratorService.start_workflow``, polls the workflows row until it
reaches the ``blocked`` approval gate, auto-approves, polls to a terminal
status, then reads the four workflow-row index columns
(``status``/``trajectory_path``/``total_cost_usd``/``total_tokens``/``total_duration_ms``)
into :class:`~amelia.qa.models.RunMetrics`.

Phase A (this module's live path) drives real drivers selected by key. Phase B
(Task 12) branches on ``mode == REPLAY`` to inject a :class:`ReplayDriver`
through the request-scoped ``driver_override`` seam (Task 10) — no monkeypatch.
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from amelia.qa.baseline import load_baseline
from amelia.qa.comparator import compare
from amelia.qa.models import (
    ComparisonOutcome,
    QaMode,
    QaReport,
    RunMetrics,
    Scenario,
    ScenarioResult,
)
from amelia.qa.replay import ReplayDriver, cassette_filename, load_cassette
from amelia.qa.report import build_report


if TYPE_CHECKING:
    from amelia.server.orchestrator.service import OrchestratorService


# Terminal workflow statuses (anything else means the run is still in flight).
_TERMINAL_STATUSES = {"completed", "failed", "cancelled"}

# Default per-cell poll timeout (seconds). Live DeepSeek driver calls can take
# several minutes end-to-end (architect -> developer -> reviewer), so this is
# deliberately generous; the scripted-driver integration path finishes in ~1s.
_DEFAULT_TIMEOUT = 600.0


async def _wait_for_status(
    orchestrator: OrchestratorService,
    workflow_id: uuid.UUID,
    status: str,
    timeout: float = _DEFAULT_TIMEOUT,
) -> None:
    """Poll the workflows row until it reaches *status* (or fail loudly).

    Reads via the orchestrator's workflow repository (the same repo the
    service uses). Used to wait for the ``blocked`` gate and for terminal
    statuses.

    Args:
        orchestrator: The :class:`OrchestratorService` driving the run.
        workflow_id: Workflow whose status to poll.
        status: Target status to wait for.
        timeout: Maximum seconds to wait.

    Raises:
        AssertionError: If *status* is not reached within *timeout*.
    """
    repo = orchestrator._repository
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    last_seen: str | None = None
    while loop.time() < deadline:
        row = await repo.get(workflow_id)
        if row is not None:
            last_seen = row.workflow_status
            if last_seen == status:
                return
        await asyncio.sleep(0.05)
    raise AssertionError(
        f"workflow {workflow_id} never reached {status!r} (last seen: {last_seen!r})"
    )


def _maybe_checkout_ref(scenario: Scenario) -> None:
    """Check out ``scenario.repo_ref`` in the worktree when pinned (A6).

    No-op when the scenario has no ``repo_ref``. Runs synchronously: a live
    run already blocks on driver calls, and a dirty-checkout failure should
    surface before the workflow starts.

    Args:
        scenario: Scenario whose worktree to prepare.

    Raises:
        ValueError: If the worktree path is missing or the checkout fails.
    """
    if not scenario.repo_ref:
        return
    if not scenario.worktree_path:
        raise ValueError(
            f"scenario {scenario.id!r} pins repo_ref but has no worktree_path"
        )
    import subprocess  # noqa: PLC0415

    try:
        subprocess.run(
            ["git", "checkout", scenario.repo_ref],
            cwd=scenario.worktree_path,
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as exc:
        raise ValueError(
            f"failed to check out repo_ref {scenario.repo_ref!r} for "
            f"scenario {scenario.id!r}: {exc.stderr!s}"
        ) from exc


async def _read_metrics(
    orchestrator: OrchestratorService, workflow_id: uuid.UUID
) -> RunMetrics:
    """Read the four index columns + status/trajectory_path into RunMetrics.

    Args:
        orchestrator: The service driving the run.
        workflow_id: Workflow whose terminal row to read.

    Returns:
        :class:`RunMetrics` built from the persisted index columns.
    """
    repo = orchestrator._repository
    row = await repo.get(workflow_id)
    if row is None:
        return RunMetrics(status="failed", trajectory_path=None)
    return RunMetrics(
        status=row.workflow_status,
        trajectory_path=row.trajectory_path,
        total_cost_usd=row.total_cost_usd,
        total_tokens=row.total_tokens,
        total_duration_ms=row.total_duration_ms,
    )


async def run_scenario(
    scenario: Scenario,
    driver: str,
    mode: QaMode,
    *,
    orchestrator: OrchestratorService,
    baseline_dir: Path,
    cassette_dir: Path | None = None,
    driver_override: object | None = None,
) -> ScenarioResult:
    """Drive one (scenario, driver) cell through the full lifecycle.

    Live path: calls ``start_workflow`` with the driver key, polls to the
    ``blocked`` gate, auto-approves, polls to terminal, reads metrics, and
    compares against the stored baseline (if any). Replay path (Task 12)
    injects a :class:`ReplayDriver` via ``driver_override``.

    A run that reaches ``failed`` is a normal result
    (``comparison.smoke_passed=False``), NOT an exception. Only infrastructure
    errors (DB down, approve on non-blocked) propagate.

    Args:
        scenario: Scenario to run.
        driver: Resolved driver key (e.g. ``"api"``).
        mode: QA execution mode (live / replay).
        orchestrator: The :class:`OrchestratorService` to drive.
        baseline_dir: Directory holding stored baselines.
        cassette_dir: Directory holding recorded cassettes (replay mode).
        driver_override: Optional pre-built driver to inject (replay mode).

    Returns:
        A :class:`ScenarioResult` for the cell.
    """
    assert scenario.worktree_path, (
        f"scenario {scenario.id!r} has no worktree_path"
    )

    _maybe_checkout_ref(scenario)

    effective_driver_override = driver_override
    if mode == QaMode.REPLAY and effective_driver_override is None:
        if cassette_dir is None:
            raise ValueError(
                f"replay: no cassette directory configured for {scenario.id}/{driver}"
            )
        cassette_path = cassette_dir / cassette_filename(scenario.id, driver)
        try:
            cassette = load_cassette(cassette_path)
        except FileNotFoundError as exc:
            raise ValueError(
                f"replay: no cassette for {scenario.id}/{driver} at {cassette_path}"
            ) from exc
        except ValueError as exc:
            raise ValueError(
                f"replay: invalid cassette for {scenario.id}/{driver}: {exc}"
            ) from exc
        effective_driver_override = ReplayDriver(cassette)

    svc = orchestrator
    start_kwargs: dict[str, object] = {
        "issue_id": scenario.issue_id or scenario.id,
        "worktree_path": scenario.worktree_path,
        "task_title": scenario.task_title,
        "task_description": scenario.task_description,
        "driver": driver,
    }
    if effective_driver_override is not None:
        start_kwargs["driver_override"] = effective_driver_override

    workflow_id = await svc.start_workflow(**start_kwargs)  # type: ignore[arg-type]
    logger.info(
        "QA scenario started",
        scenario_id=scenario.id,
        driver=driver,
        mode=mode.value,
        workflow_id=str(workflow_id),
    )

    await _wait_for_status(svc, workflow_id, "blocked")
    await svc.approve_workflow(workflow_id)

    # Poll to terminal.
    repo = svc._repository
    loop = asyncio.get_event_loop()
    deadline = loop.time() + _DEFAULT_TIMEOUT
    while loop.time() < deadline:
        row = await repo.get(workflow_id)
        if row is not None and row.workflow_status in _TERMINAL_STATUSES:
            break
        await asyncio.sleep(0.05)

    metrics = await _read_metrics(svc, workflow_id)

    baseline = load_baseline(baseline_dir, scenario.id, driver)
    comparison = compare(metrics, baseline) if baseline is not None else None

    return ScenarioResult(
        scenario_id=scenario.id,
        driver=driver,
        mode=mode,
        metrics=metrics,
        comparison=comparison,
    )


async def run_suite(
    scenarios: list[Scenario],
    drivers: list[str],
    mode: QaMode,
    *,
    orchestrator: OrchestratorService,
    baseline_dir: Path,
    cassette_dir: Path | None = None,
    max_concurrent: int | None = None,
) -> QaReport:
    """Run the (scenario x driver) matrix with bounded concurrency.

    ``drivers`` is the resolved list (the caller expands ``"all"``). For each
    scenario, only drivers present in both ``drivers`` and ``scenario.drivers``
    run (a scenario constrains its own matrix). A single cell raising an
    infrastructure error is captured as a ``failed`` result so the report
    still assembles — one broken cell must not sink the suite.

    Args:
        scenarios: Scenarios to run.
        drivers: Resolved driver keys to run.
        mode: QA execution mode.
        orchestrator: The :class:`OrchestratorService` to drive.
        baseline_dir: Directory holding stored baselines.
        cassette_dir: Directory holding recorded cassettes (replay mode).
        max_concurrent: Bound on concurrent cells (defaults to the
            orchestrator's ``max_concurrent``).

    Returns:
        The assembled :class:`QaReport`.
    """
    svc = orchestrator
    limit = max_concurrent if max_concurrent is not None else svc._max_concurrent
    semaphore = asyncio.Semaphore(max(1, limit))

    cells: list[tuple[Scenario, str]] = []
    for scenario in scenarios:
        for driver in drivers:
            if driver in scenario.drivers:
                cells.append((scenario, driver))

    async def _run_cell(scenario: Scenario, driver: str) -> ScenarioResult:
        async with semaphore:
            try:
                return await run_scenario(
                    scenario,
                    driver,
                    mode,
                    orchestrator=svc,
                    baseline_dir=baseline_dir,
                    cassette_dir=cassette_dir,
                )
            except Exception as exc:
                logger.exception(
                    "QA cell raised; recording as failed",
                    scenario_id=scenario.id,
                    driver=driver,
                )
                breach = str(exc) or exc.__class__.__name__
                return ScenarioResult(
                    scenario_id=scenario.id,
                    driver=driver,
                    mode=mode,
                    metrics=RunMetrics(status="failed", trajectory_path=None),
                    comparison=ComparisonOutcome(
                        passed=False,
                        smoke_passed=False,
                        breaches=[breach],
                        deltas={},
                    ),
                )

    results = await asyncio.gather(*[_run_cell(s, d) for s, d in cells])
    return build_report(list(results))
