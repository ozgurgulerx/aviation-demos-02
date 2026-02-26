"""
Redis-based event bus for workflow event streaming.
Supports pub/sub via Redis Streams for reliable, scalable event delivery.
"""

import asyncio
import os
import re
from datetime import datetime
from typing import AsyncGenerator, Optional
import redis.asyncio as redis
from redis.asyncio.client import Redis
import structlog

from schemas.events import WorkflowEvent, EventKind, heartbeat_event

logger = structlog.get_logger()

# Redis configuration
REDIS_HOST = os.getenv("BACKEND_REDIS_HOST", os.getenv("REDIS_HOST", "localhost"))
_redis_port = os.getenv("BACKEND_REDIS_PORT", "6379")
if _redis_port.startswith("tcp://"):
    REDIS_PORT = int(_redis_port.split(":")[-1])
else:
    REDIS_PORT = int(_redis_port)
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)
REDIS_DB = int(os.getenv("REDIS_DB", "0"))

# Stream configuration
STREAM_PREFIX = "av:events:"
MAX_STREAM_LEN = 10000
HEARTBEAT_INTERVAL = 15
STREAM_ID_RE = re.compile(r"^\d+-\d+$")


class EventBus:
    """
    Redis Streams-based event bus for workflow events.

    Features:
    - Persistent event storage in Redis Streams
    - Last-Event-ID resume capability
    - Heartbeat for SSE keepalive
    """

    def __init__(self, redis_client: Redis):
        self.redis = redis_client
        self._sequence_counters: dict[str, int] = {}

    @classmethod
    async def create(cls) -> "EventBus":
        """Factory method to create EventBus with connection."""
        client = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            password=REDIS_PASSWORD,
            db=REDIS_DB,
            decode_responses=True,
        )
        await client.ping()
        logger.info("event_bus_connected", host=REDIS_HOST, port=REDIS_PORT)
        return cls(client)

    def _stream_key(self, run_id: str) -> str:
        """Get Redis Stream key for a run."""
        return f"{STREAM_PREFIX}{run_id}"

    def _get_next_sequence(self, run_id: str) -> int:
        """Get next sequence number for a run."""
        if run_id not in self._sequence_counters:
            self._sequence_counters[run_id] = 0
        self._sequence_counters[run_id] += 1
        return self._sequence_counters[run_id]

    async def publish(self, event: WorkflowEvent) -> str:
        """Publish an event to the run's event stream."""
        if event.sequence == 0:
            event.sequence = self._get_next_sequence(event.run_id)

        stream_key = self._stream_key(event.run_id)

        event_data = {
            "data": event.model_dump_json(),
            "event_id": event.event_id,
            "kind": event.kind.value,
            "ts": event.ts.isoformat(),
        }

        message_id = await self.redis.xadd(
            stream_key,
            event_data,
            maxlen=MAX_STREAM_LEN,
        )

        event.stream_id = message_id

        logger.debug(
            "event_published",
            run_id=event.run_id,
            kind=event.kind.value,
            message_id=message_id,
            sequence=event.sequence,
        )

        return message_id

    async def _lookup_stream_id_by_event_id(self, stream_key: str, event_id: str) -> Optional[str]:
        """
        Resolve legacy UUID event IDs to Redis stream IDs.
        Used for backward-compatible SSE resume.
        """
        cursor = "-"
        while True:
            rows = await self.redis.xrange(stream_key, cursor, "+", count=250)
            if not rows:
                return None
            for stream_id, message_data in rows:
                if message_data.get("event_id") == event_id:
                    return stream_id
                cursor = f"({stream_id}"
            if len(rows) < 250:
                return None

    async def subscribe(
        self,
        run_id: str,
        last_event_id: Optional[str] = None,
        include_heartbeats: bool = True,
        max_retries: int = 10,
    ) -> AsyncGenerator[WorkflowEvent, None]:
        """Subscribe to events for a run using Redis Streams."""
        stream_key = self._stream_key(run_id)
        start_id = "0"
        if last_event_id:
            if STREAM_ID_RE.match(last_event_id):
                start_id = last_event_id
            else:
                resolved = await self._lookup_stream_id_by_event_id(stream_key, last_event_id)
                if resolved:
                    start_id = resolved
                    logger.info(
                        "event_resume_legacy_event_id_resolved",
                        run_id=run_id,
                        legacy_event_id=last_event_id,
                        stream_id=resolved,
                    )
                else:
                    logger.warning(
                        "event_resume_legacy_event_id_not_found",
                        run_id=run_id,
                        legacy_event_id=last_event_id,
                    )

        logger.info(
            "event_subscribe_started",
            run_id=run_id,
            stream_key=stream_key,
            start_id=start_id,
        )

        last_heartbeat = datetime.utcnow()
        heartbeat_sequence = 0
        retry_count = 0
        last_sequence = 0

        while True:
            try:
                messages = await self.redis.xread(
                    {stream_key: start_id},
                    count=100,
                    block=5000,
                )

                if messages:
                    for _stream_name, stream_messages in messages:
                        for _message_id, message_data in stream_messages:
                            start_id = _message_id

                            try:
                                event_json = message_data.get("data", "{}")
                                event = WorkflowEvent.model_validate_json(event_json)
                                event.stream_id = _message_id

                                if event.sequence and event.sequence <= last_sequence:
                                    logger.warning(
                                        "event_sequence_out_of_order",
                                        run_id=run_id,
                                        previous_sequence=last_sequence,
                                        current_sequence=event.sequence,
                                        stream_id=_message_id,
                                        kind=event.kind.value,
                                    )
                                else:
                                    last_sequence = event.sequence or last_sequence

                                yield event
                                retry_count = 0  # reset on success

                                if event.kind in [EventKind.RUN_COMPLETED, EventKind.RUN_FAILED]:
                                    logger.info("run_terminal_event", run_id=run_id)
                                    return

                            except Exception as e:
                                logger.error("event_parse_error", error=str(e), data=message_data)
                                continue

                # Send heartbeat if needed
                if include_heartbeats:
                    now = datetime.utcnow()
                    if (now - last_heartbeat).total_seconds() >= HEARTBEAT_INTERVAL:
                        heartbeat_sequence += 1
                        yield heartbeat_event(run_id, sequence=heartbeat_sequence)
                        last_heartbeat = now

            except asyncio.CancelledError:
                logger.info("subscription_cancelled", run_id=run_id)
                raise
            except Exception as e:
                retry_count += 1
                if retry_count >= max_retries:
                    logger.error("subscription_max_retries", run_id=run_id, retries=retry_count)
                    return
                delay = min(1 * (2 ** (retry_count - 1)), 30)  # exponential backoff, max 30s
                logger.error("subscription_error", run_id=run_id, error=str(e), retry_in=delay)
                await asyncio.sleep(delay)

    async def get_events(
        self,
        run_id: str,
        start_id: str = "-",
        end_id: str = "+",
        count: int = 1000,
    ) -> list[WorkflowEvent]:
        """Get historical events from a run's stream."""
        stream_key = self._stream_key(run_id)
        messages = await self.redis.xrange(stream_key, start_id, end_id, count=count)

        events = []
        for message_id, message_data in messages:
            try:
                event_json = message_data.get("data", "{}")
                event = WorkflowEvent.model_validate_json(event_json)
                event.stream_id = message_id
                events.append(event)
            except Exception as e:
                logger.error("event_parse_error", error=str(e))
                continue

        return events

    async def close(self):
        """Close Redis connection."""
        await self.redis.close()


# Singleton instance with async-safe lock
_event_bus: Optional[EventBus] = None
_event_bus_lock = asyncio.Lock()


async def get_event_bus() -> EventBus:
    """Get or create the singleton EventBus instance (async-safe)."""
    global _event_bus
    if _event_bus is not None:
        return _event_bus
    async with _event_bus_lock:
        if _event_bus is None:
            _event_bus = await EventBus.create()
        return _event_bus


async def close_event_bus():
    """Close the singleton EventBus instance."""
    global _event_bus
    async with _event_bus_lock:
        if _event_bus is not None:
            await _event_bus.close()
            _event_bus = None
