"""Trend Rider Strategy v3.1 — optimized trend following.

8-layer signal scoring with custom exit timing:
- EMA slope bonus (+1) — rewards accelerating trends
- DI crossover (+1 in trending ADX) — early trend detection
- RSI pullback zones: 33-50 / 50-67
- Wider SL (2xATR) — reduces premature stop-outs
- Custom _check_exit_signal: lets winners run in strong trends
"""
from typing import Dict, Optional

from backend.services.strategies.base import BaseStrategy
from backend.services.strategies.models import STRATEGIES, Signal


class TrendRiderStrategy(BaseStrategy):

    def __init__(self):
        # State from last evaluate() — available to _check_exit_signal
        self._trend_up = False
        self._trend_down = False
        self._full_alignment = False

    # ── Custom exit timing ───────────────────────────────────────────

    def _check_exit_signal(
        self,
        has_long: bool,
        has_short: bool,
        long_score: int,
        short_score: int,
        entry_price: float,
        current_price: float,
        stop_loss_pct: float,
        take_profit_pct: float,
        confidence: float,
        leverage: int,
        reasoning_str: str,
        trail_pct: float,
    ) -> Optional[Signal]:
        """Trend-specific exit timing: let winners run, cut losers quickly.

        vs default (base):
        - Winners in aligned trend: require score >= 5 AND lead by +2
        - Winners out of alignment: default threshold (score >= 3)
        - Losers: default threshold (cut quickly)
        - SL/TP signal exits: always apply (safety net)
        """

        if has_long:
            pnl_pct = ((current_price - entry_price) / entry_price * 100
                       if entry_price > 0 else 0)

            # SL/TP always apply
            if entry_price > 0:
                if pnl_pct <= -stop_loss_pct:
                    return Signal(
                        "close_long", 0.95, leverage,
                        stop_loss_pct, take_profit_pct,
                        f"CLOSE LONG \u2014 Stop-loss hit ({pnl_pct:.1f}%)",
                        {"pnl_pct": pnl_pct}, trail_pct=trail_pct,
                    )
                if pnl_pct >= take_profit_pct:
                    return Signal(
                        "close_long", 0.90, leverage,
                        stop_loss_pct, take_profit_pct,
                        f"CLOSE LONG \u2014 Take-profit hit (+{pnl_pct:.1f}%)",
                        {"pnl_pct": pnl_pct}, trail_pct=trail_pct,
                    )

            # Reversal exit — adaptive threshold
            if pnl_pct > 1.0 and self._trend_up and self._full_alignment:
                # Winning + trend intact: strong conviction needed
                if short_score >= 5 and short_score > long_score + 2:
                    return Signal(
                        "close_long", confidence, leverage,
                        stop_loss_pct, take_profit_pct,
                        f"CLOSE LONG \u2014 Strong reversal (trend override): {reasoning_str}",
                        {"long": long_score, "short": short_score},
                        trail_pct=trail_pct,
                    )
            else:
                # Losing or trend broken: default threshold
                if short_score >= 3 and short_score > long_score:
                    return Signal(
                        "close_long", confidence, leverage,
                        stop_loss_pct, take_profit_pct,
                        f"CLOSE LONG \u2014 Bearish reversal: {reasoning_str}",
                        {"long": long_score, "short": short_score},
                        trail_pct=trail_pct,
                    )

        if has_short:
            pnl_pct = ((entry_price - current_price) / entry_price * 100
                       if entry_price > 0 else 0)

            if entry_price > 0:
                if pnl_pct <= -stop_loss_pct:
                    return Signal(
                        "close_short", 0.95, leverage,
                        stop_loss_pct, take_profit_pct,
                        f"CLOSE SHORT \u2014 Stop-loss hit ({pnl_pct:.1f}%)",
                        {"pnl_pct": pnl_pct}, trail_pct=trail_pct,
                    )
                if pnl_pct >= take_profit_pct:
                    return Signal(
                        "close_short", 0.90, leverage,
                        stop_loss_pct, take_profit_pct,
                        f"CLOSE SHORT \u2014 Take-profit hit (+{pnl_pct:.1f}%)",
                        {"pnl_pct": pnl_pct}, trail_pct=trail_pct,
                    )

            if pnl_pct > 1.0 and self._trend_down and self._full_alignment:
                if long_score >= 5 and long_score > short_score + 2:
                    return Signal(
                        "close_short", confidence, leverage,
                        stop_loss_pct, take_profit_pct,
                        f"CLOSE SHORT \u2014 Strong reversal (trend override): {reasoning_str}",
                        {"long": long_score, "short": short_score},
                        trail_pct=trail_pct,
                    )
            else:
                if long_score >= 3 and long_score > short_score:
                    return Signal(
                        "close_short", confidence, leverage,
                        stop_loss_pct, take_profit_pct,
                        f"CLOSE SHORT \u2014 Bullish reversal: {reasoning_str}",
                        {"long": long_score, "short": short_score},
                        trail_pct=trail_pct,
                    )

        return None

    # ── Signal scoring ───────────────────────────────────────────────

    def evaluate(self, ind: Dict, price: float,
                 has_long: bool = False, has_short: bool = False,
                 entry_price: float = 0.0) -> Signal:

        reasons: list[str] = []
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
        ema21_slope = ind.get("ema21_slope")

        # LAYER 1: Dominant Trend Filter (EMA alignment)
        self._trend_up = False
        self._trend_down = False

        if ema9 and ema21:
            if ema9 > ema21:
                self._trend_up = True
                long_score += 1
            else:
                self._trend_down = True
                short_score += 1

            if ema55:
                if ema9 > ema21 > ema55:
                    long_score += 2
                    reasons.append("EMA 9>21>55 bullish alignment")
                elif ema9 < ema21 < ema55:
                    short_score += 2
                    reasons.append("EMA 9<21<55 bearish alignment")

        # Store full alignment for exit timing
        self._full_alignment = (
            ema55 is not None and ema9 is not None and ema21 is not None
            and ((ema9 > ema21 > ema55) or (ema9 < ema21 < ema55))
        )

        # LAYER 2: EMA Slope — Trend Velocity (additive only)
        if ema21_slope is not None:
            if ema21_slope > 0.5 and self._trend_up:
                long_score += 1
                reasons.append(f"EMA21 accelerating +{ema21_slope:.1f}%")
            elif ema21_slope < -0.5 and self._trend_down:
                short_score += 1
                reasons.append(f"EMA21 accelerating {ema21_slope:.1f}%")

        # LAYER 3: ADX Trend Strength + DI Crossover
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

            if adx["trending"] or adx["strong_trend"]:
                di_cross = adx.get("di_crossover", "none")
                if di_cross == "bullish":
                    long_score += 1
                    reasons.append("+DI crossed above -DI")
                elif di_cross == "bearish":
                    short_score += 1
                    reasons.append("-DI crossed above +DI")

        # LAYER 4: Pullback Entry (RSI)
        if rsi is not None:
            if self._trend_up and 33 <= rsi <= 50:
                long_score += 1
                reasons.append(f"Uptrend pullback: RSI {rsi:.0f}")
            elif self._trend_down and 50 <= rsi <= 67:
                short_score += 1
                reasons.append(f"Downtrend bounce: RSI {rsi:.0f}")
            elif self._trend_up and rsi > 78:
                long_score = max(0, long_score - 1)
                reasons.append(f"RSI overextended {rsi:.0f}")
            elif self._trend_down and rsi < 22:
                short_score = max(0, short_score - 1)
                reasons.append(f"RSI overextended {rsi:.0f}")

        # LAYER 5: MACD Momentum
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

        # LAYER 6: Bollinger Band Pullback
        if bb:
            if self._trend_up and bb["pct_b"] < 0.30:
                long_score += 1
                reasons.append(f"Pullback to lower BB ({bb['pct_b']:.2f})")
            elif self._trend_down and bb["pct_b"] > 0.70:
                short_score += 1
                reasons.append(f"Bounce to upper BB ({bb['pct_b']:.2f})")

        # LAYER 7: StochRSI Precision Trigger
        if stoch:
            if stoch["k"] > stoch["d"] and stoch["oversold"]:
                long_score += 1
                reasons.append("StochRSI cross up from oversold")
            elif stoch["k"] < stoch["d"] and stoch["overbought"]:
                short_score += 1
                reasons.append("StochRSI cross down from overbought")

        # LAYER 8: Volume Confirmation
        if vol:
            if vol.get("spike") or vol.get("increasing"):
                if long_score > short_score:
                    long_score += 1
                    reasons.append("Volume confirms long")
                elif short_score > long_score:
                    short_score += 1
                    reasons.append("Volume confirms short")

        # COUNTER-TREND PENALTY
        if self._trend_up and short_score > long_score:
            short_score = max(0, short_score - 2)
        if self._trend_down and long_score > short_score:
            long_score = max(0, long_score - 2)

        # HARD GATE: Require full EMA alignment for new entries
        if not self._full_alignment:
            long_score = min(long_score, 2)
            short_score = min(short_score, 2)

        # STOPS: 2xATR SL, 4.5xATR TP (R:R ~ 2.25:1)
        sl = max(atr_pct * 2.0, 2.0)
        tp = max(atr_pct * 4.5, sl * 2.25)
        trail = max(atr_pct * cfg.trail_atr_mult, sl)

        return self._build_signal(
            long_score, short_score, reasons, cfg,
            has_long, has_short, sl, tp, entry_price, price, trail
        )
