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
        # ── Entry quality ───────────────────────────────────────────
        # Higher min_score + soft ADX = only very strong confluence entries.
        "min_score": 7,
        "conf_divisor": 12.0,
        "min_score_margin": 3,
        # EMA: capped scores — 1m alignment flickers every other candle
        "ema_spread_threshold": 0.04,
        "ema_full_score": 2,
        "ema_partial_score": 1,
        # RSI zones — tighter extremes = only clear signals
        "rsi_oversold": 20, "rsi_overbought": 80,
        "rsi_pullback_range": (35, 47),
        "rsi_bounce_range": (53, 65),
        # Bollinger
        "bb_entry_low": 0.12, "bb_entry_high": 0.88,
        "bb_extreme_low": 0.05, "bb_extreme_high": 0.95,
        # Momentum
        "momentum_threshold": 0.15,
        # ── Risk management (very wide stops → survive 1m noise) ────
        "sl_atr_mult": 2.5, "tp_atr_mult": 6.0,
        "sl_min_pct": 0.35, "tp_min_rr": 2.5,
        # ── Filters ─────────────────────────────────────────────────
        "counter_trend_penalty": 1,
        "require_volume": False,
        # Soft ADX: 1m ADX (10-period = 10 min) is too noisy for hard gate
        "require_adx_trending": False,
        "adx_soft_dampen": 4,
        "leading_conflict_penalty": 4,
        "disable_squeeze_score": True,
        "squeeze_requires_volume": True,
        "disable_trailing": True,
        # OFI defensive only, no EMA slope bonus (bonuses break scalpers)
        "ofi_against_penalty": 2,
        "ema_slope_bonus": 0,
        # 120 × 1m = 2hr cooldown after SL
        "cooldown_candles": 120,
        # MTF — defensive only
        "mtf_trend_bonus": 0,
        "mtf_against_penalty": 3,
        "mtf_sr_proximity_pct": 0.15,
        "mtf_sr_penalty": 2,
        "mtf_require_trend": False,
    },
    "scalper_3m": {
        # ── Entry quality ───────────────────────────────────────────
        "min_score": 7,
        "conf_divisor": 12.0,
        "min_score_margin": 3,
        "ema_spread_threshold": 0.06,
        "ema_full_score": 2,
        "ema_partial_score": 1,
        "rsi_oversold": 22, "rsi_overbought": 78,
        "rsi_pullback_range": (36, 48),
        "rsi_bounce_range": (52, 64),
        "bb_entry_low": 0.15, "bb_entry_high": 0.85,
        "bb_extreme_low": 0.05, "bb_extreme_high": 0.95,
        "momentum_threshold": 0.20,
        # ── Risk management (wider stops) ──────────────────────────
        "sl_atr_mult": 2.0, "tp_atr_mult": 5.0,
        "sl_min_pct": 0.40, "tp_min_rr": 2.5,
        # ── Filters ─────────────────────────────────────────────────
        "counter_trend_penalty": 1,
        "require_volume": False,
        # Soft ADX: 3m ADX (10-period = 30 min) can whipsaw
        "require_adx_trending": False,
        "adx_soft_dampen": 3,
        "leading_conflict_penalty": 4,
        "disable_squeeze_score": True,
        "squeeze_requires_volume": True,
        "disable_trailing": True,
        # OFI defensive only, no EMA slope bonus
        "ofi_against_penalty": 1,
        "ema_slope_bonus": 0,
        # 40 × 3m = 2hr cooldown after SL
        "cooldown_candles": 40,
        # MTF — defensive
        "mtf_trend_bonus": 0,
        "mtf_against_penalty": 3,
        "mtf_sr_proximity_pct": 0.15,
        "mtf_sr_penalty": 1,
        "mtf_require_trend": False,
    },
    "scalper_5m": {
        # ── Entry quality ───────────────────────────────────────────
        "min_score": 6,
        "conf_divisor": 12.0,
        "min_score_margin": 3,
        "ema_spread_threshold": 0.08,
        "ema_full_score": 2,
        "ema_partial_score": 1,
        "rsi_oversold": 25, "rsi_overbought": 75,
        "rsi_pullback_range": (35, 50),
        "rsi_bounce_range": (50, 65),
        "bb_entry_low": 0.18, "bb_entry_high": 0.82,
        "bb_extreme_low": 0.05, "bb_extreme_high": 0.95,
        "momentum_threshold": 0.25,
        # ── Risk management ─────────────────────────────────────────
        "sl_atr_mult": 1.6, "tp_atr_mult": 3.8,
        "sl_min_pct": 0.40, "tp_min_rr": 2.3,
        # ── Filters ─────────────────────────────────────────────────
        "counter_trend_penalty": 1,
        "require_volume": False,
        # Hard ADX: 5m works best with hard gate (proven in V2)
        "require_adx_trending": True,
        "leading_conflict_penalty": 4,
        "disable_squeeze_score": True,
        "squeeze_requires_volume": True,
        "disable_trailing": True,
        # OFI defensive only, no EMA slope bonus
        "ofi_against_penalty": 1,
        "ema_slope_bonus": 0,
        # 20 × 5m = 100 min cooldown after SL
        "cooldown_candles": 20,
        # MTF — defensive
        "mtf_trend_bonus": 0,
        "mtf_against_penalty": 2,
        "mtf_sr_proximity_pct": 0.25,
        "mtf_sr_penalty": 2,
        "mtf_require_trend": False,
    },
    "scalper_15m": {
        # Entry — high bar ensures only quality setups
        "min_score": 6,
        "conf_divisor": 12.0,
        "min_score_margin": 3,
        "ema_spread_threshold": 0.08,
        # EMA scoring: capped for 15m because alignment flickers constantly
        "ema_full_score": 2,
        "ema_partial_score": 1,
        # RSI — standard zones, wider pullback regions
        "rsi_oversold": 25, "rsi_overbought": 75,
        "rsi_pullback_range": (33, 48),
        "rsi_bounce_range": (52, 67),
        # BB — slightly wider entry capture
        "bb_entry_low": 0.18, "bb_entry_high": 0.82,
        "bb_extreme_low": 0.06, "bb_extreme_high": 0.94,
        "momentum_threshold": 0.25,
        # Risk — moderate stops, good fee-adjusted R:R
        "sl_atr_mult": 1.6, "tp_atr_mult": 3.8,
        "sl_min_pct": 0.50, "tp_min_rr": 2.3,
        # Trend filter — lighter penalty (15m oscillates more)
        "counter_trend_penalty": 1,
        "require_volume": False,
        # Require ADX trending state for trend-following entries
        # Mean-reversion (RSI extreme) entries bypass this gate
        "require_adx_trending": True,
        # Leading indicator conflict: heavy penalty if BB/RSI/StochRSI
        # point opposite to entry direction (prevents worst trades)
        "leading_conflict_penalty": 4,
        # Disable BB squeeze scoring — it fires constantly on 15m and
        # has near-zero predictive value at this timeframe
        "disable_squeeze_score": True,
        # BB squeeze bonus only with volume confirmation (if enabled)
        "squeeze_requires_volume": True,
        "disable_trailing": True,
        # OFI + EMA slope DISABLED for 15m — bonuses break the golden config
        "ofi_against_penalty": 0,
        "ema_slope_bonus": 0,
        # 10 × 15m = 150 min cooldown after SL
        "cooldown_candles": 10,
        # MTF — disabled: 15m's native filters (ADX gate, leading conflict,
        # counter-trend penalty) are already sufficient for this timeframe.
        # Enabling MTF penalties here costs BTC 30d: +16% → +4%.
        "mtf_trend_bonus": 0,
        "mtf_against_penalty": 0,
        "mtf_sr_proximity_pct": 0.0,
        "mtf_sr_penalty": 0,
        "mtf_require_trend": False,
    },
    "scalper": {  # 1h — soft ADX dampen + OFI + slope
        # ── Entry quality ───────────────────────────────────────────
        "min_score": 6,
        "conf_divisor": 12.0,
        "min_score_margin": 3,
        "ema_spread_threshold": 0.12,
        "ema_full_score": 2,
        "ema_partial_score": 1,
        "rsi_oversold": 28, "rsi_overbought": 72,
        "rsi_pullback_range": (35, 52),
        "rsi_bounce_range": (48, 65),
        "bb_entry_low": 0.22, "bb_entry_high": 0.78,
        "bb_extreme_low": 0.08, "bb_extreme_high": 0.92,
        "momentum_threshold": 0.35,
        # ── Risk management (wider stops for 1h) ───────────────────
        "sl_atr_mult": 1.6, "tp_atr_mult": 4.0,
        "sl_min_pct": 0.65, "tp_min_rr": 2.3,
        # ── Filters ─────────────────────────────────────────────────
        "counter_trend_penalty": 1,
        "require_volume": False,
        # Soft ADX: penalise non-trending instead of blocking
        "require_adx_trending": False,
        "adx_soft_dampen": 3,           # subtract 3 when ADX < 25
        "leading_conflict_penalty": 3,
        "disable_squeeze_score": True,
        "squeeze_requires_volume": True,
        "disable_trailing": True,
        # OFI defensive only + slope bonus (1h EMA slope is meaningful)
        "ofi_against_penalty": 1,
        "ema_slope_bonus": 1,
        # 4 × 1h = 4 hours after SL (was 3, increase to avoid revenge trades)
        "cooldown_candles": 4,
        # MTF — defensive
        "mtf_trend_bonus": 0,
        "mtf_against_penalty": 1,
        "mtf_sr_proximity_pct": 0.30,
        "mtf_sr_penalty": 1,
        "mtf_require_trend": False,
    },
}


class ScalperStrategy(BaseStrategy):

    def __init__(self, strategy_key: str = "scalper"):
        """strategy_key selects config + timeframe params."""
        self.strategy_key = strategy_key

    def evaluate(self, ind: Dict, price: float,
                 has_long: bool = False, has_short: bool = False,
                 entry_price: float = 0.0,
                 mtf_context: Dict = None) -> Signal:

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

        # Pre-compute volume status (needed by squeeze filter before Layer 8)
        has_volume = bool(vol and (vol.get("spike") or vol.get("increasing")))

        # ══════════════════════════════════════════════════════════════════
        # LAYER 1: EMA 3-Line Alignment (per-TF configurable scores)
        # Full alignment (S > M > L): ema_full_score  Partial: ema_partial_score
        # ══════════════════════════════════════════════════════════════════
        ema_bullish = False
        ema_bearish = False
        ema_full_pts = p.get("ema_full_score", 3)
        ema_partial_pts = p.get("ema_partial_score", 2)

        if ema_s and ema_m and ema_l:
            if ema_s > ema_m > ema_l:
                ema_bullish = True
                long_score += ema_full_pts
                reasons.append("EMA full bullish alignment (S>M>L)")
            elif ema_s < ema_m < ema_l:
                ema_bearish = True
                short_score += ema_full_pts
                reasons.append("EMA full bearish alignment (S<M<L)")
            elif ema_s > ema_m:
                ema_bullish = True
                spread = abs(ema_s - ema_m) / ema_m * 100 if ema_m > 0 else 0
                if spread > p["ema_spread_threshold"]:
                    long_score += ema_partial_pts
                    reasons.append(f"EMA bullish S>M, spread {spread:.3f}%")
                else:
                    long_score += 1
            elif ema_s < ema_m:
                ema_bearish = True
                spread = abs(ema_s - ema_m) / ema_m * 100 if ema_m > 0 else 0
                if spread > p["ema_spread_threshold"]:
                    short_score += ema_partial_pts
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

            if bb.get("squeeze") and not p.get("disable_squeeze_score"):
                squeeze_needs_vol = p.get("squeeze_requires_volume", False)
                if not squeeze_needs_vol or has_volume:
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
        # LEADING INDICATOR CONFLICT GATE
        # Prevent entries when BB / RSI / StochRSI extremes disagree
        # with the planned entry direction.  Only penalizes
        # trend-following against reversal signals — mean-reversion
        # entries (going WITH the leading indicator) are unaffected.
        # ══════════════════════════════════════════════════════════════════
        lead_conflict_pen = p.get("leading_conflict_penalty", 0)
        if lead_conflict_pen > 0:
            # Indicators that warn AGAINST going long (= say "short")
            warns_against_long = sum([
                bool(bb and bb["pct_b"] > p["bb_entry_high"]),
                bool(stoch and stoch.get("overbought") and stoch["k"] < stoch["d"]),
                bool(rsi is not None and rsi > p["rsi_overbought"]),
            ])
            # Indicators that warn AGAINST going short (= say "long")
            warns_against_short = sum([
                bool(bb and bb["pct_b"] < p["bb_entry_low"]),
                bool(stoch and stoch.get("oversold") and stoch["k"] > stoch["d"]),
                bool(rsi is not None and rsi < p["rsi_oversold"]),
            ])

            if long_score > short_score and warns_against_long >= 1:
                long_score = max(0, long_score - lead_conflict_pen)
                reasons.append(f"Leading conflict: {warns_against_long} indicator(s) vs long, -{lead_conflict_pen}")
            elif short_score > long_score and warns_against_short >= 1:
                short_score = max(0, short_score - lead_conflict_pen)
                reasons.append(f"Leading conflict: {warns_against_short} indicator(s) vs short, -{lead_conflict_pen}")

        # ══════════════════════════════════════════════════════════════════
        # VOLUME GATE: For noisy TFs, halve score without volume confirm
        # ══════════════════════════════════════════════════════════════════
        if p["require_volume"] and not has_volume:
            long_score = long_score // 2
            short_score = short_score // 2

        # ══════════════════════════════════════════════════════════════════
        # ADX FILTER: In ranging markets (ADX < 25), dampen trend scores
        # Mean-reversion entries (RSI extreme) still allowed at full score.
        # ══════════════════════════════════════════════════════════════════
        has_rsi_extreme_entry = (rsi is not None and
                                 (rsi < p["rsi_oversold"] or rsi > p["rsi_overbought"]))

        # Hard ADX gate: require ADX trending for entries unless mean-reversion
        if p.get("require_adx_trending") and not has_rsi_extreme_entry:
            if adx_data and not adx_data.get("trending"):
                long_score = 0
                short_score = 0
                reasons.append(f"ADX gate: not trending ({adx_data.get('adx', 0):.0f}) — no entries")
        elif adx_data and not adx_data.get("trending") and not has_rsi_extreme_entry:
            # Soft dampen for strategies without hard gate
            dampen = p.get("adx_soft_dampen", 2)
            long_score = max(0, long_score - dampen)
            short_score = max(0, short_score - dampen)
            reasons.append(f"ADX low ({adx_data.get('adx', 0):.0f}) — scores dampened by {dampen}")

        # ══════════════════════════════════════════════════════════════════
        # OFI FILTER: Order Flow Imbalance — penalise entries against flow
        # Uses volume delta as proxy: bullish candles (+vol), bearish (-vol)
        # ══════════════════════════════════════════════════════════════════
        ofi_data = ind.get("ofi")
        ofi_penalty = p.get("ofi_against_penalty", 1)
        if ofi_data and ofi_penalty > 0:
            ofi_ratio = ofi_data.get("ratio", 0)
            # Long entry with bearish order flow → penalise
            if long_score > 0 and ofi_ratio < -0.3:
                long_score = max(0, long_score - ofi_penalty)
                reasons.append(f"OFI bearish ({ofi_ratio:.2f}) — long dampened -{ofi_penalty}")
            # Short entry with bullish order flow → penalise
            if short_score > 0 and ofi_ratio > 0.3:
                short_score = max(0, short_score - ofi_penalty)
                reasons.append(f"OFI bullish ({ofi_ratio:.2f}) — short dampened -{ofi_penalty}")

        # ══════════════════════════════════════════════════════════════════
        # EMA SLOPE CONFLUENCE: Reward entries aligned with EMA21 momentum
        # If EMA21 is accelerating in entry direction → +1 conviction
        # ══════════════════════════════════════════════════════════════════
        ema21_slope = ind.get("ema21_slope")
        slope_bonus = p.get("ema_slope_bonus", 1)
        if ema21_slope is not None and slope_bonus > 0:
            slope_thresh = 0.05  # 0.05% slope = meaningful trend velocity
            if ema21_slope > slope_thresh and long_score > short_score:
                long_score += slope_bonus
                reasons.append(f"EMA21 slope up ({ema21_slope:.2f}%) — long +{slope_bonus}")
            elif ema21_slope < -slope_thresh and short_score > long_score:
                short_score += slope_bonus
                reasons.append(f"EMA21 slope down ({ema21_slope:.2f}%) — short +{slope_bonus}")

        # ══════════════════════════════════════════════════════════════════
        # LAYER MTF: Higher-Timeframe Trend Alignment + S/R Proximity
        #
        # Elder Triple Screen principle: only trade in the direction of
        # the higher timeframe.  Entries into HTF S/R zones are penalized
        # (you'd be buying into resistance or selling into support).
        # ══════════════════════════════════════════════════════════════════
        if mtf_context:
            htf_trend = mtf_context.get("trend", "unknown")
            mtf_bonus = p.get("mtf_trend_bonus", 0)
            mtf_penalty = p.get("mtf_against_penalty", 0)
            mtf_require = p.get("mtf_require_trend", False)

            # --- Trend alignment ---
            if htf_trend == "bullish":
                if long_score > short_score:
                    long_score += mtf_bonus
                    reasons.append(f"MTF trend aligned bullish (+{mtf_bonus})")
                elif short_score > long_score and mtf_penalty > 0:
                    short_score = max(0, short_score - mtf_penalty)
                    reasons.append(f"MTF trend opposes short (-{mtf_penalty})")
            elif htf_trend == "bearish":
                if short_score > long_score:
                    short_score += mtf_bonus
                    reasons.append(f"MTF trend aligned bearish (+{mtf_bonus})")
                elif long_score > short_score and mtf_penalty > 0:
                    long_score = max(0, long_score - mtf_penalty)
                    reasons.append(f"MTF trend opposes long (-{mtf_penalty})")
            elif htf_trend in ("neutral", "unknown"):
                if mtf_require and not has_rsi_extreme_entry:
                    long_score = 0
                    short_score = 0
                    reasons.append("MTF trend unclear — entries blocked")

            # --- S/R proximity filter ---
            sr = mtf_context.get("support_resistance")
            sr_prox_pct = p.get("mtf_sr_proximity_pct", 0)
            sr_pen = p.get("mtf_sr_penalty", 0)

            if sr and sr_prox_pct > 0 and sr_pen > 0:
                # Penalize longs near HTF resistance
                r_dist = sr.get("resistance_distance_pct")
                if r_dist is not None and r_dist < sr_prox_pct:
                    if long_score > short_score:
                        long_score = max(0, long_score - sr_pen)
                        reasons.append(
                            f"MTF S/R: resistance {r_dist:.2f}% away (-{sr_pen})"
                        )
                # Penalize shorts near HTF support
                s_dist = sr.get("support_distance_pct")
                if s_dist is not None and s_dist < sr_prox_pct:
                    if short_score > long_score:
                        short_score = max(0, short_score - sr_pen)
                        reasons.append(
                            f"MTF S/R: support {s_dist:.2f}% away (-{sr_pen})"
                        )

            # --- HTF ADX boost: extra conviction when HTF strongly trending ---
            # Only active when MTF trend bonus is enabled (> 0)
            htf_adx = mtf_context.get("adx", 0)
            if htf_adx > 30 and mtf_bonus > 0:
                # Strong HTF trend — add 1 point to aligned side
                if htf_trend == "bullish" and long_score > short_score:
                    long_score += 1
                    reasons.append(f"HTF ADX strong ({htf_adx:.0f}) — trend boost")
                elif htf_trend == "bearish" and short_score > long_score:
                    short_score += 1
                    reasons.append(f"HTF ADX strong ({htf_adx:.0f}) — trend boost")

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
