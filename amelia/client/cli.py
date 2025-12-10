# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Thin client CLI commands that delegate to the REST API."""
import asyncio
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from amelia.client.api import (
    AmeliaClient,
    InvalidRequestError,
    RateLimitError,
    ServerUnreachableError,
    WorkflowConflictError,
)
from amelia.client.git import get_worktree_context
from amelia.client.models import CreateWorkflowResponse


console = Console()


def start_command(
    issue_id: Annotated[str, typer.Argument(help="Issue ID to work on (e.g., ISSUE-123)")],
    profile: Annotated[
        str | None,
        typer.Option("--profile", "-p", help="Profile name for configuration"),
    ] = None,
) -> None:
    """Start a workflow for an issue.

    Detects the current git worktree and creates a new workflow via the API server.

    Args:
        issue_id: Issue ID to work on (e.g., ISSUE-123).
        profile: Profile name for configuration.
    """
    # Detect worktree context
    try:
        worktree_path, worktree_name = get_worktree_context()
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        console.print("\nMake sure you're in a git repository working directory.")
        raise typer.Exit(1) from None
    except RuntimeError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from None

    # Create workflow via API
    client = AmeliaClient()

    async def _create() -> CreateWorkflowResponse:
        return await client.create_workflow(
            issue_id=issue_id,
            worktree_path=worktree_path,
            worktree_name=worktree_name,
            profile=profile,
        )

    try:
        workflow = asyncio.run(_create())

        console.print(f"[green]✓[/green] Workflow started: [bold]{workflow.id}[/bold]")
        console.print(f"  Issue: {issue_id}")
        console.print(f"  Worktree: {worktree_path}")
        console.print(f"  Status: {workflow.status}")
        console.print("\n[dim]View in dashboard: http://127.0.0.1:8420[/dim]")

    except ServerUnreachableError as e:
        console.print(f"[red]Error:[/red] {e}")
        console.print("\n[yellow]Start the server:[/yellow] amelia server")
        raise typer.Exit(1) from None

    except WorkflowConflictError as e:
        console.print(f"[red]Error:[/red] Workflow already active in {worktree_path}")

        if e.active_workflow:
            active = e.active_workflow
            console.print(f"\n  Active workflow: [bold]{active['id']}[/bold] ({active['issue_id']})")
            console.print(f"  Status: {active['status']}")

        console.print("\n[yellow]To start a new workflow:[/yellow]")
        console.print("  - Cancel the existing one: [bold]amelia cancel[/bold]")
        console.print("  - Or use a different worktree: [bold]git worktree add ../project-issue-123[/bold]")
        raise typer.Exit(1) from None

    except RateLimitError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from None

    except InvalidRequestError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from None


def reject_command(
    reason: str,
) -> None:
    """Reject the workflow plan in the current worktree.

    Provide a reason that will be sent to the Architect agent for replanning.

    Args:
        reason: Reason for rejecting the plan
    """
    # Detect worktree context
    try:
        worktree_path, _ = get_worktree_context()
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from None

    # Find workflow in this worktree
    client = AmeliaClient()

    async def _reject() -> None:
        # Get workflows for this worktree
        result = await client.get_active_workflows(worktree_path=worktree_path)

        if not result.workflows:
            console.print(f"[red]Error:[/red] No workflow active in {worktree_path}")
            console.print("\n[yellow]Start a workflow:[/yellow] amelia start ISSUE-123")
            raise typer.Exit(1)

        workflow = result.workflows[0]

        # Reject it
        try:
            await client.reject_workflow(workflow_id=workflow.id, reason=reason)
            console.print(f"[yellow]✗[/yellow] Plan rejected for workflow [bold]{workflow.id}[/bold]")
            console.print(f"  Reason: {reason}")
            console.print("\n[dim]Architect will replan based on your feedback.[/dim]")
        except InvalidRequestError as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1) from None

    try:
        asyncio.run(_reject())
    except ServerUnreachableError as e:
        console.print(f"[red]Error:[/red] {e}")
        console.print("\n[yellow]Start the server:[/yellow] amelia server")
        raise typer.Exit(1) from None


def approve_command() -> None:
    """Approve the workflow plan in the current worktree.

    Auto-detects the workflow from the current git worktree.
    """
    # Detect worktree context
    try:
        worktree_path, _ = get_worktree_context()
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from None

    # Find workflow in this worktree
    client = AmeliaClient()

    async def _approve() -> None:
        # Get workflows for this worktree
        result = await client.get_active_workflows(worktree_path=worktree_path)

        if not result.workflows:
            console.print(f"[red]Error:[/red] No workflow active in {worktree_path}")
            console.print("\n[yellow]Start a workflow:[/yellow] amelia start ISSUE-123")
            raise typer.Exit(1)

        workflow = result.workflows[0]

        # Approve it
        try:
            await client.approve_workflow(workflow_id=workflow.id)
            console.print(f"[green]✓[/green] Plan approved for workflow [bold]{workflow.id}[/bold]")
            console.print(f"  Issue: {workflow.issue_id}")
            console.print("\n[dim]Workflow will now continue execution.[/dim]")
        except InvalidRequestError:
            console.print("[red]Error:[/red] Workflow is not awaiting approval")
            console.print(f"\n  Current workflow: [bold]{workflow.id}[/bold] ({workflow.issue_id})")
            console.print(f"  Status: {workflow.status} (not blocked)")
            raise typer.Exit(1) from None

    try:
        asyncio.run(_approve())
    except ServerUnreachableError as e:
        console.print(f"[red]Error:[/red] {e}")
        console.print("\n[yellow]Start the server:[/yellow] amelia server")
        raise typer.Exit(1) from None


def status_command(
    all_worktrees: Annotated[
        bool,
        typer.Option("--all", "-a", help="Show workflows from all worktrees"),
    ] = False,
) -> None:
    """Show status of active workflows.

    By default, shows workflow for the current worktree only.
    Use --all to see workflows from all worktrees.

    Args:
        all_worktrees: Show workflows from all worktrees.
    """
    # Detect worktree context (if filtering to current)
    worktree_path = None
    if not all_worktrees:
        try:
            worktree_path, _ = get_worktree_context()
        except ValueError as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1) from None

    # Get workflows via API
    client = AmeliaClient()

    async def _status() -> None:
        result = await client.get_active_workflows(worktree_path=worktree_path)

        if not result.workflows:
            if all_worktrees:
                console.print("[dim]No active workflows across all worktrees.[/dim]")
            else:
                console.print(f"[dim]No active workflow in {worktree_path}[/dim]")
                console.print("\n[yellow]Start a workflow:[/yellow] amelia start ISSUE-123")
            return

        # Display workflows in a table
        table = Table(title="Active Workflows", show_header=True)
        table.add_column("Workflow ID", style="cyan", no_wrap=True)
        table.add_column("Issue", style="magenta")
        table.add_column("Status", style="yellow")
        table.add_column("Worktree", style="green")
        table.add_column("Started", style="blue")

        for wf in result.workflows:
            table.add_row(
                wf.id,
                wf.issue_id,
                wf.status,
                wf.worktree_name,
                wf.started_at.strftime("%Y-%m-%d %H:%M") if wf.started_at else "-",
            )

        console.print(table)
        console.print(f"\n[dim]Total: {result.total} workflow(s)[/dim]")

    try:
        asyncio.run(_status())
    except ServerUnreachableError as e:
        console.print(f"[red]Error:[/red] {e}")
        console.print("\n[yellow]Start the server:[/yellow] amelia server")
        raise typer.Exit(1) from None


def cancel_command(
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Skip confirmation prompt"),
    ] = False,
) -> None:
    """Cancel the active workflow in the current worktree.

    Requires confirmation unless --force is used.

    Args:
        force: Skip confirmation prompt.
    """
    # Detect worktree context
    try:
        worktree_path, _ = get_worktree_context()
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from None

    # Find workflow in this worktree
    client = AmeliaClient()

    async def _cancel() -> None:
        # Get workflows for this worktree
        result = await client.get_active_workflows(worktree_path=worktree_path)

        if not result.workflows:
            console.print(f"[red]Error:[/red] No workflow active in {worktree_path}")
            raise typer.Exit(1)

        workflow = result.workflows[0]

        # Confirm cancellation
        if not force:
            console.print(f"Cancel workflow [bold]{workflow.id}[/bold] ({workflow.issue_id})?")
            confirm = typer.confirm("Are you sure?")
            if not confirm:
                console.print("[dim]Aborted.[/dim]")
                raise typer.Exit(0)

        # Cancel it
        await client.cancel_workflow(workflow_id=workflow.id)
        console.print(f"[yellow]✗[/yellow] Workflow [bold]{workflow.id}[/bold] cancelled")

    try:
        asyncio.run(_cancel())
    except ServerUnreachableError as e:
        console.print(f"[red]Error:[/red] {e}")
        console.print("\n[yellow]Start the server:[/yellow] amelia server")
        raise typer.Exit(1) from None
