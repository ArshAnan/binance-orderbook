import asyncio
import logging

from orderbook.book import OrderBook
from orderbook.buffer import DepthEventBuffer
from orderbook.client import fetch_snapshot, DepthEvent
from orderbook.config import OrderBookConfig
from orderbook.features import FeatureExtractor, feature_size
from orderbook.storage import OrderBookRecorder

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)

logger = logging.getLogger(__name__)


async def producer(buffer: DepthEventBuffer, queue: asyncio.Queue) -> None:
    """
    Only job: pull validated events off the WebSocket stream as fast as
    possible and hand them to the queue. Never does any heavy processing,
    so it can never fall behind the incoming message rate.
    """
    async for event in buffer.stream_validated_events():
        await queue.put(event)


async def consumer(
    queue: asyncio.Queue,
    book: OrderBook,
    extractor: FeatureExtractor,
    recorder: OrderBookRecorder,
    config: OrderBookConfig,
) -> None:
    """
    Pulls events off the queue and does all the heavier work: applying
    to the book, extracting features, recording to disk, printing.
    Runs at its own pace, decoupled from the WebSocket receive rate.
    """
    initialized = False
    event_count = 0

    while True:
        event: DepthEvent = await queue.get()

        if not initialized:
            snapshot = await fetch_snapshot(config)
            book.initialize(snapshot)
            initialized = True
            logger.info("Order book initialized")

        book.apply_event(event)
        event_count += 1

        state = book.top_levels()
        features = extractor.update(state)
        recorder.record(state, features)

        if event_count % 10 == 0:
            derived_start = 6 + 4 * config.num_levels
            returns_start = derived_start + 3 + 2 * config.num_levels

            print(f"\n--- Order Book ({config.symbol}) | update #{event_count} ---")
            print(f"Mid price : ${state.mid_price:,.2f}")
            print(f"Spread    : ${state.spread:.2f}")
            print(f"Queue size: {queue.qsize()}")  # watch this — should stay near 0

            if not book.is_valid():
                logger.error("Book is in invalid state!")

        queue.task_done()


async def main():
    config = OrderBookConfig(symbol="BTCUSDT")
    buffer = DepthEventBuffer(config)
    book = OrderBook(config)
    extractor = FeatureExtractor(config)
    recorder = OrderBookRecorder(config)

    logger.info(f"Starting order book for {config.symbol}")
    logger.info(f"Feature vector size: {feature_size(config)}")

    queue: asyncio.Queue = asyncio.Queue()

    producer_task = asyncio.create_task(producer(buffer, queue))
    consumer_task = asyncio.create_task(
        consumer(queue, book, extractor, recorder, config)
    )

    try:
        await asyncio.gather(producer_task, consumer_task)
    except asyncio.CancelledError:
        pass
    finally:
        recorder.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting down...")