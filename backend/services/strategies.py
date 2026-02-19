"""
Elite Trading Strategies for Cryptocurrency Futures
====================================================
Inspired by the world's top traders: Paul Tudor Jones (trend following),
Jim Simons (mean reversion), Jesse Livermore (momentum breakouts),
and institutional quant desks (confluence / multi-factor).

Supports LONG and SHORT positions with configurable leverage.
"""
import logging
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


# ── Signal (output of every strategy evaluation) ────────────────────────────

@dataclass
class Signal:
    """Trading signal produced by a strategy evaluation."""
    direction: str          # "long", "short", "close_long", "close_short", "neutral"
    confidence: float       # 0.0 – 1.0
    leverage: int           # suggested leverage multiplier
    stop_loss_pct: float    # % distance from entry for stop-loss
    take_profit_pct: float  # % distance from entry for take-profit
    reasoning: str          # human-readable explanation
    scores: Dict[str, float] = field(default_factory=dict)


# ── Strategy Configuration ──────────────────────────────────────────────────

@dataclass
class StrategyConfig:
    key: str
    name: str
    description: str
    style: str                # trend, mean_reversion, momentum, scalping, grid, confluence
    default_leverage: int
    max_leverage: int
    max_positions: int        # max concurrent open positions
    risk_per_trade_pct: float # % of capital risked per trade
    min_confidence: float     # minimum confidence to open position


STRATEGIES: Dict[str, StrategyConfig] = {
    "trend_rider": StrategyConfig(
        key="trend_rider",
        name="Trend Rider",
        description="Follows strong trends using EMA alignment + ADX + pullback entries. "
                    "6-layer signal architecture with 3:1 R:R. Best in trending markets.",
        style="trend",
        default_leverage=3,
        max_leverage=5,
        max_positions=3,
        risk_per_trade_pct=2.5,
        min_confidence=0.55,
    ),
    "mean_reversion": StrategyConfig(
        key="mean_reversion",
        name="Mean Reversion",
        description="Exploits overextended moves using Bollinger Bands + RSI extremes. "
                    "Longs oversold, shorts overbought. Best in ranging markets.",
        style="mean_reversion",
        default_leverage=2,
        max_leverage=3,
        max_positions=4,
        risk_per_trade_pct=1.5,
        min_confidence=0.50,
    ),
    "momentum_sniper": StrategyConfig(
        key="momentum_sniper",
        name="Momentum Sniper",
        description="Catches explosive moves on MACD crossovers backed by volume surges. "
                    "High leverage on confirmed momentum. Best in volatile markets.",
        style="momentum",
        default_leverage=4,
        max_leverage=7,
        max_positions=2,
        risk_per_trade_pct=2.5,
        min_confidence=0.60,
    ),
    "scalper": StrategyConfig(
        key="scalper",
        name="Scalper Pro",
        description="Trend-following pullback scalping (1h candles). Enters pullbacks within "
                    "short-term trends using EMA alignment + RSI + BB confluence. "
                    "ATR-adaptive stops. Profits in any market.",
        style="scalping",
        default_leverage=5,
        max_leverage=10,
        max_positions=5,
        risk_per_trade_pct=4.0,
        min_confidence=0.50,
    ),
    "scalper_1m": StrategyConfig(
        key="scalper_1m",
        name="Scalper Pro 1m",
        description="Ultra-fast 1-minute scalper. Same 6-layer trend-pullback logic "
                    "on 1m candles. Extremely tight ATR stops. Best for high-frequency.",
        style="scalping",
        default_leverage=10,
        max_leverage=20,
        max_positions=5,
        risk_per_trade_pct=2.0,
        min_confidence=0.50,
    ),
    "scalper_3m": StrategyConfig(
        key="scalper_3m",
        name="Scalper Pro 3m",
        description="Fast 3-minute scalper. 6-layer trend-pullback logic on 3m candles. "
                    "Good balance between speed and signal quality.",
        style="scalping",
        default_leverage=8,
        max_leverage=15,
        max_positions=5,
        risk_per_trade_pct=2.5,
        min_confidence=0.50,
    ),
    "scalper_5m": StrategyConfig(
        key="scalper_5m",
        name="Scalper Pro 5m",
        description="Classic 5-minute scalper. 6-layer trend-pullback logic on 5m candles. "
                    "Standard daytrading timeframe with solid signal quality.",
        style="scalping",
        default_leverage=7,
        max_leverage=12,
        max_positions=5,
        risk_per_trade_pct=3.0,
        min_confidence=0.50,
    ),
    "scalper_15m": StrategyConfig(
        key="scalper_15m",
        name="Scalper Pro 15m",
        description="Swing scalper on 15-minute candles. Same 6-layer logic with wider ATR stops. "
                    "Fewer trades, higher quality entries.",
        style="scalping",
        default_leverage=6,
        max_leverage=10,
        max_positions=5,
        risk_per_trade_pct=3.5,
        min_confidence=0.50,
    ),
    "grid_trader": StrategyConfig(
        key="grid_trader",
        name="Grid Trader",
        description="Systematic buy/sell at predefined price levels. "
                    "Profits from oscillation. Best in sideways markets.",
        style="grid",
        default_leverage=2,
        max_leverage=3,
        max_positions=8,
        risk_per_trade_pct=1.0,
        min_confidence=0.40,
    ),
    "confluence_master": StrategyConfig(
        key="confluence_master",
        name="Confluence Master",
        description="Only trades when 5+ indicators align. Fewest trades, highest win rate. "
                    "High leverage justified by overwhelming evidence.",
        style="confluence",
        default_leverage=5,
        max_leverage=10,
        max_positions=2,
        risk_per_trade_pct=3.0,
        min_confidence=0.70,
    ),
}


# ── Indicator Library ───────────────────────────────────────────────────────

class Indicators:
    """Stateless library of technical indicator computations."""

    # ── Series helpers (needed for MACD signal line, Stochastic RSI, etc.) ──

    @staticmethod
    def ema_series(prices: List[float], period: int) -> List[float]:
        """Full EMA series. First value is SMA seed."""
        if len(prices) < period:
            return []
        k = 2.0 / (period + 1)
        emas = [sum(prices[:period]) / period]
        for price in prices[period:]:
            emas.append(price * k + emas[-1] * (1 - k))
        return emas

    @staticmethod
    def sma_series(prices: List[float], period: int) -> List[float]:
        if len(prices) < period:
            return []
        return [sum(prices[i - period + 1:i + 1]) / period for i in range(period - 1, len(prices))]

    @staticmethod
    def rsi_series(prices: List[float], period: int = 14) -> List[float]:
        """Wilder-smoothed RSI series."""
        if len(prices) < period + 1:
            return []
        deltas = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
        gains = [max(d, 0) for d in deltas]
        losses = [max(-d, 0) for d in deltas]

        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period

        rsis = []
        if avg_loss == 0:
            rsis.append(100.0)
        else:
            rsis.append(100 - 100 / (1 + avg_gain / avg_loss))

        for i in range(period, len(deltas)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period
            if avg_loss == 0:
                rsis.append(100.0)
            else:
                rsis.append(100 - 100 / (1 + avg_gain / avg_loss))
        return rsis

    # ── Point-value indicators ──────────────────────────────────────────

    @staticmethod
    def rsi(prices: List[float], period: int = 14) -> Optional[float]:
        series = Indicators.rsi_series(prices, period)
        return series[-1] if series else None

    @staticmethod
    def ema(prices: List[float], period: int) -> Optional[float]:
        series = Indicators.ema_series(prices, period)
        return series[-1] if series else None

    @staticmethod
    def sma(prices: List[float], period: int) -> Optional[float]:
        if len(prices) < period:
            return None
        return sum(prices[-period:]) / period

    # ── MACD (proper implementation with signal EMA) ────────────────────

    @staticmethod
    def macd(prices: List[float], fast: int = 12, slow: int = 26,
             signal_period: int = 9) -> Optional[Dict]:
        """MACD with proper signal line (EMA-9 of MACD series)."""
        if len(prices) < slow + signal_period:
            return None

        ema_fast = Indicators.ema_series(prices, fast)
        ema_slow = Indicators.ema_series(prices, slow)

        # Align series: ema_fast starts at index fast-1, ema_slow at slow-1
        offset = slow - fast
        if offset > len(ema_fast):
            return None

        macd_series = [ema_fast[i + offset] - ema_slow[i] for i in range(len(ema_slow))]

        if len(macd_series) < signal_period:
            return None

        signal_series = Indicators.ema_series(macd_series, signal_period)
        if not signal_series:
            return None

        macd_val = macd_series[-1]
        signal_val = signal_series[-1]
        histogram = macd_val - signal_val

        # Previous values for crossover detection
        prev_macd = macd_series[-2] if len(macd_series) >= 2 else macd_val
        prev_signal = signal_series[-2] if len(signal_series) >= 2 else signal_val
        prev_histogram = prev_macd - prev_signal

        return {
            "macd": macd_val,
            "signal": signal_val,
            "histogram": histogram,
            "crossover": "bullish" if prev_macd <= prev_signal and macd_val > signal_val
                         else "bearish" if prev_macd >= prev_signal and macd_val < signal_val
                         else "none",
            "prev_histogram": prev_histogram,
        }

    # ── Bollinger Bands ─────────────────────────────────────────────────

    @staticmethod
    def bollinger_bands(prices: List[float], period: int = 20,
                        std_mult: float = 2.0) -> Optional[Dict]:
        if len(prices) < period:
            return None
        recent = prices[-period:]
        sma = sum(recent) / period
        std = math.sqrt(sum((p - sma) ** 2 for p in recent) / period)
        upper = sma + std_mult * std
        lower = sma - std_mult * std
        width_pct = ((upper - lower) / sma * 100) if sma > 0 else 0

        # %B: position of price within bands (0 = lower, 1 = upper)
        current = prices[-1]
        pct_b = (current - lower) / (upper - lower) if (upper - lower) > 0 else 0.5

        return {
            "upper": upper,
            "middle": sma,
            "lower": lower,
            "width_pct": width_pct,
            "pct_b": pct_b,
            "squeeze": width_pct < 5,  # tight bands = potential breakout
        }

    # ── ATR (Average True Range) ────────────────────────────────────────

    @staticmethod
    def atr(ohlc: List[Dict], period: int = 14) -> Optional[float]:
        """Average True Range — Wilder smoothing."""
        if len(ohlc) < period + 1:
            return None
        trs = []
        for i in range(1, len(ohlc)):
            h = ohlc[i]["high"]
            l = ohlc[i]["low"]
            pc = ohlc[i - 1]["close"]
            trs.append(max(h - l, abs(h - pc), abs(l - pc)))

        atr_val = sum(trs[:period]) / period
        for tr in trs[period:]:
            atr_val = (atr_val * (period - 1) + tr) / period
        return atr_val

    @staticmethod
    def atr_pct(ohlc: List[Dict], period: int = 14) -> Optional[float]:
        """ATR as percentage of current price."""
        a = Indicators.atr(ohlc, period)
        if a is None or not ohlc:
            return None
        current = ohlc[-1]["close"]
        return (a / current * 100) if current > 0 else None

    # ── ADX (Average Directional Index) ─────────────────────────────────

    @staticmethod
    def adx(ohlc: List[Dict], period: int = 14) -> Optional[Dict]:
        """ADX with +DI / -DI. Requires 2*period + 1 bars minimum."""
        if len(ohlc) < 2 * period + 1:
            return None

        plus_dms, minus_dms, trs = [], [], []

        for i in range(1, len(ohlc)):
            h, l = ohlc[i]["high"], ohlc[i]["low"]
            ph, pl = ohlc[i - 1]["high"], ohlc[i - 1]["low"]
            pc = ohlc[i - 1]["close"]

            up = h - ph
            down = pl - l
            plus_dms.append(up if up > down and up > 0 else 0)
            minus_dms.append(down if down > up and down > 0 else 0)
            trs.append(max(h - l, abs(h - pc), abs(l - pc)))

        # Wilder smoothing
        sm_plus = sum(plus_dms[:period])
        sm_minus = sum(minus_dms[:period])
        sm_tr = sum(trs[:period])

        dx_values = []
        for i in range(period, len(trs)):
            sm_plus = sm_plus - sm_plus / period + plus_dms[i]
            sm_minus = sm_minus - sm_minus / period + minus_dms[i]
            sm_tr = sm_tr - sm_tr / period + trs[i]

            plus_di = (100 * sm_plus / sm_tr) if sm_tr > 0 else 0
            minus_di = (100 * sm_minus / sm_tr) if sm_tr > 0 else 0
            di_sum = plus_di + minus_di
            dx = (abs(plus_di - minus_di) / di_sum * 100) if di_sum > 0 else 0
            dx_values.append((dx, plus_di, minus_di))

        if len(dx_values) < period:
            return None

        adx_val = sum(d[0] for d in dx_values[:period]) / period
        for dx, _, _ in dx_values[period:]:
            adx_val = (adx_val * (period - 1) + dx) / period

        return {
            "adx": adx_val,
            "plus_di": dx_values[-1][1],
            "minus_di": dx_values[-1][2],
            "trending": adx_val > 25,
            "strong_trend": adx_val > 40,
        }

    # ── Stochastic RSI ──────────────────────────────────────────────────

    @staticmethod
    def stochastic_rsi(prices: List[float], rsi_period: int = 14,
                       stoch_period: int = 14, k_smooth: int = 3) -> Optional[Dict]:
        rsi_vals = Indicators.rsi_series(prices, rsi_period)
        if len(rsi_vals) < stoch_period:
            return None

        stoch_rsi_vals = []
        for i in range(stoch_period - 1, len(rsi_vals)):
            window = rsi_vals[i - stoch_period + 1:i + 1]
            min_r, max_r = min(window), max(window)
            stoch_rsi_vals.append(
                ((rsi_vals[i] - min_r) / (max_r - min_r) * 100)
                if max_r != min_r else 50.0
            )

        # %K = SMA of raw stochastic RSI
        k = (sum(stoch_rsi_vals[-k_smooth:]) / k_smooth
             if len(stoch_rsi_vals) >= k_smooth else stoch_rsi_vals[-1])
        # %D = previous %K (simplified)
        prev_k = (sum(stoch_rsi_vals[-k_smooth - 1:-1]) / k_smooth
                  if len(stoch_rsi_vals) >= k_smooth + 1 else k)

        return {"k": k, "d": prev_k, "oversold": k < 20, "overbought": k > 80}

    # ── Volume Analysis ─────────────────────────────────────────────────

    @staticmethod
    def volume_analysis(ohlc: List[Dict]) -> Optional[Dict]:
        """Analyze volume trend and detect surges."""
        volumes = [bar.get("volume", 0) for bar in ohlc]
        if not any(v > 0 for v in volumes):
            return None

        recent_5 = volumes[-5:] if len(volumes) >= 5 else volumes
        older_10 = volumes[-15:-5] if len(volumes) >= 15 else volumes[:max(len(volumes) - 5, 1)]

        avg_recent = sum(recent_5) / len(recent_5) if recent_5 else 1
        avg_older = sum(older_10) / len(older_10) if older_10 else 1

        ratio = avg_recent / avg_older if avg_older > 0 else 1.0
        last_vol = volumes[-1] if volumes else 0
        spike = last_vol > avg_older * 2.0 if avg_older > 0 else False

        return {
            "ratio": ratio,
            "increasing": ratio > 1.3,
            "spike": spike,
            "avg_volume": avg_recent,
        }

    # ── Composite indicator set (used by all strategies) ────────────────

    @staticmethod
    def compute_all(close_prices: List[float], ohlc: List[Dict],
                    current_price: float) -> Dict:
        """Compute all indicators at once and return a flat dict."""
        result: Dict = {"current_price": current_price}

        result["rsi"] = Indicators.rsi(close_prices)
        result["macd"] = Indicators.macd(close_prices)
        result["bb"] = Indicators.bollinger_bands(close_prices)
        result["atr"] = Indicators.atr(ohlc)
        result["atr_pct"] = Indicators.atr_pct(ohlc)
        result["adx"] = Indicators.adx(ohlc)
        result["stoch_rsi"] = Indicators.stochastic_rsi(close_prices)
        result["volume"] = Indicators.volume_analysis(ohlc)

        # EMA alignment
        result["ema_9"] = Indicators.ema(close_prices, 9)
        result["ema_21"] = Indicators.ema(close_prices, 21)
        result["ema_55"] = Indicators.ema(close_prices, 55)

        # SMA
        result["sma_7"] = Indicators.sma(close_prices, 7)
        result["sma_21"] = Indicators.sma(close_prices, 21)
        result["sma_50"] = Indicators.sma(close_prices, 50)

        # Momentum
        avg_7 = result["sma_7"]
        if avg_7 and avg_7 > 0:
            result["momentum"] = (current_price - avg_7) / avg_7 * 100
        else:
            result["momentum"] = 0.0

        return result


# ── Strategy Engine ─────────────────────────────────────────────────────────

class StrategyEngine:
    """Evaluates market conditions and emits trading signals per strategy."""

    def evaluate(self, strategy_key: str, indicators: Dict,
                 current_price: float, has_long: bool = False,
                 has_short: bool = False,
                 entry_price: float = 0.0) -> Signal:
        """Route evaluation to the correct strategy method."""

        dispatch = {
            "trend_rider": self._trend_rider,
            "mean_reversion": self._mean_reversion,
            "momentum_sniper": self._momentum_sniper,
            "scalper": self._scalper,
            "scalper_1m": self._scalper,
            "scalper_3m": self._scalper,
            "scalper_5m": self._scalper,
            "scalper_15m": self._scalper,
            "grid_trader": self._grid_trader,
            "confluence_master": self._confluence_master,
        }

        fn = dispatch.get(strategy_key, self._confluence_master)
        try:
            return fn(indicators, current_price, has_long, has_short, entry_price)
        except Exception as e:
            logger.error(f"Strategy {strategy_key} error: {e}")
            return Signal("neutral", 0.0, 1, 5.0, 10.0, f"Strategy error: {e}")

    # ── 1. Trend Rider ──────────────────────────────────────────────────

    def _trend_rider(self, ind: Dict, price: float,
                     has_long: bool, has_short: bool,
                     entry_price: float) -> Signal:
        """
        Paul Tudor Jones / Trend Following — v2.

        Philosophy:
        - Only trade WITH the dominant trend (EMA 9>21>55)
        - Wait for a pullback within the trend to enter (RSI dip/bounce)
        - Use ADX to confirm trend strength (avoid choppy markets)
        - MACD crossover as momentum catalyst
        - BB position for pullback timing
        - Volume + StochRSI as final confirmation layers
        - ATR-adaptive stops with 3:1 R:R
        - Counter-trend penalty to avoid whipsaws
        """
        reasons = []
        long_score = 0
        short_score = 0
        cfg = STRATEGIES["trend_rider"]

        ema9 = ind.get("ema_9")
        ema21 = ind.get("ema_21")
        ema55 = ind.get("ema_55")
        adx = ind.get("adx")
        macd = ind.get("macd")
        rsi = ind.get("rsi")
        bb = ind.get("bb")
        stoch = ind.get("stoch_rsi")
        vol = ind.get("volume")
        mom = ind.get("momentum", 0)
        atr_pct = ind.get("atr_pct") or 3.0

        # ═══════════════════════════════════════════════════════════════
        # LAYER 1: Dominant Trend Filter (EMA alignment)
        #   This is the GATE — we only trade in the trend direction
        #   Partial alignment is just a filter (+1 pt)
        #   Full alignment (9>21>55) is a quality signal (+2 more pts)
        # ═══════════════════════════════════════════════════════════════
        trend_up = False
        trend_down = False

        if ema9 and ema21:
            if ema9 > ema21:
                trend_up = True
                long_score += 1
            else:
                trend_down = True
                short_score += 1

            # Full alignment (9>21>55) = confirmed trend — award points
            if ema55:
                if ema9 > ema21 > ema55:
                    long_score += 2
                    reasons.append("EMA 9>21>55 bullish alignment")
                elif ema9 < ema21 < ema55:
                    short_score += 2
                    reasons.append("EMA 9<21<55 bearish alignment")

        # ═══════════════════════════════════════════════════════════════
        # LAYER 2: ADX Trend Strength (quality filter)
        #   Strong trend = high conviction; weak/no trend = skip
        # ═══════════════════════════════════════════════════════════════
        if adx:
            if adx["strong_trend"]:  # ADX > 30
                if adx["plus_di"] > adx["minus_di"]:
                    long_score += 2
                    reasons.append(f"Strong uptrend ADX {adx['adx']:.0f}")
                else:
                    short_score += 2
                    reasons.append(f"Strong downtrend ADX {adx['adx']:.0f}")
            elif adx["trending"]:  # ADX 20-30
                if adx["plus_di"] > adx["minus_di"]:
                    long_score += 1
                else:
                    short_score += 1
                reasons.append(f"Moderate trend ADX {adx['adx']:.0f}")
            else:
                # Weak trend — penalize both sides to avoid choppy entries
                long_score = max(0, long_score - 2)
                short_score = max(0, short_score - 2)
                reasons.append(f"Weak trend ADX {adx['adx']:.0f} — reduced")

        # ═══════════════════════════════════════════════════════════════
        # LAYER 3: Pullback Entry (RSI in trend direction)
        #   Don't chase — wait for RSI to dip/bounce before entering
        # ═══════════════════════════════════════════════════════════════
        if rsi is not None:
            # In uptrend: RSI pullback to 35-48 = buying opportunity
            if trend_up and 35 <= rsi <= 48:
                long_score += 2
                reasons.append(f"Uptrend pullback: RSI {rsi:.0f}")
            # In downtrend: RSI bounce to 52-65 = shorting opportunity
            elif trend_down and 52 <= rsi <= 65:
                short_score += 2
                reasons.append(f"Downtrend bounce: RSI {rsi:.0f}")
            # Chasing warning: RSI already extended in trend direction
            elif trend_up and rsi > 72:
                long_score = max(0, long_score - 1)
                reasons.append(f"RSI overextended {rsi:.0f} — avoid chasing")
            elif trend_down and rsi < 28:
                short_score = max(0, short_score - 1)
                reasons.append(f"RSI overextended {rsi:.0f} — avoid chasing")

        # ═══════════════════════════════════════════════════════════════
        # LAYER 4: MACD Momentum Catalyst
        #   Crossover is a strong trigger; histogram direction confirms
        # ═══════════════════════════════════════════════════════════════
        if macd:
            crossover = macd.get("crossover", "none")
            hist = macd.get("histogram", 0)
            if crossover == "bullish":
                long_score += 2
                reasons.append("MACD bullish crossover")
            elif crossover == "bearish":
                short_score += 2
                reasons.append("MACD bearish crossover")
            elif hist > 0 and long_score > short_score:
                long_score += 1
            elif hist < 0 and short_score > long_score:
                short_score += 1

        # ═══════════════════════════════════════════════════════════════
        # LAYER 5: BB Pullback Timing + StochRSI
        #   Price near lower BB in uptrend = pullback to support (buy)
        #   StochRSI crossover from oversold = precision trigger
        # ═══════════════════════════════════════════════════════════════
        if bb:
            if trend_up and bb["pct_b"] < 0.30:
                long_score += 1
                reasons.append(f"Price near lower BB ({bb['pct_b']:.2f}) — pullback support")
            elif trend_down and bb["pct_b"] > 0.70:
                short_score += 1
                reasons.append(f"Price near upper BB ({bb['pct_b']:.2f}) — bounce resistance")

        if stoch:
            if stoch["k"] > stoch["d"] and stoch["oversold"]:
                long_score += 1
                reasons.append("StochRSI cross up from oversold")
            elif stoch["k"] < stoch["d"] and stoch["overbought"]:
                short_score += 1
                reasons.append("StochRSI cross down from overbought")

        # ═══════════════════════════════════════════════════════════════
        # LAYER 6: Volume Confirmation
        # ═══════════════════════════════════════════════════════════════
        if vol and vol.get("increasing"):
            if long_score > short_score:
                long_score += 1
                reasons.append("Volume increasing")
            elif short_score > long_score:
                short_score += 1
                reasons.append("Volume increasing")

        # ═══════════════════════════════════════════════════════════════
        # COUNTER-TREND PENALTY
        #   Fighting the dominant trend is a losing game
        # ═══════════════════════════════════════════════════════════════
        if trend_up and short_score > long_score:
            short_score = max(0, short_score - 2)
        if trend_down and long_score > short_score:
            long_score = max(0, long_score - 2)

        # ═══════════════════════════════════════════════════════════════
        # HARD GATE: Require full EMA alignment for new entries
        #   Trend Rider should only enter confirmed trends (9>21>55).
        #   Without full alignment, cap scores below entry threshold
        #   so no new positions open. Existing positions can still close.
        # ═══════════════════════════════════════════════════════════════
        full_alignment = (ema55 is not None and ema9 is not None and ema21 is not None
                          and ((ema9 > ema21 > ema55) or (ema9 < ema21 < ema55)))
        if not full_alignment:
            long_score = min(long_score, 2)
            short_score = min(short_score, 2)

        # ═══════════════════════════════════════════════════════════════
        # STOPS: ATR-adaptive with 3:1 R:R
        #   Wider SL than Scalper (1.5×ATR) because trends need room to breathe
        #   TP at 4.5×ATR = 3:1 ratio
        # ═══════════════════════════════════════════════════════════════
        sl = max(atr_pct * 1.5, 1.5)
        tp = max(atr_pct * 4.5, sl * 3.0)

        return self._build_signal(
            long_score, short_score, reasons, cfg,
            has_long, has_short, sl, tp, entry_price, price
        )

    # ── 2. Mean Reversion ───────────────────────────────────────────────

    def _mean_reversion(self, ind: Dict, price: float,
                        has_long: bool, has_short: bool,
                        entry_price: float) -> Signal:
        """
        Jim Simons / Renaissance style.
        Buy at lower BB + RSI oversold, short at upper BB + RSI overbought.
        Target: return to BB middle.
        """
        reasons = []
        long_score = 0
        short_score = 0
        cfg = STRATEGIES["mean_reversion"]

        bb = ind.get("bb")
        rsi = ind.get("rsi")
        stoch = ind.get("stoch_rsi")

        # Bollinger Bands position
        if bb:
            pct_b = bb["pct_b"]
            if pct_b <= 0.05:
                long_score += 3
                reasons.append(f"Price at/below lower BB (%B={pct_b:.2f})")
            elif pct_b <= 0.2:
                long_score += 2
                reasons.append(f"Price near lower BB (%B={pct_b:.2f})")
            elif pct_b >= 0.95:
                short_score += 3
                reasons.append(f"Price at/above upper BB (%B={pct_b:.2f})")
            elif pct_b >= 0.8:
                short_score += 2
                reasons.append(f"Price near upper BB (%B={pct_b:.2f})")

        # RSI extremes
        if rsi is not None:
            if rsi < 25:
                long_score += 3
                reasons.append(f"RSI deeply oversold ({rsi:.1f})")
            elif rsi < 35:
                long_score += 1
                reasons.append(f"RSI oversold zone ({rsi:.1f})")
            elif rsi > 75:
                short_score += 3
                reasons.append(f"RSI deeply overbought ({rsi:.1f})")
            elif rsi > 65:
                short_score += 1
                reasons.append(f"RSI overbought zone ({rsi:.1f})")

        # Stochastic RSI for timing
        if stoch:
            if stoch["oversold"]:
                long_score += 1
                reasons.append(f"StochRSI oversold ({stoch['k']:.0f})")
            elif stoch["overbought"]:
                short_score += 1
                reasons.append(f"StochRSI overbought ({stoch['k']:.0f})")

        # Avoid trading WITH strong trends (mean reversion fails in trends)
        adx = ind.get("adx")
        if adx and adx["strong_trend"]:
            long_score = max(0, long_score - 2)
            short_score = max(0, short_score - 2)
            reasons.append(f"⚠ Strong trend (ADX {adx['adx']:.0f}) — reducing confidence")

        # Mean reversion targets BB middle
        atr_pct = ind.get("atr_pct") or 2.0
        sl = max(atr_pct * 1.5, 2.0)
        tp = max(atr_pct * 2.5, 4.0)

        return self._build_signal(
            long_score, short_score, reasons, cfg,
            has_long, has_short, sl, tp, entry_price, price
        )

    # ── 3. Momentum Sniper ──────────────────────────────────────────────

    def _momentum_sniper(self, ind: Dict, price: float,
                         has_long: bool, has_short: bool,
                         entry_price: float) -> Signal:
        """
        Jesse Livermore style.
        Enter on MACD crossover + volume spike + momentum confirmation.
        """
        reasons = []
        long_score = 0
        short_score = 0
        cfg = STRATEGIES["momentum_sniper"]

        macd = ind.get("macd")
        vol = ind.get("volume")
        mom = ind.get("momentum", 0)
        rsi = ind.get("rsi")

        # MACD crossover is the primary trigger
        if macd:
            if macd["crossover"] == "bullish":
                long_score += 3
                reasons.append("MACD bullish crossover (primary signal)")
            elif macd["crossover"] == "bearish":
                short_score += 3
                reasons.append("MACD bearish crossover (primary signal)")
            # Histogram acceleration
            if macd["histogram"] > 0 and macd["prev_histogram"] < macd["histogram"]:
                long_score += 1
                reasons.append("MACD histogram accelerating up")
            elif macd["histogram"] < 0 and macd["prev_histogram"] > macd["histogram"]:
                short_score += 1
                reasons.append("MACD histogram accelerating down")

        # Volume confirmation (critical for momentum)
        if vol:
            if vol["spike"]:
                long_score += 2 if mom > 0 else 0
                short_score += 2 if mom < 0 else 0
                reasons.append("Volume spike detected")
            elif vol["increasing"]:
                if mom > 0:
                    long_score += 1
                elif mom < 0:
                    short_score += 1
                reasons.append("Increasing volume")

        # Strong momentum
        if mom > 5:
            long_score += 2
            reasons.append(f"Strong momentum +{mom:.1f}%")
        elif mom > 2:
            long_score += 1
        elif mom < -5:
            short_score += 2
            reasons.append(f"Strong negative momentum {mom:.1f}%")
        elif mom < -2:
            short_score += 1

        # RSI filter — avoid overstretched entries
        if rsi is not None:
            if rsi > 80:
                long_score = max(0, long_score - 2)
                reasons.append(f"⚠ RSI too high ({rsi:.0f}) — momentum exhaustion risk")
            elif rsi < 20:
                short_score = max(0, short_score - 2)
                reasons.append(f"⚠ RSI too low ({rsi:.0f}) — bounce risk")

        atr_pct = ind.get("atr_pct") or 3.0
        sl = max(atr_pct * 1.5, 2.0)
        tp = max(atr_pct * 4, 8.0)  # momentum -> let winners run

        return self._build_signal(
            long_score, short_score, reasons, cfg,
            has_long, has_short, sl, tp, entry_price, price
        )

    # ── 4. Scalper Pro ──────────────────────────────────────────────────

    def _scalper(self, ind: Dict, price: float,
                 has_long: bool, has_short: bool,
                 entry_price: float) -> Signal:
        """
        Professional trend-following scalper.

        Philosophy:
        - Trade WITH the short-term trend (EMA9 vs EMA21)
        - Enter on pullbacks within the trend (RSI dips/bounces)
        - Require BB confirmation for timing
        - Use ATR-adaptive stops with 2:1+ R:R
        - Exit on counter-trend signals or when target hit
        """
        reasons = []
        long_score = 0
        short_score = 0
        cfg = STRATEGIES["scalper"]

        rsi = ind.get("rsi")
        bb = ind.get("bb")
        stoch = ind.get("stoch_rsi")
        mom = ind.get("momentum", 0)
        ema9 = ind.get("ema_9")
        ema21 = ind.get("ema_21")
        ema55 = ind.get("ema_55")
        atr_pct = ind.get("atr_pct") or 2.0
        macd = ind.get("macd")
        adx = ind.get("adx")
        vol = ind.get("volume")

        # ═══════════════════════════════════════════════════════════════
        # LAYER 1: Short-term Trend (EMA alignment)
        #   This is the FILTER — we only trade in direction of trend
        # ═══════════════════════════════════════════════════════════════
        trend_up = False
        trend_down = False

        if ema9 and ema21:
            if ema9 > ema21:
                trend_up = True
                long_score += 1
            else:
                trend_down = True
                short_score += 1

            # Stronger trend: EMA9 > EMA21 > EMA55
            if ema55:
                if ema9 > ema21 > ema55:
                    long_score += 1
                    reasons.append("EMA alignment bullish (9>21>55)")
                elif ema9 < ema21 < ema55:
                    short_score += 1
                    reasons.append("EMA alignment bearish (9<21<55)")

        # ═══════════════════════════════════════════════════════════════
        # LAYER 2: Pullback Entry (RSI in trend direction)
        #   Buy when RSI dips in uptrend; Short when RSI bounces in downtrend
        # ═══════════════════════════════════════════════════════════════
        if rsi is not None:
            # IN UPTREND: RSI pullback to 35-48 is a buying opportunity
            if trend_up and 30 <= rsi <= 48:
                long_score += 2
                reasons.append(f"Uptrend pullback: RSI {rsi:.0f}")
            # IN DOWNTREND: RSI bounce to 52-70 is a shorting opportunity
            elif trend_down and 52 <= rsi <= 70:
                short_score += 2
                reasons.append(f"Downtrend bounce: RSI {rsi:.0f}")
            # Extreme oversold in ANY market = long opportunity
            elif rsi < 25:
                long_score += 2
                reasons.append(f"Extreme oversold: RSI {rsi:.0f}")
            # Extreme overbought in ANY market = short opportunity
            elif rsi > 75:
                short_score += 2
                reasons.append(f"Extreme overbought: RSI {rsi:.0f}")

        # ═══════════════════════════════════════════════════════════════
        # LAYER 3: Bollinger Band position (entry timing)
        # ═══════════════════════════════════════════════════════════════
        if bb:
            # In uptrend: price near lower band = pullback to support
            if trend_up and bb["pct_b"] < 0.30:
                long_score += 1
                reasons.append(f"Price near lower BB ({bb['pct_b']:.2f})")
            # In downtrend: price near upper band = bounce to resistance
            elif trend_down and bb["pct_b"] > 0.70:
                short_score += 1
                reasons.append(f"Price near upper BB ({bb['pct_b']:.2f})")
            # Extreme positions regardless of trend
            if bb["pct_b"] < 0.05:
                long_score += 1
                reasons.append("BB extreme low")
            elif bb["pct_b"] > 0.95:
                short_score += 1
                reasons.append("BB extreme high")

        # ═══════════════════════════════════════════════════════════════
        # LAYER 4: MACD Momentum Confirmation
        # ═══════════════════════════════════════════════════════════════
        if macd:
            hist = macd.get("histogram", 0)
            crossover = macd.get("crossover", "none")
            # MACD crossover is a strong signal
            if crossover == "bullish":
                long_score += 2
                reasons.append("MACD bullish crossover")
            elif crossover == "bearish":
                short_score += 2
                reasons.append("MACD bearish crossover")
            # Histogram direction confirms momentum
            elif hist > 0 and long_score > short_score:
                long_score += 1
            elif hist < 0 and short_score > long_score:
                short_score += 1

        # ═══════════════════════════════════════════════════════════════
        # LAYER 5: Stochastic RSI crossover
        # ═══════════════════════════════════════════════════════════════
        if stoch:
            # Stoch RSI cross up from oversold = strong long trigger
            if stoch["k"] > stoch["d"] and stoch["oversold"]:
                long_score += 1
                reasons.append("StochRSI cross up from oversold")
            elif stoch["k"] < stoch["d"] and stoch["overbought"]:
                short_score += 1
                reasons.append("StochRSI cross down from overbought")

        # ═══════════════════════════════════════════════════════════════
        # LAYER 6: Volume confirmation
        # ═══════════════════════════════════════════════════════════════
        if vol and vol.get("increasing"):
            if long_score > short_score:
                long_score += 1
                reasons.append("Volume increasing")
            elif short_score > long_score:
                short_score += 1
                reasons.append("Volume increasing")

        # ═══════════════════════════════════════════════════════════════
        # COUNTER-TREND PENALTY: Reduce score for fighting the trend
        # ═══════════════════════════════════════════════════════════════
        if trend_up and short_score > long_score:
            short_score = max(0, short_score - 2)
        if trend_down and long_score > short_score:
            long_score = max(0, long_score - 2)

        # ═══════════════════════════════════════════════════════════════
        # STOPS: ATR-adaptive with minimum 3:1 R:R
        # ═══════════════════════════════════════════════════════════════
        sl = max(atr_pct * 1.0, 0.6)
        tp = max(atr_pct * 3.0, sl * 3.0)

        return self._build_signal(
            long_score, short_score, reasons, cfg,
            has_long, has_short, sl, tp, entry_price, price
        )

    # ── 5. Grid Trader ──────────────────────────────────────────────────

    def _grid_trader(self, ind: Dict, price: float,
                     has_long: bool, has_short: bool,
                     entry_price: float) -> Signal:
        """
        Systematic grid trading.
        Places positions at regular intervals from a moving average.
        Profits from oscillation around the mean.
        """
        reasons = []
        long_score = 0
        short_score = 0
        cfg = STRATEGIES["grid_trader"]

        sma21 = ind.get("sma_21")
        bb = ind.get("bb")
        atr_pct = ind.get("atr_pct") or 2.0

        if sma21 and sma21 > 0:
            deviation = (price - sma21) / sma21 * 100

            # Grid levels based on ATR
            grid_step = max(atr_pct, 1.5)

            if deviation < -grid_step * 2:
                long_score += 3
                reasons.append(f"Price {deviation:.1f}% below SMA21 — deep grid buy")
            elif deviation < -grid_step:
                long_score += 2
                reasons.append(f"Price {deviation:.1f}% below SMA21 — grid buy")
            elif deviation > grid_step * 2:
                short_score += 3
                reasons.append(f"Price +{deviation:.1f}% above SMA21 — deep grid sell")
            elif deviation > grid_step:
                short_score += 2
                reasons.append(f"Price +{deviation:.1f}% above SMA21 — grid sell")

        # BB width for market regime
        if bb:
            if bb["squeeze"]:
                reasons.append("BB squeeze — expect breakout, reduce grid size")
                long_score = max(0, long_score - 1)
                short_score = max(0, short_score - 1)

        # Additional confirmation
        rsi = ind.get("rsi")
        if rsi is not None:
            if rsi < 30:
                long_score += 1
            elif rsi > 70:
                short_score += 1

        sl = max(atr_pct * 3, 4.0)  # wider stops for grid
        tp = max(atr_pct * 1.5, 2.5)  # take profit at next grid level

        return self._build_signal(
            long_score, short_score, reasons, cfg,
            has_long, has_short, sl, tp, entry_price, price
        )

    # ── 6. Confluence Master ────────────────────────────────────────────

    def _confluence_master(self, ind: Dict, price: float,
                           has_long: bool, has_short: bool,
                           entry_price: float) -> Signal:
        """
        Institutional multi-factor approach.
        Only trades when 5+ indicators align. Higher leverage for
        overwhelming confluence. Fewest trades, highest win rate.
        """
        reasons = []
        long_signals = 0
        short_signals = 0
        total_checks = 0
        cfg = STRATEGIES["confluence_master"]

        # 1. RSI
        rsi = ind.get("rsi")
        if rsi is not None:
            total_checks += 1
            if rsi < 35:
                long_signals += 1
                reasons.append(f"✓ RSI bullish ({rsi:.0f})")
            elif rsi > 65:
                short_signals += 1
                reasons.append(f"✓ RSI bearish ({rsi:.0f})")
            else:
                reasons.append(f"○ RSI neutral ({rsi:.0f})")

        # 2. MACD
        macd = ind.get("macd")
        if macd:
            total_checks += 1
            if macd["histogram"] > 0:
                long_signals += 1
                reasons.append("✓ MACD bullish")
            else:
                short_signals += 1
                reasons.append("✓ MACD bearish")
            # Crossover bonus
            if macd["crossover"] == "bullish":
                long_signals += 1
                reasons.append("✓ MACD bullish crossover")
            elif macd["crossover"] == "bearish":
                short_signals += 1
                reasons.append("✓ MACD bearish crossover")

        # 3. Bollinger Bands
        bb = ind.get("bb")
        if bb:
            total_checks += 1
            if bb["pct_b"] < 0.2:
                long_signals += 1
                reasons.append(f"✓ BB oversold (%B={bb['pct_b']:.2f})")
            elif bb["pct_b"] > 0.8:
                short_signals += 1
                reasons.append(f"✓ BB overbought (%B={bb['pct_b']:.2f})")
            else:
                reasons.append(f"○ BB neutral (%B={bb['pct_b']:.2f})")

        # 4. EMA alignment
        ema9 = ind.get("ema_9")
        ema21 = ind.get("ema_21")
        if ema9 and ema21:
            total_checks += 1
            if ema9 > ema21:
                long_signals += 1
                reasons.append("✓ EMA bullish alignment")
            else:
                short_signals += 1
                reasons.append("✓ EMA bearish alignment")

        # 5. ADX trend strength
        adx = ind.get("adx")
        if adx:
            total_checks += 1
            if adx["trending"]:
                if adx["plus_di"] > adx["minus_di"]:
                    long_signals += 1
                    reasons.append(f"✓ ADX uptrend ({adx['adx']:.0f})")
                else:
                    short_signals += 1
                    reasons.append(f"✓ ADX downtrend ({adx['adx']:.0f})")
            else:
                reasons.append(f"○ ADX no trend ({adx['adx']:.0f})")

        # 6. Stochastic RSI
        stoch = ind.get("stoch_rsi")
        if stoch:
            total_checks += 1
            if stoch["oversold"]:
                long_signals += 1
                reasons.append(f"✓ StochRSI oversold ({stoch['k']:.0f})")
            elif stoch["overbought"]:
                short_signals += 1
                reasons.append(f"✓ StochRSI overbought ({stoch['k']:.0f})")
            else:
                reasons.append(f"○ StochRSI neutral ({stoch['k']:.0f})")

        # 7. Volume
        vol = ind.get("volume")
        if vol:
            total_checks += 1
            if vol["spike"] or vol["increasing"]:
                reasons.append("✓ Volume confirms")
                # Volume confirms the dominant direction
                if long_signals > short_signals:
                    long_signals += 1
                elif short_signals > long_signals:
                    short_signals += 1

        # 8. Momentum
        mom = ind.get("momentum", 0)
        total_checks += 1
        if mom > 2:
            long_signals += 1
            reasons.append(f"✓ Momentum bullish (+{mom:.1f}%)")
        elif mom < -2:
            short_signals += 1
            reasons.append(f"✓ Momentum bearish ({mom:.1f}%)")
        else:
            reasons.append(f"○ Momentum neutral ({mom:.1f}%)")

        # Confluence requires at least 5 signals aligned
        max_signals = max(long_signals, short_signals)
        dominant = "long" if long_signals > short_signals else "short"
        confidence = max_signals / max(total_checks, 1)

        # Only trade with overwhelming evidence
        if max_signals < 5:
            return Signal(
                "neutral", confidence, cfg.default_leverage,
                3.0, 8.0,
                f"HOLD — Insufficient confluence: {long_signals}L/{short_signals}S "
                f"out of {total_checks} checks. Need 5+. | " + "; ".join(reasons),
                {"long": long_signals, "short": short_signals, "checks": total_checks}
            )

        # Higher leverage for stronger confluence
        leverage = cfg.default_leverage
        if max_signals >= 7:
            leverage = min(cfg.max_leverage, 10)
        elif max_signals >= 6:
            leverage = min(cfg.max_leverage, 7)

        atr_pct = ind.get("atr_pct") or 3.0
        sl = max(atr_pct * 2, 3.0)
        tp = max(atr_pct * 5, 10.0)

        direction = dominant
        reasoning = (
            f"{'LONG' if direction == 'long' else 'SHORT'} — "
            f"Confluence {max_signals}/{total_checks} | " + "; ".join(reasons)
        )

        # Check existing positions for close signals
        if has_long and direction == "short":
            direction = "close_long"
            reasoning = f"CLOSE LONG — Confluence shifted bearish ({short_signals}/{total_checks}) | " + "; ".join(reasons)
        elif has_short and direction == "long":
            direction = "close_short"
            reasoning = f"CLOSE SHORT — Confluence shifted bullish ({long_signals}/{total_checks}) | " + "; ".join(reasons)

        return Signal(
            direction, confidence, leverage, sl, tp, reasoning,
            {"long": long_signals, "short": short_signals, "checks": total_checks}
        )

    # ── Shared signal builder ───────────────────────────────────────────

    def _build_signal(
        self,
        long_score: int,
        short_score: int,
        reasons: List[str],
        cfg: StrategyConfig,
        has_long: bool,
        has_short: bool,
        stop_loss_pct: float,
        take_profit_pct: float,
        entry_price: float,
        current_price: float,
    ) -> Signal:
        """Convert raw scores into a Signal object."""
        max_score = max(long_score, short_score)
        min_score_to_act = 3
        confidence = min(max_score / 10.0, 0.95)
        reasoning_str = "; ".join(reasons) if reasons else "No clear signals"

        # Scale leverage with confidence
        leverage = cfg.default_leverage
        if confidence > 0.7:
            leverage = min(cfg.max_leverage, cfg.default_leverage + 2)
        elif confidence < 0.5:
            leverage = max(1, cfg.default_leverage - 1)

        # Check for position close signals first
        if has_long:
            if short_score >= min_score_to_act and short_score > long_score:
                return Signal(
                    "close_long", confidence, leverage, stop_loss_pct, take_profit_pct,
                    f"CLOSE LONG — Bearish reversal: {reasoning_str}",
                    {"long": long_score, "short": short_score}
                )
            # Check stop-loss / take-profit on existing long
            if entry_price > 0:
                pnl_pct = (current_price - entry_price) / entry_price * 100
                if pnl_pct <= -stop_loss_pct:
                    return Signal(
                        "close_long", 0.95, leverage, stop_loss_pct, take_profit_pct,
                        f"CLOSE LONG — Stop-loss hit ({pnl_pct:.1f}%)",
                        {"pnl_pct": pnl_pct}
                    )
                if pnl_pct >= take_profit_pct:
                    return Signal(
                        "close_long", 0.90, leverage, stop_loss_pct, take_profit_pct,
                        f"CLOSE LONG — Take-profit hit (+{pnl_pct:.1f}%)",
                        {"pnl_pct": pnl_pct}
                    )

        if has_short:
            if long_score >= min_score_to_act and long_score > short_score:
                return Signal(
                    "close_short", confidence, leverage, stop_loss_pct, take_profit_pct,
                    f"CLOSE SHORT — Bullish reversal: {reasoning_str}",
                    {"long": long_score, "short": short_score}
                )
            # Check stop-loss / take-profit on existing short
            if entry_price > 0:
                pnl_pct = (entry_price - current_price) / entry_price * 100
                if pnl_pct <= -stop_loss_pct:
                    return Signal(
                        "close_short", 0.95, leverage, stop_loss_pct, take_profit_pct,
                        f"CLOSE SHORT — Stop-loss hit ({pnl_pct:.1f}%)",
                        {"pnl_pct": pnl_pct}
                    )
                if pnl_pct >= take_profit_pct:
                    return Signal(
                        "close_short", 0.90, leverage, stop_loss_pct, take_profit_pct,
                        f"CLOSE SHORT — Take-profit hit (+{pnl_pct:.1f}%)",
                        {"pnl_pct": pnl_pct}
                    )

        # New position signals
        if long_score >= min_score_to_act and long_score > short_score and not has_long:
            if confidence >= cfg.min_confidence:
                return Signal(
                    "long", confidence, leverage, stop_loss_pct, take_profit_pct,
                    f"LONG — {reasoning_str}",
                    {"long": long_score, "short": short_score}
                )

        if short_score >= min_score_to_act and short_score > long_score and not has_short:
            if confidence >= cfg.min_confidence:
                return Signal(
                    "short", confidence, leverage, stop_loss_pct, take_profit_pct,
                    f"SHORT — {reasoning_str}",
                    {"long": long_score, "short": short_score}
                )

        return Signal(
            "neutral", confidence, leverage, stop_loss_pct, take_profit_pct,
            f"HOLD — {reasoning_str} (L={long_score}/S={short_score})",
            {"long": long_score, "short": short_score}
        )


# ── Position Sizing ─────────────────────────────────────────────────────────

def calculate_position_size(
    balance: float,
    strategy_key: str,
    leverage: int,
    stop_loss_pct: float,
    current_price: float,
) -> float:
    """
    Professional risk-based position sizing.
    Risk per trade = % of capital. Position sized so that if stop-loss
    is hit, loss equals the risk amount.

    Returns: margin (USD to commit)
    """
    cfg = STRATEGIES.get(strategy_key)
    if not cfg:
        return 0.0

    risk_pct = cfg.risk_per_trade_pct / 100.0
    risk_amount = balance * risk_pct  # max USD to lose

    # margin = risk_amount / (stop_loss_pct/100 * leverage)
    # Because: loss = margin * leverage * (stop_loss_pct/100)
    if stop_loss_pct <= 0 or leverage <= 0:
        return 0.0

    margin = risk_amount / (stop_loss_pct / 100 * leverage)

    # Cap at 25% of balance per position
    margin = min(margin, balance * 0.25)

    # Minimum: 1% of balance or $1 (whichever is larger)
    min_margin = max(balance * 0.01, 1.0)
    if margin < min_margin:
        return 0.0

    return round(margin, 2)


def calculate_liquidation_price(
    entry_price: float, leverage: int, direction: str
) -> float:
    """Calculate liquidation price for a futures position."""
    if leverage <= 0:
        return 0.0
    if direction == "long":
        return entry_price * (1 - 0.9 / leverage)
    else:  # short
        return entry_price * (1 + 0.9 / leverage)
