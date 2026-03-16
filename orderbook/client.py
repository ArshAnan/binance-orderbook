import asyncio
import json
import logging
from dataclasses import dataclass

import aiohttp
import websockets

from orderbook.config import OrderBookConfig

logger = logging.getLogger(__name__)


@dataclass
class DepthEvent:
    event_time: int
    symbol: str
    first_update_id: int
    final_update_id: int
    bids: list[tuple[float, float]]
    asks: list[tuple[float, float]]


@dataclass
class OrderBookSnapshot:
    last_update_id: int
    bids: list[tuple[float, float]]
    asks: list[tuple[float, float]]


def _parse_depth_event(raw: str) -> DepthEvent:  # fix 1: moved outside DepthEvent class
    data = json.loads(raw)
    return DepthEvent(
        event_time=data["E"],
        symbol=data["s"],
        first_update_id=data["U"],
        final_update_id=data["u"],
        bids=[(float(p), float(q)) for p, q in data["b"]],
        asks=[(float(p), float(q)) for p, q in data["a"]],
    )


async def stream_depth_events(config: OrderBookConfig):
    attempt = 0

    while attempt < config.max_reconnect_attempts:
        try:
            logger.info(f"Connecting to {config.ws_stream_url} (attempt {attempt + 1})")  # fix 2: logger.infor → logger.info

            async with websockets.connect(config.ws_stream_url) as ws:
                logger.info("Connected successfully")
                attempt = 0

                async for raw_message in ws:  # fix 3: moved inside the async with block
                    yield _parse_depth_event(raw_message)

        except websockets.ConnectionClosed as e:
            logger.warning(f"Connection closed: {e}")

        except Exception as e:
            logger.error(f"Unexpected error: {e}")

        attempt += 1
        wait = min(
            config.base_backoff_seconds * (2 ** attempt),
            config.max_backoff_seconds
        )
        logger.info(f"Reconnecting in {wait:.1f} seconds...")
        await asyncio.sleep(wait)

    raise RuntimeError(f"Failed to connect after {config.max_reconnect_attempts} attempts")


async def fetch_snapshot(config: OrderBookConfig) -> OrderBookSnapshot:
    params = {
        "symbol": config.symbol,
        "limit": config.snapshot_depth_limit,
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(
            config.rest_snapshot_url,
            params=params,
            timeout=aiohttp.ClientTimeout(total=10),
        ) as response:
            if response.status == 429:
                raise RuntimeError("Rate limited by Binance REST API")
            if response.status != 200:
                raise RuntimeError(f"Unexpected status code: {response.status}")

            data = await response.json()

    return OrderBookSnapshot(
        last_update_id=data["lastUpdateId"],
        bids=[(float(p), float(q)) for p, q in data["bids"]],
        asks=[(float(p), float(q)) for p, q in data["asks"]],
    )