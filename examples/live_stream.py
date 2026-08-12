import asyncio
import logging

from orderbook.book import OrderBook
from orderbook.buffer import DepthEventBuffer
from orderbook.client import fetch_snapshot
from orderbook.config import OrderBookConfig
from orderbook.features import FeatureExtractor, feature_size
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
    extractor = FeatureExtractor(config)
    recorder = OrderBookRecorder(config)

    logger.info(f"Starting order book for {config.symbol}")
    logger.info(f"Feature vector size: {feature_size(config)}")

    initialized = False
    event_count = 0

    try:
        async for event in buffer.stream_validated_events():
            if not initialized:
                snapshot = await fetch_snapshot(config)
                book.initialize(snapshot)
                initialized = True
                logger.info("Order book initialized")

            book.apply_event(event)
            event_count += 1

            state = book.top_levels()
            features = extractor.update(state)       # compute features once
            recorder.record(state, features)          # pass features to recorder

            if event_count % 10 == 0:
                derived_start = 6 + 4 * config.num_levels
                returns_start = derived_start + 3 + 2 * config.num_levels

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

                print()
                print(f"Imbalance     : {features[derived_start]:.4f}")
                print(f"Weighted mid  : ${features[derived_start + 1]:,.2f}")
                print(f"Spread bps    : {features[derived_start + 2]:.2f}")
                print(f"Last return   : {features[returns_start + config.num_price_returns - 1] * 100:.6f}%")
                print(f"Feature vector: shape={features.shape} dtype={features.dtype}")
                print(f"Returns slice : {features[returns_start:returns_start + config.num_price_returns]}")
                print(f"Mid history   : {list(extractor._mid_price_history)}")

                if not book.is_valid():
                    logger.error("Book is in invalid state!")

    finally:
        recorder.close()


if __name__ == "__main__":
    asyncio.run(main())