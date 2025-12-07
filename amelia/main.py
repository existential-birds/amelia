import asyncio

import typer
from langgraph.checkpoint.memory import MemorySaver

from amelia.agents.architect import Architect
from amelia.client.cli import (
    approve_command,
    cancel_command,
    reject_command,
    start_command,
    status_command,
)
from amelia.config import load_settings, validate_profile
from amelia.core.orchestrator import call_reviewer_node, create_orchestrator_graph
from amelia.core.state import ExecutionState
from amelia.core.types import Issue, Profile, Settings
from amelia.drivers.factory import DriverFactory
from amelia.logging import configure_logging
from amelia.server.cli import server_app
from amelia.server.dev import dev_app
from amelia.tools.shell_executor import run_shell_command
from amelia.trackers.factory import create_tracker
from amelia.utils.design_parser import parse_design


app = typer.Typer(help="Amelia Agentic Orchestrator CLI")
app.add_typer(server_app, name="server")
app.add_typer(dev_app, name="dev")
app.command(name="start", help="Start a workflow for an issue.")(start_command)
app.command(name="approve", help="Approve the workflow plan in the current worktree.")(approve_command)
app.command(name="reject", help="Reject the workflow plan in the current worktree.")(reject_command)
app.command(name="status", help="Show status of active workflows.")(status_command)
app.command(name="cancel", help="Cancel the active workflow in the current worktree.")(cancel_command)

@app.callback()
def main_callback() -> None:
    """
    Amelia: A local agentic coding system.
    """
    configure_logging()

def _get_active_profile(settings: Settings, profile_name: str | None) -> Profile:
    """Get the active profile from settings, either specified or default.

    Args:
        settings: Application settings containing profile configurations.
        profile_name: Optional specific profile name to use, or None for default.

    Returns:
        The requested Profile object.

    Raises:
        typer.Exit: If the specified profile name is not found in settings.
    """
    if profile_name:
        if profile_name not in settings.profiles:
            typer.echo(f"Error: Profile '{profile_name}' not found in settings.", err=True)
            raise typer.Exit(code=1)
        return settings.profiles[profile_name]
    else:
        return settings.profiles[settings.active_profile]

def _safe_load_settings() -> Settings:
    """Load settings from configuration file with error handling.

    Returns:
        Application settings loaded from YAML configuration.

    Raises:
        typer.Exit: If settings file is not found or fails to load.
    """
    try:
        return load_settings()
    except FileNotFoundError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from None
    except Exception as e:
        typer.echo(f"Error loading settings: {e}", err=True)
        raise typer.Exit(code=1) from None

@app.command(name="start-local")
def start_local(
    ctx: typer.Context,
    issue_id: str = typer.Argument(..., help="The ID of the issue to work on (e.g., PROJ-123)."),
    profile_name: str | None = typer.Option(
        None,
        "--profile",
        "-p",
        help="Specify the profile to use from settings.amelia.yaml."
    ),
) -> None:
    """Starts the Amelia orchestrator locally (without server).

    DEPRECATED: Use 'amelia server' and 'amelia start' instead.

    Args:
        ctx: Typer context (unused).
        issue_id: The ID of the issue to work on (e.g., PROJ-123).
        profile_name: Optional profile name to use from settings.amelia.yaml.

    Raises:
        typer.Exit: On validation failure or orchestration error.
    """
    settings = _safe_load_settings()
    active_profile = _get_active_profile(settings, profile_name)

    try:
        validate_profile(active_profile)
    except ValueError as e:
        typer.echo(f"Profile validation failed: {e}", err=True)
        raise typer.Exit(code=1) from None

    typer.echo(f"Starting Amelia with profile: {active_profile.name} (Driver: {active_profile.driver}, Tracker: {active_profile.tracker})")

    checkpoint_saver = MemorySaver()

    app_graph = create_orchestrator_graph(checkpoint_saver=checkpoint_saver)

    tracker = create_tracker(active_profile)
    try:
        issue = tracker.get_issue(issue_id)
    except ValueError as e:
        typer.echo(f"Error fetching issue: {e}", err=True)
        raise typer.Exit(code=1) from None

    # Prepare initial state
    initial_state = ExecutionState(profile=active_profile, issue=issue)

    # Run the orchestrator
    try:
        # check if there is a running event loop
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # If we are already in an async environment (e.g. tests), use the existing loop
            # This technically shouldn't happen with standard Typer usage but good for safety
             typer.echo("Warning: event loop already running, using existing loop", err=True)
             # We can't await here easily because start() is sync.
             # But Typer/Click commands are usually sync entry points.
             # If we really are in a loop, we might need a different approach or just fail.
             # For now, let's assume standard CLI usage where no loop exists yet.
             raise RuntimeError("Async event loop already running. Cannot use asyncio.run()")

        asyncio.run(app_graph.ainvoke(initial_state))

    except Exception as e:
        typer.echo(f"An unexpected error occurred during orchestration: {e}", err=True)
        raise typer.Exit(code=1) from None
    
@app.command(name="plan-only")
def plan_only_command(
    ctx: typer.Context,
    issue_id: str = typer.Argument(..., help="The ID of the issue to generate a plan for."),
    profile_name: str | None = typer.Option(
        None, "--profile", "-p", help="Specify the profile to use from settings.amelia.yaml."
    ),
    design_path: str | None = typer.Option(
        None, "--design", "-d", help="Path to design markdown file from brainstorming."
    ),
) -> None:
    """Generate a plan for an issue without executing it.

    Uses the Architect agent to analyze the issue and create a task DAG,
    saving the plan to a markdown file without proceeding to execution.

    Args:
        ctx: Typer context (unused).
        issue_id: The ID of the issue to generate a plan for.
        profile_name: Optional profile name to use from settings.amelia.yaml.
        design_path: Optional path to design markdown file from brainstorming.

    Raises:
        typer.Exit: On validation failure, issue fetch error, or planning error.
    """
    async def _run() -> None:
        """Async implementation of plan generation."""
        settings = _safe_load_settings()
        active_profile = _get_active_profile(settings, profile_name)
        
        try:
            validate_profile(active_profile)
        except ValueError as e:
            typer.echo(f"Profile validation failed: {e}", err=True)
            raise typer.Exit(code=1) from None

        typer.echo(f"Generating plan for issue {issue_id} with profile: {active_profile.name}")

        tracker = create_tracker(active_profile)
        try:
            issue = tracker.get_issue(issue_id)
        except ValueError as e:
            typer.echo(f"Error fetching issue: {e}", err=True)
            raise typer.Exit(code=1) from None

        # Parse design if provided
        design = None
        if design_path:
            try:
                driver = DriverFactory.get_driver(active_profile.driver)
                design = await parse_design(design_path, driver)
                typer.echo(f"Loaded design from: {design_path}")
            except FileNotFoundError:
                typer.echo(f"Error: Design file not found: {design_path}", err=True)
                raise typer.Exit(code=1) from None

        architect = Architect(DriverFactory.get_driver(active_profile.driver))
        result = await architect.plan(issue, design=design, output_dir=active_profile.plan_output_dir)
        
        typer.echo("\n--- GENERATED PLAN ---")
        if result.task_dag and result.task_dag.tasks:
            for task in result.task_dag.tasks:
                deps = f" (Dependencies: {', '.join(task.dependencies)})" if task.dependencies else ""
                typer.echo(f"  - [{task.id}] {task.description}{deps}")

            typer.echo(f"\nPlan saved to: {result.markdown_path}")
        else:
            typer.echo("No plan generated.")

    asyncio.run(_run())

@app.command()
def review(
    ctx: typer.Context,
    local: bool = typer.Option(
        False,
        "--local",
        "-l",
        help="Review local uncommitted changes (git diff)."
    ),
    profile_name: str | None = typer.Option(
        None,
        "--profile",
        "-p",
        help="Specify the profile to use from settings.amelia.yaml."
    ),
) -> None:
    """Trigger a code review process for the current project.

    Runs the Reviewer agent to analyze code changes and provide feedback
    on code quality, potential issues, and improvements.

    Args:
        ctx: Typer context (unused).
        local: If True, review local uncommitted changes from git diff.
        profile_name: Optional profile name to use from settings.amelia.yaml.

    Raises:
        typer.Exit: On validation failure or review error.
    """
    async def _run() -> None:
        """Async implementation of the review process."""
        typer.echo("Starting Amelia Review process...")
        
        settings = _safe_load_settings()
        
        if profile_name:
            if profile_name not in settings.profiles:
                typer.echo(f"Error: Profile '{profile_name}' not found in settings.", err=True)
                raise typer.Exit(code=1)
            active_profile = settings.profiles[profile_name]
        else:
            active_profile = settings.profiles[settings.active_profile]

        try:
            validate_profile(active_profile)
        except ValueError as e:
            typer.echo(f"Profile validation failed: {e}", err=True)
            raise typer.Exit(code=1) from None

        if local:
            typer.echo("Reviewing local uncommitted changes...")
            try:
                code_changes = await run_shell_command("git diff")
                if not code_changes:
                    typer.echo("No local uncommitted changes found to review.", err=True)
                    raise typer.Exit(code=0) # Exit gracefully if nothing to review
                typer.echo(f"Found local changes (first 500 chars):\n{code_changes[:500]}...")
                
                # Create a dummy issue for review context
                dummy_issue = Issue(id="LOCAL-REVIEW", title="Local Code Review", description="Review local uncommitted changes.")
                
                # Create an initial state for review
                initial_state = ExecutionState(
                    profile=active_profile, 
                    issue=dummy_issue,
                    code_changes_for_review=code_changes
                )
                
                # Directly call the reviewer node, it will use the driver from profile
                result_state = await call_reviewer_node(initial_state)
                
                if result_state.review_results:
                    review_result = result_state.review_results[-1]
                    typer.echo(f"\n--- REVIEW RESULT ({review_result.reviewer_persona}) ---")
                    typer.echo(f"Approved: {review_result.approved}")
                    typer.echo(f"Severity: {review_result.severity}")
                    typer.echo("Comments:")
                    for comment in review_result.comments:
                        typer.echo(f"- {comment}")
                else:
                    typer.echo("No review results obtained.")

            except RuntimeError as e:
                typer.echo(f"Error getting local changes: {e}", err=True)
                raise typer.Exit(code=1) from None
        else:
            typer.echo("Please specify '--local' to review local changes or an issue ID for an orchestrator review (not yet implemented).", err=True)
            raise typer.Exit(code=1)
            
    asyncio.run(_run())

if __name__ == "__main__":
    app()