# border

A high-performance, async Python library for real-time order book reconstruction from Binance WebSocket streams. Maintains a fully synchronized local L2 order book via incremental diff application, with sequence validation, automatic resync on gap detection, and Parquet-based recording and deterministic replay.

---

## Features

- **Real-time L2 reconstruction** — incremental diff application via Binance `@depth@100ms` stream
- **Sequence validation** — enforces gapless update sequencing per Binance's sync protocol; triggers automatic resync on any detected gap
- **O(log n) updates** — price level insertions and deletions via `SortedDict`; best bid/ask access in O(1)
- **Async-first** — built entirely on `asyncio`, `websockets`, and `aiohttp`; non-blocking throughout
- **Exponential backoff reconnection** — configurable retry logic with bounded backoff
- **Feature extraction** — computes spread, order book imbalance, weighted mid price, VWAP, cumulative depth, and price impact estimates from raw book state
- **Parquet recording** — columnar storage via `pyarrow` with Snappy compression; schema-stable across sessions
- **Deterministic replay** — replay engine serves recorded data at arbitrary speed with optional looping for backtesting and simulation

---

## Installation

Requires Python 3.11+. Install with `uv`:

```bash
git clone https://github.com/ArshAnan/border.git
cd border
uv sync
uv pip install -e .
```

Or with `pip`:

```bash
pip install -e .
```

---

## Quickstart

### Stream live order book events

```python
import asyncio
from orderbook.book import OrderBook
from orderbook.buffer import DepthEventBuffer
from orderbook.client import fetch_snapshot
from orderbook.config import OrderBookConfig

async def main():
    config = OrderBookConfig(symbol="BTCUSDT")
    buffer = DepthEventBuffer(config)
    book = OrderBook(config)
    initialized = False

    async for event in buffer.stream_validated_events():
        if not initialized:
            snapshot = await fetch_snapshot(config)
            book.initialize(snapshot)
            initialized = True

        book.apply_event(event)
        state = book.top_levels()
        print(f"mid={state.mid_price:.2f} spread={state.spread:.4f}")

asyncio.run(main())
```

### Record to Parquet

```python
from orderbook.storage import OrderBookRecorder

recorder = OrderBookRecorder(config)

async for event in buffer.stream_validated_events():
    ...
    book.apply_event(event)
    state = book.top_levels()
    recorder.record(state)

recorder.close()
```

### Replay recorded data

```python
from orderbook.storage import OrderBookReplay

replay = OrderBookReplay(config)

for frame in replay.replay(loop=True):
    print(frame.timestamp_ms, frame.features.shape)
```

---

## Architecture

```
Binance WebSocket (@depth@100ms)
          │
          ▼
      client.py          — async WebSocket client, exponential backoff reconnection
          │
          ▼
      buffer.py          — event queue, REST snapshot alignment, sequence validation
          │
          ▼
        book.py          — SortedDict L2 book, O(log n) incremental updates
          │
          ▼
     features.py         — numerical feature extraction (spread, imbalance, VWAP, depth)
          │
          ▼
      storage.py         — Parquet recorder + deterministic replay engine
```

---

## Configuration

All settings are controlled via `OrderBookConfig`:

```python
from orderbook.config import OrderBookConfig

config = OrderBookConfig(
    symbol="BTCUSDT",
    depth_update_speed="100ms",   # "100ms" or "1000ms"
    snapshot_depth_limit=1000,    # 100, 500, or 1000
    num_levels=20,                # price levels to maintain
    max_reconnect_attempts=10,
    base_backoff_seconds=1.0,
    max_backoff_seconds=60.0,
    storage_dir="data",
    snapshot_interval_seconds=1.0,
)
```

---

## Feature Vector

`features.py` produces a fixed-length `float64` numpy array per book state. With `num_levels=20` (default), the vector is **129 elements**:

| Segment | Size | Description |
|---|---|---|
| Top of book | 6 | best bid/ask price and qty, mid price, spread |
| Bid depth | 2 × N | prices and quantities for top N bid levels |
| Ask depth | 2 × N | prices and quantities for top N ask levels |
| Derived | 3 | imbalance, weighted mid price, spread in bps |
| Cumulative volume | 2 × N | cumulative bid and ask volume at each level |

Order book imbalance is defined as `bid_vol / (bid_vol + ask_vol)` across the top N levels — values near 1.0 indicate buying pressure, near 0.0 indicate selling pressure.

---

## Sync Protocol

`border` follows Binance's official order book management protocol:

1. Open WebSocket stream and buffer incoming diff events
2. Once buffer reaches threshold, fetch REST snapshot via `GET /api/v3/depth`
3. Drop all buffered events where `final_update_id < snapshot.last_update_id`
4. Find first valid event satisfying `first_update_id <= last_update_id <= final_update_id`
5. Apply all subsequent events in sequence order
6. On any sequence gap: discard book, re-fetch snapshot, re-establish sync

---

## Replay Engine

Recorded Parquet files can be replayed deterministically for backtesting or simulation:

```python
replay = OrderBookReplay(config, data_dir="data/")
files = replay.list_files(symbol="BTCUSDT")

for frame in replay.replay(files=files, loop=False):
    # frame.timestamp_ms  — original event timestamp
    # frame.last_update_id — sequence ID
    # frame.features       — numpy float64 array, shape (129,)
    pass
```

Files are named `{SYMBOL}_{TIMESTAMP}_{COUNT}.parquet` and sorted chronologically. Train/validation/test splits should be made by time — never shuffle across episode boundaries.

---

## Known Limitations / Future Work

- **Gap handling** — current implementation triggers a full resync on any sequence gap. A more durable approach would attempt targeted recovery by fetching a fresh snapshot and continuing without full restart. This is tracked as a known improvement.
- **Single symbol** — one `OrderBook` instance per symbol. Multi-symbol support would require a multiplexed WebSocket connection.
- **Float64 precision** — prices and quantities are stored as `float64`. For production execution use cases, `Decimal` arithmetic should be considered to avoid floating point rounding on financial values.

---

## Dependencies

| Package | Purpose |
|---|---|
| `websockets` | async WebSocket client |
| `aiohttp` | async HTTP for REST snapshot |
| `sortedcontainers` | O(log n) sorted price level storage |
| `pyarrow` | Parquet recording and replay |
| `numpy` | feature vector construction |

---

## License

Apache 2.0