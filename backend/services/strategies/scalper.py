"""
Scalper Pro Strategy — Per-Timeframe Optimized Scalper.

Each timeframe (1m, 3m, 5m, 15m, 1h) uses individually tuned:
  • Scoring thresholds (RSI zones, EMA spread, momentum)
  • SL/TP multipliers (wider for noisy TFs, tighter for stable TFs)
  • Counter-trend penalties (stronger for lower TFs)
  • Entry requirements (higher min_score for noisier TFs)
  • Trailing stop control (disabled for 1m/3m, moderate for 5m+)

World-class scalping best practices applied:
  • EMA 3-line alignment for trend context (not just 9 vs 21)
  • Leading indicators (BB extremes, StochRSI) weighted more than lagging
  • ADX trend-strength filter for trending entries
  • Volume confirmation required for noisy timeframes
  • Counter-trend penalty prevents fighting strong trends
  • Wider stops to survive market noise
  • Lower leverage to reduce commission drag
"""
from typing import Dict

from backend.services.strategies.base import BaseStrategy
from backend.services.strategies.models import STRATEGIES, Signal


# ── Per-timeframe tuning parameters ─────────────────────────────────────────

TIMEFRAME_PARAMS: Dict[str, Dict] = {
    "scalper_1m": {
        # Entry quality
        "min_score": 5,
        "conf_divisor": 14.0,
        "min_score_margin": 2,       # long-short gap required
        # EMA
        "ema_spread_threshold": 0.04,
        # RSI zones
        "rsi_oversold": 22, "rsi_overbought": 78,
        "rsi_pullback_range": (35, 47),
        "rsi_bounce_range": (53, 65),
        # Bollinger
        "bb_entry_low": 0.15, "bb_entry_high": 0.85,
        "bb_extreme_low": 0.05, "bb_extreme_high": 0.95,
        # Momentum
        "momentum_threshold": 0.15,
        # Risk management
        "sl_atr_mult": 1.5, "tp_atr_mult": 2.25,
        "sl_min_pct": 0.15, "tp_min_rr": 1.5,
        # Trend filter
        "counter_trend_penalty": 3,
        "require_volume": True,
        # Trailing: trail < 0 signals to backtester to disable
        "disable_trailing": True,
    },
    "scalper_3m": {
        "min_score": 5,
        "conf_divisor": 14.0,
        "min_score_margin": 2,
        "ema_spread_threshold": 0.06,
        "rsi_oversold": 24, "rsi_overbought": 76,
        "rsi_pullback_range": (36, 48),
        "rsi_bounce_range": (52, 64),
        "bb_entry_low": 0.17, "bb_entry_high": 0.83,
        "bb_extreme_low": 0.05, "bb_extreme_high": 0.95,
        "momentum_threshold": 0.20,
        "sl_atr_mult": 1.3, "tp_atr_mult": 2.6,
        "sl_min_pct": 0.20, "tp_min_rr": 2.0,
        "counter_trend_penalty": 3,
        "require_volume": True,
        "disable_trailing": True,
    },
    "scalper_5m": {
        "min_score": 4,
        "conf_divisor": 12.0,
        "min_score_margin": 2,
        "ema_spread_threshold": 0.08,
        "rsi_oversold": 25, "rsi_overbought": 75,
        "rsi_pullback_range": (35, 50),
        "rsi_bounce_range": (50, 65),
        "bb_entry_low": 0.20, "bb_entry_high": 0.80,
        "bb_extreme_low": 0.05, "bb_extreme_high": 0.95,
        "momentum_threshold": 0.25,
        "sl_atr_mult": 1.2, "tp_atr_mult": 2.4,
        "sl_min_pct": 0.25, "tp_min_rr": 2.0,
        "counter_trend_penalty": 2,
        "require_volume": False,
        "disable_trailing": False,
    },
    "scalper_15m": {
        "min_score": 4,
        "conf_divisor": 12.0,
        "min_score_margin": 2,
        "ema_spread_threshold": 0.10,
        "rsi_oversold": 27, "rsi_overbought": 73,
        "rsi_pullback_range": (35, 50),
        "rsi_bounce_range": (50, 65),
        "bb_entry_low": 0.22, "bb_entry_high": 0.78,
        "bb_extreme_low": 0.08, "bb_extreme_high": 0.92,
        "momentum_threshold": 0.30,
        "sl_atr_mult": 1.2, "tp_atr_mult": 3.0,
        "sl_min_pct": 0.35, "tp_min_rr": 2.5,
        "counter_trend_penalty": 2,
        "require_volume": False,
        "disable_trailing": False,
    },
    "scalper": {  # 1h
        "min_score": 4,
        "conf_divisor": 12.0,
        "min_score_margin": 2,
        "ema_spread_threshold": 0.12,
        "rsi_oversold": 28, "rsi_overbought": 72,
        "rsi_pullback_range": (35, 52),
        "rsi_bounce_range": (48, 65),
        "bb_entry_low": 0.22, "bb_entry_high": 0.78,
        "bb_extreme_low": 0.08, "bb_extreme_high": 0.92,
        "momentum_threshold": 0.35,
        "sl_atr_mult": 1.2, "tp_atr_mult": 3.0,
        "sl_min_pct": 0.40, "tp_min_rr": 2.5,
        "counter_trend_penalty": 1,
        "require_volume": False,
        "disable_trailing": False,
    },
}


class ScalperStrategy(BaseStrategy):

    def __init__(self, strategy_key: str = "scalper"):
        """strategy_key selects config + timeframe params."""
        self.strategy_key = strategy_key

    def evaluate(self, ind: Dict, price: float,
                 has_long: bool = False, has_short: bool = False,
                 entry_price: float = 0.0) -> Signal:

        reasons: list[str] = []
        long_score = 0
        short_score = 0
        cfg = STRATEGIES[self.strategy_key]
        p = TIMEFRAME_PARAMS.get(self.strategy_key, TIMEFRAME_PARAMS["scalper"])

        # ── Extract indicators ───────────────────────────────────────────
        rsi = ind.get("rsi")
        bb = ind.get("bb")
        stoch = ind.get("stoch_rsi")
        mom = ind.get("momentum", 0)
        ema_s = ind.get("ema_9")     # short EMA (period varies per TF)
        ema_m = ind.get("ema_21")    # mid EMA
        ema_l = ind.get("ema_55")    # long EMA
        atr_pct = ind.get("atr_pct") or 2.0
        macd = ind.get("macd")
        vol = ind.get("volume")
        adx_data = ind.get("adx")

        # ══════════════════════════════════════════════════════════════════
        # LAYER 1: EMA 3-Line Alignment (0-3 points/side)
        # Full alignment (S > M > L): +3  Partial (S > M): +2  Weak: +1
        # ══════════════════════════════════════════════════════════════════
        ema_bullish = False
        ema_bearish = False

        if ema_s and ema_m and ema_l:
            if ema_s > ema_m > ema_l:
                ema_bullish = True
                long_score += 3
                reasons.append("EMA full bullish alignment (S>M>L)")
            elif ema_s < ema_m < ema_l:
                ema_bearish = True
                short_score += 3
                reasons.append("EMA full bearish alignment (S<M<L)")
            elif ema_s > ema_m:
                ema_bullish = True
                spread = abs(ema_s - ema_m) / ema_m * 100 if ema_m > 0 else 0
                if spread > p["ema_spread_threshold"]:
                    long_score += 2
                    reasons.append(f"EMA bullish S>M, spread {spread:.3f}%")
                else:
                    long_score += 1
            elif ema_s < ema_m:
                ema_bearish = True
                spread = abs(ema_s - ema_m) / ema_m * 100 if ema_m > 0 else 0
                if spread > p["ema_spread_threshold"]:
                    short_score += 2
                    reasons.append(f"EMA bearish S<M, spread {spread:.3f}%")
                else:
                    short_score += 1

        # ══════════════════════════════════════════════════════════════════
        # LAYER 2: RSI — Extremes (leading) + Pullbacks (confluence)
        # Extreme oversold/overbought: +2   Pullback in trend: +1
        # ══════════════════════════════════════════════════════════════════
        if rsi is not None:
            if rsi < p["rsi_oversold"]:
                long_score += 2
                reasons.append(f"RSI oversold ({rsi:.0f})")
            elif rsi > p["rsi_overbought"]:
                short_score += 2
                reasons.append(f"RSI overbought ({rsi:.0f})")
            else:
                pb_lo, pb_hi = p["rsi_pullback_range"]
                bn_lo, bn_hi = p["rsi_bounce_range"]
                if ema_bullish and pb_lo <= rsi <= pb_hi:
                    long_score += 1
                    reasons.append(f"RSI pullback in uptrend ({rsi:.0f})")
                elif ema_bearish and bn_lo <= rsi <= bn_hi:
                    short_score += 1
                    reasons.append(f"RSI bounce in downtrend ({rsi:.0f})")

        # ══════════════════════════════════════════════════════════════════
        # LAYER 3: Bollinger Bands — Extremes + Squeeze
        # Extreme: +2   Entry zone: +1   Squeeze in trend: +1
        # ══════════════════════════════════════════════════════════════════
        if bb:
            pct_b = bb["pct_b"]
            if pct_b < p["bb_extreme_low"]:
                long_score += 2
                reasons.append(f"BB extreme low ({pct_b:.2f})")
            elif pct_b > p["bb_extreme_high"]:
                short_score += 2
                reasons.append(f"BB extreme high ({pct_b:.2f})")
            elif pct_b < p["bb_entry_low"]:
                long_score += 1
                reasons.append(f"Price near lower BB ({pct_b:.2f})")
            elif pct_b > p["bb_entry_high"]:
                short_score += 1
                reasons.append(f"Price near upper BB ({pct_b:.2f})")

            if bb.get("squeeze"):
                if ema_bullish:
                    long_score += 1
                    reasons.append("BB squeeze — bullish breakout expected")
                elif ema_bearish:
                    short_score += 1
                    reasons.append("BB squeeze — bearish breakout expected")

        # ══════════════════════════════════════════════════════════════════
        # LAYER 4: MACD — Crossover + Histogram
        # Crossover: +2   Histogram acceleration: +1
        # ══════════════════════════════════════════════════════════════════
        if macd:
            crossover = macd.get("crossover", "none")
            hist = macd.get("histogram", 0)
            prev_hist = macd.get("prev_histogram", 0)

            if crossover == "bullish":
                long_score += 2
                reasons.append("MACD bullish crossover")
            elif crossover == "bearish":
                short_score += 2
                reasons.append("MACD bearish crossover")

            if hist > 0 and prev_hist > 0 and hist > prev_hist:
                long_score += 1
                reasons.append("MACD histogram accelerating ↑")
            elif hist < 0 and prev_hist < 0 and hist < prev_hist:
                short_score += 1
                reasons.append("MACD histogram accelerating ↓")

        # ══════════════════════════════════════════════════════════════════
        # LAYER 5: Stochastic RSI — Cross from extreme (leading)
        # Extreme + cross: +2   Mid-zone alignment: +1
        # ══════════════════════════════════════════════════════════════════
        if stoch:
            k, d = stoch["k"], stoch["d"]
            if stoch["oversold"] and k > d:
                long_score += 2
                reasons.append("StochRSI bullish cross from oversold")
            elif stoch["overbought"] and k < d:
                short_score += 2
                reasons.append("StochRSI bearish cross from overbought")
            elif 20 < k < 80:
                if k > d and ema_bullish:
                    long_score += 1
                elif k < d and ema_bearish:
                    short_score += 1

        # ══════════════════════════════════════════════════════════════════
        # LAYER 6: ADX Trend Strength (0-1 point/side)
        # ADX trending + DI alignment: +1
        # ══════════════════════════════════════════════════════════════════
        if adx_data and adx_data.get("trending"):
            if adx_data["plus_di"] > adx_data["minus_di"]:
                long_score += 1
                reasons.append(f"ADX trending bullish ({adx_data['adx']:.0f})")
            else:
                short_score += 1
                reasons.append(f"ADX trending bearish ({adx_data['adx']:.0f})")

        # ══════════════════════════════════════════════════════════════════
        # LAYER 7: Momentum (0-1 point/side)
        # ══════════════════════════════════════════════════════════════════
        if abs(mom) > p["momentum_threshold"]:
            if mom > 0:
                long_score += 1
                reasons.append(f"Momentum +{mom:.2f}%")
            else:
                short_score += 1
                reasons.append(f"Momentum {mom:.2f}%")

        # ══════════════════════════════════════════════════════════════════
        # LAYER 8: Volume Confirmation (0-2 points)
        # Spike: +2   Increasing: +1
        # ══════════════════════════════════════════════════════════════════
        has_volume = False
        if vol:
            if vol.get("spike"):
                has_volume = True
                if long_score > short_score:
                    long_score += 2
                    reasons.append("Volume spike confirms")
                elif short_score > long_score:
                    short_score += 2
                    reasons.append("Volume spike confirms")
            elif vol.get("increasing"):
                has_volume = True
                if long_score > short_score:
                    long_score += 1
                elif short_score > long_score:
                    short_score += 1

        # ══════════════════════════════════════════════════════════════════
        # PENALTY: Counter-trend (fighting the EMA alignment)
        # ══════════════════════════════════════════════════════════════════
        penalty = p["counter_trend_penalty"]
        has_rsi_extreme = (rsi is not None and
                           (rsi < p["rsi_oversold"] or rsi > p["rsi_overbought"]))

        # Don't penalize mean-reversion trades at RSI extremes
        if not has_rsi_extreme:
            if ema_bearish and long_score > short_score:
                long_score = max(0, long_score - penalty)
                reasons.append(f"Counter-trend penalty (long vs bearish EMA, -{penalty})")
            elif ema_bullish and short_score > long_score:
                short_score = max(0, short_score - penalty)
                reasons.append(f"Counter-trend penalty (short vs bullish EMA, -{penalty})")

        # ══════════════════════════════════════════════════════════════════
        # VOLUME GATE: For noisy TFs, halve score without volume confirm
        # ══════════════════════════════════════════════════════════════════
        if p["require_volume"] and not has_volume:
            long_score = long_score // 2
            short_score = short_score // 2

        # ══════════════════════════════════════════════════════════════════
        # STOPS: ATR-adaptive, per-timeframe R:R
        # ══════════════════════════════════════════════════════════════════
        sl = max(atr_pct * p["sl_atr_mult"], p["sl_min_pct"])
        tp = max(atr_pct * p["tp_atr_mult"], sl * p["tp_min_rr"])

        # Trailing stop control
        if p.get("disable_trailing"):
            trail = -1.0  # Sentinel: backtester will set trail_pct=0
        else:
            trail = max(atr_pct * cfg.trail_atr_mult, sl)

        return self._build_signal(
            long_score, short_score, reasons, cfg,
            has_long, has_short, sl, tp, entry_price, price, trail,
            min_score_override=p["min_score"],
            confidence_divisor=p["conf_divisor"],
            min_score_margin=p["min_score_margin"],
        )
