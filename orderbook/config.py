from dataclasses import dataclass, field


@dataclass

class OrderBookConfig:
    symbol: str = "BTCUSDT"

    # Binance URLs
    ws_base_url: str = "wss://stream.binance.com:9443/ws"
    rest_base_url: str = "https://api.binance.com"

    #Stream Settings
    depth_update_speed: str = "100ms"
    snapshot_depth_limit: int = 1000

    # Orderbook Settings
    num_levels: int = 20 # Number of price levels to maintain

    # Reconnection Settings
    max_reconnect_attempts: int = 10
    base_backoff_seconds: float = 1.0
    max_backoff_seconds: float = 60.0

    # Storage Settings
    storage_dir: str = "data"
    snapshot_interval_seconds: float = 1.0

    # Derived Properties
    @property
    def ws_stream_url(self) -> str:
        symbol = self.symbol.lower()
        return f"{self.ws_base_url}/{symbol}@depth@{self.depth_update_speed}"

    @property
    def rest_snapshot_url(self) -> str:
        return f"{self.rest_base_url}/api/v3/depth"