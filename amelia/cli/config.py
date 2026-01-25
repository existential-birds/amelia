"""CLI commands for configuration management.

Provides commands for managing profiles and server settings through the CLI.
"""

import asyncio
import os
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from amelia.core.types import AgentConfig, DriverType, Profile, TrackerType
from amelia.server.config import ServerConfig
from amelia.server.database import (
    Database,
    ProfileRepository,
    SettingsRepository,
)


console = Console()

config_app = typer.Typer(
    name="config",
    help="Configuration management commands.",
)

profile_app = typer.Typer(
    name="profile",
    help="Profile management commands.",
)

server_app = typer.Typer(
    name="server",
    help="Server settings commands.",
)

config_app.add_typer(profile_app, name="profile")
config_app.add_typer(server_app, name="server")


def get_database() -> Database:
    """Create a Database instance from ServerConfig.

    Returns:
        Database instance configured with the path from ServerConfig.
    """
    config = ServerConfig()
    return Database(config.database_path)


async def _get_profile_repository() -> tuple[Database, ProfileRepository]:
    """Get connected ProfileRepository.

    Returns:
        Tuple of (Database, ProfileRepository) with connected database.
    """
    db = get_database()
    await db.connect()
    await db.ensure_schema()
    return db, ProfileRepository(db)


async def _get_settings_repository() -> tuple[Database, SettingsRepository]:
    """Get connected SettingsRepository.

    Returns:
        Tuple of (Database, SettingsRepository) with connected database.
    """
    db = get_database()
    await db.connect()
    await db.ensure_schema()
    repo = SettingsRepository(db)
    await repo.ensure_defaults()
    return db, repo


VALID_DRIVERS: set[DriverType] = {
    DriverType.CLI,
    DriverType.API,
}
VALID_TRACKERS: set[TrackerType] = {
    TrackerType.JIRA,
    TrackerType.GITHUB,
    TrackerType.NOOP,
}


def _validate_driver(value: str) -> DriverType:
    """Validate and cast a string to DriverType.

    Args:
        value: The driver string from user input.

    Returns:
        The validated DriverType.

    Raises:
        typer.BadParameter: If the driver is invalid.
    """
    if value not in VALID_DRIVERS:
        raise typer.BadParameter(
            f"Invalid driver '{value}'. Valid options: {sorted(VALID_DRIVERS)}"
        )
    return value  # type: ignore[return-value]


def _validate_tracker(value: str) -> TrackerType:
    """Validate and cast a string to TrackerType.

    Args:
        value: The tracker string from user input.

    Returns:
        The validated TrackerType.

    Raises:
        typer.BadParameter: If the tracker is invalid.
    """
    if value not in VALID_TRACKERS:
        raise typer.BadParameter(
            f"Invalid tracker '{value}'. Valid options: {sorted(VALID_TRACKERS)}"
        )
    return value  # type: ignore[return-value]


def _build_default_agents(driver: DriverType, model: str) -> dict[str, AgentConfig]:
    """Build default agents dict for a profile.

    Args:
        driver: Driver to use for all agents (converted to DriverType enum).
        model: Model to use for all agents.

    Returns:
        Dict mapping agent names to AgentConfig.
    """
    driver_type = DriverType(driver)
    return {
        "architect": AgentConfig(driver=driver_type, model=model),
        "developer": AgentConfig(driver=driver_type, model=model),
        "reviewer": AgentConfig(driver=driver_type, model=model),
        "task_reviewer": AgentConfig(driver=driver_type, model=model),
        "evaluator": AgentConfig(driver=driver_type, model=model),
        "brainstormer": AgentConfig(driver=driver_type, model=model),
        "plan_validator": AgentConfig(driver=driver_type, model=model),
    }


# =============================================================================
# Profile Commands
# =============================================================================


@profile_app.command("list")
def profile_list() -> None:
    """List all profiles."""
    async def _run() -> None:
        db, repo = await _get_profile_repository()
        try:
            profiles = await repo.list_profiles()

            if not profiles:
                console.print("[yellow]No profiles found.[/yellow]")
                console.print(
                    "\nCreate a profile with: [bold]amelia config profile create <name>[/bold]"
                )
                return

            table = Table(title="Profiles")
            table.add_column("Name", style="cyan")
            table.add_column("Driver", style="green")
            table.add_column("Model", style="blue")
            table.add_column("Tracker", style="magenta")
            table.add_column("Agents", style="yellow")

            for profile in profiles:
                # Get driver/model from first agent for display
                display_driver: str = "-"
                display_model: str = "-"
                if profile.agents:
                    first_agent = next(iter(profile.agents.values()))
                    display_driver = first_agent.driver
                    display_model = first_agent.model
                table.add_row(
                    profile.name,
                    display_driver,
                    display_model,
                    profile.tracker,
                    str(len(profile.agents)),
                )

            console.print(table)
        finally:
            await db.close()

    asyncio.run(_run())


@profile_app.command("show")
def profile_show(
    name: Annotated[str, typer.Argument(help="Profile name to show")],
) -> None:
    """Show details of a specific profile."""
    async def _run() -> None:
        db, repo = await _get_profile_repository()
        try:
            profile = await repo.get_profile(name)

            if profile is None:
                console.print(f"[red]Profile '{name}' not found.[/red]")
                raise typer.Exit(code=1)

            table = Table(title=f"Profile: {profile.name}")
            table.add_column("Field", style="cyan")
            table.add_column("Value", style="white")

            table.add_row("Tracker", profile.tracker)
            table.add_row("Working Dir", profile.working_dir)
            table.add_row("Plan Output Dir", profile.plan_output_dir)
            table.add_row("Plan Path Pattern", profile.plan_path_pattern)

            console.print(table)

            # Show agents table
            if profile.agents:
                agents_table = Table(title="Agent Configurations")
                agents_table.add_column("Agent", style="cyan")
                agents_table.add_column("Driver", style="green")
                agents_table.add_column("Model", style="blue")
                agents_table.add_column("Options", style="magenta")

                for agent_name, agent_config in profile.agents.items():
                    options_str = str(agent_config.options) if agent_config.options else "-"
                    agents_table.add_row(
                        agent_name,
                        agent_config.driver,
                        agent_config.model,
                        options_str,
                    )

                console.print(agents_table)
        finally:
            await db.close()

    asyncio.run(_run())


@profile_app.command("create")
def profile_create(
    name: Annotated[str, typer.Argument(help="Profile name")],
    driver: Annotated[
        str | None,
        typer.Option("--driver", "-d", help="Driver (cli or api)"),
    ] = None,
    model: Annotated[
        str | None,
        typer.Option("--model", "-m", help="Model name"),
    ] = None,
    tracker: Annotated[
        str | None,
        typer.Option("--tracker", "-t", help="Issue tracker (noop, github, jira)"),
    ] = None,
    working_dir: Annotated[
        str | None,
        typer.Option("--working-dir", "-w", help="Working directory path"),
    ] = None,
    activate: Annotated[
        bool,
        typer.Option("--activate", "-a", help="Set as active profile"),
    ] = False,
) -> None:
    """Create a new profile.

    If options are not provided, prompts interactively.
    Creates default agent configurations using the specified driver and model.
    """
    # Interactive prompts if options not provided
    if driver is None:
        driver = typer.prompt(
            "Driver",
            default="cli",
            show_default=True,
        )
    if model is None:
        model = typer.prompt(
            "Model",
            default="sonnet",
            show_default=True,
        )
    if tracker is None:
        tracker = typer.prompt(
            "Tracker",
            default="noop",
            show_default=True,
        )
    if working_dir is None:
        working_dir = typer.prompt(
            "Working directory",
            default=os.getcwd(),
            show_default=True,
        )

    async def _run() -> None:
        db, repo = await _get_profile_repository()
        try:
            # Check if profile already exists
            existing = await repo.get_profile(name)
            if existing:
                console.print(f"[red]Profile '{name}' already exists.[/red]")
                raise typer.Exit(code=1)

            # At this point, all optional values have been filled via prompts
            assert driver is not None
            assert model is not None
            assert tracker is not None
            assert working_dir is not None

            # Validate and cast to proper types
            validated_driver = _validate_driver(driver)
            validated_tracker = _validate_tracker(tracker)

            # Build default agents configuration
            agents = _build_default_agents(validated_driver, model)

            profile = Profile(
                name=name,
                tracker=validated_tracker,
                working_dir=working_dir,
                agents=agents,
            )

            created = await repo.create_profile(profile)
            console.print(f"[green]Profile '{created.name}' created successfully.[/green]")

            if activate:
                await repo.set_active(name)
                console.print(f"[green]Profile '{created.name}' is now active.[/green]")
        finally:
            await db.close()

    asyncio.run(_run())


@profile_app.command("delete")
def profile_delete(
    name: Annotated[str, typer.Argument(help="Profile name to delete")],
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Skip confirmation"),
    ] = False,
) -> None:
    """Delete a profile."""
    if not force:
        confirm = typer.confirm(f"Delete profile '{name}'?")
        if not confirm:
            console.print("[yellow]Cancelled.[/yellow]")
            raise typer.Exit(code=0)

    async def _run() -> None:
        db, repo = await _get_profile_repository()
        try:
            deleted = await repo.delete_profile(name)
            if deleted:
                console.print(f"[green]Profile '{name}' deleted.[/green]")
            else:
                console.print(f"[red]Profile '{name}' not found.[/red]")
                raise typer.Exit(code=1)
        finally:
            await db.close()

    asyncio.run(_run())


@profile_app.command("activate")
def profile_activate(
    name: Annotated[str, typer.Argument(help="Profile name to activate")],
) -> None:
    """Set a profile as active."""
    async def _run() -> None:
        db, repo = await _get_profile_repository()
        try:
            await repo.set_active(name)
            console.print(f"[green]Profile '{name}' is now active.[/green]")
        except ValueError as e:
            console.print(f"[red]{e}[/red]")
            raise typer.Exit(code=1) from None
        finally:
            await db.close()

    asyncio.run(_run())


# =============================================================================
# First-Run Setup
# =============================================================================


async def check_and_run_first_time_setup() -> bool:
    """Check if this is first run and prompt for profile creation.

    Returns:
        True if setup completed or not needed, False if user cancelled.
    """
    db, repo = await _get_profile_repository()
    try:
        profiles = await repo.list_profiles()

        if profiles:
            return True  # Not first run

        console.print(
            "[yellow]No profiles configured. Let's create your first profile.[/yellow]\n"
        )

        name = typer.prompt("Profile name", default="dev")
        driver_input = typer.prompt("Driver (cli or api)", default="cli")
        model = typer.prompt("Model", default="opus")
        working_dir = typer.prompt("Working directory", default=str(Path.cwd()))

        # Validate driver
        validated_driver = _validate_driver(driver_input)

        # Build default agents configuration
        agents = _build_default_agents(validated_driver, model)

        profile = Profile(
            name=name,
            tracker=TrackerType.NOOP,
            working_dir=working_dir,
            agents=agents,
        )

        await repo.create_profile(profile)
        await repo.set_active(name)

        console.print(f"\n[green]Profile '{name}' created and set as active.[/green]")
        return True
    finally:
        await db.close()


def run_first_time_setup() -> bool:
    """Sync wrapper for first-time setup.

    Returns:
        True if setup completed or not needed, False if user cancelled.
    """
    return asyncio.run(check_and_run_first_time_setup())


# =============================================================================
# Server Settings Commands
# =============================================================================


@server_app.command("show")
def server_show() -> None:
    """Show current server settings."""
    async def _run() -> None:
        db, repo = await _get_settings_repository()
        try:
            settings = await repo.get_server_settings()

            table = Table(title="Server Settings")
            table.add_column("Setting", style="cyan")
            table.add_column("Value", style="white")

            table.add_row("Log Retention Days", str(settings.log_retention_days))
            table.add_row(
                "Log Retention Max Events", str(settings.log_retention_max_events)
            )
            table.add_row("Trace Retention Days", str(settings.trace_retention_days))
            table.add_row(
                "Checkpoint Retention Days", str(settings.checkpoint_retention_days)
            )
            table.add_row("Checkpoint Path", settings.checkpoint_path)
            table.add_row(
                "WebSocket Idle Timeout (s)",
                str(settings.websocket_idle_timeout_seconds),
            )
            table.add_row(
                "Workflow Start Timeout (s)",
                str(settings.workflow_start_timeout_seconds),
            )
            table.add_row("Max Concurrent Workflows", str(settings.max_concurrent))
            table.add_row("Stream Tool Results", str(settings.stream_tool_results))
            table.add_row("Created", settings.created_at.isoformat())
            table.add_row("Updated", settings.updated_at.isoformat())

            console.print(table)
        finally:
            await db.close()

    asyncio.run(_run())


@server_app.command("set")
def server_set(
    setting: Annotated[str, typer.Argument(help="Setting name")],
    value: Annotated[str, typer.Argument(help="New value")],
) -> None:
    """Set a server setting value.

    Valid settings:
    - log_retention_days (int)
    - log_retention_max_events (int)
    - trace_retention_days (int)
    - checkpoint_retention_days (int)
    - checkpoint_path (str)
    - websocket_idle_timeout_seconds (float)
    - workflow_start_timeout_seconds (float)
    - max_concurrent (int)
    - stream_tool_results (bool: true/false)
    """
    # Convert value to appropriate type
    int_fields = {
        "log_retention_days",
        "log_retention_max_events",
        "trace_retention_days",
        "checkpoint_retention_days",
        "max_concurrent",
    }
    float_fields = {"websocket_idle_timeout_seconds", "workflow_start_timeout_seconds"}
    bool_fields = {"stream_tool_results"}
    str_fields = {"checkpoint_path"}

    parsed_value: int | float | bool | str
    try:
        if setting in int_fields:
            parsed_value = int(value)
        elif setting in float_fields:
            parsed_value = float(value)
        elif setting in bool_fields:
            value_lower = value.lower()
            if value_lower in ("true", "1", "yes"):
                parsed_value = True
            elif value_lower in ("false", "0", "no"):
                parsed_value = False
            else:
                console.print(
                    f"[red]Invalid boolean for {setting}: {value}. "
                    "Use true/false, yes/no, or 1/0.[/red]"
                )
                raise typer.Exit(code=1)
        elif setting in str_fields:
            parsed_value = value
        else:
            console.print(f"[red]Unknown setting: {setting}[/red]")
            console.print("\nValid settings:")
            all_fields = int_fields | float_fields | bool_fields | str_fields
            for field in sorted(all_fields):
                console.print(f"  - {field}")
            raise typer.Exit(code=1)
    except ValueError:
        console.print(f"[red]Invalid value for {setting}: {value}[/red]")
        raise typer.Exit(code=1) from None

    async def _run() -> None:
        db, repo = await _get_settings_repository()
        try:
            await repo.update_server_settings({setting: parsed_value})
            console.print(f"[green]Set {setting} = {parsed_value}[/green]")
        except ValueError as e:
            console.print(f"[red]{e}[/red]")
            raise typer.Exit(code=1) from None
        finally:
            await db.close()

    asyncio.run(_run())
