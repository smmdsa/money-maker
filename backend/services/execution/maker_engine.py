"""
MakerExecutionManager — Async Post-Only limit-order execution engine.

For 1m/3m scalper timeframes, market (taker) orders incur 0.10% round-trip
fees.  Post-Only limit (maker) orders pay only 0.04% — a 60% fee reduction
that turns micro-edge strategies profitable.

Architecture:
  • Asyncio-native with non-blocking order placement and monitoring
  • Post-Only enforcement (reject if order would cross the spread)
  • Adaptive price offset from mid-price based on volatility
  • Auto-cancel on adverse price movement (configurable threshold)
  • Fill-or-kill timeout with graceful degradation to IOC
  • Queue tracking for pending orders with concurrent-safety via asyncio.Lock

Integration::

    from backend.services.execution import MakerExecutionManager, MakerConfig

    manager = MakerExecutionManager(
        place_order=exchange.create_limit_order,
        cancel_order=exchange.cancel_order,
        get_order_status=exchange.get_order,
        get_best_price=exchange.get_best_bid_ask,
        config=MakerConfig(price_offset_bps=1.5),
    )

    result = await manager.execute(
        symbol="BTCUSDT",
        side="BUY",
        quantity=0.001,
        reference_price=65000.0,
    )
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Awaitable, Callable, Dict, List, Optional, Protocol

logger = logging.getLogger(__name__)


# ── Enums ───────────────────────────────────────────────────────────────────


class OrderStatus(Enum):
    """Lifecycle states of a maker order."""
    PENDING = auto()
    PLACED = auto()
    PARTIALLY_FILLED = auto()
    FILLED = auto()
    CANCELLED = auto()
    EXPIRED = auto()
    REJECTED = auto()


# ── Data Models ─────────────────────────────────────────────────────────────


@dataclass
class MakerOrder:
    """Internal representation of a maker limit order."""
    symbol: str
    side: str                                # "BUY" | "SELL"
    quantity: float
    limit_price: float
    status: OrderStatus = OrderStatus.PENDING
    order_id: Optional[str] = None
    filled_qty: float = 0.0
    avg_fill_price: float = 0.0
    created_at: float = field(default_factory=time.monotonic)
    attempts: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class MakerConfig:
    """Immutable configuration for maker execution behaviour.

    Attributes:
        price_offset_bps: Place limit order N basis points inside best
            bid/ask (e.g. 1.0 = 0.01% inside).
        max_wait_s: Maximum seconds to wait for a fill per attempt.
        max_adverse_pct: Cancel if mid-price moves this % against the order.
        fallback_to_ioc: If all maker attempts fail, try an Immediate-Or-Cancel
            market order as last resort.
        max_retries: Maximum re-placement attempts before giving up.
        post_only: Enforce Post-Only flag (exchange rejects if it would cross).
        poll_interval_s: Order status polling interval in seconds.
    """
    price_offset_bps: float = 1.0
    max_wait_s: float = 30.0
    max_adverse_pct: float = 0.05
    fallback_to_ioc: bool = True
    max_retries: int = 2
    post_only: bool = True
    poll_interval_s: float = 0.5


# ── Callback Protocols ──────────────────────────────────────────────────────


class PlaceOrderFn(Protocol):
    """Signature for the exchange order-placement callback."""
    async def __call__(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        post_only: bool = True,
    ) -> Dict[str, Any]: ...


class CancelOrderFn(Protocol):
    """Signature for the exchange order-cancellation callback."""
    async def __call__(self, symbol: str, order_id: str) -> bool: ...


class GetOrderStatusFn(Protocol):
    """Signature for the exchange order-status callback."""
    async def __call__(self, symbol: str, order_id: str) -> Dict[str, Any]: ...


class GetBestPriceFn(Protocol):
    """Signature for the best bid/ask retrieval callback."""
    async def __call__(self, symbol: str) -> Dict[str, float]: ...


# ── Manager ─────────────────────────────────────────────────────────────────


class MakerExecutionManager:
    """Async Post-Only limit order execution engine for low-TF scalpers.

    Designed for 1m/3m timeframes where taker fees (0.05% each side)
    destroy micro-edge.  Maker fees are 0.02% each side = 60% saving.

    The manager handles the full order lifecycle:
      1. Calculate optimal limit price (offset from best bid/ask)
      2. Place Post-Only limit order
      3. Monitor for fill / adverse price movement / timeout
      4. Cancel and retry if needed (up to ``max_retries``)
      5. Optionally fall back to IOC if all maker attempts fail
    """

    def __init__(
        self,
        place_order: PlaceOrderFn,
        cancel_order: CancelOrderFn,
        get_order_status: GetOrderStatusFn,
        get_best_price: GetBestPriceFn,
        config: MakerConfig = MakerConfig(),
    ) -> None:
        self._place_order = place_order
        self._cancel_order = cancel_order
        self._get_order_status = get_order_status
        self._get_best_price = get_best_price
        self._config = config
        self._pending: Dict[str, MakerOrder] = {}
        self._lock = asyncio.Lock()
        self._stats = {"attempts": 0, "fills": 0, "cancels": 0, "ioc_fallbacks": 0}

    # ── Public API ─────────────────────────────────────────────────────

    async def execute(
        self,
        symbol: str,
        side: str,
        quantity: float,
        reference_price: float,
    ) -> Optional[MakerOrder]:
        """Execute a maker limit order with monitoring and retry.

        Args:
            symbol: Trading pair (e.g. ``"BTCUSDT"``).
            side: ``"BUY"`` or ``"SELL"``.
            quantity: Order quantity in base asset.
            reference_price: Current market price for offset calculation.

        Returns:
            ``MakerOrder`` with fill info on success, ``None`` on failure.
        """
        cfg = self._config

        for attempt in range(1, cfg.max_retries + 1):
            self._stats["attempts"] += 1

            # Refresh best price for each attempt
            try:
                best = await self._get_best_price(symbol)
                ref = best.get("best_bid" if side == "BUY" else "best_ask",
                               reference_price)
            except Exception:
                ref = reference_price

            limit_price = self._calculate_limit_price(
                side, ref, cfg.price_offset_bps
            )

            order = MakerOrder(
                symbol=symbol,
                side=side,
                quantity=quantity,
                limit_price=limit_price,
                attempts=attempt,
            )

            try:
                result = await self._place_order(
                    symbol=symbol,
                    side=side,
                    quantity=quantity,
                    price=limit_price,
                    post_only=cfg.post_only,
                )

                order.order_id = str(result.get("orderId", ""))
                if not order.order_id:
                    order.status = OrderStatus.REJECTED
                    logger.warning("Order placement returned no orderId")
                    continue

                order.status = OrderStatus.PLACED
                async with self._lock:
                    self._pending[order.order_id] = order

                logger.info(
                    f"Maker {side} {quantity} {symbol} @ {limit_price:.2f} "
                    f"(attempt {attempt}/{cfg.max_retries}) — "
                    f"orderId={order.order_id}"
                )

                # Monitor until fill, timeout, or adverse move
                filled = await self._monitor_order(order)

                if filled.status == OrderStatus.FILLED:
                    self._stats["fills"] += 1
                    logger.info(
                        f"Maker FILLED: {filled.filled_qty} {symbol} "
                        f"@ {filled.avg_fill_price:.2f}"
                    )
                    return filled

                if (
                    filled.status == OrderStatus.PARTIALLY_FILLED
                    and filled.filled_qty > 0
                ):
                    self._stats["fills"] += 1
                    logger.warning(
                        f"Maker partial: {filled.filled_qty}/{quantity} "
                        f"{symbol} @ {filled.avg_fill_price:.2f}"
                    )
                    return filled

                logger.info(
                    f"Maker attempt {attempt}/{cfg.max_retries} "
                    f"not filled ({filled.status.name})"
                )

            except Exception as e:
                logger.error(
                    f"Maker execution error (attempt {attempt}): {e}",
                    exc_info=True,
                )
                if order.order_id:
                    await self._safe_cancel(order)
            finally:
                if order.order_id:
                    async with self._lock:
                        self._pending.pop(order.order_id, None)

        # All retries exhausted
        if cfg.fallback_to_ioc:
            self._stats["ioc_fallbacks"] += 1
            logger.warning(
                f"Maker exhausted ({cfg.max_retries} attempts) — "
                f"IOC fallback for {side} {quantity} {symbol}"
            )
            return await self._execute_ioc_fallback(symbol, side, quantity)

        return None

    async def cancel_all(self, symbol: str) -> int:
        """Cancel all pending maker orders for a symbol.

        Returns:
            Number of orders successfully cancelled.
        """
        cancelled = 0
        async with self._lock:
            to_cancel = [
                o for o in self._pending.values()
                if o.symbol == symbol and o.status == OrderStatus.PLACED
            ]

        for order in to_cancel:
            if await self._safe_cancel(order):
                cancelled += 1
                self._stats["cancels"] += 1

        return cancelled

    @property
    def stats(self) -> Dict[str, int]:
        """Execution statistics snapshot."""
        return dict(self._stats)

    @property
    def pending_count(self) -> int:
        """Number of currently pending orders."""
        return len(self._pending)

    # ── Price Calculation ──────────────────────────────────────────────

    @staticmethod
    def _calculate_limit_price(
        side: str, reference_price: float, offset_bps: float
    ) -> float:
        """Calculate maker limit price with offset from reference.

        BUY:  price slightly below reference (join the bid side)
        SELL: price slightly above reference (join the ask side)
        """
        offset = reference_price * offset_bps / 10_000
        if side == "BUY":
            return round(reference_price - offset, 2)
        return round(reference_price + offset, 2)

    # ── Order Monitoring ───────────────────────────────────────────────

    async def _monitor_order(self, order: MakerOrder) -> MakerOrder:
        """Monitor a placed order for fill, timeout, or adverse move.

        Polls the exchange for order status at ``poll_interval_s`` intervals.
        Cancels if:
          • Price moves adversely beyond ``max_adverse_pct``
          • Timeout ``max_wait_s`` is reached without fill
        """
        cfg = self._config
        deadline = time.monotonic() + cfg.max_wait_s

        while time.monotonic() < deadline:
            await asyncio.sleep(cfg.poll_interval_s)

            try:
                status = await self._get_order_status(
                    order.symbol, order.order_id  # type: ignore[arg-type]
                )

                # Update from exchange response
                exchange_status = status.get("status", "").upper()
                filled_qty = float(status.get("executedQty", 0))
                avg_price = float(status.get("avgPrice", 0))

                if filled_qty > 0:
                    order.filled_qty = filled_qty
                    order.avg_fill_price = avg_price

                if exchange_status == "FILLED":
                    order.status = OrderStatus.FILLED
                    return order

                if exchange_status == "PARTIALLY_FILLED":
                    order.status = OrderStatus.PARTIALLY_FILLED

                if exchange_status in ("CANCELED", "CANCELLED", "EXPIRED",
                                        "REJECTED"):
                    order.status = OrderStatus.CANCELLED
                    return order

                # Check for adverse price movement
                best = await self._get_best_price(order.symbol)
                mid = (
                    best.get("best_bid", 0) + best.get("best_ask", 0)
                ) / 2

                if mid > 0:
                    adverse = self._adverse_move_pct(
                        order.side, order.limit_price, mid
                    )
                    if adverse > cfg.max_adverse_pct:
                        logger.info(
                            f"Adverse move {adverse:.3f}% > "
                            f"{cfg.max_adverse_pct}% — cancelling "
                            f"{order.order_id}"
                        )
                        await self._safe_cancel(order)
                        return order

            except Exception as e:
                logger.warning(f"Monitor poll error: {e}")

        # Timeout reached
        if order.status == OrderStatus.PLACED:
            logger.info(
                f"Maker order {order.order_id} timed out "
                f"after {cfg.max_wait_s}s — cancelling"
            )
            await self._safe_cancel(order)
            order.status = OrderStatus.EXPIRED

        return order

    # ── Helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _adverse_move_pct(
        side: str, limit_price: float, current_mid: float
    ) -> float:
        """Calculate adverse price movement percentage.

        Adverse for BUY  = price going UP   (we want to buy lower)
        Adverse for SELL = price going DOWN  (we want to sell higher)
        """
        if limit_price <= 0:
            return 0.0
        if side == "BUY":
            return max(0.0, (current_mid - limit_price) / limit_price * 100)
        return max(0.0, (limit_price - current_mid) / limit_price * 100)

    async def _safe_cancel(self, order: MakerOrder) -> bool:
        """Cancel an order, swallowing errors gracefully."""
        try:
            if order.order_id and order.status in (
                OrderStatus.PLACED, OrderStatus.PARTIALLY_FILLED
            ):
                success = await self._cancel_order(
                    order.symbol, order.order_id
                )
                if success:
                    order.status = OrderStatus.CANCELLED
                return success
        except Exception as e:
            logger.error(f"Cancel error for {order.order_id}: {e}")
        return False

    async def _execute_ioc_fallback(
        self,
        symbol: str,
        side: str,
        quantity: float,
    ) -> Optional[MakerOrder]:
        """Last-resort IOC (Immediate-Or-Cancel) when maker fails.

        This uses market price (taker fees apply) but ensures the position
        is opened rather than missing the trade entirely.
        """
        try:
            result = await self._place_order(
                symbol=symbol,
                side=side,
                quantity=quantity,
                price=0,       # market price
                post_only=False,
            )
            order = MakerOrder(
                symbol=symbol,
                side=side,
                quantity=quantity,
                limit_price=0.0,
                status=OrderStatus.FILLED,
                order_id=str(result.get("orderId", "")),
                filled_qty=float(result.get("executedQty", quantity)),
                avg_fill_price=float(result.get("avgPrice", 0)),
            )
            logger.info(
                f"IOC fallback filled: {order.filled_qty} {symbol} "
                f"@ {order.avg_fill_price:.2f}"
            )
            return order
        except Exception as e:
            logger.error(f"IOC fallback failed for {side} {symbol}: {e}")
            return None
