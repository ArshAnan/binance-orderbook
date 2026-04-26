import asyncio
import logging
from collections import deque
from enum import Enum, auto
from typing import AsyncGenerator

from orderbook.client import DepthEvent, OrderBookSnapshot, fetch_snapshot, stream_depth_events
from orderbook.config import OrderBookConfig

logger = logging.getLogger(__name__)


class SyncState(Enum):
    BUFFERING = auto()
    SYNCED = auto()
    RESYNCING = auto()


class DepthEventBuffer:
    def __init__(self, config: OrderBookConfig):
        self.config = config
        self._queue: deque[DepthEvent] = deque()
        self._state = SyncState.BUFFERING
        self._last_update_id: int | None = None

    def _buffer_event(self, event: DepthEvent) -> None:
        self._queue.append(event)

    def _drop_stale_events(self, snapshot: OrderBookSnapshot) -> None:
        while self._queue:
            event = self._queue[0]
            if event.final_update_id < snapshot.last_update_id:
                self._queue.popleft()
                logger.debug(f"Dropped stale event u={event.final_update_id}")
            else:
                break

    def _find_first_valid_event(self, snapshot: OrderBookSnapshot) -> bool:
        if not self._queue:
            logger.warning("Queue is empty after dropping stale events")
            return False

        first = self._queue[0]
        logger.info(
            f"Alignment check — snapshot={snapshot.last_update_id}, "
            f"first_update_id={first.first_update_id}, "
            f"final_update_id={first.final_update_id}"
        )
        valid = (
            first.first_update_id <= snapshot.last_update_id
            <= first.final_update_id
        )

        if valid:
            self._last_update_id = snapshot.last_update_id
            logger.info(f"Sync established - snapshot last_update_id={snapshot.last_update_id}")
        else:
            logger.warning(
                f"Could not find valid first event - "
                f"snapshot last_update_id={snapshot.last_update_id}, "
                f"first event U={first.first_update_id}"
            )
        return valid

    def _validate_sequence(self, event: DepthEvent) -> bool:
        if self._last_update_id is None:
            return False

        expected = self._last_update_id + 1
        if event.first_update_id != expected:
            logger.error(
                f"Sequence gap detected - expected U={expected}, "
                f"got U={event.first_update_id}"
            )
            return False
        return True

    async def stream_validated_events(self) -> AsyncGenerator[DepthEvent, None]:
        while True:
            self._state = SyncState.BUFFERING
            self._queue.clear()
            self._last_update_id = None

            logger.info("Starting sync sequence...")

            async for raw_event in stream_depth_events(self.config):
                if self._state == SyncState.BUFFERING:
                    self._buffer_event(raw_event)

                    if len(self._queue) >= 50:  # increased from 10 to 50
                        logger.info("Buffer has 50 events, fetching snapshot...")
                        snapshot = await fetch_snapshot(self.config)

                        # keep collecting events while we process the snapshot
                        logger.info(
                            f"Snapshot last_update_id={snapshot.last_update_id}, "
                            f"buffer has {len(self._queue)} events, "
                            f"first={self._queue[0].first_update_id}, "
                            f"last={self._queue[-1].final_update_id}"
                        )

                        self._drop_stale_events(snapshot)

                        logger.info(
                            f"After drop: {len(self._queue)} events remain in buffer"
                        )

                        if not self._find_first_valid_event(snapshot):
                            logger.warning("Sync failed, restarting...")
                            self._state = SyncState.RESYNCING
                            break

                        self._state = SyncState.SYNCED
                        logger.info("Synced — draining buffered events...")

                        while self._queue:
                            buffered_event = self._queue.popleft()
                            self._last_update_id = buffered_event.final_update_id
                            yield buffered_event

                elif self._state == SyncState.SYNCED:
                    if not self._validate_sequence(raw_event):
                        logger.error("Sequence gap — resyncing...")
                        self._state = SyncState.RESYNCING
                        break

                    self._last_update_id = raw_event.final_update_id
                    yield raw_event