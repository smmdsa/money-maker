"""
Grid Trader Strategy — Systematic grid trading.

Places positions at regular intervals from a moving average.
Profits from oscillation around the mean. Best in sideways markets.
"""
from typing import Dict

from backend.services.strategies.base import BaseStrategy
from backend.services.strategies.models import STRATEGIES, Signal


class GridTraderStrategy(BaseStrategy):

    def evaluate(self, ind: Dict, price: float,
                 has_long: bool = False, has_short: bool = False,
                 entry_price: float = 0.0) -> Signal:

        reasons = []
        long_score = 0
        short_score = 0
        cfg = STRATEGIES["grid_trader"]

        sma21 = ind.get("sma_21")
        bb = ind.get("bb")
        atr_pct = ind.get("atr_pct") or 2.0

        if sma21 and sma21 > 0:
            deviation = (price - sma21) / sma21 * 100
            grid_step = max(atr_pct, 1.5)

            if deviation < -grid_step * 2:
                long_score += 3
                reasons.append(f"Price {deviation:.1f}% below SMA21 \u2014 deep grid buy")
            elif deviation < -grid_step:
                long_score += 2
                reasons.append(f"Price {deviation:.1f}% below SMA21 \u2014 grid buy")
            elif deviation > grid_step * 2:
                short_score += 3
                reasons.append(f"Price +{deviation:.1f}% above SMA21 \u2014 deep grid sell")
            elif deviation > grid_step:
                short_score += 2
                reasons.append(f"Price +{deviation:.1f}% above SMA21 \u2014 grid sell")

        if bb:
            if bb["squeeze"]:
                reasons.append("BB squeeze \u2014 expect breakout, reduce grid size")
                long_score = max(0, long_score - 1)
                short_score = max(0, short_score - 1)

        rsi = ind.get("rsi")
        if rsi is not None:
            if rsi < 30:
                long_score += 1
            elif rsi > 70:
                short_score += 1

        sl = max(atr_pct * 3, 4.0)
        tp = max(atr_pct * 1.5, 2.5)
        trail = max(atr_pct * cfg.trail_atr_mult, sl)

        return self._build_signal(
            long_score, short_score, reasons, cfg,
            has_long, has_short, sl, tp, entry_price, price, trail
        )
