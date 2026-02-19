"""
Scalper Pro Strategy — Professional trend-following pullback scalper.

Trades WITH the short-term trend (EMA9 vs EMA21).
Enters on pullbacks (RSI dips/bounces) with BB confirmation.
ATR-adaptive stops with 3:1 R:R.
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

        # LAYER 1: Short-term Trend (EMA alignment)
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
                    long_score += 1
                    reasons.append("EMA alignment bullish (9>21>55)")
                elif ema9 < ema21 < ema55:
                    short_score += 1
                    reasons.append("EMA alignment bearish (9<21<55)")

        # LAYER 2: Pullback Entry (RSI)
        if rsi is not None:
            if trend_up and 30 <= rsi <= 48:
                long_score += 2
                reasons.append(f"Uptrend pullback: RSI {rsi:.0f}")
            elif trend_down and 52 <= rsi <= 70:
                short_score += 2
                reasons.append(f"Downtrend bounce: RSI {rsi:.0f}")
            elif rsi < 25:
                long_score += 2
                reasons.append(f"Extreme oversold: RSI {rsi:.0f}")
            elif rsi > 75:
                short_score += 2
                reasons.append(f"Extreme overbought: RSI {rsi:.0f}")

        # LAYER 3: Bollinger Band position
        if bb:
            if trend_up and bb["pct_b"] < 0.30:
                long_score += 1
                reasons.append(f"Price near lower BB ({bb['pct_b']:.2f})")
            elif trend_down and bb["pct_b"] > 0.70:
                short_score += 1
                reasons.append(f"Price near upper BB ({bb['pct_b']:.2f})")
            if bb["pct_b"] < 0.05:
                long_score += 1
                reasons.append("BB extreme low")
            elif bb["pct_b"] > 0.95:
                short_score += 1
                reasons.append("BB extreme high")

        # LAYER 4: MACD Momentum Confirmation
        if macd:
            hist = macd.get("histogram", 0)
            crossover = macd.get("crossover", "none")
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

        # LAYER 5: Stochastic RSI crossover
        if stoch:
            if stoch["k"] > stoch["d"] and stoch["oversold"]:
                long_score += 1
                reasons.append("StochRSI cross up from oversold")
            elif stoch["k"] < stoch["d"] and stoch["overbought"]:
                short_score += 1
                reasons.append("StochRSI cross down from overbought")

        # LAYER 6: Volume confirmation
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

        # STOPS: ATR-adaptive 3:1 R:R
        sl = max(atr_pct * 1.0, 0.6)
        tp = max(atr_pct * 3.0, sl * 3.0)
        trail = max(atr_pct * cfg.trail_atr_mult, sl)

        return self._build_signal(
            long_score, short_score, reasons, cfg,
            has_long, has_short, sl, tp, entry_price, price, trail
        )
