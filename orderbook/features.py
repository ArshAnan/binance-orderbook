import logging

import numpy as np

from orderbook.book import OrderBookState, OrderBook
from orderbook.config import OrderBookConfig

logger = logging.getLogger(__name__)

def extract_features(state: OrderBookState, config: OrderBookConfig) -> np.ndarray:
    n = config.num_levels
    bids = state.bids[:n]
    asks = state.asks[:n]

    best_bid_price = bids[0].price if bids else 0.0
    best_bid_qty = bids[0].quantity if bids else 0.0
    best_ask_price = asks[0].price if asks else 0.0
    best_ask_qty = asks[0].quantity if asks else 0.0
    mid_price = state.mid_price
    spread = state.spread

    bid_prices = np.array([b.price for b in bids] + [0.0] * (n - len(bids)))
    bid_qtys   = np.array([b.quantity for b in bids] + [0.0] * (n - len(bids)))
    ask_prices = np.array([a.price for a in asks] + [0.0] * (n - len(asks)))
    ask_qtys   = np.array([a.quantity for a in asks] + [0.0] * (n - len(asks)))

    total_bid_vol = float(np.sum(bid_qtys))
    total_ask_vol = float(np.sum(ask_qtys))
    total_vol = total_bid_vol + total_ask_vol
    imbalance = total_bid_vol / total_vol if total_vol > 0 else 0.5

    denom = best_bid_qty + best_ask_qty
    weighted_mid = (
        (best_bid_price * best_ask_qty + best_ask_price * best_bid_qty) / denom
        if denom > 0
        else mid_price
    )

    spread_bps = (spread / mid_price * 10000) if mid_price > 0 else 0.0

    cum_bid_vol = np.cumsum(bid_qtys)
    cum_ask_vol = np.cumsum(ask_qtys)

    features = np.concatenate([
        [best_bid_price, best_bid_qty,
         best_ask_price, best_ask_qty,
         mid_price, spread],
        bid_prices, bid_qtys,
        ask_prices, ask_qtys,
        [imbalance, weighted_mid, spread_bps],
        cum_bid_vol,
        cum_ask_vol,
    ], dtype=np.float64)

    return features