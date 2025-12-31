"""WebSocket endpoint for real-time event streaming."""
import asyncio
import contextlib
from typing import Annotated

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from loguru import logger

from amelia.server.events.connection_manager import ConnectionManager


router = APIRouter(tags=["websocket"])

# Global connection manager instance
connection_manager = ConnectionManager()


@router.websocket("/ws/events")
async def websocket_endpoint(
    websocket: WebSocket,
    since: Annotated[str | None, Query()] = None,
) -> None:
    """WebSocket endpoint for real-time event streaming.

    Protocol:
        Client -> Server:
            {"type": "subscribe", "workflow_id": "uuid"}
            {"type": "unsubscribe", "workflow_id": "uuid"}
            {"type": "subscribe_all"}
            {"type": "pong"}

        Server -> Client:
            {"type": "event", "payload": WorkflowEvent}
            {"type": "ping"}
            {"type": "backfill_complete", "count": 15}
            {"type": "backfill_expired", "message": "..."}

    Args:
        websocket: The WebSocket connection.
        since: Optional event ID for backfill on reconnect.
    """
    await connection_manager.connect(websocket)
    logger.info("websocket_connected", active_connections=connection_manager.active_connections)

    try:
        # Handle backfill if reconnecting
        if since:
            repository = connection_manager.get_repository()
            if repository:
                try:
                    # Replay missed events from database
                    events = await repository.get_events_after(since)

                    for event in events:
                        await websocket.send_json({
                            "type": "event",
                            "payload": event.model_dump(mode="json"),
                        })

                    await websocket.send_json({
                        "type": "backfill_complete",
                        "count": len(events),
                    })
                    logger.info("backfill_complete", count=len(events))
                except ValueError:
                    # Event was cleaned up by retention - client needs full refresh
                    await websocket.send_json({
                        "type": "backfill_expired",
                        "message": "Requested event no longer exists. Full refresh required.",
                    })
                    logger.warning("backfill_expired", since_event_id=since)
            else:
                logger.warning("backfill_unavailable", reason="repository_not_initialized")

        # Start heartbeat task
        heartbeat_task = asyncio.create_task(_heartbeat_loop(websocket))

        try:
            # Message handling loop
            while True:
                data = await websocket.receive_json()
                message_type = data.get("type")

                if message_type == "subscribe":
                    workflow_id = data.get("workflow_id")
                    if workflow_id:
                        await connection_manager.subscribe(websocket, workflow_id)
                        logger.debug("subscription_added", workflow_id=workflow_id)

                elif message_type == "unsubscribe":
                    workflow_id = data.get("workflow_id")
                    if workflow_id:
                        await connection_manager.unsubscribe(websocket, workflow_id)
                        logger.debug("subscription_removed", workflow_id=workflow_id)

                elif message_type == "subscribe_all":
                    await connection_manager.subscribe_all(websocket)
                    logger.debug("subscribed_to_all")

                elif message_type == "pong":
                    # Heartbeat response - just log
                    logger.debug("heartbeat_pong_received")

        finally:
            # Cancel heartbeat when loop exits
            heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat_task

    except WebSocketDisconnect:
        logger.info("websocket_disconnected")
    except Exception as e:
        logger.error("websocket_error", error=str(e), exc_info=True)
    finally:
        await connection_manager.disconnect(websocket)
        logger.info("websocket_cleanup", active_connections=connection_manager.active_connections)


async def _heartbeat_loop(websocket: WebSocket, interval: float = 30.0) -> None:
    """Send periodic ping messages to keep WebSocket connection alive.

    Args:
        websocket: The WebSocket connection to send pings to.
        interval: Seconds between ping messages. Defaults to 30.0.
    """
    try:
        while True:
            await asyncio.sleep(interval)
            await websocket.send_json({"type": "ping"})
            logger.debug("heartbeat_ping_sent")
    except asyncio.CancelledError:
        # Normal cancellation on disconnect
        pass
    except Exception as e:
        logger.error("heartbeat_error", error=str(e))
