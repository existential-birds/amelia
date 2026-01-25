"""Thin client CLI commands that delegate to the REST API."""
import asyncio
from pathlib import Path
from typing import Annotated

import httpx
import typer
from loguru import logger
from rich.console import Console
from rich.table import Table

from amelia.agents.architect import Architect
from amelia.client.api import (
    AmeliaClient,
    InvalidRequestError,
    RateLimitError,
    ServerUnreachableError,
    WorkflowConflictError,
    WorkflowNotFoundError,
)
from amelia.client.git import get_worktree_context
from amelia.client.models import BatchStartResponse, CreateWorkflowResponse, WorkflowSummary
from amelia.core.types import Issue, Profile
from amelia.pipelines.implementation.state import ImplementationState
from amelia.trackers.factory import create_tracker


console = Console()


def _get_worktree_context() -> tuple[str, str]:
    """Get current git worktree context with error handling.

    Wraps get_worktree_context() and converts exceptions to user-friendly
    error messages before exiting.

    Returns:
        Tuple of (worktree_path, worktree_name).

    Raises:
        typer.Exit: If not in a git repository or worktree detection fails.
    """
    try:
        return get_worktree_context()
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        console.print("\nMake sure you're in a git repository working directory.")
        raise typer.Exit(1) from None
    except RuntimeError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from None


def _handle_workflow_api_error(
    exc: ServerUnreachableError | WorkflowConflictError | RateLimitError | InvalidRequestError,
    worktree_path: str | None = None,
) -> None:
    """Handle workflow API errors with user-friendly messaging and guidance.

    Displays error-specific messages with suggested actions for recovery.
    Always exits with code 1.

    Args:
        exc: The exception to handle from the API client.
        worktree_path: Optional worktree path for context in error messages.

    Raises:
        typer.Exit: Always exits with code 1 after displaying error.
    """
    if isinstance(exc, ServerUnreachableError):
        console.print(f"[red]Error:[/red] {exc}")
        console.print("\n[yellow]Start the server:[/yellow] amelia server")

    elif isinstance(exc, WorkflowConflictError):
        console.print(f"[red]Error:[/red] Workflow already active in {worktree_path}")

        if exc.active_workflow:
            active = exc.active_workflow
            console.print(f"\n  Active workflow: [bold]{active['id']}[/bold] ({active['issue_id']})")
            console.print(f"  Status: {active['status']}")

        console.print("\n[yellow]To start a new workflow:[/yellow]")
        console.print("  - Cancel the existing one: [bold]amelia cancel[/bold]")
        console.print("  - Or use a different worktree: [bold]git worktree add ../project-issue-123[/bold]")

    elif isinstance(exc, (RateLimitError, InvalidRequestError)):
        console.print(f"[red]Error:[/red] {exc}")

    raise typer.Exit(1) from None


def start_command(
    issue_id: Annotated[str, typer.Argument(help="Issue ID to work on (e.g., ISSUE-123)")],
    profile: Annotated[
        str | None,
        typer.Option("--profile", "-p", help="Profile name for configuration"),
    ] = None,
    title: Annotated[
        str | None,
        typer.Option("--title", help="Task title for none tracker (bypasses issue lookup)"),
    ] = None,
    description: Annotated[
        str | None,
        typer.Option("--description", help="Task description (requires --title)"),
    ] = None,
    queue: Annotated[
        bool,
        typer.Option("--queue", help="Queue workflow without starting immediately"),
    ] = False,
    plan: Annotated[
        bool,
        typer.Option("--plan", help="Run Architect before queueing (requires --queue)"),
    ] = False,
) -> None:
    """Start a new workflow for an issue in the current worktree.

    Detects the current git worktree context and creates a new workflow
    via the Amelia API server. Displays workflow details and dashboard URL.

    Args:
        issue_id: Issue identifier to work on (e.g., ISSUE-123).
        profile: Optional profile name for driver and tracker configuration.
        title: Optional task title for none tracker (bypasses issue lookup).
        description: Optional task description (requires --title to be set).
        queue: If True, queue workflow without starting immediately.
        plan: If True, run Architect before queueing (requires --queue).
    """
    # Validate --description requires --title
    if description and not title:
        console.print("[red]Error:[/red] --description requires --title to be set")
        raise typer.Exit(1)

    # Validate --plan requires --queue
    if plan and not queue:
        console.print("[red]Error:[/red] --plan requires --queue flag")
        raise typer.Exit(1)

    worktree_path, _ = _get_worktree_context()

    client = AmeliaClient()

    async def _create() -> CreateWorkflowResponse:
        return await client.create_workflow(
            issue_id=issue_id,
            worktree_path=worktree_path,
            profile=profile,
            task_title=title,
            task_description=description,
            start=not queue,
            plan_now=plan,
        )

    try:
        workflow = asyncio.run(_create())

        if queue:
            if plan:
                console.print(f"[green]✓[/green] Workflow queued with plan: [bold]{workflow.id}[/bold]")
            else:
                console.print(f"[green]✓[/green] Workflow queued: [bold]{workflow.id}[/bold]")
        else:
            console.print(f"[green]✓[/green] Workflow started: [bold]{workflow.id}[/bold]")
        console.print(f"  Issue: {issue_id}")
        console.print(f"  Worktree: {worktree_path}")
        console.print(f"  Status: {workflow.status}")
        console.print("\n[dim]View in dashboard: http://127.0.0.1:8420[/dim]")

    except (ServerUnreachableError, WorkflowConflictError, RateLimitError, InvalidRequestError) as e:
        _handle_workflow_api_error(e, worktree_path=worktree_path)


def reject_command(
    reason: str,
) -> None:
    """Reject the workflow plan in the current worktree with feedback.

    Sends rejection reason to the Architect agent, which will replan
    based on the provided feedback.

    Args:
        reason: Detailed reason for rejecting the plan to guide replanning.
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

    Auto-detects the active workflow from the current git worktree context
    and approves the pending plan, allowing execution to continue.
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
    """Show status of active workflows in a formatted table.

    By default shows the workflow for the current worktree only.
    Use --all to display workflows across all worktrees.

    Args:
        all_worktrees: If True, show workflows from all worktrees instead of current only.
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
                wf.worktree_path,
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

    Auto-detects the workflow from the current git worktree and cancels it.
    Prompts for confirmation unless --force is specified.

    Args:
        force: If True, skip the confirmation prompt.
    """
    # Detect worktree context
    try:
        worktree_path, _ = get_worktree_context()
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from None

    # Find workflow in this worktree
    client = AmeliaClient()

    async def _get_workflow() -> WorkflowSummary:
        """Fetch the active workflow for the current worktree."""
        result = await client.get_active_workflows(worktree_path=worktree_path)

        if not result.workflows:
            console.print(f"[red]Error:[/red] No workflow active in {worktree_path}")
            raise typer.Exit(1)

        return result.workflows[0]

    async def _do_cancel(workflow_id: str) -> None:
        """Cancel the workflow via API."""
        await client.cancel_workflow(workflow_id=workflow_id)

    # Step 1: Get workflow info (async)
    try:
        workflow = asyncio.run(_get_workflow())
    except ServerUnreachableError as e:
        console.print(f"[red]Error:[/red] {e}")
        console.print("\n[yellow]Start the server:[/yellow] amelia server")
        raise typer.Exit(1) from None

    # Step 2: Confirm cancellation (sync - must be outside async context)
    if not force:
        console.print(f"Cancel workflow [bold]{workflow.id}[/bold] ({workflow.issue_id})?")
        confirm = typer.confirm("Are you sure?")
        if not confirm:
            console.print("[dim]Aborted.[/dim]")
            raise typer.Exit(0)

    # Step 3: Cancel it (async)
    try:
        asyncio.run(_do_cancel(workflow.id))
        console.print(f"[yellow]✗[/yellow] Workflow [bold]{workflow.id}[/bold] cancelled")
    except ServerUnreachableError as e:
        console.print(f"[red]Error:[/red] {e}")
        console.print("\n[yellow]Start the server:[/yellow] amelia server")
        raise typer.Exit(1) from None


async def _get_profile_from_server(profile_name: str | None) -> Profile:
    """Get profile from server API.

    Args:
        profile_name: Profile ID to fetch, or None for active profile.

    Returns:
        Profile object from the server.

    Raises:
        ValueError: If profile not found or server unreachable.
    """
    # Use same default as AmeliaClient for consistency
    base_url = AmeliaClient().base_url
    timeout = httpx.Timeout(10.0, connect=5.0)

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            if profile_name:
                # Get specific profile
                response = await client.get(f"{base_url}/api/profiles/{profile_name}")
                if response.status_code == 404:
                    raise ValueError(f"Profile '{profile_name}' not found")
            else:
                # Get active profile via config endpoint
                response = await client.get(f"{base_url}/api/config")
                if response.status_code != 200:
                    raise ValueError("Failed to get server config")
                config_data = response.json()
                active_profile_id = config_data.get("active_profile")
                if not active_profile_id:
                    raise ValueError("No active profile set. Create one via the dashboard.")
                # Now get the full profile
                response = await client.get(f"{base_url}/api/profiles/{active_profile_id}")

            if response.status_code != 200:
                raise ValueError(f"Failed to get profile: {response.text}")

            data = response.json()
            # Convert API response to Profile type
            # Parse agents dict from API response
            from amelia.core.types import AgentConfig  # noqa: PLC0415

            agents: dict[str, AgentConfig] = {}
            if "agents" in data and data["agents"]:
                for agent_name, agent_data in data["agents"].items():
                    agents[agent_name] = AgentConfig(
                        driver=agent_data["driver"],
                        model=agent_data["model"],
                        options=agent_data.get("options", {}),
                    )

            return Profile(
                name=data["id"],
                tracker=data["tracker"],
                working_dir=data["working_dir"],
                plan_output_dir=data["plan_output_dir"],
                plan_path_pattern=data["plan_path_pattern"],
                agents=agents,
            )
    except httpx.ConnectError as e:
        raise ValueError(
            "Cannot connect to Amelia server. Start it with: amelia server"
        ) from e


def plan_command(
    issue_id: Annotated[str, typer.Argument(help="Issue ID to generate a plan for (e.g., ISSUE-123)")],
    profile_name: Annotated[
        str | None,
        typer.Option("--profile", "-p", help="Profile name for configuration"),
    ] = None,
    title: Annotated[
        str | None,
        typer.Option("--title", help="Task title for none tracker (bypasses issue lookup)"),
    ] = None,
    description: Annotated[
        str | None,
        typer.Option("--description", help="Task description (requires --title)"),
    ] = None,
) -> None:
    """Generate an implementation plan for an issue without executing it.

    Creates a markdown implementation plan in docs/plans/ that can be
    reviewed before execution. Calls the Architect directly without
    going through the full LangGraph orchestration.

    Args:
        issue_id: Issue identifier to generate a plan for (e.g., ISSUE-123).
        profile_name: Optional profile name for driver and tracker configuration.
        title: Optional task title for none tracker (bypasses issue lookup).
        description: Optional task description (requires --title to be set).
    """
    # Validate --description requires --title
    if description and not title:
        console.print("[red]Error:[/red] --description requires --title to be set")
        raise typer.Exit(1)

    worktree_path, _ = _get_worktree_context()

    async def _generate_plan() -> ImplementationState:
        # Get profile from server
        profile = await _get_profile_from_server(profile_name)

        # Update profile with worktree path
        profile = profile.model_copy(update={"working_dir": worktree_path})

        # Get issue: construct directly if title provided with noop tracker, else use tracker
        if title is not None and profile.tracker == "noop":
            issue = Issue(
                id=issue_id,
                title=title,
                description=description or "",
            )
        elif title is not None:
            # --title provided but tracker is not noop - reject like server does
            raise ValueError(
                f"--title requires noop tracker, but profile uses '{profile.tracker}'"
            )
        else:
            # Fetch issue using tracker
            tracker = create_tracker(profile)
            issue = tracker.get_issue(issue_id, cwd=worktree_path)

        # Create minimal implementation state
        from datetime import UTC, datetime  # noqa: PLC0415

        state = ImplementationState(
            workflow_id=f"plan-{issue_id}",
            created_at=datetime.now(UTC),
            status="running",
            profile_id=profile.name,
            issue=issue,
        )

        # Create architect with agent config
        agent_config = profile.get_agent_config("architect")
        architect = Architect(agent_config)

        # Generate plan by consuming the async generator
        final_state = state
        async for new_state, _event in architect.plan(
            state=state,
            profile=profile,
            workflow_id=f"plan-{issue_id}",
        ):
            final_state = new_state

        return final_state

    try:
        console.print(f"[dim]Generating plan for {issue_id}...[/dim]")
        final_state = asyncio.run(_generate_plan())

        console.print("\n[green]✓[/green] Plan generated successfully!")
        console.print(f"  Saved to: [bold]{final_state.plan_path}[/bold]\n")

        # Show preview of the plan
        if final_state.plan_path and Path(final_state.plan_path).exists():
            plan_lines = Path(final_state.plan_path).read_text().splitlines()[:30]
            console.print("\n".join(plan_lines))
            if len(plan_lines) == 30:
                console.print("[dim]...[/dim]")

    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from None
    except Exception as e:
        console.print(f"[red]Error generating plan:[/red] {e}")
        logger.exception("Unexpected error in plan command")
        raise typer.Exit(1) from None


def run_command(
    workflow_id: Annotated[str | None, typer.Argument(help="Workflow ID to start")] = None,
    all_pending: Annotated[bool, typer.Option("--all", help="Start all pending workflows")] = False,
    worktree: Annotated[str | None, typer.Option("--worktree", help="Filter by worktree path")] = None,
) -> None:
    """Start pending workflow(s).

    Either starts a specific workflow by ID, or starts all pending workflows
    when using the --all flag. Optionally filter by worktree path.

    Args:
        workflow_id: Optional workflow ID to start.
        all_pending: If True, start all pending workflows.
        worktree: Optional worktree path filter (only with --all).
    """
    if not workflow_id and not all_pending:
        console.print("[red]Error:[/red] Provide workflow ID or use --all flag")
        raise typer.Exit(1)

    client = AmeliaClient()

    if workflow_id:
        # Start specific workflow
        async def _start_one() -> dict[str, str]:
            return await client.start_workflow(workflow_id)

        try:
            result = asyncio.run(_start_one())
            console.print(f"[green]Started workflow:[/green] {workflow_id}")
            console.print(f"  Status: {result.get('status', 'started')}")
        except ServerUnreachableError as e:
            console.print(f"[red]Error:[/red] {e}")
            console.print("\n[yellow]Start the server:[/yellow] amelia server")
            raise typer.Exit(1) from None
        except WorkflowNotFoundError:
            console.print(f"[red]Error:[/red] Workflow {workflow_id} not found")
            raise typer.Exit(1) from None
        except InvalidRequestError as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1) from None

    else:
        # Batch start
        async def _start_batch() -> BatchStartResponse:
            return await client.start_batch(
                workflow_ids=None,
                worktree_path=worktree,
            )

        try:
            batch_result = asyncio.run(_start_batch())
            started = batch_result.started
            errors = batch_result.errors

            if started:
                console.print(f"[green]Started {len(started)} workflow(s):[/green]")
                for wf_id in started:
                    console.print(f"  - {wf_id}")

            if errors:
                console.print(f"[yellow]Failed to start {len(errors)} workflow(s):[/yellow]")
                for wf_id, error in errors.items():
                    console.print(f"  - {wf_id}: {error}")

            if not started and not errors:
                console.print("[dim]No pending workflows to start[/dim]")

        except ServerUnreachableError as e:
            console.print(f"[red]Error:[/red] {e}")
            console.print("\n[yellow]Start the server:[/yellow] amelia server")
            raise typer.Exit(1) from None
