"""
Scalper Pro Strategy — Aggressive short-term scalper.

Designed to generate frequent trades using short-timeframe candles.
Enters on micro-trends, pullbacks, momentum bursts, and mean-reversion extremes.
Lower entry threshold (score >= 2) for high trade frequency.
ATR-adaptive stops with 2:1 R:R (tighter than swing strategies).
Used for all scalper variants (1h, 1m, 3m, 5m, 15m).
"""
from typing import Dict

from backend.services.strategies.base import BaseStrategy
from backend.services.strategies.models import STRATEGIES, Signal


class ScalperStrategy(BaseStrategy):

    def __init__(self, strategy_key: str = "scalper"):
        """strategy_key selects the correct config (scalper, scalper_1m, etc.)."""
        self.strategy_key = strategy_key

    def evaluate(self, ind: Dict, price: float,
                 has_long: bool = False, has_short: bool = False,
                 entry_price: float = 0.0) -> Signal:

        reasons = []
        long_score = 0
        short_score = 0
        cfg = STRATEGIES[self.strategy_key]

        rsi = ind.get("rsi")
        bb = ind.get("bb")
        stoch = ind.get("stoch_rsi")
        mom = ind.get("momentum", 0)
        ema9 = ind.get("ema_9")
        ema21 = ind.get("ema_21")
        ema55 = ind.get("ema_55")
        atr_pct = ind.get("atr_pct") or 2.0
        macd = ind.get("macd")
        vol = ind.get("volume")

        # ── LAYER 1: Micro-Trend (EMA 9 vs 21) ──────────────────────────
        trend_up = False
        trend_down = False

        if ema9 and ema21:
            ema_spread = abs(ema9 - ema21) / ema21 * 100 if ema21 > 0 else 0
            if ema9 > ema21:
                trend_up = True
                long_score += 1
                if ema_spread > 0.1:  # clear separation
                    long_score += 1
                    reasons.append(f"EMA9>21 spread {ema_spread:.2f}%")
            else:
                trend_down = True
                short_score += 1
                if ema_spread > 0.1:
                    short_score += 1
                    reasons.append(f"EMA9<21 spread {ema_spread:.2f}%")

        # ── LAYER 2: RSI — Multiple zones, not just pullbacks ─────────────
        if rsi is not None:
            # Trend-with-pullback entries
            if trend_up and 35 <= rsi <= 55:
                long_score += 1
                reasons.append(f"RSI pullback in uptrend: {rsi:.0f}")
            elif trend_down and 45 <= rsi <= 65:
                short_score += 1
                reasons.append(f"RSI bounce in downtrend: {rsi:.0f}")

            # Mean-reversion extremes (works even without trend)
            if rsi < 30:
                long_score += 2
                reasons.append(f"RSI oversold: {rsi:.0f}")
            elif rsi > 70:
                short_score += 2
                reasons.append(f"RSI overbought: {rsi:.0f}")

            # Mild oversold/overbought
            if rsi < 40 and not trend_down:
                long_score += 1
            elif rsi > 60 and not trend_up:
                short_score += 1

        # ── LAYER 3: Bollinger Band — Position + Squeeze ─────────────────
        if bb:
            pct_b = bb["pct_b"]
            squeeze = bb.get("squeeze", False)

            if pct_b < 0.20:
                long_score += 1
                reasons.append(f"Price at lower BB ({pct_b:.2f})")
            elif pct_b > 0.80:
                short_score += 1
                reasons.append(f"Price at upper BB ({pct_b:.2f})")

            if pct_b < 0.05:
                long_score += 1
                reasons.append("BB extreme low — bounce expected")
            elif pct_b > 0.95:
                short_score += 1
                reasons.append("BB extreme high — rejection expected")

            # Squeeze breakout anticipation
            if squeeze:
                if trend_up:
                    long_score += 1
                    reasons.append("BB squeeze — bullish breakout expected")
                elif trend_down:
                    short_score += 1
                    reasons.append("BB squeeze — bearish breakout expected")

        # ── LAYER 4: MACD — Crossover + Histogram Momentum ──────────────
        if macd:
            hist = macd.get("histogram", 0)
            prev_hist = macd.get("prev_histogram", 0)
            crossover = macd.get("crossover", "none")

            if crossover == "bullish":
                long_score += 2
                reasons.append("MACD bullish crossover")
            elif crossover == "bearish":
                short_score += 2
                reasons.append("MACD bearish crossover")

            # Histogram acceleration (momentum building)
            if hist > 0 and prev_hist > 0 and hist > prev_hist:
                long_score += 1
                reasons.append("MACD histogram accelerating up")
            elif hist < 0 and prev_hist < 0 and hist < prev_hist:
                short_score += 1
                reasons.append("MACD histogram accelerating down")

        # ── LAYER 5: Stochastic RSI — Crosses ───────────────────────────
        if stoch:
            k, d = stoch["k"], stoch["d"]
            if k > d and stoch["oversold"]:
                long_score += 1
                reasons.append("StochRSI cross up from oversold")
            elif k < d and stoch["overbought"]:
                short_score += 1
                reasons.append("StochRSI cross down from overbought")

            # Mid-zone momentum
            if k > d and 20 < k < 80:
                long_score += 1
            elif k < d and 20 < k < 80:
                short_score += 1

        # ── LAYER 6: Momentum (price vs SMA7) ───────────────────────────
        if mom != 0:
            if mom > 0.3:
                long_score += 1
                reasons.append(f"Momentum +{mom:.1f}%")
            elif mom < -0.3:
                short_score += 1
                reasons.append(f"Momentum {mom:.1f}%")

        # ── LAYER 7: Volume confirmation ─────────────────────────────────
        if vol:
            if vol.get("spike"):
                # Volume spike = strong confirmation
                if long_score > short_score:
                    long_score += 1
                    reasons.append("Volume spike confirms")
                elif short_score > long_score:
                    short_score += 1
                    reasons.append("Volume spike confirms")
            elif vol.get("increasing"):
                if long_score > short_score:
                    long_score += 1
                elif short_score > long_score:
                    short_score += 1

        # ── NO COUNTER-TREND PENALTY (scalping trades both directions) ───

        # ── STOPS: ATR-adaptive with 2:1 R:R for scalping ───────────────
        sl = max(atr_pct * 0.8, 0.3)       # tighter SL for scalping
        tp = max(atr_pct * 1.6, sl * 2.0)   # 2:1 R:R minimum
        trail = max(atr_pct * cfg.trail_atr_mult, sl)

        return self._build_signal(
            long_score, short_score, reasons, cfg,
            has_long, has_short, sl, tp, entry_price, price, trail
        )
