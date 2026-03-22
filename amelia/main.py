import asyncio
import os
from typing import Annotated

import typer

from amelia.cli.config import config_app
from amelia.client.api import (
    AmeliaClient,
    InvalidRequestError,
    RateLimitError,
    ServerUnreachableError,
    WorkflowConflictError,
    WorkflowNotFoundError,
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


@app.command(name="fix-pr")
def fix_pr(
    pr_number: Annotated[int, typer.Argument(help="PR number to fix")],
    profile_name: Annotated[str, typer.Option("--profile", "-p", help="Profile name (required)")],
    aggressiveness: Annotated[str | None, typer.Option("--aggressiveness", "-a", help="Override: critical/standard/thorough")] = None,
    quiet: Annotated[bool, typer.Option("--quiet", "-q", help="Suppress event streaming")] = False,
) -> None:
    """Trigger a one-shot PR auto-fix cycle.

    Validates that PR auto-fix is enabled on the profile, triggers a fix cycle
    via the API, streams events, and prints a summary.

    Args:
        pr_number: PR number to fix.
        profile_name: Profile name (required).
        aggressiveness: Optional aggressiveness override.
        quiet: Suppress event streaming display.
    """
    async def _run() -> None:
        client = AmeliaClient()

        # Validate pr_autofix is enabled
        status = await client.get_pr_autofix_status(profile_name)
        if not status.enabled:
            typer.echo(
                f"PR auto-fix not enabled on profile {profile_name}. "
                "Configure it in the dashboard."
            )
            raise typer.Exit(code=1)

        # Trigger the fix cycle
        response = await client.trigger_pr_autofix(
            pr_number, profile_name, aggressiveness
        )
        typer.echo(
            f"Triggered auto-fix for PR #{pr_number} (workflow: {response.workflow_id})"
        )

        # Stream events and collect summary
        summary = await stream_workflow_events(
            response.workflow_id, display=not quiet
        )

        # Print summary line
        summary_line = (
            f"{summary.fixed} comments fixed, "
            f"{summary.skipped} skipped, "
            f"{summary.failed} failed"
        )
        if summary.commit_sha is not None:
            summary_line += f" (commit: {summary.commit_sha[:8]})"
        typer.echo(summary_line)

    try:
        asyncio.run(_run())
    except ServerUnreachableError:
        typer.echo("Server not running. Start with: amelia server", err=True)
        raise typer.Exit(code=1) from None
    except (WorkflowNotFoundError, WorkflowConflictError) as e:
        typer.echo(f"Workflow error: {e}", err=True)
        raise typer.Exit(code=1) from None
    except InvalidRequestError as e:
        typer.echo(f"Invalid request: {e}", err=True)
        raise typer.Exit(code=1) from None
    except RateLimitError as e:
        typer.echo(f"Rate limit exceeded: {e}", err=True)
        raise typer.Exit(code=1) from None


@app.command(name="watch-pr")
def watch_pr(
    pr_number: Annotated[int, typer.Argument(help="PR number to watch")],
    profile_name: Annotated[str, typer.Option("--profile", "-p", help="Profile name (required)")],
    aggressiveness: Annotated[str | None, typer.Option("--aggressiveness", "-a", help="Override: critical/standard/thorough")] = None,
    interval: Annotated[int, typer.Option("--interval", "-i", help="Polling interval in seconds")] = 60,
    quiet: Annotated[bool, typer.Option("--quiet", "-q", help="Suppress event streaming")] = False,
) -> None:
    """Watch a PR and continuously fix review comments.

    Validates that PR auto-fix is enabled, then loops: trigger fix cycle,
    stream events, check unresolved comments, wait. Stops when zero
    unresolved comments remain.

    Args:
        pr_number: PR number to watch.
        profile_name: Profile name (required).
        aggressiveness: Optional aggressiveness override.
        interval: Polling interval in seconds (default 60).
        quiet: Suppress event streaming display.
    """
    async def _run() -> None:
        client = AmeliaClient()

        # Validate pr_autofix is enabled
        status = await client.get_pr_autofix_status(profile_name)
        if not status.enabled:
            typer.echo(
                f"PR auto-fix not enabled on profile {profile_name}. "
                "Configure it in the dashboard."
            )
            raise typer.Exit(code=1)

        previous_comment_ids: set[int] = set()

        while True:
            # Trigger a fix cycle
            response = await client.trigger_pr_autofix(
                pr_number, profile_name, aggressiveness
            )
            typer.echo(
                f"Triggered auto-fix for PR #{pr_number} (workflow: {response.workflow_id})"
            )

            # Stream events and collect summary
            summary = await stream_workflow_events(
                response.workflow_id, display=not quiet
            )

            # Print summary line
            summary_line = (
                f"{summary.fixed} comments fixed, "
                f"{summary.skipped} skipped, "
                f"{summary.failed} failed"
            )
            if summary.commit_sha is not None:
                summary_line += f" (commit: {summary.commit_sha[:8]})"
            typer.echo(summary_line)

            # Check if any unresolved comments remain
            comments_response = await client.get_pr_comments(
                pr_number, profile_name
            )
            if len(comments_response.comments) == 0:
                typer.echo("All comments resolved. Stopping.")
                break

            # Stop if the set of unresolved comments hasn't changed —
            # remaining comments were skipped/failed and won't resolve
            current_comment_ids = {c.id for c in comments_response.comments}
            if current_comment_ids == previous_comment_ids:
                typer.echo(
                    f"{len(current_comment_ids)} unresolved comments remain "
                    "unchanged after fix cycle. Stopping watch."
                )
                break
            previous_comment_ids = current_comment_ids

            typer.echo(
                f"Waiting for new comments... next check in {interval}s"
            )
            await asyncio.sleep(interval)

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        typer.echo("\nStopped watching.")
    except ServerUnreachableError:
        typer.echo("Server not running. Start with: amelia server", err=True)
        raise typer.Exit(code=1) from None
    except (WorkflowNotFoundError, WorkflowConflictError) as e:
        typer.echo(f"Workflow error: {e}", err=True)
        raise typer.Exit(code=1) from None
    except InvalidRequestError as e:
        typer.echo(f"Invalid request: {e}", err=True)
        raise typer.Exit(code=1) from None
    except RateLimitError as e:
        typer.echo(f"Rate limit exceeded: {e}", err=True)
        raise typer.Exit(code=1) from None


if __name__ == "__main__":
    app()