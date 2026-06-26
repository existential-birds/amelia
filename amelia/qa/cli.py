"""``amelia qa`` Typer sub-app — the agent-launchable entrypoint.

Exposes ``amelia qa run``: a non-interactive command that loads the
scenario corpus, builds an in-process :class:`OrchestratorService`, drives
the (scenario x driver) matrix through the lifecycle via
:func:`~amelia.qa.runner.run_suite`, then prints a human table and exits
with the report's pass/fail code. Optional ``--json-out`` writes the
machine-readable report. ``--rebaseline`` writes each cell's metrics as
the new baseline (A7).
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

import typer
from langgraph.checkpoint.memory import MemorySaver
from loguru import logger

from amelia.qa.baseline import save_baseline
from amelia.qa.loader import DEFAULT_SCENARIO_DIR, load_scenarios
from amelia.qa.models import (
    QaMode,
    QaReport,
    RunMetrics,
    Scenario,
    ScenarioResult,
    Thresholds,
)
from amelia.qa.replay import record_cassette_from_recorder, save_cassette
from amelia.qa.report import exit_code, render_table
from amelia.qa.runner import run_suite


# Known driver keys. ``--driver all`` expands to this list.
_KNOWN_DRIVERS: list[str] = ["api", "claude", "codex"]


qa_app = typer.Typer(
    name="qa",
    help="Automated QA harness — drive scenarios through the lifecycle unattended.",
)


def _resolve_drivers(driver: str) -> list[str]:
    """Expand the ``--driver`` flag to a concrete list of driver keys.

    ``all`` resolves to every known driver; any other value is treated as
    a literal key (validated against the known set so a typo doesn't
    silently run nothing).
    """
    if driver == "all":
        return list(_KNOWN_DRIVERS)
    if driver not in _KNOWN_DRIVERS:
        raise typer.BadParameter(
            f"Unknown driver {driver!r}. Expected one of "
            f"{', '.join(_KNOWN_DRIVERS)} or 'all'."
        )
    return [driver]


def _require_matching_cells(scenarios: list[Scenario], drivers: list[str]) -> None:
    """Fail loudly when no (scenario x driver) cell matches the requested drivers.

    ``run_suite`` silently produces an empty report when a requested driver is
    not opted into by any scenario (the matrix intersects to zero cells). That
    surfaces as a confusing empty table with ``OVERALL: FAIL`` and no
    explanation. This guard turns it into an actionable error that lists which
    drivers each scenario actually supports.
    """
    requested = set(drivers)
    if any(requested & set(s.drivers) for s in scenarios):
        return
    supported = ", ".join(
        f"{s.id} -> {', '.join(s.drivers)}" for s in scenarios
    )
    raise typer.BadParameter(
        f"No scenario opts into driver(s) {', '.join(drivers)}. "
        f"Supported (scenario -> drivers): {supported}. "
        f"Add the driver to a scenario's 'drivers:' list or pick a supported one."
    )


def _ensure_default_worktrees(scenarios: list[Scenario]) -> list[Scenario]:
    """Materialize scratch git worktrees for scenarios that omit one.

    Bundled scenarios intentionally keep ``worktree_path`` null so they are
    portable across machines. The agent-launchable CLI resolves those nulls
    to deterministic scratch repositories under the current checkout before
    handing scenarios to the runner.
    """
    prepared: list[Scenario] = []
    root = Path.cwd() / ".hermes" / "scratch" / "qa-worktrees"
    scratch_root = root.resolve()
    for scenario in scenarios:
        if scenario.worktree_path is not None:
            prepared.append(scenario)
            continue

        worktree = (scratch_root / scenario.id).resolve()
        try:
            worktree.relative_to(scratch_root)
        except ValueError:
            raise ValueError(
                f"scenario id {scenario.id!r} resolves outside QA scratch directory"
            ) from None
        worktree.mkdir(parents=True, exist_ok=True)
        (worktree / "README.md").write_text("# QA scratch worktree\n", encoding="utf-8")
        (worktree / "settings.amelia.yaml").write_text(
            "active_profile: test\n"
            "profiles:\n"
            "  test:\n"
            "    name: test\n"
            "    driver: api\n"
            "    model: replay\n"
            "    validator_model: replay\n"
            "    tracker: noop\n"
            "    strategy: single\n",
            encoding="utf-8",
        )
        if not (worktree / ".git").exists():
            subprocess.run(["git", "init"], cwd=worktree, check=True, capture_output=True)
            subprocess.run(
                ["git", "config", "user.email", "qa@example.com"],
                cwd=worktree,
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "QA Harness"],
                cwd=worktree,
                check=True,
                capture_output=True,
            )
        branches = subprocess.run(
            ["git", "for-each-ref", "--format=%(refname:short)", "refs/heads"],
            cwd=worktree,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
        base_branch = next((b for b in branches if not b.startswith("amelia/")), "main")
        subprocess.run(
            ["git", "checkout", "-B", base_branch],
            cwd=worktree,
            check=True,
            capture_output=True,
        )
        for branch in branches:
            if branch.startswith("amelia/"):
                subprocess.run(
                    ["git", "branch", "-D", branch],
                    cwd=worktree,
                    check=False,
                    capture_output=True,
                )
        subprocess.run(["git", "add", "."], cwd=worktree, check=True, capture_output=True)
        subprocess.run(
            [
                "git",
                "commit",
                "--allow-empty",
                "--no-gpg-sign",
                "--no-verify",
                "-m",
                "Initialize QA scratch worktree",
            ],
            cwd=worktree,
            check=True,
            capture_output=True,
        )
        subprocess.run(["git", "checkout", "--", "."], cwd=worktree, check=True, capture_output=True)
        subprocess.run(["git", "clean", "-fd"], cwd=worktree, check=True, capture_output=True)
        prepared.append(scenario.model_copy(update={"worktree_path": str(worktree)}))
    return prepared


@asynccontextmanager
async def _build_orchestrator() -> AsyncIterator[Any]:
    """Construct an in-process OrchestratorService against real Postgres.

    Mirrors the integration-test wiring: real repos from
    :class:`~amelia.server.config.ServerConfig`, ``MemorySaver``
    checkpointer, and the configured trajectory dir. The database pool is
    tied to this context so it closes cleanly after the suite.
    """
    from amelia.server.config import ServerConfig  # noqa: PLC0415
    from amelia.server.database.connection import Database  # noqa: PLC0415
    from amelia.server.database.profile_repository import (  # noqa: PLC0415
        ProfileRepository,
    )
    from amelia.server.database.repository import WorkflowRepository  # noqa: PLC0415
    from amelia.server.events.bus import EventBus  # noqa: PLC0415
    from amelia.server.events.connection_manager import (  # noqa: PLC0415
        ConnectionManager,
    )
    from amelia.server.orchestrator.service import (  # noqa: PLC0415
        OrchestratorService,
    )

    config = ServerConfig()
    db = Database(
        config.database_url,
        min_size=config.db_pool_min_size,
        max_size=config.db_pool_max_size,
    )
    await db.connect()
    try:
        bus = EventBus(buffer_size=config.event_bus_buffer_size)
        bus.set_connection_manager(ConnectionManager())
        repository = WorkflowRepository(db)
        profile_repo = ProfileRepository(db)
        service = OrchestratorService(
            event_bus=bus,
            repository=repository,
            profile_repo=profile_repo,
            checkpointer=MemorySaver(),
            trajectory_dir=config.trajectory_dir,
        )
        try:
            yield service
        finally:
            await service.cancel_all_workflows(timeout=5.0)
    finally:
        await db.close()


def _write_json(report: QaReport, path: Path) -> None:
    """Write the report as JSON via Pydantic ``model_dump`` (mode="json")."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.model_dump(mode="json"), indent=2))


def _rebaseline(results: list[ScenarioResult], baseline_dir: Path) -> None:
    """Write each cell's metrics as the new baseline (A7 explicit action).

    Only ``completed`` cells are rebaselined — persisting a failed/cancelled
    run as the new gold standard would silently enshrine a regression. Each
    skipped cell is logged so an operator notices a run that was supposed to
    refresh baselines but mostly failed.
    """
    for r in results:
        if r.metrics.status != "completed":
            logger.warning(
                "Skipping rebaseline for non-completed cell",
                scenario_id=r.scenario_id,
                driver=r.driver,
                status=r.metrics.status,
            )
            continue
        save_baseline(
            baseline_dir,
            r.scenario_id,
            r.driver,
            RunMetrics(
                status=r.metrics.status,
                trajectory_path=r.metrics.trajectory_path,
                total_cost_usd=r.metrics.total_cost_usd,
                total_tokens=r.metrics.total_tokens,
                total_duration_ms=r.metrics.total_duration_ms,
            ),
            Thresholds(),
        )
        logger.info(
            "Rebaselined cell",
            scenario_id=r.scenario_id,
            driver=r.driver,
            baseline_dir=str(baseline_dir),
        )


def _write_cassettes(results: list[ScenarioResult], cassette_dir: Path) -> int:
    """Write replay cassettes from finalized trajectory files.

    Live workflow finalization removes recorders from the orchestrator's active
    registry, so the record command rebuilds a ``WorkflowTrajectoryRecorder``
    from each result's finalized ``trajectory.json`` and asks the Task 9
    cassette converter to serialize the subagent invocations.
    """
    from amelia.trajectory.recorder import WorkflowTrajectoryRecorder  # noqa: PLC0415

    written = 0
    for r in results:
        if r.metrics.trajectory_path is None:
            logger.warning(
                "Skipping cassette for cell with no trajectory",
                scenario_id=r.scenario_id,
                driver=r.driver,
            )
            continue
        path = Path(r.metrics.trajectory_path)
        try:
            workflow_id = uuid.UUID(path.parent.name)
        except ValueError:
            logger.warning(
                "Skipping cassette for trajectory with non-UUID parent",
                scenario_id=r.scenario_id,
                driver=r.driver,
                trajectory_path=str(path),
            )
            continue
        recorder = WorkflowTrajectoryRecorder(
            workflow_id=workflow_id,
            trajectory_dir=path.parent.parent,
            profile_snapshot={},
        )
        cassette = record_cassette_from_recorder(recorder, r.scenario_id, r.driver)
        save_cassette(cassette_dir, cassette)
        written += 1
    return written


@qa_app.command("run")
def run(
    driver: Annotated[
        str,
        typer.Option(
            "--driver",
            "-d",
            help="Driver key (api/claude/codex) or 'all' (default: all).",
        ),
    ] = "all",
    mode: Annotated[
        str,
        typer.Option(
            "--mode",
            "-m",
            help="Execution mode: 'live' (real drivers) or 'replay' (cassettes).",
        ),
    ] = "live",
    scenario: Annotated[
        list[str] | None,
        typer.Option(
            "--scenario",
            "-s",
            help="Scenario id to run (repeatable). Default: all bundled scenarios.",
        ),
    ] = None,
    json_out: Annotated[
        Path | None,
        typer.Option("--json-out", help="Path to write the machine-readable report."),
    ] = None,
    baseline_dir: Annotated[
        Path,
        typer.Option(
            "--baseline-dir",
            help="Directory holding stored baselines.",
        ),
    ] = DEFAULT_SCENARIO_DIR.parent / "baselines",
    cassette_dir: Annotated[
        Path,
        typer.Option(
            "--cassette-dir",
            help="Directory holding recorded cassettes (replay mode).",
        ),
    ] = DEFAULT_SCENARIO_DIR.parent / "cassettes",
    scenarios_dir: Annotated[
        Path,
        typer.Option(
            "--scenarios-dir",
            help="Directory holding scenario YAML files.",
        ),
    ] = DEFAULT_SCENARIO_DIR,
    rebaseline: Annotated[
        bool,
        typer.Option(
            "--rebaseline",
            help="After the run, write each cell's metrics as the new baseline.",
        ),
    ] = False,
) -> None:
    """Run the QA suite over the scenario corpus.

    Loads scenarios, drives each (scenario x driver) cell through the
    full Amelia lifecycle, compares against the stored baseline, and
    exits 0 on overall pass / 1 on any failure. Agent-launchable:
    non-interactive, all input via flags.
    """
    try:
        qa_mode = QaMode(mode)
    except ValueError as exc:
        raise typer.BadParameter(
            f"Invalid mode {mode!r}; expected 'live' or 'replay'."
        ) from exc

    drivers = _resolve_drivers(driver)
    only = set(scenario) if scenario else None
    scenarios = _ensure_default_worktrees(load_scenarios(scenarios_dir, only=only))
    if not scenarios:
        typer.echo("No scenarios matched; nothing to run.", err=True)
        raise typer.Exit(code=1)
    _require_matching_cells(scenarios, drivers)

    async def _run() -> QaReport:
        async with _build_orchestrator() as svc:
            return await run_suite(
                scenarios,
                drivers=drivers,
                mode=qa_mode,
                orchestrator=svc,
                baseline_dir=baseline_dir,
                cassette_dir=cassette_dir,
            )

    report = asyncio.run(_run())

    if rebaseline:
        _rebaseline(report.results, baseline_dir)

    typer.echo(render_table(report))
    if json_out is not None:
        _write_json(report, json_out)
    raise typer.Exit(code=exit_code(report))


@qa_app.command("record")
def record(
    driver: Annotated[
        str,
        typer.Option(
            "--driver",
            "-d",
            help="Driver key (api/claude/codex) or 'all' (default: all).",
        ),
    ] = "all",
    scenario: Annotated[
        list[str] | None,
        typer.Option(
            "--scenario",
            "-s",
            help="Scenario id to record (repeatable). Default: all bundled scenarios.",
        ),
    ] = None,
    json_out: Annotated[
        Path | None,
        typer.Option("--json-out", help="Path to write the live-run report."),
    ] = None,
    baseline_dir: Annotated[
        Path,
        typer.Option(
            "--baseline-dir",
            help="Directory holding stored baselines for the live run comparison.",
        ),
    ] = DEFAULT_SCENARIO_DIR.parent / "baselines",
    cassette_dir: Annotated[
        Path,
        typer.Option(
            "--cassette-dir",
            help="Directory to write recorded replay cassettes.",
        ),
    ] = DEFAULT_SCENARIO_DIR.parent / "cassettes",
    scenarios_dir: Annotated[
        Path,
        typer.Option(
            "--scenarios-dir",
            help="Directory holding scenario YAML files.",
        ),
    ] = DEFAULT_SCENARIO_DIR,
) -> None:
    """Run the QA suite live once and write replay cassettes.

    This is the production recording path for replay mode. The run is live
    (real drivers), non-interactive, and writes one cassette per cell that
    produced a finalized trajectory.
    """
    drivers = _resolve_drivers(driver)
    only = set(scenario) if scenario else None
    scenarios = _ensure_default_worktrees(load_scenarios(scenarios_dir, only=only))
    if not scenarios:
        typer.echo("No scenarios matched; nothing to record.", err=True)
        raise typer.Exit(code=1)
    _require_matching_cells(scenarios, drivers)

    async def _run() -> QaReport:
        async with _build_orchestrator() as svc:
            return await run_suite(
                scenarios,
                drivers=drivers,
                mode=QaMode.LIVE,
                orchestrator=svc,
                baseline_dir=baseline_dir,
                cassette_dir=cassette_dir,
            )

    report = asyncio.run(_run())
    written = _write_cassettes(report.results, cassette_dir)

    typer.echo(render_table(report))
    typer.echo(f"Wrote {written} cassette(s) to {cassette_dir}")
    if json_out is not None:
        _write_json(report, json_out)

    any_failed = any(r.metrics.status != "completed" for r in report.results)
    raise typer.Exit(code=1 if any_failed or written == 0 else 0)
