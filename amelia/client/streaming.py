"""WebSocket streaming helpers for CLI."""

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import websockets
from rich.console import Console


@dataclass(frozen=True)
class EventFormat:
    """Format configuration for displaying an event type."""

    style: str
    """Rich markup style for the message (e.g., 'blue', 'bold green')."""
    prefix: str = ""
    """Optional prefix to prepend to the message."""
    include_message: bool = True
    """Whether to include the event message in output."""
    newline_before: bool = False
    """Whether to print a newline before the message."""


# Simple event types with straightforward formatting
_SIMPLE_EVENT_FORMATS: dict[str, EventFormat] = {
    "workflow_started": EventFormat(style="blue", prefix="Workflow started: "),
    "workflow_completed": EventFormat(
        style="bold green",
        prefix="Workflow completed successfully!",
        include_message=False,
        newline_before=True,
    ),
    "workflow_failed": EventFormat(
        style="bold red", prefix="Workflow failed: ", newline_before=True
    ),
    "workflow_cancelled": EventFormat(
        style="yellow", prefix="Workflow cancelled: ", newline_before=True
    ),
    "approval_granted": EventFormat(
        style="green", prefix="Plan approved", include_message=False
    ),
    "approval_rejected": EventFormat(style="red", prefix="Plan rejected: "),
    "approval_required": EventFormat(
        style="yellow bold", prefix="Approval required: ", newline_before=True
    ),
}

# Event types that require custom formatting logic
EventFormatter = Callable[[Console, dict[str, Any]], None]


def _format_stage_started(console: Console, event: dict[str, Any]) -> None:
    """Format stage started event."""
    data = event.get("data", {}) or {}
    stage = data.get("stage", "unknown")
    console.print(f"[dim]Starting {stage}...[/dim]")


def _format_stage_completed(console: Console, event: dict[str, Any]) -> None:
    """Format stage completed event."""
    data = event.get("data", {}) or {}
    stage = data.get("stage", "unknown")
    console.print(f"[green]Completed {stage}[/green]")


def _format_review_completed(console: Console, event: dict[str, Any]) -> None:
    """Format review completion event with approval status and details."""
    data = event.get("data", {}) or {}
    approved = data.get("approved", False)
    severity = data.get("severity", "unknown")
    issue_count = data.get("issue_count", 0)
    status = "[green]approved[/green]" if approved else "[yellow]changes requested[/yellow]"
    console.print(
        f"\n[bold]Review {status}[/bold] ({severity} severity, {issue_count} issues)"
    )


def _format_agent_message(console: Console, event: dict[str, Any]) -> None:
    """Format agent message with agent name prefix."""
    message = event.get("message", "")
    agent = event.get("agent", "system")
    console.print(f"[cyan][{agent}][/cyan] {message}")


_CUSTOM_FORMATTERS: dict[str, EventFormatter] = {
    "stage_started": _format_stage_started,
    "stage_completed": _format_stage_completed,
    "review_completed": _format_review_completed,
    "agent_message": _format_agent_message,
}


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
        await ws.send(json.dumps({"type": "subscribe", "workflow_id": workflow_id}))

        async for message in ws:
            data = json.loads(message)
            message_type = data.get("type")

            if message_type == "ping":
                await ws.send(json.dumps({"type": "pong"}))
                continue

            if message_type == "event":
                event = data.get("payload", {})
                _display_event(console, event)

                event_type = event.get("event_type")
                if event_type in {"workflow_completed", "workflow_failed", "workflow_cancelled"}:
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

    # Check for custom formatters first (events needing special logic)
    if event_type in _CUSTOM_FORMATTERS:
        _CUSTOM_FORMATTERS[event_type](console, event)
        return

    # Check for simple format configurations
    if event_type in _SIMPLE_EVENT_FORMATS:
        fmt = _SIMPLE_EVENT_FORMATS[event_type]
        text = fmt.prefix + (message if fmt.include_message else "")
        newline = "\n" if fmt.newline_before else ""
        console.print(f"{newline}[{fmt.style}]{text}[/{fmt.style}]")
        return

    # Default: show other events with less emphasis
    console.print(f"[dim]{event_type}: {message}[/dim]")
