"""
WebSocket Hub for Real-Time Streaming & Operator Notifications.

Distributes live watch events, AIS stream updates, async job states,
and critical alerts directly to connected browser clients.
"""

import asyncio
from datetime import datetime, timezone
import json
import logging
from typing import Any, Dict, List, Set
from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger("aegis.ws")


class WebSocketHub:
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def set_event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.add(websocket)
        # Send greeting
        await websocket.send_text(
            json.dumps({
                "type": "CONNECTION_ESTABLISHED",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "message": "Connected to AEGIS-SAR Live Intelligence Stream",
            })
        )

    def disconnect(self, websocket: WebSocket) -> None:
        self.active_connections.discard(websocket)

    async def broadcast_async(self, message: Dict[str, Any]) -> None:
        text = json.dumps(message)
        dead = []
        for connection in self.active_connections:
            try:
                await connection.send_text(text)
            except Exception:
                dead.append(connection)
        for d in dead:
            self.active_connections.discard(d)

    def broadcast(self, message: Dict[str, Any]) -> None:
        """Thread-safe synchronous broadcast from any thread or job."""
        if not self.active_connections:
            return
        try:
            loop = self._loop or asyncio.get_event_loop()
            if loop.is_running():
                asyncio.run_coroutine_threadsafe(self.broadcast_async(message), loop)
        except Exception as e:
            logger.debug(f"Broadcast dispatch error: {e}")


global_ws_hub = WebSocketHub()


def setup_job_ws_forwarding():
    from src.api.jobs import global_job_manager

    def on_job_update(job):
        global_ws_hub.broadcast({
            "type": "JOB_UPDATE",
            "job": job.to_dict(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    global_job_manager.register_listener(on_job_update)
