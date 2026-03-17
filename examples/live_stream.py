import asyncio
import logging

from orderbook.client import fetch_snapshot, stream_depth_events
from orderbook.config import OrderBookConfig

# Set up logging so can see what is happening
logging.basicConfig(
    level = logging.INFO,
    format = "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

logger = logging.getLogger(__name__)

async def main():
    config = OrderBookConfig(symbol="BTCUSDT")

    logger.info(f"Starting live stream for {config.symbol}")
    logger.info(f"WebSocket URL: {config.ws_stream_url}")
    logger.info(f"REST Snapshot URL: {config.rest_snapshot_url}")

    #Step 1: Collect the first 10 websocket events to get the initial snapshot
    logger.info("Buffering initial WebSocket events...")
    buffered_events = []

    async for event in stream_depth_events(config):
        buffered_events.append(event)

        if len(buffered_events) >= 10:
            break

    logger.info(f"Buffered {len(buffered_events)} events")

    # Step 2: Fetch the REST snapshot
    logger.info("Fetching REST snapshot...")
    snapshot = await fetch_snapshot(config)
    logger.info(f"Snapshot received - last_update_id: {snapshot.last_update_id}")
    logger.info(f"Snapshot has {len(snapshot.bids)} bids and {len(snapshot.asks)} asks")

    # Step 3: Print the buffered events
    print("\nBuffered WebSocket events:")
    for i, event in enumerate(buffered_events):
        print(
            f"Event {i + 1}: "
            f"first_update_id: {event.first_update_id}, "
            f"final_update_id: {event.final_update_id}, "
            f"bids_changed: {len(event.bids)}, "
            f"asks_changed: {len(event.asks)}"
        )

    # Step 4: check alignment
    print("\nChecking event alignment...")
    print(f"Snapshot last_update_id: {snapshot.last_update_id}")
    print(f"First buffered event first_update_id: {buffered_events[0].first_update_id}")
    print(f"Last buffered event final_update_id: {buffered_events[-1].final_update_id}")

    aligned = any(
        event.first_update_id <= snapshot.last_update_id <= event.final_update_id
        for event in buffered_events
    )

    print(f"\nStream and snapshot are aligned: {aligned}")

    if not aligned:
        print("\nWARNING: Stream and snapshot are not aligned! Snapshot may be too old for buffered events.")
        print("This is normal is the buffer is small. Incease buffer size or retry")

        #Step 5: Print the top 5 levels of the snapshot
    print("\nTop 5 levels of the snapshot:")
    print(f"{'BID PRICE':>12} {'BID QUANTITY':>12} {'ASK PRICE':>12} {'ASK QUANTITY':>12}")
    print("-" * 50)

    for i in range(5):
        bid_price, bid_qty = snapshot.bids[i]
        ask_price, ask_qty = snapshot.asks[i]
        print(f"{bid_price:>12.2f} {bid_qty:>12.6f} {ask_price:>12.2f} {ask_qty:>12.6f}")

if __name__ == "__main__":
    asyncio.run(main())