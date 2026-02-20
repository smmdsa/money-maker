"""
Reactive Risk Monitor — Event-Driven SL/TP/Liquidation Detection
================================================================
Subscribes to BinanceWSManager price tick callbacks (1s interval)
and checks open positions for stop-loss, take-profit, and liquidation
in real time — reducing detection latency from 5s polling to ~1s.

Architecture:
  WS tick (1s) → callback → filter watchlist → thread pool → risk check → DB commit

Safety:
  - Non-blocking lock: skips tick if trading cycle holds lock (retry in 1s, not 5s)
  - 5s scheduler fallback remains as defense-in-depth safety net
  - Thread-safe idle flag prevents stacking concurrent checks
  - Watchlist refreshed every 30s + immediately on position open/close
  - Each tick gets a fresh DB session — no stale object references
  - Single commit per tick batch (trailing stop updates)
  - Position deletions committed inline by _close_position (immediate)

Performance:
  - O(n) filter where n = watchlist size (typically 1-5 positions)
  - DB queries by primary key only (~1ms each)
  - Entire risk check per tick: ~5-15ms for 5 positions
  - Event loop thread blocked for ~0.01ms (watchlist filter only)
"""

import asyncio
import logging
import time
import threading
from typing import Dict, List, Optional, Callable, Tuple

from sqlalchemy.orm import Session

from backend.models.database import TradingAgent, Portfolio
from backend.services.market_data import BinanceProvider

logger = logging.getLogger(__name__)


class ReactiveRiskMonitor:
    """Event-driven risk monitor that reacts to WebSocket price ticks.

    Instead of polling every 5 seconds, subscribes to the WS manager's
    price tick callback (fired every 1s with all mark prices) and checks
    only the positions whose symbol price just updated.

    Usage:
        monitor = ReactiveRiskMonitor(trading_service, ws_manager, get_db, lock)
        await monitor.start()
        # ... runs automatically on each WS tick ...
        monitor.refresh()          # call after position open/close
        monitor.stop()
    """

    WATCHLIST_REFRESH_INTERVAL = 30  # seconds

    def __init__(
        self,
        trading_service,            # TradingAgentService
        ws_manager,                 # BinanceWSManager
        get_db: Callable,           # get_db generator function
        trading_lock: threading.Lock,
        broadcast_fn: Optional[Callable] = None,
    ):
        self._trading_service = trading_service
        self._ws_manager = ws_manager
        self._get_db = get_db
        self._trading_lock = trading_lock
        self._broadcast_fn = broadcast_fn

        # Watchlist: Binance symbol → [(agent_id, pos_id, coin_id)]
        self._watchlist: Dict[str, List[Tuple[int, int, str]]] = {}
        self._watchlist_lock = threading.Lock()
        self._last_refresh: float = 0

        # Concurrency: prevent stacking async checks.
        # threading.Event is used because it's checked from the event loop
        # thread (sync) and cleared/set from thread pool (async) — both
        # thread-safe operations.
        self._idle = threading.Event()
        self._idle.set()   # Initially idle

        # Async event loop reference (set in start())
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._active = False

        # Stats
        self._ticks_received = 0
        self._ticks_processed = 0
        self._ticks_skipped_no_match = 0
        self._ticks_skipped_busy = 0
        self._ticks_skipped_locked = 0
        self._actions_taken = 0
        self._last_check_ms: float = 0
        self._start_time: float = 0

    # ══════════════════════════════════════════════════════════════════════
    #  Lifecycle
    # ══════════════════════════════════════════════════════════════════════

    async def start(self):
        """Start the reactive risk monitor. Must be called from asyncio loop."""
        self._loop = asyncio.get_running_loop()
        self._active = True
        self._start_time = time.time()

        # Build initial watchlist (blocking, runs in thread pool)
        await asyncio.to_thread(self._refresh_watchlist)

        # Register callback on WS manager
        self._ws_manager.on_price_tick(self._on_tick)

        watch_count = sum(len(v) for v in self._watchlist.values())
        logger.info(
            f"⚡ Reactive Risk Monitor started — "
            f"watching {len(self._watchlist)} symbol(s), "
            f"{watch_count} position(s)"
        )

    def stop(self):
        """Stop the reactive risk monitor."""
        self._active = False
        self._ws_manager.remove_price_tick(self._on_tick)
        logger.info(
            f"⚡ Reactive Risk Monitor stopped — "
            f"processed {self._ticks_processed} ticks, "
            f"{self._actions_taken} actions taken"
        )

    # ══════════════════════════════════════════════════════════════════════
    #  Watchlist Management
    # ══════════════════════════════════════════════════════════════════════

    def _refresh_watchlist(self):
        """Rebuild watchlist from DB. Thread-safe, creates own session."""
        try:
            db = next(self._get_db())
            try:
                self._refresh_watchlist_from_db(db)
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Reactive watchlist refresh error: {e}")

    def _refresh_watchlist_from_db(self, db: Session):
        """Rebuild watchlist using an existing DB session."""
        try:
            new_watchlist: Dict[str, List[Tuple[int, int, str]]] = {}

            agents = db.query(TradingAgent).filter(
                TradingAgent.status == "active"
            ).all()

            for agent in agents:
                for pos in agent.portfolio:
                    if pos.amount > 0:
                        # Map coin_id → Binance symbol (e.g. "bitcoin" → "BTCUSDT")
                        binance_sym = BinanceProvider.SYMBOL_MAP.get(pos.cryptocurrency)
                        if binance_sym:
                            new_watchlist.setdefault(binance_sym, []).append(
                                (agent.id, pos.id, pos.cryptocurrency)
                            )

            with self._watchlist_lock:
                self._watchlist = new_watchlist
                self._last_refresh = time.time()

            watch_count = sum(len(v) for v in new_watchlist.values())
            if watch_count > 0:
                logger.debug(
                    f"Reactive watchlist refreshed: "
                    f"{len(new_watchlist)} symbol(s), {watch_count} position(s)"
                )
        except Exception as e:
            logger.error(f"Reactive watchlist rebuild error: {e}")

    def refresh(self):
        """Public: trigger watchlist refresh after position open/close.

        Safe to call from any thread — dispatches to thread pool via the
        asyncio event loop. If the loop isn't running, does nothing.
        """
        if self._loop and self._active:
            self._loop.call_soon_threadsafe(
                self._loop.create_task,
                asyncio.to_thread(self._refresh_watchlist)
            )

    # ══════════════════════════════════════════════════════════════════════
    #  Event Handler (called on event loop thread — MUST BE FAST)
    # ══════════════════════════════════════════════════════════════════════

    def _on_tick(self, prices: Dict[str, float]):
        """Callback from WS manager on each mark price batch (1s).

        Runs on the asyncio event loop thread. Only does a quick O(n)
        watchlist filter (n = number of watched symbols, typically 1-5),
        then dispatches the actual risk check to the thread pool.
        """
        if not self._active:
            return

        self._ticks_received += 1

        # Quick filter: only symbols with open positions
        with self._watchlist_lock:
            relevant = {
                sym: prices[sym]
                for sym in self._watchlist
                if sym in prices
            }

        if not relevant:
            self._ticks_skipped_no_match += 1
            return

        # Don't stack concurrent checks — if previous tick's check is still
        # running, skip this tick. With 1s ticks and ~10ms checks, this
        # almost never fires. When it does, the next tick retries in 1s.
        if not self._idle.is_set():
            self._ticks_skipped_busy += 1
            return

        self._idle.clear()  # Mark as busy
        self._loop.create_task(self._async_check(relevant))

    # ══════════════════════════════════════════════════════════════════════
    #  Async Dispatch → Thread Pool
    # ══════════════════════════════════════════════════════════════════════

    async def _async_check(self, prices: Dict[str, float]):
        """Dispatch risk check to thread pool and broadcast results."""
        try:
            actions = await asyncio.to_thread(self._sync_check, prices)

            # Broadcast any closes triggered by the reactive monitor
            if actions and self._broadcast_fn:
                for action in actions:
                    try:
                        await self._broadcast_fn(action)
                    except Exception as e:
                        logger.error(f"Reactive risk broadcast error: {e}")

        except Exception as e:
            logger.error(f"Reactive risk async dispatch error: {e}")
        finally:
            self._idle.set()  # Mark as idle — allow next tick

    # ══════════════════════════════════════════════════════════════════════
    #  Synchronous Risk Check (runs in thread pool)
    # ══════════════════════════════════════════════════════════════════════

    def _sync_check(self, prices: Dict[str, float]) -> List[Dict]:
        """Run risk checks on positions matching the given symbols.

        Acquires _trading_lock non-blocking. If the trading cycle holds it,
        skips this tick (retry in 1s instead of 5s with the old poller).
        Each invocation gets a fresh DB session — no stale references.
        """
        t0 = time.monotonic()

        if not self._trading_lock.acquire(blocking=False):
            self._ticks_skipped_locked += 1
            return []

        try:
            db = next(self._get_db())
            actions = []
            position_closed = False

            try:
                # Periodic watchlist refresh (every 30s)
                if time.time() - self._last_refresh > self.WATCHLIST_REFRESH_INTERVAL:
                    self._refresh_watchlist_from_db(db)

                # Build check list from current watchlist snapshot
                with self._watchlist_lock:
                    entries_to_check = []
                    for sym, price in prices.items():
                        for agent_id, pos_id, coin_id in self._watchlist.get(sym, []):
                            entries_to_check.append((agent_id, pos_id, coin_id, price))

                # Check each position (typically 1-5 positions)
                for agent_id, pos_id, coin_id, price in entries_to_check:
                    try:
                        agent = db.query(TradingAgent).get(agent_id)
                        pos = db.query(Portfolio).get(pos_id)

                        # Safety: skip if agent deactivated or position gone
                        if not agent or agent.status != "active":
                            continue
                        if not pos or pos.amount <= 0:
                            continue

                        result = self._trading_service._risk_check_position(
                            agent, pos, price, db
                        )
                        if result:
                            actions.append(result)
                            self._actions_taken += 1
                            position_closed = True
                            logger.info(
                                f"⚡ REACTIVE: {result.get('action', 'close')} "
                                f"{result.get('coin', '?')} — "
                                f"PnL: ${result.get('profit_loss', 0):.2f}"
                            )

                    except Exception as e:
                        logger.error(
                            f"Reactive risk check error for "
                            f"agent={agent_id} pos={pos_id}: {e}"
                        )

                # Single commit for all trailing stop updates in this tick.
                # (Position closes are already committed inline by _close_position)
                db.commit()

                # If any position was closed, rebuild watchlist immediately
                if position_closed:
                    self._refresh_watchlist_from_db(db)

            finally:
                db.close()

            self._ticks_processed += 1
            self._last_check_ms = (time.monotonic() - t0) * 1000

            return actions

        except Exception as e:
            logger.error(f"Reactive risk monitor sync error: {e}")
            return []
        finally:
            self._trading_lock.release()

    # ══════════════════════════════════════════════════════════════════════
    #  Health / Stats
    # ══════════════════════════════════════════════════════════════════════

    def health_check(self) -> Dict:
        """Return reactive risk monitor stats for /api/health endpoint."""
        uptime = time.time() - self._start_time if self._start_time else 0

        with self._watchlist_lock:
            symbols = len(self._watchlist)
            positions = sum(len(v) for v in self._watchlist.values())
            watched = list(self._watchlist.keys())

        return {
            "active": self._active,
            "uptime_s": round(uptime, 0),
            "watchlist_symbols": symbols,
            "watchlist_positions": positions,
            "watched_symbols": watched,
            "ticks_received": self._ticks_received,
            "ticks_processed": self._ticks_processed,
            "ticks_skipped_no_match": self._ticks_skipped_no_match,
            "ticks_skipped_busy": self._ticks_skipped_busy,
            "ticks_skipped_locked": self._ticks_skipped_locked,
            "actions_taken": self._actions_taken,
            "last_check_ms": round(self._last_check_ms, 2),
            "idle": self._idle.is_set(),
        }
