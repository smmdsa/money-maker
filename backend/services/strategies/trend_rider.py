"""
Trend Rider Strategy — Paul Tudor Jones / Trend Following v2.

Only trades WITH the dominant trend (EMA 9>21>55).
Waits for pullbacks, uses ADX for trend strength, MACD as catalyst.
ATR-adaptive stops with 3:1 R:R.
"""
from typing import Dict

from backend.services.strategies.base import BaseStrategy
from backend.services.strategies.models import STRATEGIES, Signal


class TrendRiderStrategy(BaseStrategy):

    def evaluate(self, ind: Dict, price: float,
                 has_long: bool = False, has_short: bool = False,
                 entry_price: float = 0.0) -> Signal:

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
        atr_pct = ind.get("atr_pct") or 3.0

        # LAYER 1: Dominant Trend Filter (EMA alignment)
        trend_up = False
        trend_down = False

        if ema9 and ema21:
            if ema9 > ema21:
                trend_up = True
                long_score += 1
            else:
                trend_down = True
                short_score += 1

            if ema55:
                if ema9 > ema21 > ema55:
                    long_score += 2
                    reasons.append("EMA 9>21>55 bullish alignment")
                elif ema9 < ema21 < ema55:
                    short_score += 2
                    reasons.append("EMA 9<21<55 bearish alignment")

        # LAYER 2: ADX Trend Strength
        if adx:
            if adx["strong_trend"]:
                if adx["plus_di"] > adx["minus_di"]:
                    long_score += 2
                    reasons.append(f"Strong uptrend ADX {adx['adx']:.0f}")
                else:
                    short_score += 2
                    reasons.append(f"Strong downtrend ADX {adx['adx']:.0f}")
            elif adx["trending"]:
                if adx["plus_di"] > adx["minus_di"]:
                    long_score += 1
                else:
                    short_score += 1
                reasons.append(f"Moderate trend ADX {adx['adx']:.0f}")
            else:
                long_score = max(0, long_score - 2)
                short_score = max(0, short_score - 2)
                reasons.append(f"Weak trend ADX {adx['adx']:.0f} \u2014 reduced")

        # LAYER 3: Pullback Entry (RSI)
        if rsi is not None:
            if trend_up and 35 <= rsi <= 48:
                long_score += 2
                reasons.append(f"Uptrend pullback: RSI {rsi:.0f}")
            elif trend_down and 52 <= rsi <= 65:
                short_score += 2
                reasons.append(f"Downtrend bounce: RSI {rsi:.0f}")
            elif trend_up and rsi > 72:
                long_score = max(0, long_score - 1)
                reasons.append(f"RSI overextended {rsi:.0f} \u2014 avoid chasing")
            elif trend_down and rsi < 28:
                short_score = max(0, short_score - 1)
                reasons.append(f"RSI overextended {rsi:.0f} \u2014 avoid chasing")

        # LAYER 4: MACD Momentum Catalyst
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

        # LAYER 5: BB Pullback Timing + StochRSI
        if bb:
            if trend_up and bb["pct_b"] < 0.30:
                long_score += 1
                reasons.append(f"Price near lower BB ({bb['pct_b']:.2f}) \u2014 pullback support")
            elif trend_down and bb["pct_b"] > 0.70:
                short_score += 1
                reasons.append(f"Price near upper BB ({bb['pct_b']:.2f}) \u2014 bounce resistance")

        if stoch:
            if stoch["k"] > stoch["d"] and stoch["oversold"]:
                long_score += 1
                reasons.append("StochRSI cross up from oversold")
            elif stoch["k"] < stoch["d"] and stoch["overbought"]:
                short_score += 1
                reasons.append("StochRSI cross down from overbought")

        # LAYER 6: Volume Confirmation
        if vol and vol.get("increasing"):
            if long_score > short_score:
                long_score += 1
                reasons.append("Volume increasing")
            elif short_score > long_score:
                short_score += 1
                reasons.append("Volume increasing")

        # COUNTER-TREND PENALTY
        if trend_up and short_score > long_score:
            short_score = max(0, short_score - 2)
        if trend_down and long_score > short_score:
            long_score = max(0, long_score - 2)

        # HARD GATE: Require full EMA alignment for new entries
        full_alignment = (ema55 is not None and ema9 is not None and ema21 is not None
                          and ((ema9 > ema21 > ema55) or (ema9 < ema21 < ema55)))
        if not full_alignment:
            long_score = min(long_score, 2)
            short_score = min(short_score, 2)

        # STOPS: ATR-adaptive 3:1 R:R
        sl = max(atr_pct * 1.5, 1.5)
        tp = max(atr_pct * 4.5, sl * 3.0)
        trail = max(atr_pct * cfg.trail_atr_mult, sl)

        return self._build_signal(
            long_score, short_score, reasons, cfg,
            has_long, has_short, sl, tp, entry_price, price, trail
        )
