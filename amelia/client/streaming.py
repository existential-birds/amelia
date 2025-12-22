# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
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

    Args:
        workflow_id: The workflow ID to stream events for.
        base_url: The Amelia API base URL. Defaults to http://localhost:8420.
    """
    console = Console()
    ws_url = base_url.replace("http://", "ws://").replace("https://", "wss://") + f"/api/ws/{workflow_id}"

    async with websockets.connect(ws_url) as ws:
        async for message in ws:
            event = json.loads(message)
            _display_event(console, event)

            # Exit on terminal states
            if event.get("type") == "workflow_completed":
                break
            if event.get("type") == "workflow_failed":
                break


def _display_event(console: Console, event: dict[str, Any]) -> None:
    """Display a workflow event in the terminal with Rich formatting.

    Formats different event types (reviewer_completed, developer_started, etc.)
    with appropriate styling and detail level.

    Args:
        console: Rich Console instance for formatted output.
        event: Event dictionary from WebSocket containing type, message, and data.
    """
    event_type = event.get("type", "unknown")

    if event_type == "reviewer_completed":
        review = event.get("data", {})
        console.print("\n[bold]--- REVIEW RESULT ---[/bold]")
        console.print(f"Approved: {review.get('approved')}")
        console.print(f"Severity: {review.get('severity')}")
        for comment in review.get("comments", []):
            console.print(f"  - {comment}")
    elif event_type == "developer_started":
        console.print("\n[dim]Developer addressing review comments...[/dim]")
    elif event_type == "developer_completed":
        console.print("[green]Developer completed fixes[/green]")
    elif event_type == "workflow_started":
        console.print(f"[blue]Workflow started: {event.get('message', '')}[/blue]")
    elif event_type == "workflow_completed":
        console.print("\n[bold green]Workflow completed successfully![/bold green]")
    elif event_type == "workflow_failed":
        console.print(f"\n[bold red]Workflow failed: {event.get('message', '')}[/bold red]")
    elif event_type == "reviewer_started":
        console.print("[dim]Reviewing code changes...[/dim]")
    else:
        # Show other events with less emphasis
        console.print(f"[dim]{event_type}: {event.get('message', '')}[/dim]")
