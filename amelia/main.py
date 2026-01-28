import asyncio
import os

import typer

from amelia.cli.config import config_app
from amelia.client.api import (
    AmeliaClient,
    InvalidRequestError,
    ServerUnreachableError,
    WorkflowConflictError,
)
from amelia.client.cli import (
    approve_command,
    cancel_command,
    plan_command,
    reject_command,
    resume_command,
    run_command,
    start_command,
    status_command,
)
from amelia.client.streaming import stream_workflow_events
from amelia.logging import configure_logging
from amelia.server.cli import server_app
from amelia.server.dev import dev_app
from amelia.tools.shell_executor import run_shell_command


app = typer.Typer(help="Amelia Agentic Orchestrator CLI")
app.add_typer(config_app, name="config")
app.add_typer(server_app, name="server")
app.add_typer(dev_app, name="dev")
app.command(name="start", help="Start a workflow for an issue.")(start_command)
app.command(name="plan", help="Generate a plan for an issue without executing.")(plan_command)
app.command(name="approve", help="Approve the workflow plan in the current worktree.")(approve_command)
app.command(name="reject", help="Reject the workflow plan in the current worktree.")(reject_command)
app.command(name="status", help="Show status of active workflows.")(status_command)
app.command(name="cancel", help="Cancel the active workflow in the current worktree.")(cancel_command)
app.command(name="resume", help="Resume a failed workflow from checkpoint.")(resume_command)
app.command(name="run", help="Start pending workflow(s).")(run_command)

@app.callback()
def main_callback() -> None:
    """Initialize the Amelia CLI application.

    Configures logging with the Amelia dashboard color palette.
    Called automatically by Typer before any subcommand execution.
    """
    log_level = os.environ.get("AMELIA_LOG_LEVEL", "INFO").upper()
    configure_logging(level=log_level)

@app.command()
def review(
    ctx: typer.Context,
    local: bool = typer.Option(
        False,
        "--local",
        "-l",
        help="Review local uncommitted changes."
    ),
    profile_name: str | None = typer.Option(
        None,
        "--profile",
        "-p",
        help="Profile to use (from database)."
    ),
) -> None:
    """Trigger a code review process.

    Args:
        ctx: Typer context (unused).
        local: If True, review local uncommitted changes from git diff.
        profile_name: Optional profile name to use (managed by server).

    Raises:
        typer.Exit: On validation failure or review error.
    """
    async def _run() -> None:
        """Async implementation of the review process."""
        typer.echo("Starting Amelia Review process...")

        if local:
            typer.echo("Reviewing local uncommitted changes...")

            # Gather git diff
            diff_content = await run_shell_command("git diff")
            if not diff_content or not diff_content.strip():
                typer.echo("No local uncommitted changes found.")
                raise typer.Exit(code=0)

            typer.echo(f"Found {len(diff_content)} bytes of changes")

            # Create workflow via API
            client = AmeliaClient()
            try:
                response = await client.create_review_workflow(
                    diff_content=diff_content,
                    worktree_path=os.getcwd(),
                    profile=profile_name,
                )
                typer.echo(f"Created review workflow: {response.id}")

                # Stream events via WebSocket
                await stream_workflow_events(response.id)

            except ServerUnreachableError:
                typer.echo("Server not running. Start with: amelia server", err=True)
                raise typer.Exit(code=1) from None
            except WorkflowConflictError as e:
                typer.echo(f"Workflow conflict: {e}", err=True)
                raise typer.Exit(code=1) from None
            except InvalidRequestError as e:
                typer.echo(f"Invalid request: {e}", err=True)
                raise typer.Exit(code=1) from None
        else:
            typer.echo("Use --local to review local uncommitted changes.", err=True)
            raise typer.Exit(code=1)

    asyncio.run(_run())

if __name__ == "__main__":
    app()