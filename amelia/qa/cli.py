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
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

import typer
from langgraph.checkpoint.memory import MemorySaver
from loguru import logger

from amelia.qa.baseline import save_baseline
from amelia.qa.loader import DEFAULT_SCENARIO_DIR, load_scenarios
from amelia.qa.models import QaMode, QaReport, RunMetrics, ScenarioResult, Thresholds
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
    """Write each cell's metrics as the new baseline (A7 explicit action)."""
    for r in results:
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
    scenarios = load_scenarios(scenarios_dir, only=only)
    if not scenarios:
        typer.echo("No scenarios matched; nothing to run.", err=True)
        raise typer.Exit(code=1)

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
