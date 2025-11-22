import typer
import sys
from loguru import logger
import asyncio
from typing import Optional

from amelia.config import load_settings, validate_profile
from amelia.core.types import Profile, Settings, Issue
from amelia.core.orchestrator import create_orchestrator_graph, call_reviewer_node
from amelia.agents.project_manager import create_project_manager
from amelia.core.state import ExecutionState, AgentMessage
from amelia.agents.architect import Architect
from amelia.drivers.factory import DriverFactory
from langgraph.checkpoint.memory import MemorySaver
from amelia.tools.git import get_git_diff

app = typer.Typer(help="Amelia Agentic Orchestrator CLI")

def configure_logging():
    logger.remove()
    logger.add(sys.stderr, level="INFO")

@app.callback()
def main_callback():
    """
    Amelia: A local agentic coding system.
    """
    configure_logging()

def _get_active_profile(settings: Settings, profile_name: Optional[str]) -> Profile:
    if profile_name:
        if profile_name not in settings.profiles:
            typer.echo(f"Error: Profile '{profile_name}' not found in settings.", err=True)
            raise typer.Exit(code=1)
        return settings.profiles[profile_name]
    else:
        return settings.profiles[settings.active_profile]

def _safe_load_settings() -> Settings:
    try:
        return load_settings()
    except FileNotFoundError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)
    except Exception as e:
        typer.echo(f"Error loading settings: {e}", err=True)
        raise typer.Exit(code=1)

@app.command()
def start(
    ctx: typer.Context,
    issue_id: str = typer.Argument(..., help="The ID of the issue to work on (e.g., PROJ-123)."),
    profile_name: Optional[str] = typer.Option(
        None,
        "--profile",
        "-p",
        help="Specify the profile to use from settings.yaml."
    ),
):
    """
    Starts the Amelia orchestrator with the specified or default profile.
    """
    settings = _safe_load_settings()
    active_profile = _get_active_profile(settings, profile_name)
    
    try:
        validate_profile(active_profile)
    except ValueError as e:
        typer.echo(f"Profile validation failed: {e}", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"Starting Amelia with profile: {active_profile.name} (Driver: {active_profile.driver}, Tracker: {active_profile.tracker})")

    checkpoint_saver = MemorySaver() 
    
    app_graph = create_orchestrator_graph(checkpoint_saver=checkpoint_saver)
    
    # Get issue using ProjectManager
    project_manager = create_project_manager(active_profile)
    try:
        issue = project_manager.get_issue(issue_id)
    except ValueError as e:
        typer.echo(f"Error fetching issue: {e}", err=True)
        raise typer.Exit(code=1)

    # Prepare initial state
    initial_state = ExecutionState(profile=active_profile, issue=issue)
    
    # Run the orchestrator
    try:
        try:
            # Check if an event loop is already running (e.g., during tests)
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No running event loop, safe to use asyncio.run
            pass
            
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass

        asyncio.run(app_graph.ainvoke(initial_state))
    except RuntimeError as e:
        if "asyncio.run() cannot be called from a running event loop" in str(e):
            raise e
        typer.echo(f"An unexpected error occurred during orchestration: {e}", err=True)
        raise typer.Exit(code=1)
    except Exception as e:
        typer.echo(f"An unexpected error occurred during orchestration: {e}", err=True)
        raise typer.Exit(code=1)
    
@app.command(name="plan-only")
def plan_only_command(
    ctx: typer.Context,
    issue_id: str = typer.Argument(..., help="The ID of the issue to generate a plan for."),
    profile_name: Optional[str] = typer.Option(
        None, "--profile", "-p", help="Specify the profile to use from settings.yaml."
    ),
):
    """
    Generates a plan for the specified issue using the Architect agent without execution.
    """
    async def _run():
        settings = _safe_load_settings()
        active_profile = _get_active_profile(settings, profile_name)
        
        try:
            validate_profile(active_profile)
        except ValueError as e:
            typer.echo(f"Profile validation failed: {e}", err=True)
            raise typer.Exit(code=1)

        typer.echo(f"Generating plan for issue {issue_id} with profile: {active_profile.name}")

        project_manager = create_project_manager(active_profile)
        try:
            issue = project_manager.get_issue(issue_id)
        except ValueError as e:
            typer.echo(f"Error fetching issue: {e}", err=True)
            raise typer.Exit(code=1)

        architect = Architect(DriverFactory.get_driver(active_profile.driver))
        plan = await architect.plan(issue)
        
        typer.echo("\n--- GENERATED PLAN ---")
        if plan and plan.tasks:
            for task in plan.tasks:
                typer.echo(f"  - [{task.id}] {task.description} (Dependencies: {', '.join(task.dependencies)})")
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
    profile_name: Optional[str] = typer.Option(
        None,
        "--profile",
        "-p",
        help="Specify the profile to use from settings.yaml."
    ),
):
    """
    Triggers a review process for the current project.
    """
    async def _run():
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
            raise typer.Exit(code=1)

        if local:
            typer.echo("Reviewing local uncommitted changes...")
            try:
                code_changes = await get_git_diff(staged=False)
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
                raise typer.Exit(code=1)
        else:
            typer.echo("Please specify '--local' to review local changes or an issue ID for an orchestrator review (not yet implemented).", err=True)
            raise typer.Exit(code=1)
            
    asyncio.run(_run())

if __name__ == "__main__":
    app()