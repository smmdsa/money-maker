"""
Binance Futures WebSocket Manager
=================================
Real-time market data via persistent WebSocket connections to Binance Futures.

Latency: ~100ms (vs ~5s REST polling)

Streams:
  !markPrice@arr@1s  — All mark prices + funding rates, every 1 second
  <symbol>@kline_<i> — Real-time candle updates (dynamic subscription)

Features:
  - Auto-reconnect with exponential backoff (1s → 60s max)
  - Dynamic kline subscription management (subscribe/unsubscribe on the fly)
  - Thread-safe data access (sync threads can read while async loop writes)
  - Health check endpoint with connection stats
  - Stale data detection (price_age_seconds)
  - Falls back to REST API when disconnected

Integration:
  - MarketDataService reads WS prices as L0 cache (before REST/cache)
  - Risk Monitor (5s) gets instant prices — no REST call needed
  - Frontend receives pushed price updates via app WebSocket (3s broadcast)
"""

import asyncio
import json
import logging
import time
from threading import Lock
from typing import Dict, List, Optional, Set
from datetime import datetime

import websockets

logger = logging.getLogger(__name__)

# Binance Futures combined stream endpoint (public, no API key)
BINANCE_WS_STREAM_URL = "wss://fstream.binance.com/stream"


class BinanceWSManager:
    """Real-time market data via Binance Futures WebSocket streams.

    Thread-safe: the async event loop writes data; sync threads read it
    through Lock-protected getters.

    Usage:
        ws = BinanceWSManager()
        await ws.start()          # from asyncio event loop
        price = ws.get_mark_price("BTCUSDT")  # from any thread
        await ws.stop()
    """

    def __init__(self):
        self._ws = None
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._connected = False
        self._reconnect_delay = 1.0
        self._max_reconnect_delay = 60.0
        self._last_message_time: float = 0
        self._subscribe_id = 1

        # ── Thread-safe caches ────────────────────────────────────────────
        self._lock = Lock()
        self._mark_prices: Dict[str, float] = {}       # BTCUSDT → 97000.0
        self._funding_rates: Dict[str, float] = {}     # BTCUSDT → 0.0001
        self._index_prices: Dict[str, float] = {}      # BTCUSDT → 96950.0
        self._kline_data: Dict[str, Dict] = {}          # BTCUSDT_5m → {ohlcv}

        # ── Active kline subscriptions ────────────────────────────────────
        self._kline_streams: Set[str] = set()           # btcusdt@kline_5m
        # ── Price tick callbacks (event-driven risk monitor) ─────────
        self._price_callbacks = []
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        # ── Stats ─────────────────────────────────────────────────────────
        self._messages_received = 0
        self._connection_count = 0
        self._errors = 0

    # ══════════════════════════════════════════════════════════════════════
    #  Lifecycle
    # ══════════════════════════════════════════════════════════════════════

    async def start(self):
        """Start the WebSocket manager. Must be called from asyncio event loop."""
        if self._running:
            return
        self._running = True
        self._loop = asyncio.get_running_loop()
        self._task = asyncio.create_task(self._connection_loop())
        logger.info("🔌 Binance WebSocket manager started")

    async def stop(self):
        """Gracefully stop the WebSocket manager."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None
        self._connected = False
        logger.info("🔌 Binance WebSocket manager stopped")

    # ══════════════════════════════════════════════════════════════════════
    #  Connection Management
    # ══════════════════════════════════════════════════════════════════════

    async def _connection_loop(self):
        """Main loop: connect → receive messages → reconnect on failure."""
        while self._running:
            try:
                await self._connect_and_listen()
            except asyncio.CancelledError:
                logger.info("WebSocket connection loop cancelled")
                break
            except websockets.ConnectionClosed as e:
                logger.warning(f"WebSocket closed: code={e.code} reason={e.reason}")
            except Exception as e:
                logger.error(f"WebSocket error: {type(e).__name__}: {e}")
                self._errors += 1

            if not self._running:
                break

            self._connected = False
            delay = min(self._reconnect_delay, self._max_reconnect_delay)
            logger.info(f"WebSocket reconnecting in {delay:.0f}s...")
            try:
                await asyncio.sleep(delay)
            except asyncio.CancelledError:
                break
            self._reconnect_delay = min(
                self._reconnect_delay * 2, self._max_reconnect_delay
            )

    async def _connect_and_listen(self):
        """Connect to Binance combined stream and process messages."""
        # Base streams: all mark prices every 1 second
        base_streams = ["!markPrice@arr@1s"]
        all_streams = base_streams + list(self._kline_streams)

        url = f"{BINANCE_WS_STREAM_URL}?streams={'/'.join(all_streams)}"

        logger.info(
            f"Connecting to Binance Futures WebSocket "
            f"({len(all_streams)} stream(s))..."
        )

        async with websockets.connect(
            url,
            ping_interval=20,
            ping_timeout=10,
            max_size=2 ** 22,   # 4 MB max message
        ) as ws:
            self._ws = ws
            self._connected = True
            self._reconnect_delay = 1.0   # Reset backoff
            self._connection_count += 1

            logger.info(
                f"✅ Binance WebSocket connected "
                f"(#{self._connection_count}, {len(all_streams)} stream(s))"
            )

            async for raw in ws:
                if not self._running:
                    break
                self._process_message(raw)

    # ══════════════════════════════════════════════════════════════════════
    #  Message Routing
    # ══════════════════════════════════════════════════════════════════════

    def _process_message(self, raw: str):
        """Parse and route incoming messages."""
        try:
            msg = json.loads(raw)
            self._messages_received += 1
            self._last_message_time = time.time()

            # Combined stream format: {"stream": "...", "data": ...}
            stream = msg.get("stream", "")
            data = msg.get("data", msg)

            if "markPrice" in stream:
                self._on_mark_price_batch(data)
            elif "kline" in stream:
                self._on_kline(data)
            # Subscription confirmations ({"result": null, "id": N}) — ignored

        except json.JSONDecodeError:
            pass
        except Exception as e:
            logger.debug(f"WS message processing error: {e}")

    # ── Stream Handlers ───────────────────────────────────────────────────

    def _on_mark_price_batch(self, data):
        """Process !markPrice@arr — all mark prices at once (every 1s).

        Each item: {s: symbol, p: markPrice, i: indexPrice, r: fundingRate, ...}
        Fires registered price callbacks after updating caches (outside lock).
        """
        if not isinstance(data, list):
            data = [data]

        updated: Dict[str, float] = {}

        with self._lock:
            for item in data:
                symbol = item.get("s", "")
                if not symbol:
                    continue
                try:
                    price = float(item.get("p", 0))
                    if price > 0:
                        self._mark_prices[symbol] = price
                        updated[symbol] = price

                    funding = item.get("r")
                    if funding is not None:
                        self._funding_rates[symbol] = float(funding)

                    idx = item.get("i")
                    if idx:
                        self._index_prices[symbol] = float(idx)
                except (ValueError, TypeError):
                    continue

        # Fire callbacks OUTSIDE the lock — subscribers do their own filtering
        if updated and self._price_callbacks:
            for cb in self._price_callbacks:
                try:
                    cb(updated)
                except Exception as e:
                    logger.error(f"Price tick callback error: {e}")

    def _on_kline(self, data):
        """Process individual kline (candlestick) update.

        Payload: {e: "kline", s: "BTCUSDT", k: {t, o, h, l, c, v, x, ...}}
        x = true when candle is closed (final update).
        """
        k = data.get("k")
        if not k:
            return

        symbol = k.get("s", "")
        interval = k.get("i", "")
        if not symbol or not interval:
            return

        key = f"{symbol}_{interval}"

        with self._lock:
            try:
                self._kline_data[key] = {
                    "timestamp": datetime.fromtimestamp(k["t"] / 1000),
                    "open": float(k["o"]),
                    "high": float(k["h"]),
                    "low": float(k["l"]),
                    "close": float(k["c"]),
                    "volume": float(k["v"]),
                    "closed": k.get("x", False),
                    "updated_at": time.time(),
                }
            except (ValueError, TypeError, KeyError):
                pass

    # ══════════════════════════════════════════════════════════════════════
    #  Public Read API (thread-safe)
    # ══════════════════════════════════════════════════════════════════════

    def get_mark_price(self, symbol: str) -> Optional[float]:
        """Get latest mark price for a Binance Futures symbol.

        Example: get_mark_price('BTCUSDT') → 97123.45
        Returns None if no data available.
        """
        with self._lock:
            return self._mark_prices.get(symbol)

    def get_all_mark_prices(self) -> Dict[str, float]:
        """Get all current mark prices. Returns a thread-safe copy."""
        with self._lock:
            return dict(self._mark_prices)

    def get_funding_rate(self, symbol: str) -> Optional[float]:
        """Get latest funding rate for a symbol."""
        with self._lock:
            return self._funding_rates.get(symbol)

    def get_all_funding_rates(self) -> Dict[str, float]:
        """Get all current funding rates. Returns a thread-safe copy."""
        with self._lock:
            return dict(self._funding_rates)

    def get_index_price(self, symbol: str) -> Optional[float]:
        """Get latest index price for a symbol."""
        with self._lock:
            return self._index_prices.get(symbol)

    def get_latest_kline(self, symbol: str, interval: str) -> Optional[Dict]:
        """Get latest kline data for a symbol + interval.

        Example: get_latest_kline('BTCUSDT', '5m')
        Returns dict with: timestamp, open, high, low, close, volume, closed
        """
        key = f"{symbol}_{interval}"
        with self._lock:
            d = self._kline_data.get(key)
            return dict(d) if d else None

    # ── Price Tick Callbacks (event-driven subscribers) ────────────────

    def on_price_tick(self, callback):
        """Register a callback invoked on each mark price batch (1s).

        Callback signature: callback(prices: Dict[str, float])
          - prices: {"BTCUSDT": 97000.0, "ETHUSDT": 3200.0, ...}
          - Runs on the asyncio event loop thread — must be fast.
        """
        if callback not in self._price_callbacks:
            self._price_callbacks.append(callback)
            logger.info(f"WS: registered price tick callback ({len(self._price_callbacks)} total)")

    def remove_price_tick(self, callback):
        """Remove a previously registered price tick callback."""
        try:
            self._price_callbacks.remove(callback)
            logger.info(f"WS: removed price tick callback ({len(self._price_callbacks)} remaining)")
        except ValueError:
            pass

    # ── Connection State ──────────────────────────────────────────────────

    @property
    def is_connected(self) -> bool:
        """Whether the WebSocket is currently connected."""
        return self._connected

    @property
    def price_age_seconds(self) -> float:
        """Seconds since last message received. >10 = stale."""
        if self._last_message_time == 0:
            return float("inf")
        return time.time() - self._last_message_time

    @property
    def prices_available(self) -> bool:
        """True if we have recent price data (< 10 seconds old)."""
        return self._connected and self.price_age_seconds < 10

    # ══════════════════════════════════════════════════════════════════════
    #  Dynamic Kline Subscriptions
    # ══════════════════════════════════════════════════════════════════════

    async def subscribe_klines(self, symbol: str, interval: str):
        """Subscribe to real-time kline stream for a symbol + interval.

        Example: await subscribe_klines('BTCUSDT', '5m')
        """
        stream = f"{symbol.lower()}@kline_{interval}"
        if stream in self._kline_streams:
            return

        self._kline_streams.add(stream)

        if self._ws and self._connected:
            try:
                self._subscribe_id += 1
                await self._ws.send(json.dumps({
                    "method": "SUBSCRIBE",
                    "params": [stream],
                    "id": self._subscribe_id,
                }))
                logger.info(f"WebSocket: subscribed to {stream}")
            except Exception as e:
                logger.warning(f"Failed to subscribe to {stream}: {e}")

    async def unsubscribe_klines(self, symbol: str, interval: str):
        """Unsubscribe from a kline stream."""
        stream = f"{symbol.lower()}@kline_{interval}"
        self._kline_streams.discard(stream)

        if self._ws and self._connected:
            try:
                self._subscribe_id += 1
                await self._ws.send(json.dumps({
                    "method": "UNSUBSCRIBE",
                    "params": [stream],
                    "id": self._subscribe_id,
                }))
                logger.info(f"WebSocket: unsubscribed from {stream}")
            except Exception as e:
                logger.warning(f"Failed to unsubscribe from {stream}: {e}")

    async def sync_kline_subscriptions(self, needed: Set[str]):
        """Synchronize kline subscriptions with a set of needed streams.

        Input: set of 'SYMBOL_INTERVAL' strings.
        Example: {'BTCUSDT_5m', 'ETHUSDT_1m'}

        Subscribes to new streams, unsubscribes from old ones.
        """
        needed_streams = set()
        for s in needed:
            parts = s.split("_", 1)
            if len(parts) == 2:
                needed_streams.add(f"{parts[0].lower()}@kline_{parts[1]}")

        to_add = needed_streams - self._kline_streams
        to_remove = self._kline_streams - needed_streams

        for stream in to_add:
            parts = stream.split("@kline_")
            if len(parts) == 2:
                await self.subscribe_klines(parts[0].upper(), parts[1])

        for stream in to_remove:
            parts = stream.split("@kline_")
            if len(parts) == 2:
                await self.unsubscribe_klines(parts[0].upper(), parts[1])

    # ══════════════════════════════════════════════════════════════════════
    #  Health Check
    # ══════════════════════════════════════════════════════════════════════

    def health_check(self) -> Dict:
        """Return WebSocket connection health and stats."""
        with self._lock:
            price_count = len(self._mark_prices)
            kline_count = len(self._kline_data)

        return {
            "status": "connected" if self._connected else "disconnected",
            "messages_received": self._messages_received,
            "price_symbols_tracked": price_count,
            "kline_streams_active": len(self._kline_streams),
            "kline_data_keys": kline_count,
            "last_message_age_s": (
                round(self.price_age_seconds, 1)
                if self._last_message_time > 0 else None
            ),
            "connection_count": self._connection_count,
            "errors": self._errors,
            "prices_fresh": self.prices_available,
            "price_callbacks": len(self._price_callbacks),
        }
