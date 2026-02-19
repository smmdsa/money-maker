"""
Mean Reversion Strategy — Jim Simons / Renaissance style.

Buys at lower BB + RSI oversold, shorts at upper BB + RSI overbought.
Target: return to BB middle. Avoids strong trending markets.
"""
from typing import Dict

from backend.services.strategies.base import BaseStrategy
from backend.services.strategies.models import STRATEGIES, Signal


class MeanReversionStrategy(BaseStrategy):

    def evaluate(self, ind: Dict, price: float,
                 has_long: bool = False, has_short: bool = False,
                 entry_price: float = 0.0) -> Signal:

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

        # Avoid trading WITH strong trends
        adx = ind.get("adx")
        if adx and adx["strong_trend"]:
            long_score = max(0, long_score - 2)
            short_score = max(0, short_score - 2)
            reasons.append(f"\u26a0 Strong trend (ADX {adx['adx']:.0f}) \u2014 reducing confidence")

        # Mean reversion targets BB middle
        atr_pct = ind.get("atr_pct") or 2.0
        sl = max(atr_pct * 1.5, 2.0)
        tp = max(atr_pct * 2.5, 4.0)
        trail = max(atr_pct * cfg.trail_atr_mult, sl)

        return self._build_signal(
            long_score, short_score, reasons, cfg,
            has_long, has_short, sl, tp, entry_price, price, trail
        )
