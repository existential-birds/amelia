"""WebSocket streaming helpers for CLI."""

import json
from typing import Any

import websockets
from rich.console import Console


async def stream_workflow_events(
    workflow_id: str,
    base_url: str = "http://localhost:8420",
) -> None:
    """Stream workflow events via WebSocket and display in terminal.

    Connects to the workflow WebSocket endpoint and prints formatted events
    to the console. Automatically exits when the workflow completes or fails.

    The WebSocket protocol works as follows:
    1. Client connects to /ws/events
    2. Client sends {"type": "subscribe", "workflow_id": "<id>"} to subscribe
    3. Server sends events as {"type": "event", "payload": WorkflowEvent}
    4. Server sends {"type": "ping"} periodically, client responds with {"type": "pong"}

    Args:
        workflow_id: The workflow ID to stream events for.
        base_url: The Amelia API base URL. Defaults to http://localhost:8420.
    """
    console = Console()
    ws_url = base_url.replace("http://", "ws://").replace("https://", "wss://") + "/ws/events"

    async with websockets.connect(ws_url) as ws:
        # Subscribe to the specific workflow
        await ws.send(json.dumps({"type": "subscribe", "workflow_id": workflow_id}))

        async for message in ws:
            data = json.loads(message)
            message_type = data.get("type")

            # Handle server pings
            if message_type == "ping":
                await ws.send(json.dumps({"type": "pong"}))
                continue

            # Handle wrapped events from server
            if message_type == "event":
                event = data.get("payload", {})
                _display_event(console, event)

                # Exit on terminal states
                event_type = event.get("event_type")
                if event_type == "workflow_completed":
                    break
                if event_type == "workflow_failed":
                    break
                if event_type == "workflow_cancelled":
                    break
            elif message_type == "backfill_complete":
                console.print(f"[dim]Backfill complete: {data.get('count', 0)} events[/dim]")
            elif message_type == "backfill_expired":
                console.print(f"[yellow]Warning: {data.get('message', 'Backfill expired')}[/yellow]")


def _display_event(console: Console, event: dict[str, Any]) -> None:
    """Display a workflow event in the terminal with Rich formatting.

    Formats different event types with appropriate styling and detail level.
    Event types match the EventType enum (e.g., workflow_started, stage_completed).

    Args:
        console: Rich Console instance for formatted output.
        event: WorkflowEvent dictionary with event_type, message, data, and agent fields.
    """
    event_type = event.get("event_type", "unknown")
    message = event.get("message", "")
    data = event.get("data", {}) or {}
    agent = event.get("agent", "system")

    if event_type == "workflow_started":
        console.print(f"[blue]Workflow started: {message}[/blue]")
    elif event_type == "workflow_completed":
        console.print("\n[bold green]Workflow completed successfully![/bold green]")
    elif event_type == "workflow_failed":
        console.print(f"\n[bold red]Workflow failed: {message}[/bold red]")
    elif event_type == "workflow_cancelled":
        console.print(f"\n[yellow]Workflow cancelled: {message}[/yellow]")
    elif event_type == "stage_started":
        stage = data.get("stage", "unknown")
        console.print(f"[dim]Starting {stage}...[/dim]")
    elif event_type == "stage_completed":
        stage = data.get("stage", "unknown")
        console.print(f"[green]Completed {stage}[/green]")
    elif event_type == "approval_required":
        console.print(f"\n[yellow bold]Approval required: {message}[/yellow bold]")
    elif event_type == "approval_granted":
        console.print("[green]Plan approved[/green]")
    elif event_type == "approval_rejected":
        console.print(f"[red]Plan rejected: {message}[/red]")
    elif event_type == "review_completed":
        approved = data.get("approved", False)
        severity = data.get("severity", "unknown")
        comment_count = data.get("comment_count", 0)
        status = "[green]approved[/green]" if approved else "[yellow]changes requested[/yellow]"
        console.print(f"\n[bold]Review {status}[/bold] ({severity} severity, {comment_count} comments)")
    elif event_type == "agent_message":
        console.print(f"[cyan][{agent}][/cyan] {message}")
    else:
        # Show other events with less emphasis
        console.print(f"[dim]{event_type}: {message}[/dim]")
