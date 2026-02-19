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
    final_balance: float
    total_return_pct: float
    buy_hold_return_pct: float
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
    equity_curve: List[Dict]   # [{time (epoch), equity, buy_hold}]
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


def _get_kline_config(period_days: int) -> tuple:
    """Choose interval and total candles needed for backtesting.
    We use 4h candles for most periods (good balance of resolution & quantity).
    """
    if period_days <= 7:
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
    ) -> BacktestResult:
        """Execute a full backtest and return results."""

        cfg = STRATEGIES.get(strategy_key)
        if not cfg:
            raise ValueError(f"Unknown strategy: {strategy_key}")

        if leverage <= 0:
            leverage = cfg.default_leverage
        leverage = min(leverage, cfg.max_leverage)

        # --- Fetch historical klines ---
        interval, num_candles = _get_kline_config(period_days)
        # We need extra candles for indicator warm-up (55 candles for EMA-55)
        warmup = 60
        klines = _fetch_klines(coin, interval, num_candles + warmup)

        if len(klines) < warmup + 20:
            raise ValueError(f"Not enough data: got {len(klines)} candles, need {warmup + 20}+")

        # --- Simulation state ---
        balance = initial_balance
        position: Optional[_Position] = None
        trades: List[BacktestTrade] = []
        equity_curve: List[Dict] = []
        peak_equity = initial_balance
        max_drawdown = 0.0

        # Buy & hold reference
        first_price = klines[warmup]["close"]
        last_price = klines[-1]["close"]

        # --- Main loop: iterate candle by candle ---
        for i in range(warmup, len(klines)):
            candle = klines[i]
            close = candle["close"]
            high = candle["high"]
            low = candle["low"]
            ts = candle["timestamp"]

            # Build close price series up to this candle
            close_prices = [k["close"] for k in klines[:i + 1]]
            ohlc_slice = klines[:i + 1]

            # --- Check SL / TP / Liquidation on current candle ---
            if position:
                closed = self._check_position_exit(
                    position, high, low, close, ts,
                    balance, trades
                )
                if closed:
                    balance += closed
                    position = None

            # --- Compute indicators ---
            try:
                indicators = Indicators.compute_all(close_prices, ohlc_slice, close)
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
                    position = self._open_position(
                        signal, close, leverage, strategy_key,
                        balance, ts, trades
                    )
                    if position:
                        balance -= position.margin

            elif position and signal.direction in ("close_long", "close_short"):
                # Strategy wants to close
                pnl = self._calc_pnl(position, close)
                cash_back = max(position.margin + pnl, 0)
                balance += cash_back
                trades.append(BacktestTrade(
                    trade_type=f"close_{position.direction}",
                    timestamp=ts, price=close,
                    amount=position.amount, margin=position.margin,
                    leverage=position.leverage,
                    total_value=position.amount * close,
                    profit_loss=pnl,
                    reason=signal.reasoning,
                ))
                position = None

            # --- Record equity ---
            equity = balance
            if position:
                equity += position.margin + self._calc_pnl(position, close)

            bh_equity = initial_balance * (close / first_price)
            equity_curve.append({"timestamp": ts, "equity": round(equity, 2), "buy_hold": round(bh_equity, 2)})

            if equity > peak_equity:
                peak_equity = equity
            dd = (peak_equity - equity) / peak_equity * 100 if peak_equity > 0 else 0
            if dd > max_drawdown:
                max_drawdown = dd

        # --- Force close any open position at end ---
        if position:
            pnl = self._calc_pnl(position, last_price)
            cash_back = max(position.margin + pnl, 0)
            balance += cash_back
            trades.append(BacktestTrade(
                trade_type=f"close_{position.direction}",
                timestamp=klines[-1]["timestamp"], price=last_price,
                amount=position.amount, margin=position.margin,
                leverage=position.leverage,
                total_value=position.amount * last_price,
                profit_loss=pnl,
                reason="Backtest end — force close",
            ))
            position = None

        # --- Compute metrics ---
        final_equity = balance
        total_return = (final_equity - initial_balance) / initial_balance * 100
        buy_hold_return = (last_price - first_price) / first_price * 100

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
            total_return_pct=round(total_return, 2),
            buy_hold_return_pct=round(buy_hold_return, 2),
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
            equity_curve=[
                {
                    "time": int(datetime.fromisoformat(e["timestamp"]).timestamp()),
                    "equity": e["equity"],
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
                "reason": t.reason,
            } for t in trades],
            candles_processed=len(klines) - warmup,
            start_date=klines[warmup]["timestamp"],
            end_date=klines[-1]["timestamp"],
        )

        logger.info(
            f"Backtest {strategy_key} on {coin} ({period_days}d, {leverage}x): "
            f"{total_return:+.2f}% return, {len(close_trades)} trades, "
            f"{win_rate:.0f}% win rate, {max_drawdown:.1f}% max DD"
        )

        return result

    # ── Helpers ──────────────────────────────────────────────────────────

    def _open_position(
        self, signal: Signal, price: float, leverage: int,
        strategy_key: str, balance: float, ts: str,
        trades: List[BacktestTrade],
    ) -> Optional[_Position]:
        """Open a simulated position. Returns the Position or None."""
        margin = calculate_position_size(
            balance, strategy_key, leverage,
            signal.stop_loss_pct, price
        )
        if margin <= 0 or margin > balance:
            return None

        position_value = margin * leverage
        amount = position_value / price
        direction = signal.direction

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
            reason=signal.reasoning,
        ))

        return _Position(
            direction=direction,
            entry_price=price,
            amount=amount,
            margin=margin,
            leverage=leverage,
            stop_loss=sl,
            take_profit=tp,
            liquidation=liq,
            opened_at=ts,
        )

    def _check_position_exit(
        self, pos: _Position, high: float, low: float,
        close: float, ts: str,
        balance: float, trades: List[BacktestTrade],
    ) -> Optional[float]:
        """Check if position should be closed by SL/TP/liquidation.
        Returns cash returned to balance if closed, else None.
        """
        exit_price = None
        reason = ""

        if pos.direction == "long":
            if low <= pos.liquidation:
                exit_price = pos.liquidation
                reason = "💀 Liquidated"
                pnl = -pos.margin  # total loss
            elif low <= pos.stop_loss:
                exit_price = pos.stop_loss
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
                reason = "🛑 Stop-loss hit"
                pnl = self._calc_pnl(pos, exit_price)
            elif low <= pos.take_profit:
                exit_price = pos.take_profit
                reason = "🎯 Take-profit hit"
                pnl = self._calc_pnl(pos, exit_price)

        if exit_price is None:
            return None

        cash_back = max(pos.margin + pnl, 0)
        trades.append(BacktestTrade(
            trade_type=f"close_{pos.direction}",
            timestamp=ts, price=exit_price,
            amount=pos.amount, margin=pos.margin,
            leverage=pos.leverage,
            total_value=pos.amount * exit_price,
            profit_loss=pnl,
            reason=reason,
        ))
        return cash_back

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
