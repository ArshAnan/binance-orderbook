import asyncio
import logging

import numpy as np

from orderbook.book import OrderBook
from orderbook.buffer import DepthEventBuffer
from orderbook.config import OrderBookConfig
from orderbook.features import extract_features

from orderbook.storage import OrderBookRecorder

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)

logger = logging.getLogger(__name__)


async def main():
    config = OrderBookConfig(symbol="BTCUSDT")
    buffer = DepthEventBuffer(config)
    book = OrderBook(config)
    recorder = OrderBookRecorder(config)
    logger.info(f"Starting order book for {config.symbol}")

    initialized = False
    event_count = 0

    try:
        async for event in buffer.stream_validated_events():
            if not initialized:
                from orderbook.client import fetch_snapshot
                snapshot = await fetch_snapshot(config)
                book.initialize(snapshot)
                initialized = True
                logger.info("Order book initialized")

            book.apply_event(event)
            event_count += 1

            if event_count % 10 == 0:
                state = book.top_levels(5)
                recorder.record(state)

                print(f"\n--- Order Book ({config.symbol}) | update #{event_count} ---")
                print(f"Mid price : ${state.mid_price:,.2f}")
                print(f"Spread    : ${state.spread:.2f}")
                print()
                print(f"{'BID PRICE':>12} {'BID QTY':>12}  {'ASK PRICE':>12} {'ASK QTY':>12}")
                print("-" * 56)

                for i in range(min(5, len(state.bids), len(state.asks))):
                    bid = state.bids[i]
                    ask = state.asks[i]
                    print(
                        f"{bid.price:>12,.2f} {bid.quantity:>12.6f}  "
                        f"{ask.price:>12,.2f} {ask.quantity:>12.6f}"
                    )

                state = book.top_levels()
                features = extract_features(state, config)

                print()
                print(f"Imbalance     : {features[6 + 4*config.num_levels]:.4f}")
                print(f"Weighted mid  : ${features[7 + 4*config.num_levels]:,.2f}")
                print(f"Spread bps    : {features[8 + 4*config.num_levels]:.2f}")
                print(f"Feature vector: shape={features.shape} dtype={features.dtype}")

                if not book.is_valid():
                    logger.error("Book is in invalid state!")
    finally:
        recorder.close()

if __name__ == "__main__":
    asyncio.run(main())