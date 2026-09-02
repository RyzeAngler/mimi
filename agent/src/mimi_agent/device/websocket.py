"""WebSocket server for device events and streaming audio."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

import websockets

from mimi_agent.protocol.codec import decode_json_message
from mimi_agent.protocol.messages import PhysicalEvent, SensorTelemetry

from .session import DeviceSession

logger = logging.getLogger(__name__)
EventHandler = Callable[[DeviceSession, PhysicalEvent], Awaitable[None]]
TelemetryHandler = Callable[[DeviceSession, SensorTelemetry], Awaitable[None]]
DisconnectHandler = Callable[[DeviceSession], Awaitable[None]]


class DeviceWebSocketServer:
    def __init__(
        self,
        event_handler: EventHandler,
        telemetry_handler: TelemetryHandler,
        disconnect_handler: DisconnectHandler | None = None,
    ) -> None:
        self.event_handler = event_handler
        self.telemetry_handler = telemetry_handler
        self.disconnect_handler = disconnect_handler

    async def handler(self, websocket: Any, path: str | None = None) -> None:
        del path
        session = DeviceSession(websocket)
        logger.info("device connected: %s", getattr(websocket, "remote_address", None))
        try:
            async for raw in websocket:
                if isinstance(raw, bytes):
                    logger.debug("ignoring %d-byte device binary frame", len(raw))
                    continue
                try:
                    payload = decode_json_message(raw)
                except (UnicodeDecodeError, ValueError) as exc:
                    logger.warning("invalid device control frame: %s", exc)
                    continue
                message_type = str(payload.get("type", ""))
                if message_type == "hello":
                    session.device_id = str(payload.get("device_id") or "unknown")
                    await session.send_text(
                        '{"type":"hello_ack","protocol":"mimi.v1"}'
                    )
                elif message_type == "motion_event":
                    try:
                        await self.event_handler(session, PhysicalEvent.from_dict(payload))
                    except ValueError as exc:
                        logger.warning("invalid physical event: %s", exc)
                elif message_type == "sensor_telemetry":
                    try:
                        await self.telemetry_handler(
                            session, SensorTelemetry.from_dict(payload)
                        )
                    except ValueError as exc:
                        logger.warning("invalid sensor telemetry: %s", exc)
                elif message_type == "ping":
                    await session.send_text('{"type":"pong"}')
                else:
                    logger.debug("unhandled device message type=%s", message_type)
        except websockets.ConnectionClosed:
            logger.info("device disconnected: %s", session.device_id)
        finally:
            if self.disconnect_handler is not None:
                await self.disconnect_handler(session)
