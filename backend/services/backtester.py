"""
Backtesting Engine
==================
Replays historical kline data through the StrategyEngine to simulate
how a strategy would have performed in the past.

Uses Binance Futures klines (same data source as live trading).
Simulates the full futures lifecycle: position sizing, SL/TP, liquidation.
"""
import logging
import math
import time
import requests
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime

from backend.services.strategies import (
    StrategyEngine, Indicators, STRATEGIES,
    calculate_position_size, calculate_liquidation_price, Signal,
)
from backend.services.strategies.indicators import SCALP_PROFILES

logger = logging.getLogger(__name__)

FUTURES_URL = "https://fapi.binance.com/fapi/v1"
SPOT_URL = "https://api.binance.com/api/v3"

SYMBOL_MAP = {
    "bitcoin": "BTCUSDT",
    "ethereum": "ETHUSDT",
    "binancecoin": "BNBUSDT",
    "cardano": "ADAUSDT",
    "solana": "SOLUSDT",
    "ripple": "XRPUSDT",
    "polkadot": "DOTUSDT",
    "dogecoin": "DOGEUSDT",
}

COIN_NAMES = {
    "bitcoin": "Bitcoin", "ethereum": "Ethereum", "binancecoin": "BNB",
    "cardano": "Cardano", "solana": "Solana", "ripple": "XRP",
    "polkadot": "Polkadot", "dogecoin": "Dogecoin",
}

# ── Commission / Fee Model (Binance Futures USDⓈ-M, VIP 0) ─────────────────
TAKER_FEE_PCT = 0.05     # 0.05% per side (market orders)
MAKER_FEE_PCT = 0.02     # 0.02% per side (limit orders)
FUNDING_RATE_PCT = 0.01  # 0.01% every 8 hours (typical)
FUNDING_INTERVAL_H = 8   # funding rate applied every N hours

# Interval → hours per candle (for funding rate calculation)
_INTERVAL_HOURS = {
    "1m": 1/60, "3m": 3/60, "5m": 5/60, "15m": 15/60, "30m": 0.5,
    "1h": 1, "2h": 2, "4h": 4, "6h": 6, "8h": 8, "12h": 12, "1d": 24,
}


# ── Data Classes ────────────────────────────────────────────────────────────

@dataclass
class BacktestTrade:
    """A single trade in the backtest."""
    trade_type: str            # open_long, close_long, open_short, close_short
    timestamp: str
    price: float
    amount: float              # coins
    margin: float
    leverage: int
    total_value: float
    profit_loss: float = 0.0
    commission: float = 0.0    # fee paid on this trade
    reason: str = ""


@dataclass
class BacktestResult:
    """Aggregate results of a backtest run."""
    strategy: str
    strategy_name: str
    coin: str
    coin_name: str
    period_days: int
    leverage: int
    initial_balance: float
    final_balance: float           # net (after fees)
    final_balance_gross: float     # gross (no fees)
    total_return_pct: float        # net
    total_return_gross_pct: float   # gross
    buy_hold_return_pct: float
    total_commissions: float       # total trading fees paid
    total_funding: float           # total funding rate paid
    total_fees: float              # commissions + funding
    max_drawdown_pct: float
    sharpe_ratio: float
    win_rate: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    avg_win: float
    avg_loss: float
    profit_factor: float
    max_consecutive_wins: int
    max_consecutive_losses: int
    trailing_stops_moved: int      # how many times SL was trailed
    trailing_sl_closes: int        # how many closes triggered by trailed SL
    equity_curve: List[Dict]   # [{time (epoch), equity, equity_gross, buy_hold}]
    trades: List[Dict]         # serialized BacktestTrade list
    candles_processed: int
    start_date: str
    end_date: str


# ── Kline Fetcher ───────────────────────────────────────────────────────────

def _fetch_klines(coin: str, interval: str, limit: int) -> List[Dict]:
    """Fetch klines from Binance Futures, paginating if needed.
    Binance allows max 1500 candles per request.
    """
    sym = SYMBOL_MAP.get(coin)
    if not sym:
        return []

    session = requests.Session()
    session.headers.update({"Accept": "application/json", "User-Agent": "MoneyMaker/1.0"})

    all_klines = []
    remaining = limit
    end_time = None     # start from most recent and go backwards

    while remaining > 0:
        batch = min(remaining, 1500)
        params = {"symbol": sym, "interval": interval, "limit": batch}
        if end_time:
            params["endTime"] = end_time

        try:
            resp = session.get(f"{FUTURES_URL}/klines", params=params, timeout=20)
            if resp.status_code != 200:
                # Fallback to spot
                resp = session.get(f"{SPOT_URL}/klines", params=params, timeout=20)
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"Backtest kline fetch failed: {e}")
            break

        data = resp.json()
        if not data:
            break

        klines = []
        for k in data:
            klines.append({
                "timestamp": datetime.fromtimestamp(k[0] / 1000).isoformat(),
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4]),
                "volume": float(k[5]),
            })

        all_klines = klines + all_klines   # prepend (oldest first)
        remaining -= len(data)

        if len(data) < batch:
            break  # no more data available

        # Set endTime to just before the first candle we got
        end_time = int(data[0][0]) - 1

        # Small delay to be polite
        time.sleep(0.15)

    logger.info(f"Backtest: fetched {len(all_klines)} klines ({interval}) for {coin}")
    return all_klines


# Map of scalper variants to their native candle interval + max backtest days
_SCALPER_INTERVALS = {
    "scalper_1m":  ("1m",  1440, 3),    # 1440 candles/day, max 3d
    "scalper_3m":  ("3m",  480,  14),   # 480 candles/day,  max 14d
    "scalper_5m":  ("5m",  288,  30),   # 288 candles/day,  max 30d
    "scalper_15m": ("15m", 96,   90),   # 96 candles/day,   max 90d
    "scalper":     ("1h",  24,   180),  # 24 candles/day,   max 180d
}


def _get_kline_config(period_days: int, strategy_key: str = "") -> tuple:
    """Choose interval and total candles needed for backtesting.
    Scalper variants use their native timeframe interval.
    Other strategies use 4h for medium periods, 1d for long.
    """
    # Check if this is a scalper variant with a specific interval
    scalper_cfg = _SCALPER_INTERVALS.get(strategy_key)
    if scalper_cfg:
        interval, candles_per_day, max_days = scalper_cfg
        capped_days = min(period_days, max_days)
        if capped_days < period_days:
            logger.warning(
                f"Backtest: {strategy_key} capped from {period_days}d to {capped_days}d "
                f"(max for {interval} candles)"
            )
        return interval, capped_days * candles_per_day

    style = STRATEGIES.get(strategy_key, None)
    is_fast = style and style.style in ("scalping",)

    if period_days <= 7:
        return "1h", period_days * 24
    elif is_fast and period_days <= 180:
        return "1h", period_days * 24
    elif period_days <= 90:
        return "4h", period_days * 6
    else:
        return "1d", period_days


# ── Position Tracker ────────────────────────────────────────────────────────

@dataclass
class _Position:
    """Internal position tracker for the backtest simulation."""
    direction: str       # "long" or "short"
    entry_price: float
    amount: float        # coins
    margin: float
    leverage: int
    stop_loss: float
    take_profit: float
    liquidation: float
    initial_sl: float = 0.0    # original SL for reference
    best_price: float = 0.0    # best price seen (for trailing stop)
    trail_pct: float = 0.0     # trailing distance in % (0 = disabled)
    opened_at: str = ""


# ── Backtester ──────────────────────────────────────────────────────────────

class Backtester:
    """Runs a strategy against historical data."""

    def __init__(self):
        self.engine = StrategyEngine()

    def run(
        self,
        strategy_key: str,
        coin: str,
        period_days: int = 90,
        leverage: int = 0,        # 0 = use strategy default
        initial_balance: float = 10000.0,
        trailing_enabled: bool = True,
    ) -> BacktestResult:
        """Execute a full backtest and return results."""

        cfg = STRATEGIES.get(strategy_key)
        if not cfg:
            raise ValueError(f"Unknown strategy: {strategy_key}")

        if leverage <= 0:
            leverage = cfg.default_leverage
        leverage = min(leverage, cfg.max_leverage)

        # --- Fetch historical klines ---
        interval, num_candles = _get_kline_config(period_days, strategy_key)
        # We need extra candles for indicator warm-up
        # EMA-55 needs ~55, ADX needs ~2*14+1=29, MACD needs ~35
        warmup = 100
        klines = _fetch_klines(coin, interval, num_candles + warmup)

        if len(klines) < warmup + 20:
            raise ValueError(f"Not enough data: got {len(klines)} candles, need {warmup + 20}+")

        # --- Simulation state ---
        balance = initial_balance        # net balance (with fees)
        balance_gross = initial_balance  # gross balance (no fees)
        position: Optional[_Position] = None
        trades: List[BacktestTrade] = []
        equity_curve: List[Dict] = []
        peak_equity = initial_balance
        max_drawdown = 0.0
        total_commissions = 0.0
        total_funding = 0.0
        trailing_stops_moved = 0
        trailing_sl_closes = 0

        # Funding rate tracking
        hours_per_candle = _INTERVAL_HOURS.get(interval, 1)
        candles_per_funding = FUNDING_INTERVAL_H / hours_per_candle if hours_per_candle > 0 else 999999
        candles_since_funding = 0.0

        # Buy & hold reference
        first_price = klines[warmup]["close"]
        last_price = klines[-1]["close"]

        # --- Main loop: iterate candle by candle ---
        # Use a sliding window for indicator computation (O(n) instead of O(n²))
        # 200 candles is enough for all indicators (longest: EMA-55 + ADX warm-up)
        indicator_window = 200

        for i in range(warmup, len(klines)):
            candle = klines[i]
            close = candle["close"]
            high = candle["high"]
            low = candle["low"]
            ts = candle["timestamp"]

            # Sliding window: only last N candles for indicator computation
            window_start = max(0, i + 1 - indicator_window)
            close_prices = [k["close"] for k in klines[window_start:i + 1]]
            ohlc_slice = klines[window_start:i + 1]

            # --- Trailing stop update + SL / TP / Liquidation ---
            if position:
                # Update trailing stops BEFORE exit checks
                trail_moved = self._update_trailing_stop(position, high, low)
                if trail_moved:
                    trailing_stops_moved += 1

                closed = self._check_position_exit(
                    position, high, low, close, ts,
                    balance, trades
                )
                if closed is not None:
                    cash_back, cash_back_gross, close_fee, is_trailing_sl = closed
                    balance += cash_back
                    balance_gross += cash_back_gross
                    total_commissions += close_fee
                    if is_trailing_sl:
                        trailing_sl_closes += 1
                    position = None

            # --- Funding rate (every 8h on open position value) ---
            if position:
                candles_since_funding += 1
                if candles_since_funding >= candles_per_funding:
                    candles_since_funding = 0.0
                    position_value = position.amount * close
                    funding_fee = position_value * (FUNDING_RATE_PCT / 100)
                    balance -= funding_fee
                    total_funding += funding_fee

            # --- Compute indicators ---
            try:
                profile = SCALP_PROFILES.get(strategy_key)
                indicators = Indicators.compute_all(close_prices, ohlc_slice, close, profile=profile)
            except Exception:
                continue

            # --- Evaluate strategy ---
            has_long = position is not None and position.direction == "long"
            has_short = position is not None and position.direction == "short"
            entry_price = position.entry_price if position else 0.0

            signal = self.engine.evaluate(
                strategy_key, indicators, close,
                has_long, has_short, entry_price
            )

            # --- Act on signal ---
            if position is None and signal.direction in ("long", "short"):
                if signal.confidence >= cfg.min_confidence:
                    result = self._open_position(
                        signal, close, leverage, strategy_key,
                        balance, ts, trades, trailing_enabled
                    )
                    if result:
                        position, open_fee = result
                        balance -= position.margin + open_fee
                        balance_gross -= position.margin
                        total_commissions += open_fee

            elif position and signal.direction in ("close_long", "close_short"):
                # Only honour signal-based close for non-scalper strategies
                # All scalper variants rely purely on mechanical SL/TP exits
                if strategy_key.startswith("scalper"):
                    pass  # ignore signal closes for scalper variants
                else:
                    curr_pnl = self._calc_pnl(position, close)
                    should_close = (
                        signal.confidence >= 0.55
                        or curr_pnl > 0
                    )
                    if should_close:
                        curr_pnl = self._calc_pnl(position, close)
                        close_value = position.amount * close
                        close_fee = close_value * (TAKER_FEE_PCT / 100)
                        net_pnl = curr_pnl - close_fee
                        cash_back = max(position.margin + net_pnl, 0)
                        cash_back_gross = max(position.margin + curr_pnl, 0)
                        balance += cash_back
                        balance_gross += cash_back_gross
                        total_commissions += close_fee
                        trades.append(BacktestTrade(
                            trade_type=f"close_{position.direction}",
                            timestamp=ts, price=close,
                            amount=position.amount, margin=position.margin,
                            leverage=position.leverage,
                            total_value=close_value,
                            profit_loss=net_pnl,
                            commission=close_fee,
                            reason=signal.reasoning,
                        ))
                        position = None

            # --- Record equity ---
            equity = balance
            equity_gross = balance_gross
            if position:
                pos_pnl = self._calc_pnl(position, close)
                equity += position.margin + pos_pnl
                equity_gross += position.margin + pos_pnl

            bh_equity = initial_balance * (close / first_price)
            equity_curve.append({
                "timestamp": ts,
                "equity": round(equity, 2),
                "equity_gross": round(equity_gross, 2),
                "buy_hold": round(bh_equity, 2),
            })

            if equity > peak_equity:
                peak_equity = equity
            dd = (peak_equity - equity) / peak_equity * 100 if peak_equity > 0 else 0
            if dd > max_drawdown:
                max_drawdown = dd

        # --- Force close any open position at end ---
        if position:
            pnl = self._calc_pnl(position, last_price)
            close_value = position.amount * last_price
            close_fee = close_value * (TAKER_FEE_PCT / 100)
            net_pnl = pnl - close_fee
            cash_back = max(position.margin + net_pnl, 0)
            cash_back_gross = max(position.margin + pnl, 0)
            balance += cash_back
            balance_gross += cash_back_gross
            total_commissions += close_fee
            trades.append(BacktestTrade(
                trade_type=f"close_{position.direction}",
                timestamp=klines[-1]["timestamp"], price=last_price,
                amount=position.amount, margin=position.margin,
                leverage=position.leverage,
                total_value=close_value,
                profit_loss=net_pnl,
                commission=close_fee,
                reason="Backtest end — force close",
            ))
            position = None

        # --- Compute metrics ---
        final_equity = balance
        final_equity_gross = balance_gross
        total_return = (final_equity - initial_balance) / initial_balance * 100
        total_return_gross = (final_equity_gross - initial_balance) / initial_balance * 100
        buy_hold_return = (last_price - first_price) / first_price * 100
        total_fees = total_commissions + total_funding

        close_trades = [t for t in trades if t.trade_type.startswith("close_")]
        wins = [t for t in close_trades if t.profit_loss > 0]
        losses = [t for t in close_trades if t.profit_loss <= 0]

        win_rate = len(wins) / len(close_trades) * 100 if close_trades else 0
        avg_win = sum(t.profit_loss for t in wins) / len(wins) if wins else 0
        avg_loss = sum(t.profit_loss for t in losses) / len(losses) if losses else 0
        total_win = sum(t.profit_loss for t in wins)
        total_loss = abs(sum(t.profit_loss for t in losses))
        profit_factor = total_win / total_loss if total_loss > 0 else (999.0 if total_win > 0 else 0.0)

        # Sharpe ratio (simple: daily/candle returns)
        sharpe = self._calc_sharpe(equity_curve)

        # Consecutive wins/losses
        max_consec_wins, max_consec_losses = self._calc_streaks(close_trades)

        # Downsample equity curve for frontend (max ~200 points)
        if len(equity_curve) > 200:
            step = len(equity_curve) // 200
            equity_curve_sampled = equity_curve[::step]
        else:
            equity_curve_sampled = equity_curve

        result = BacktestResult(
            strategy=strategy_key,
            strategy_name=cfg.name,
            coin=coin,
            coin_name=COIN_NAMES.get(coin, coin),
            period_days=period_days,
            leverage=leverage,
            initial_balance=initial_balance,
            final_balance=round(final_equity, 2),
            final_balance_gross=round(final_equity_gross, 2),
            total_return_pct=round(total_return, 2),
            total_return_gross_pct=round(total_return_gross, 2),
            buy_hold_return_pct=round(buy_hold_return, 2),
            total_commissions=round(total_commissions, 2),
            total_funding=round(total_funding, 2),
            total_fees=round(total_fees, 2),
            max_drawdown_pct=round(max_drawdown, 2),
            sharpe_ratio=round(sharpe, 3),
            win_rate=round(win_rate, 1),
            total_trades=len(close_trades),
            winning_trades=len(wins),
            losing_trades=len(losses),
            avg_win=round(avg_win, 2),
            avg_loss=round(avg_loss, 2),
            profit_factor=round(profit_factor, 2),
            max_consecutive_wins=max_consec_wins,
            max_consecutive_losses=max_consec_losses,
            trailing_stops_moved=trailing_stops_moved,
            trailing_sl_closes=trailing_sl_closes,
            equity_curve=[
                {
                    "time": int(datetime.fromisoformat(e["timestamp"]).timestamp()),
                    "equity": e["equity"],
                    "equity_gross": e.get("equity_gross"),
                    "buy_hold": e.get("buy_hold"),
                }
                for e in equity_curve_sampled
            ],
            trades=[{
                "trade_type": t.trade_type,
                "side": "LONG" if "long" in t.trade_type else "SHORT",
                "action": "OPEN" if t.trade_type.startswith("open") else "CLOSE",
                "timestamp": int(datetime.fromisoformat(t.timestamp).timestamp()),
                "price": t.price,
                "size": round(t.amount, 6),
                "margin": round(t.margin, 2),
                "leverage": t.leverage,
                "total_value": round(t.total_value, 2),
                "pnl": round(t.profit_loss, 2) if t.trade_type.startswith("close") else None,
                "commission": round(t.commission, 4),
                "reason": t.reason,
            } for t in trades],
            candles_processed=len(klines) - warmup,
            start_date=klines[warmup]["timestamp"],
            end_date=klines[-1]["timestamp"],
        )

        logger.info(
            f"Backtest {strategy_key} on {coin} ({period_days}d, {leverage}x): "
            f"gross {total_return_gross:+.2f}% / net {total_return:+.2f}% return, "
            f"{len(close_trades)} trades, fees ${total_fees:.2f} "
            f"(comm ${total_commissions:.2f} + fund ${total_funding:.2f}), "
            f"{win_rate:.0f}% win rate, {max_drawdown:.1f}% max DD, "
            f"trailing: {trailing_stops_moved} moves / {trailing_sl_closes} closes"
        )

        return result

    # ── Helpers ──────────────────────────────────────────────────────────

    def _open_position(
        self, signal: Signal, price: float, leverage: int,
        strategy_key: str, balance: float, ts: str,
        trades: List[BacktestTrade],
        trailing_enabled: bool = True,
    ) -> Optional[tuple]:
        """Open a simulated position. Returns (Position, fee) or None."""
        margin = calculate_position_size(
            balance, strategy_key, leverage,
            signal.stop_loss_pct, price
        )
        if margin <= 0 or margin > balance:
            return None

        position_value = margin * leverage
        amount = position_value / price
        direction = signal.direction

        # Commission on entry
        open_fee = position_value * (TAKER_FEE_PCT / 100)

        liq = calculate_liquidation_price(price, leverage, direction)
        if direction == "long":
            sl = price * (1 - signal.stop_loss_pct / 100)
            tp = price * (1 + signal.take_profit_pct / 100)
        else:
            sl = price * (1 + signal.stop_loss_pct / 100)
            tp = price * (1 - signal.take_profit_pct / 100)

        trades.append(BacktestTrade(
            trade_type=f"open_{direction}",
            timestamp=ts, price=price,
            amount=amount, margin=margin,
            leverage=leverage,
            total_value=position_value,
            commission=open_fee,
            reason=signal.reasoning,
        ))

        pos = _Position(
            direction=direction,
            entry_price=price,
            amount=amount,
            margin=margin,
            leverage=leverage,
            stop_loss=sl,
            take_profit=tp,
            liquidation=liq,
            initial_sl=sl,
            best_price=price,
            # trail_pct < 0 means strategy explicitly disabled trailing
            trail_pct=(
                0 if (not trailing_enabled
                      or (signal.trail_pct is not None and signal.trail_pct < 0))
                else (signal.trail_pct if signal.trail_pct and signal.trail_pct > 0
                      else signal.stop_loss_pct)
            ),
            opened_at=ts,
        )
        return pos, open_fee

    @staticmethod
    def _update_trailing_stop(pos: _Position, high: float, low: float) -> bool:
        """Update trailing stop based on candle high/low.
        Returns True if SL was moved. DRY: mirrors live _update_trailing_stops().

        Two-phase trailing (Ed Seykota / Turtle Traders):
          Phase 1 — Breakeven: at +1R from entry, move SL to entry price.
          Phase 2 — Chandelier: trail SL at trail_pct from best price.
        """
        if pos.trail_pct <= 0:
            return False

        # 1R = initial SL distance
        initial_sl_dist = abs(pos.entry_price - pos.initial_sl) if pos.initial_sl > 0 else pos.entry_price * pos.trail_pct / 100
        initial_sl_dist_pct = initial_sl_dist / pos.entry_price * 100 if pos.entry_price > 0 else pos.trail_pct

        moved = False
        if pos.direction == "long":
            if high > pos.best_price:
                pos.best_price = high

            # Phase 1: Breakeven at +1R
            breakeven_trigger = pos.entry_price + initial_sl_dist
            if pos.best_price >= breakeven_trigger and pos.stop_loss < pos.entry_price:
                pos.stop_loss = pos.entry_price
                moved = True

            # Phase 2: Chandelier trail from peak
            activation_price = pos.entry_price * (1 + pos.trail_pct / 100)
            if pos.best_price >= activation_price:
                new_sl = pos.best_price * (1 - pos.trail_pct / 100)
                if new_sl > pos.stop_loss:
                    pos.stop_loss = new_sl
                    moved = True
        else:  # short
            if pos.best_price == 0 or low < pos.best_price:
                pos.best_price = low

            # Phase 1: Breakeven at +1R
            breakeven_trigger = pos.entry_price - initial_sl_dist
            if pos.best_price <= breakeven_trigger and (pos.stop_loss <= 0 or pos.stop_loss > pos.entry_price):
                pos.stop_loss = pos.entry_price
                moved = True

            # Phase 2: Chandelier trail from low
            activation_price = pos.entry_price * (1 - pos.trail_pct / 100)
            if pos.best_price <= activation_price:
                new_sl = pos.best_price * (1 + pos.trail_pct / 100)
                if pos.stop_loss <= 0 or new_sl < pos.stop_loss:
                    pos.stop_loss = new_sl
                    moved = True
        return moved

    def _check_position_exit(
        self, pos: _Position, high: float, low: float,
        close: float, ts: str,
        balance: float, trades: List[BacktestTrade],
    ) -> Optional[tuple]:
        """Check if position should be closed by SL/TP/liquidation.
        Returns (net_cash_back, gross_cash_back, close_fee, is_trailing_sl) if closed, else None.
        """
        exit_price = None
        reason = ""
        is_trailing_sl = False

        # Detect if SL has been trailed from its original position
        sl_trailed = pos.trail_pct > 0 and abs(pos.stop_loss - pos.initial_sl) / max(pos.initial_sl, 1e-9) > 0.001

        # ── Check exit conditions (SL/TP/Liquidation only) ──
        if pos.direction == "long":
            if low <= pos.liquidation:
                exit_price = pos.liquidation
                reason = "💀 Liquidated"
                pnl = -pos.margin
            elif low <= pos.stop_loss:
                exit_price = pos.stop_loss
                if sl_trailed:
                    reason = f"🔄 Trailing SL hit (moved from ${pos.initial_sl:.2f})"
                    is_trailing_sl = True
                else:
                    reason = "🛑 Stop-loss hit"
                pnl = self._calc_pnl(pos, exit_price)
            elif high >= pos.take_profit:
                exit_price = pos.take_profit
                reason = "🎯 Take-profit hit"
                pnl = self._calc_pnl(pos, exit_price)
        else:  # short
            if high >= pos.liquidation:
                exit_price = pos.liquidation
                reason = "💀 Liquidated"
                pnl = -pos.margin
            elif high >= pos.stop_loss:
                exit_price = pos.stop_loss
                if sl_trailed:
                    reason = f"🔄 Trailing SL hit (moved from ${pos.initial_sl:.2f})"
                    is_trailing_sl = True
                else:
                    reason = "🛑 Stop-loss hit"
                pnl = self._calc_pnl(pos, exit_price)
            elif low <= pos.take_profit:
                exit_price = pos.take_profit
                reason = "🎯 Take-profit hit"
                pnl = self._calc_pnl(pos, exit_price)

        if exit_price is None:
            return None

        # Commission on close
        close_value = pos.amount * exit_price
        close_fee = close_value * (TAKER_FEE_PCT / 100)
        net_pnl = pnl - close_fee

        cash_back = max(pos.margin + net_pnl, 0)
        cash_back_gross = max(pos.margin + pnl, 0)
        trades.append(BacktestTrade(
            trade_type=f"close_{pos.direction}",
            timestamp=ts, price=exit_price,
            amount=pos.amount, margin=pos.margin,
            leverage=pos.leverage,
            total_value=close_value,
            profit_loss=net_pnl,
            commission=close_fee,
            reason=reason,
        ))
        return cash_back, cash_back_gross, close_fee, is_trailing_sl

    @staticmethod
    def _calc_pnl(pos: _Position, price: float) -> float:
        if pos.direction == "long":
            return pos.amount * (price - pos.entry_price)
        else:
            return pos.amount * (pos.entry_price - price)

    @staticmethod
    def _calc_sharpe(equity_curve: List[Dict], risk_free: float = 0.0) -> float:
        """Annualized Sharpe ratio from equity series."""
        if len(equity_curve) < 10:
            return 0.0

        returns = []
        for i in range(1, len(equity_curve)):
            prev = equity_curve[i - 1]["equity"]
            curr = equity_curve[i]["equity"]
            if prev > 0:
                returns.append((curr - prev) / prev)

        if not returns:
            return 0.0

        mean_r = sum(returns) / len(returns)
        var = sum((r - mean_r) ** 2 for r in returns) / len(returns)
        std = math.sqrt(var) if var > 0 else 0.0001

        # Annualize: assume ~252 trading days, scale by sqrt(periods_per_year)
        # For 4h candles: 6 per day × 365 = 2190 periods/year
        periods_per_year = 2190 if len(equity_curve) > 500 else 365
        sharpe = (mean_r - risk_free) / std * math.sqrt(periods_per_year)
        return max(min(sharpe, 99.0), -99.0)

    @staticmethod
    def _calc_streaks(close_trades: List[BacktestTrade]) -> tuple:
        """Max consecutive wins and losses."""
        max_w = max_l = cur_w = cur_l = 0
        for t in close_trades:
            if t.profit_loss > 0:
                cur_w += 1
                cur_l = 0
                max_w = max(max_w, cur_w)
            else:
                cur_l += 1
                cur_w = 0
                max_l = max(max_l, cur_l)
        return max_w, max_l
