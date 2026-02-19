"""
Momentum Sniper Strategy — Jesse Livermore style.

Enters on MACD crossover + volume spike + momentum confirmation.
High leverage on confirmed momentum. Lets winners run.
"""
from typing import Dict

from backend.services.strategies.base import BaseStrategy
from backend.services.strategies.models import STRATEGIES, Signal


class MomentumSniperStrategy(BaseStrategy):

    def evaluate(self, ind: Dict, price: float,
                 has_long: bool = False, has_short: bool = False,
                 entry_price: float = 0.0) -> Signal:

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
            if macd["histogram"] > 0 and macd["prev_histogram"] < macd["histogram"]:
                long_score += 1
                reasons.append("MACD histogram accelerating up")
            elif macd["histogram"] < 0 and macd["prev_histogram"] > macd["histogram"]:
                short_score += 1
                reasons.append("MACD histogram accelerating down")

        # Volume confirmation
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

        # RSI filter
        if rsi is not None:
            if rsi > 80:
                long_score = max(0, long_score - 2)
                reasons.append(f"\u26a0 RSI too high ({rsi:.0f}) \u2014 momentum exhaustion risk")
            elif rsi < 20:
                short_score = max(0, short_score - 2)
                reasons.append(f"\u26a0 RSI too low ({rsi:.0f}) \u2014 bounce risk")

        atr_pct = ind.get("atr_pct") or 3.0
        sl = max(atr_pct * 1.5, 2.0)
        tp = max(atr_pct * 4, 8.0)
        trail = max(atr_pct * cfg.trail_atr_mult, sl)

        return self._build_signal(
            long_score, short_score, reasons, cfg,
            has_long, has_short, sl, tp, entry_price, price, trail
        )
