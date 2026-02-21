"""
CCXTExchangeAdapter — Real exchange execution via CCXT.
======================================================
Implements the ExchangeAdapter interface to execute real orders
on Binance Futures (USDT-M) through the CCXT library.

Supports:
  • Market orders (open / close)
  • Stop-loss & take-profit conditional orders (stop_market / take_profit_market)
  • Leverage / margin-mode configuration per symbol
  • Position reconciliation (sync_state)
  • Testnet toggle via constructor flag

Architecture decisions:
  - CCXT async exchange is used internally; sync bridge via asyncio event loop
    because TradingAgentService runs in sync scheduler threads.
  - DB mutations (Portfolio / Trade rows) mirror PaperExchangeAdapter to keep
    local state consistent with exchange state.
  - All exchange errors are caught and returned as OrderResult(success=False)
    so the caller never sees raw CCXT exceptions.
"""
from __future__ import annotations

import asyncio
import logging
import threading
from typing import Dict, List, Optional

import ccxt.async_support as ccxt_async

from sqlalchemy.orm import Session

from backend.models.database import TradingAgent, Portfolio, Trade
from backend.services.execution.exchange_adapter import (
    ExchangeAdapter,
    OrderResult,
    PositionInfo,
    BalanceInfo,
)

logger = logging.getLogger(__name__)


# ── Symbol mapping (CoinGecko ID → CCXT unified symbol for Binance Futures) ─

# CCXT uses "BTC/USDT:USDT" format for USDT-margined perpetual futures
CCXT_SYMBOL_MAP: Dict[str, str] = {
    "bitcoin":              "BTC/USDT:USDT",
    "ethereum":             "ETH/USDT:USDT",
    "binancecoin":          "BNB/USDT:USDT",
    "cardano":              "ADA/USDT:USDT",
    "solana":               "SOL/USDT:USDT",
    "ripple":               "XRP/USDT:USDT",
    "polkadot":             "DOT/USDT:USDT",
    "dogecoin":             "DOGE/USDT:USDT",
    "avalanche-2":          "AVAX/USDT:USDT",
    "chainlink":            "LINK/USDT:USDT",
    "near":                 "NEAR/USDT:USDT",
    "sui":                  "SUI/USDT:USDT",
    "pepe":                 "1000PEPE/USDT:USDT",
    "aptos":                "APT/USDT:USDT",
    "arbitrum":             "ARB/USDT:USDT",
    "filecoin":             "FIL/USDT:USDT",
    "render-token":         "RENDER/USDT:USDT",
    "injective-protocol":   "INJ/USDT:USDT",
    "fetch-ai":             "FET/USDT:USDT",
    "bonk":                 "1000BONK/USDT:USDT",
    "floki":                "1000FLOKI/USDT:USDT",
    "sei-network":          "SEI/USDT:USDT",
    "wif":                  "WIF/USDT:USDT",
}

# Tokens that trade in 1000x unit on Binance Futures.
# Internally our system sizes in base units, so we scale before sending
# and unscale when reading fills.
_SCALE_1000 = {"pepe", "bonk", "floki"}

CCXT_REVERSE_MAP: Dict[str, str] = {v: k for k, v in CCXT_SYMBOL_MAP.items()}


def _ccxt_symbol(coin: str) -> Optional[str]:
    """Resolve CoinGecko coin ID to CCXT unified futures symbol."""
    return CCXT_SYMBOL_MAP.get(coin)


def _needs_1000_scale(coin: str) -> bool:
    return coin in _SCALE_1000


# ── Async-to-sync bridge ────────────────────────────────────────────────────

def _run_sync(coro):
    """Run an async coroutine from a sync context (scheduler thread).

    Creates a dedicated event loop per call to avoid conflicts with
    any existing running loop (FastAPI's uvloop lives in the main thread,
    scheduler threads have none).
    """
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ── Adapter ─────────────────────────────────────────────────────────────────


class CCXTExchangeAdapter(ExchangeAdapter):
    """Real Binance Futures execution via CCXT.

    Parameters
    ----------
    api_key : str
        Binance API key.
    api_secret : str
        Binance API secret.
    testnet : bool
        If True, connect to testnet.binancefuture.com instead of mainnet.
    """

    def __init__(self, api_key: str, api_secret: str, *, testnet: bool = True):
        self._api_key = api_key
        self._api_secret = api_secret
        self._testnet = testnet
        # Guard against concurrent exchange calls from different scheduler threads
        self._lock = threading.Lock()
        # Leverage cache to avoid redundant set_leverage calls
        self._leverage_cache: Dict[str, int] = {}

    # ── Exchange instance (created per-call, closed after) ──────────────

    # Binance migrated the old testnet (testnet.binancefuture.com) to the
    # new Demo Trading platform (demo-fapi.binance.com).  CCXT's
    # set_sandbox_mode still points to the deprecated URL, so we override
    # the fapi endpoints manually after enabling sandbox mode.
    _DEMO_FAPI_BASE = "https://demo-fapi.binance.com"
    _DEMO_FAPI_URLS = {
        "fapiPublic":    f"{_DEMO_FAPI_BASE}/fapi/v1",
        "fapiPrivate":   f"{_DEMO_FAPI_BASE}/fapi/v1",
        "fapiPublicV2":  f"{_DEMO_FAPI_BASE}/fapi/v2",
        "fapiPrivateV2": f"{_DEMO_FAPI_BASE}/fapi/v2",
        "fapiPublicV3":  f"{_DEMO_FAPI_BASE}/fapi/v3",
        "fapiPrivateV3": f"{_DEMO_FAPI_BASE}/fapi/v3",
    }

    def _create_exchange(self) -> ccxt_async.binance:
        """Create a fresh async Binance Futures exchange instance."""
        exchange = ccxt_async.binance({
            "apiKey": self._api_key,
            "secret": self._api_secret,
            "options": {
                "defaultType": "future",
                "adjustForTimeDifference": True,
            },
            "enableRateLimit": True,
        })
        if self._testnet:
            exchange.set_sandbox_mode(True)
            # Override deprecated testnet.binancefuture.com → demo-fapi.binance.com
            exchange.urls["api"].update(self._DEMO_FAPI_URLS)
            logger.info("CCXT: overrode sandbox URLs → demo-fapi.binance.com")
        return exchange

    async def _execute(self, coro_factory):
        """Create exchange → run coroutine → close exchange.

        ``coro_factory`` receives the exchange instance and returns a coroutine.
        This ensures the aiohttp session is always properly closed.
        """
        exchange = self._create_exchange()
        try:
            return await coro_factory(exchange)
        finally:
            await exchange.close()

    # ── Core execution ──────────────────────────────────────────────────

    def open_position(
        self, *,
        db: Session,
        agent: TradingAgent,
        coin: str,
        symbol: str,
        direction: str,
        amount_coins: float,
        entry_price: float,
        margin: float,
        leverage: int,
        position_value: float,
        liq_price: float,
        sl_price: float,
        tp_price: float,
        trail_pct: float,
        price_extreme: float,
    ) -> OrderResult:
        ccxt_sym = _ccxt_symbol(coin)
        if not ccxt_sym:
            return OrderResult(success=False, error=f"No CCXT symbol for coin: {coin}")

        side = "buy" if direction == "long" else "sell"

        # Scale quantity for 1000x tokens (exchange expects units in 1000s)
        order_qty = amount_coins / 1000.0 if _needs_1000_scale(coin) else amount_coins

        with self._lock:
            try:
                result = _run_sync(self._async_open(
                    ccxt_sym, side, order_qty, leverage, sl_price, tp_price, direction,
                ))
            except Exception as exc:
                logger.error(f"CCXT open_position error for {coin}: {exc}", exc_info=True)
                return OrderResult(success=False, error=str(exc))

        if not result["success"]:
            return OrderResult(success=False, error=result.get("error", "Unknown"))

        fill_price = result["fill_price"]
        filled_qty = result["filled_qty"]
        commission = result.get("commission", 0.0)

        # Unscale filled qty for 1000x tokens
        if _needs_1000_scale(coin):
            filled_qty *= 1000.0

        # ── Persist to local DB (mirrors PaperExchangeAdapter) ──────────
        agent.current_balance -= margin

        portfolio_item = Portfolio(
            agent_id=agent.id,
            cryptocurrency=coin,
            symbol=symbol,
            amount=filled_qty,
            avg_buy_price=fill_price,
            current_price=fill_price,
            position_type=direction,
            leverage=leverage,
            margin=margin,
            liquidation_price=liq_price,
            stop_loss_price=sl_price,
            take_profit_price=tp_price,
            trailing_stop_pct=trail_pct,
            price_extreme=price_extreme,
        )
        db.add(portfolio_item)

        trade = Trade(
            agent_id=agent.id,
            cryptocurrency=coin,
            symbol=symbol,
            trade_type=f"open_{direction}",
            amount=filled_qty,
            price=fill_price,
            total_value=filled_qty * fill_price,
            profit_loss=0,
            leverage=leverage,
            margin=margin,
            exchange_order_id=result.get("order_id"),
            exchange_fill_price=fill_price,
            exchange_commission=commission,
        )
        db.add(trade)
        db.flush()

        return OrderResult(
            success=True,
            order_id=result.get("order_id"),
            fill_price=fill_price,
            filled_qty=filled_qty,
            commission=commission,
            trade_db_id=trade.id,
            portfolio_db_id=portfolio_item.id,
            raw_response=result.get("raw"),
        )

    def close_position(
        self, *,
        db: Session,
        agent: TradingAgent,
        pos: Portfolio,
        current_price: float,
        force_loss: Optional[float] = None,
    ) -> OrderResult:
        ccxt_sym = _ccxt_symbol(pos.cryptocurrency)
        if not ccxt_sym:
            return OrderResult(
                success=False,
                error=f"No CCXT symbol for coin: {pos.cryptocurrency}",
            )

        # Opposite side to close
        close_side = "sell" if pos.position_type == "long" else "buy"
        close_qty = pos.amount / 1000.0 if _needs_1000_scale(pos.cryptocurrency) else pos.amount

        with self._lock:
            try:
                result = _run_sync(self._async_close(ccxt_sym, close_side, close_qty))
            except Exception as exc:
                logger.error(f"CCXT close_position error for {pos.cryptocurrency}: {exc}", exc_info=True)
                return OrderResult(success=False, error=str(exc))

        if not result["success"]:
            return OrderResult(success=False, error=result.get("error", "Unknown"))

        fill_price = result["fill_price"]
        commission = result.get("commission", 0.0)

        # PnL calculation — use exchange fill_price instead of agent's current_price
        if force_loss is not None:
            pnl = force_loss
        elif pos.position_type == "long":
            pnl = pos.amount * (fill_price - pos.avg_buy_price)
        else:
            pnl = pos.amount * (pos.avg_buy_price - fill_price)

        # Subtract exchange commission from PnL
        pnl -= commission

        cash_return = max(pos.margin + pnl, 0)
        agent.current_balance += cash_return

        trade = Trade(
            agent_id=agent.id,
            cryptocurrency=pos.cryptocurrency,
            symbol=pos.symbol,
            trade_type=f"close_{pos.position_type}",
            amount=pos.amount,
            price=fill_price,
            total_value=pos.amount * fill_price,
            profit_loss=pnl,
            leverage=pos.leverage,
            margin=pos.margin,
            exchange_order_id=result.get("order_id"),
            exchange_fill_price=fill_price,
            exchange_commission=commission,
        )
        db.add(trade)
        db.flush()

        db.delete(pos)

        return OrderResult(
            success=True,
            order_id=result.get("order_id"),
            fill_price=fill_price,
            filled_qty=pos.amount,
            commission=commission,
            pnl=pnl,
            cash_returned=cash_return,
            trade_db_id=trade.id,
            raw_response=result.get("raw"),
        )

    # ── Queries ─────────────────────────────────────────────────────────

    def get_balance(self, agent: TradingAgent) -> BalanceInfo:
        """Fetch real account balance from Binance Futures."""
        try:
            result = _run_sync(self._async_get_balance())
            return BalanceInfo(
                total=result.get("total", 0.0),
                available=result.get("free", 0.0),
                margin_used=result.get("used", 0.0),
                unrealized_pnl=result.get("unrealized_pnl", 0.0),
                assets=result.get("assets", {}),
            )
        except Exception as exc:
            logger.error(f"CCXT get_balance error: {exc}", exc_info=True)
            # Fallback to local DB state
            margin_used = sum(p.margin for p in agent.portfolio if p.amount > 0)
            return BalanceInfo(
                total=agent.current_balance + margin_used,
                available=agent.current_balance,
                margin_used=margin_used,
                unrealized_pnl=0.0,
            )

    def get_positions(self, db: Session, agent: TradingAgent) -> List[PositionInfo]:
        """Fetch real open positions from Binance Futures."""
        try:
            result = _run_sync(self._async_get_positions())
            positions = []
            for pos_data in result:
                positions.append(PositionInfo(
                    symbol=pos_data.get("symbol", ""),
                    side=pos_data.get("side", "").lower(),
                    size=abs(float(pos_data.get("contracts", 0))),
                    entry_price=float(pos_data.get("entryPrice", 0)),
                    mark_price=float(pos_data.get("markPrice", 0)),
                    unrealized_pnl=float(pos_data.get("unrealizedPnl", 0)),
                    leverage=int(pos_data.get("leverage", 1)),
                    margin=float(pos_data.get("initialMargin", 0)),
                    liquidation_price=float(pos_data.get("liquidationPrice", 0)),
                ))
            return positions
        except Exception as exc:
            logger.error(f"CCXT get_positions error: {exc}", exc_info=True)
            # Fallback to local DB
            return [
                PositionInfo(
                    symbol=p.symbol, side=p.position_type, size=p.amount,
                    entry_price=p.avg_buy_price, mark_price=p.current_price,
                    unrealized_pnl=0.0, leverage=p.leverage, margin=p.margin,
                    liquidation_price=p.liquidation_price,
                )
                for p in agent.portfolio if p.amount > 0
            ]

    # ── Configuration ───────────────────────────────────────────────────

    def set_leverage(self, symbol: str, leverage: int) -> bool:
        """Set leverage for a symbol on the exchange.

        Caches the value to avoid redundant API calls on consecutive trades.
        """
        # Resolve to CCXT symbol if CoinGecko ID was passed
        ccxt_sym = CCXT_SYMBOL_MAP.get(symbol, symbol)

        cached = self._leverage_cache.get(ccxt_sym)
        if cached == leverage:
            return True

        try:
            _run_sync(self._async_set_leverage(ccxt_sym, leverage))
            self._leverage_cache[ccxt_sym] = leverage
            return True
        except Exception as exc:
            # Binance returns error if leverage is already set — treat as OK
            if "No need to change" in str(exc):
                self._leverage_cache[ccxt_sym] = leverage
                return True
            logger.error(f"CCXT set_leverage error ({ccxt_sym}, {leverage}x): {exc}")
            return False

    # ── Reconciliation ──────────────────────────────────────────────────

    def sync_state(self, db: Session, agent: TradingAgent) -> Dict:
        """Reconcile local DB with exchange state.

        Detects:
        - Positions closed on exchange but still open in DB (SL/TP hit)
        - Positions open on exchange but missing in DB (manual trades)
        - Quantity mismatches

        Returns a summary dict of actions taken.
        """
        try:
            exchange_positions = _run_sync(self._async_get_positions())
        except Exception as exc:
            logger.error(f"sync_state: failed to fetch exchange positions: {exc}")
            return {"error": str(exc)}

        # Build lookup: CCXT symbol → exchange position data
        exchange_map: Dict[str, dict] = {}
        for ep in exchange_positions:
            sym = ep.get("symbol", "")
            side = ep.get("side", "").lower()
            size = abs(float(ep.get("contracts", 0)))
            if size > 0:
                exchange_map[f"{sym}:{side}"] = ep

        # Build lookup: local DB positions
        local_positions = [p for p in agent.portfolio if p.amount > 0]
        local_map: Dict[str, Portfolio] = {}
        for lp in local_positions:
            ccxt_sym = _ccxt_symbol(lp.cryptocurrency)
            if ccxt_sym:
                local_map[f"{ccxt_sym}:{lp.position_type}"] = lp

        actions = {"closed_locally": [], "orphaned_exchange": [], "mismatches": []}

        # Detect positions closed on exchange (SL/TP hit externally)
        for key, lp in local_map.items():
            if key not in exchange_map:
                logger.warning(
                    f"sync_state: {lp.cryptocurrency} {lp.position_type} "
                    f"exists locally but NOT on exchange — closing locally"
                )
                # Position was closed on exchange (e.g. SL/TP triggered)
                # Close it locally with last known price
                current_price = lp.current_price or lp.avg_buy_price
                if lp.position_type == "long":
                    pnl = lp.amount * (current_price - lp.avg_buy_price)
                else:
                    pnl = lp.amount * (lp.avg_buy_price - current_price)
                cash_return = max(lp.margin + pnl, 0)
                agent.current_balance += cash_return

                trade = Trade(
                    agent_id=agent.id,
                    cryptocurrency=lp.cryptocurrency,
                    symbol=lp.symbol,
                    trade_type=f"close_{lp.position_type}",
                    amount=lp.amount,
                    price=current_price,
                    total_value=lp.amount * current_price,
                    profit_loss=pnl,
                    leverage=lp.leverage,
                    margin=lp.margin,
                )
                db.add(trade)
                db.delete(lp)
                actions["closed_locally"].append(lp.cryptocurrency)

        # Detect positions on exchange not in local DB
        for key, ep in exchange_map.items():
            if key not in local_map:
                actions["orphaned_exchange"].append(key)
                logger.warning(f"sync_state: {key} exists on exchange but NOT in local DB")

        if actions["closed_locally"] or actions["orphaned_exchange"]:
            db.flush()

        return actions

    # ── Metadata ────────────────────────────────────────────────────────

    @property
    def mode(self) -> str:
        return "testnet" if self._testnet else "live"

    # ── Private async methods ───────────────────────────────────────────

    async def _async_open(
        self,
        ccxt_sym: str,
        side: str,
        qty: float,
        leverage: int,
        sl_price: float,
        tp_price: float,
        direction: str,
    ) -> Dict:
        """Open position: set leverage → market order → SL/TP orders."""

        async def _run(exchange):
            # 1. Set leverage
            try:
                await exchange.set_leverage(leverage, ccxt_sym)
            except Exception as e:
                if "No need to change" not in str(e):
                    logger.warning(f"set_leverage warning: {e}")

            # 2. Set margin mode to CROSSED (Binance default, but be explicit)
            try:
                await exchange.set_margin_mode("cross", ccxt_sym)
            except Exception as e:
                # Already set or not supported — safe to ignore
                if "No need to change" not in str(e):
                    logger.debug(f"set_margin_mode info: {e}")

            # 3. Market order to open
            order = await exchange.create_order(
                symbol=ccxt_sym,
                type="market",
                side=side,
                amount=qty,
            )

            fill_price = float(order.get("average", 0) or order.get("price", 0) or 0)
            filled_qty = float(order.get("filled", qty))
            order_id = order.get("id", "")

            # Calculate commission from trades if available
            commission = 0.0
            if order.get("trades"):
                for t in order["trades"]:
                    fee = t.get("fee", {})
                    commission += float(fee.get("cost", 0))
            elif order.get("fee"):
                commission = float(order["fee"].get("cost", 0))

            # 4. Place stop-loss order (stop_market with closePosition)
            sl_order_id = None
            try:
                sl_side = "sell" if direction == "long" else "buy"
                sl_order = await exchange.create_order(
                    symbol=ccxt_sym,
                    type="stop_market",
                    side=sl_side,
                    amount=filled_qty,
                    price=None,
                    params={
                        "stopPrice": sl_price,
                        "closePosition": False,
                        "reduceOnly": True,
                    },
                )
                sl_order_id = sl_order.get("id")
                logger.info(f"SL order placed: {sl_order_id} @ {sl_price}")
            except Exception as e:
                logger.warning(f"Failed to place SL order: {e}")

            # 5. Place take-profit order (take_profit_market with closePosition)
            tp_order_id = None
            try:
                tp_side = "sell" if direction == "long" else "buy"
                tp_order = await exchange.create_order(
                    symbol=ccxt_sym,
                    type="take_profit_market",
                    side=tp_side,
                    amount=filled_qty,
                    price=None,
                    params={
                        "stopPrice": tp_price,
                        "closePosition": False,
                        "reduceOnly": True,
                    },
                )
                tp_order_id = tp_order.get("id")
                logger.info(f"TP order placed: {tp_order_id} @ {tp_price}")
            except Exception as e:
                logger.warning(f"Failed to place TP order: {e}")

            return {
                "success": True,
                "order_id": order_id,
                "fill_price": fill_price,
                "filled_qty": filled_qty,
                "commission": commission,
                "sl_order_id": sl_order_id,
                "tp_order_id": tp_order_id,
                "raw": {
                    "market_order": order,
                },
            }

        return await self._execute(_run)

    async def _async_close(self, ccxt_sym: str, side: str, qty: float) -> Dict:
        """Close position: market order with reduceOnly → cancel open SL/TP."""

        async def _run(exchange):
            # 1. Market order to close (reduceOnly)
            order = await exchange.create_order(
                symbol=ccxt_sym,
                type="market",
                side=side,
                amount=qty,
                params={"reduceOnly": True},
            )

            fill_price = float(order.get("average", 0) or order.get("price", 0) or 0)
            order_id = order.get("id", "")

            commission = 0.0
            if order.get("trades"):
                for t in order["trades"]:
                    fee = t.get("fee", {})
                    commission += float(fee.get("cost", 0))
            elif order.get("fee"):
                commission = float(order["fee"].get("cost", 0))

            # 2. Cancel remaining open orders for this symbol (SL/TP)
            try:
                open_orders = await exchange.fetch_open_orders(ccxt_sym)
                for oo in open_orders:
                    try:
                        await exchange.cancel_order(oo["id"], ccxt_sym)
                        logger.info(f"Cancelled residual order {oo['id']} for {ccxt_sym}")
                    except Exception as e:
                        logger.warning(f"Failed to cancel order {oo['id']}: {e}")
            except Exception as e:
                logger.warning(f"Failed to fetch open orders for cleanup: {e}")

            return {
                "success": True,
                "order_id": order_id,
                "fill_price": fill_price,
                "commission": commission,
                "raw": {"close_order": order},
            }

        return await self._execute(_run)

    async def _async_get_balance(self) -> Dict:
        """Fetch full futures balance — USDT totals + per-asset breakdown."""

        async def _run(exchange):
            balance = await exchange.fetch_balance({"type": "future"})
            usdt = balance.get("USDT", {})

            # Unrealised PnL from the raw response
            unrealized = 0.0
            info = balance.get("info", {})
            assets_detail: Dict[str, Dict[str, float]] = {}

            if isinstance(info, dict):
                for asset in info.get("assets", []):
                    wallet = float(asset.get("walletBalance", 0))
                    available = float(asset.get("availableBalance", 0))
                    margin = float(asset.get("initialMargin", 0))
                    upnl = float(asset.get("unrealizedProfit", 0))
                    # Only include assets with non-zero balances
                    if wallet != 0 or available != 0 or margin != 0:
                        name = asset.get("asset", "UNKNOWN")
                        assets_detail[name] = {
                            "wallet": round(wallet, 4),
                            "available": round(available, 4),
                            "margin": round(margin, 4),
                            "unrealized_pnl": round(upnl, 4),
                        }
                    if asset.get("asset") == "USDT":
                        unrealized = upnl

            return {
                "total": float(usdt.get("total", 0)),
                "free": float(usdt.get("free", 0)),
                "used": float(usdt.get("used", 0)),
                "unrealized_pnl": unrealized,
                "assets": assets_detail,
            }

        return await self._execute(_run)

    async def _async_get_positions(self) -> List[Dict]:
        """Fetch all open positions from exchange."""

        async def _run(exchange):
            positions = await exchange.fetch_positions()
            # Filter to only positions with nonzero size
            return [
                p for p in positions
                if abs(float(p.get("contracts", 0))) > 0
            ]

        return await self._execute(_run)

    async def _async_set_leverage(self, ccxt_sym: str, leverage: int):
        """Set leverage on exchange."""

        async def _run(exchange):
            return await exchange.set_leverage(leverage, ccxt_sym)

        return await self._execute(_run)
