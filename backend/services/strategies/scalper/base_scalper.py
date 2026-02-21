"""
BaseScalperStrategy — Polymorphic base for all scalper timeframe variants (V5).

V5 architecture changes from V4:
  • REMOVED: Slope Gate, ADX Directional Gate, CVD Gate (triple-redundant
    direction checks that stacked to make entries mathematically impossible)
  • ADDED: Layer 9 — Candlestick Patterns (engulfing, hammer, pin bar, 3WS/3BC)
  • ADDED: Layer 10 — VWAP bias alignment
  • SOFTENED: Volume gate (reduce 30% vs halving), OFI penalty (capped -2),
    leading conflict penalty (capped -2), ADX dampen (capped -1)
  • LOOSENED: Volatility block threshold (only extreme spikes)
  • PHILOSOPHY: Inclusive scoring (each filter ADDS confidence) rather than
    exclusive gating (each filter BLOCKS entries). High frequency + small edge
    per trade = consistent profits via law of large numbers.
"""
from __future__ import annotations

from typing import Dict, Optional

from backend.services.strategies.base import BaseStrategy
from backend.services.strategies.models import STRATEGIES, Signal
from backend.services.strategies.scalper.params import ScalperParams


class BaseScalperStrategy(BaseStrategy):
    """Abstract scalper with shared 8-layer scoring engine.

    Subclasses provide:
      • ``strategy_key`` — key into the ``STRATEGIES`` registry
      • ``params``       — frozen ``ScalperParams`` with per-TF tuning values
    """

    def __init__(self, strategy_key: str, params: ScalperParams) -> None:
        self._strategy_key = strategy_key
        self._params = params

    # ── Public properties ──────────────────────────────────────────────

    @property
    def strategy_key(self) -> str:
        """STRATEGIES registry key (e.g. ``'scalper_15m'``)."""
        return self._strategy_key

    @property
    def params(self) -> ScalperParams:
        """Per-timeframe tuning parameters (frozen dataclass)."""
        return self._params

    # ── Scoring engine ─────────────────────────────────────────────────

    def evaluate(
        self,
        ind: Dict,
        price: float,
        has_long: bool = False,
        has_short: bool = False,
        entry_price: float = 0.0,
        mtf_context: Optional[Dict] = None,
    ) -> Signal:
        """10-layer scoring engine + soft filters (V5).

        Layers:
          1. EMA 3-line alignment
          2. RSI extremes + pullbacks
          3. Bollinger Bands extremes + squeeze
          4. MACD crossover + histogram
          5. Stochastic RSI cross
          6. ADX trend strength
          7. Momentum
          8. Volume confirmation
          9. Candlestick patterns (V5)
         10. VWAP bias alignment (V5)

        Post-scoring filters (V5 — soft penalties, NO hard zero-gates):
          • Counter-trend penalty
          • Leading-indicator conflict (capped -2)
          • Volume gate (30% reduction, not halving)
          • ADX filter (soft dampen only, capped -1)
          • OFI order-flow filter (capped -2)
          • EMA slope confluence (bonus)
          • Multi-timeframe alignment + S/R proximity
        """
        p = self._params
        cfg = STRATEGIES[self._strategy_key]
        reasons: list[str] = []
        long_score = 0
        short_score = 0

        # ══════════════════════════════════════════════════════════════
        # EARLY GATE — Volatility Block (only extreme spikes)
        # V5: loosened threshold — only blocks genuine flash crashes,
        # not normal intraday volatility.
        # ══════════════════════════════════════════════════════════════
        if p.volatility_block_atr_mult > 0:
            atr_vol_ratio = ind.get("atr_volatility_ratio")
            if atr_vol_ratio is not None and atr_vol_ratio > p.volatility_block_atr_mult:
                return self._build_signal(
                    0, 0,
                    [f"VOLATILITY BLOCK: ATR ratio {atr_vol_ratio:.2f} > "
                     f"{p.volatility_block_atr_mult:.1f}x — no entries"],
                    cfg, has_long, has_short,
                    max(ind.get("atr_pct", 2.0) * p.sl_atr_mult, p.sl_min_pct),
                    max(ind.get("atr_pct", 2.0) * p.tp_atr_mult, p.sl_min_pct * p.tp_min_rr),
                    entry_price, price,
                    -1.0 if p.disable_trailing else max(
                        ind.get("atr_pct", 2.0) * cfg.trail_atr_mult,
                        ind.get("atr_pct", 2.0) * p.sl_atr_mult,
                    ),
                    min_score_override=p.min_score,
                    confidence_divisor=p.conf_divisor,
                    min_score_margin=p.min_score_margin,
                )

        # ── Extract indicators ───────────────────────────────────────
        rsi = ind.get("rsi")
        bb = ind.get("bb")
        stoch = ind.get("stoch_rsi")
        mom = ind.get("momentum", 0)
        ema_s = ind.get("ema_9")     # short EMA
        ema_m = ind.get("ema_21")    # mid EMA
        ema_l = ind.get("ema_55")    # long EMA
        atr_pct = ind.get("atr_pct") or 2.0
        macd = ind.get("macd")
        vol = ind.get("volume")
        adx_data = ind.get("adx")

        has_volume = bool(vol and (vol.get("spike") or vol.get("increasing")))

        # ══════════════════════════════════════════════════════════════
        # LAYER 1 — EMA 3-Line Alignment
        # ══════════════════════════════════════════════════════════════
        ema_bullish = False
        ema_bearish = False

        if ema_s and ema_m and ema_l:
            if ema_s > ema_m > ema_l:
                ema_bullish = True
                long_score += p.ema_full_score
                reasons.append("EMA full bullish alignment (S>M>L)")
            elif ema_s < ema_m < ema_l:
                ema_bearish = True
                short_score += p.ema_full_score
                reasons.append("EMA full bearish alignment (S<M<L)")
            elif ema_s > ema_m:
                ema_bullish = True
                spread = (
                    abs(ema_s - ema_m) / ema_m * 100 if ema_m > 0 else 0
                )
                if spread > p.ema_spread_threshold:
                    long_score += p.ema_partial_score
                    reasons.append(f"EMA bullish S>M, spread {spread:.3f}%")
                else:
                    long_score += 1
            elif ema_s < ema_m:
                ema_bearish = True
                spread = (
                    abs(ema_s - ema_m) / ema_m * 100 if ema_m > 0 else 0
                )
                if spread > p.ema_spread_threshold:
                    short_score += p.ema_partial_score
                    reasons.append(f"EMA bearish S<M, spread {spread:.3f}%")
                else:
                    short_score += 1

        # ══════════════════════════════════════════════════════════════
        # LAYER 2 — RSI Extremes + Pullbacks
        # ══════════════════════════════════════════════════════════════
        if rsi is not None:
            if rsi < p.rsi_oversold:
                long_score += 2
                reasons.append(f"RSI oversold ({rsi:.0f})")
            elif rsi > p.rsi_overbought:
                short_score += 2
                reasons.append(f"RSI overbought ({rsi:.0f})")
            else:
                pb_lo, pb_hi = p.rsi_pullback_range
                bn_lo, bn_hi = p.rsi_bounce_range
                if ema_bullish and pb_lo <= rsi <= pb_hi:
                    long_score += 1
                    reasons.append(f"RSI pullback in uptrend ({rsi:.0f})")
                elif ema_bearish and bn_lo <= rsi <= bn_hi:
                    short_score += 1
                    reasons.append(f"RSI bounce in downtrend ({rsi:.0f})")

        # ══════════════════════════════════════════════════════════════
        # LAYER 3 — Bollinger Bands Extremes + Squeeze
        # ══════════════════════════════════════════════════════════════
        if bb:
            pct_b = bb["pct_b"]
            if pct_b < p.bb_extreme_low:
                long_score += 2
                reasons.append(f"BB extreme low ({pct_b:.2f})")
            elif pct_b > p.bb_extreme_high:
                short_score += 2
                reasons.append(f"BB extreme high ({pct_b:.2f})")
            elif pct_b < p.bb_entry_low:
                long_score += 1
                reasons.append(f"Price near lower BB ({pct_b:.2f})")
            elif pct_b > p.bb_entry_high:
                short_score += 1
                reasons.append(f"Price near upper BB ({pct_b:.2f})")

            if bb.get("squeeze") and not p.disable_squeeze_score:
                squeeze_ok = not p.squeeze_requires_volume or has_volume
                if squeeze_ok:
                    if ema_bullish:
                        long_score += 1
                        reasons.append("BB squeeze — bullish breakout expected")
                    elif ema_bearish:
                        short_score += 1
                        reasons.append("BB squeeze — bearish breakout expected")

        # ══════════════════════════════════════════════════════════════
        # LAYER 4 — MACD Crossover + Histogram
        # ══════════════════════════════════════════════════════════════
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

        # ══════════════════════════════════════════════════════════════
        # LAYER 5 — Stochastic RSI Cross
        # ══════════════════════════════════════════════════════════════
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

        # ══════════════════════════════════════════════════════════════
        # LAYER 6 — ADX Trend Strength
        # ══════════════════════════════════════════════════════════════
        if adx_data and adx_data.get("trending"):
            if adx_data["plus_di"] > adx_data["minus_di"]:
                long_score += 1
                reasons.append(
                    f"ADX trending bullish ({adx_data['adx']:.0f})"
                )
            else:
                short_score += 1
                reasons.append(
                    f"ADX trending bearish ({adx_data['adx']:.0f})"
                )

        # ══════════════════════════════════════════════════════════════
        # LAYER 7 — Momentum
        # ══════════════════════════════════════════════════════════════
        if abs(mom) > p.momentum_threshold:
            if mom > 0:
                long_score += 1
                reasons.append(f"Momentum +{mom:.2f}%")
            else:
                short_score += 1
                reasons.append(f"Momentum {mom:.2f}%")

        # ══════════════════════════════════════════════════════════════
        # LAYER 8 — Volume Confirmation
        # ══════════════════════════════════════════════════════════════
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

        # ══════════════════════════════════════════════════════════════
        # LAYER 9 — Candlestick Patterns (V5)
        # Engulfing (+1-2), Hammer/Shooting Star (+1-2),
        # Pin Bar (+2), Three White Soldiers/Black Crows (+3)
        # ══════════════════════════════════════════════════════════════
        candle_pat = ind.get("candle_pattern")
        if candle_pat and p.pattern_weight > 0:
            pat_dir = candle_pat["direction"]
            pat_str = candle_pat["strength"]
            bonus = max(1, int(pat_str * p.pattern_weight))
            if pat_dir == "long":
                long_score += bonus
                reasons.append(
                    f"Candle pattern: {candle_pat['pattern']} (+{bonus})"
                )
            elif pat_dir == "short":
                short_score += bonus
                reasons.append(
                    f"Candle pattern: {candle_pat['pattern']} (+{bonus})"
                )

        # ══════════════════════════════════════════════════════════════
        # LAYER 10 — VWAP Bias Alignment (V5)
        # Price above VWAP = institutional bullish bias,
        # below = bearish bias. Simple +1 when aligned with direction.
        # ══════════════════════════════════════════════════════════════
        vwap_data = ind.get("vwap")
        if vwap_data and p.vwap_bonus > 0:
            if vwap_data["above"] and long_score >= short_score:
                long_score += p.vwap_bonus
                reasons.append(
                    f"VWAP bullish (price {vwap_data['distance_pct']:+.2f}% "
                    f"above VWAP)"
                )
            elif vwap_data["below"] and short_score >= long_score:
                short_score += p.vwap_bonus
                reasons.append(
                    f"VWAP bearish (price {vwap_data['distance_pct']:+.2f}% "
                    f"below VWAP)"
                )

        # ══════════════════════════════════════════════════════════════
        # PENALTY — Counter-trend (fighting the EMA alignment)
        # ══════════════════════════════════════════════════════════════
        has_rsi_extreme = rsi is not None and (
            rsi < p.rsi_oversold or rsi > p.rsi_overbought
        )

        if not has_rsi_extreme:
            if ema_bearish and long_score > short_score:
                long_score = max(0, long_score - p.counter_trend_penalty)
                reasons.append(
                    f"Counter-trend penalty (long vs bearish EMA, "
                    f"-{p.counter_trend_penalty})"
                )
            elif ema_bullish and short_score > long_score:
                short_score = max(0, short_score - p.counter_trend_penalty)
                reasons.append(
                    f"Counter-trend penalty (short vs bullish EMA, "
                    f"-{p.counter_trend_penalty})"
                )

        # ══════════════════════════════════════════════════════════════
        # LEADING INDICATOR CONFLICT (V5: capped, no longer devastating)
        # V4 had penalty=4, which alone could destroy any setup.
        # V5 caps at -2 and requires ≥2 conflicting indicators.
        # ══════════════════════════════════════════════════════════════
        if p.leading_conflict_penalty > 0:
            warns_against_long = sum([
                bool(bb and bb["pct_b"] > p.bb_entry_high),
                bool(
                    stoch
                    and stoch.get("overbought")
                    and stoch["k"] < stoch["d"]
                ),
                bool(rsi is not None and rsi > p.rsi_overbought),
            ])
            warns_against_short = sum([
                bool(bb and bb["pct_b"] < p.bb_entry_low),
                bool(
                    stoch
                    and stoch.get("oversold")
                    and stoch["k"] > stoch["d"]
                ),
                bool(rsi is not None and rsi < p.rsi_oversold),
            ])

            pen = p.leading_conflict_penalty
            # V5: require ≥2 conflicting indicators (was ≥1)
            if long_score > short_score and warns_against_long >= 2:
                long_score = max(0, long_score - pen)
                reasons.append(
                    f"Leading conflict: {warns_against_long} indicator(s) "
                    f"vs long, -{pen}"
                )
            elif short_score > long_score and warns_against_short >= 2:
                short_score = max(0, short_score - pen)
                reasons.append(
                    f"Leading conflict: {warns_against_short} indicator(s) "
                    f"vs short, -{pen}"
                )

        # ══════════════════════════════════════════════════════════════
        # VOLUME GATE — V5: reduce by 30% (not halving)
        # Halving was too aggressive — many valid setups in low-vol
        # periods (Asian session, pre-news consolidation).
        # ══════════════════════════════════════════════════════════════
        if p.require_volume and not has_volume:
            reduce_long = max(1, int(long_score * 0.3))
            reduce_short = max(1, int(short_score * 0.3))
            long_score = max(0, long_score - reduce_long)
            short_score = max(0, short_score - reduce_short)

        # ══════════════════════════════════════════════════════════════
        # ADX FILTER — soft dampen only (V5: no hard gate)
        # V5 removes the hard gate option entirely. ADX at low TFs is
        # noisy; hard-gating on ADX kills 40-60% of valid entries.
        # ══════════════════════════════════════════════════════════════
        has_rsi_extreme_entry = rsi is not None and (
            rsi < p.rsi_oversold or rsi > p.rsi_overbought
        )

        if (
            adx_data
            and not adx_data.get("trending")
            and not has_rsi_extreme_entry
        ):
            dampen = p.adx_soft_dampen
            if dampen > 0:
                long_score = max(0, long_score - dampen)
                short_score = max(0, short_score - dampen)
                reasons.append(
                    f"ADX low ({adx_data.get('adx', 0):.0f}) — "
                    f"scores dampened by {dampen}"
                )

        # ══════════════════════════════════════════════════════════════
        # OFI FILTER — Order Flow Imbalance (V5: penalty only, no gate)
        # ══════════════════════════════════════════════════════════════
        ofi_data = ind.get("ofi")
        if ofi_data and p.ofi_against_penalty > 0:
            ofi_ratio = ofi_data.get("ratio", 0)
            pen = p.ofi_against_penalty
            if long_score > 0 and ofi_ratio < -0.3:
                long_score = max(0, long_score - pen)
                reasons.append(
                    f"OFI bearish ({ofi_ratio:.2f}) — long dampened -{pen}"
                )
            if short_score > 0 and ofi_ratio > 0.3:
                short_score = max(0, short_score - pen)
                reasons.append(
                    f"OFI bullish ({ofi_ratio:.2f}) — short dampened -{pen}"
                )

        # ══════════════════════════════════════════════════════════════
        # V5: CVD Gate REMOVED — redundant with OFI filter above.
        # Having both OFI penalty AND CVD zero-gate meant the same
        # signal (volume direction) blocked entries TWICE.
        # ══════════════════════════════════════════════════════════════

        # ══════════════════════════════════════════════════════════════
        # EMA SLOPE CONFLUENCE
        # ══════════════════════════════════════════════════════════════
        ema21_slope = ind.get("ema21_slope")
        if ema21_slope is not None and p.ema_slope_bonus > 0:
            slope_thresh = 0.05
            bonus = p.ema_slope_bonus
            if ema21_slope > slope_thresh and long_score > short_score:
                long_score += bonus
                reasons.append(
                    f"EMA21 slope up ({ema21_slope:.2f}%) — long +{bonus}"
                )
            elif ema21_slope < -slope_thresh and short_score > long_score:
                short_score += bonus
                reasons.append(
                    f"EMA21 slope down ({ema21_slope:.2f}%) — short +{bonus}"
                )

        # ══════════════════════════════════════════════════════════════
        # LAYER MTF — Higher-Timeframe Trend Alignment + S/R Proximity
        # ══════════════════════════════════════════════════════════════
        if mtf_context:
            long_score, short_score = self._apply_mtf_scores(
                mtf_context, p, long_score, short_score,
                has_rsi_extreme_entry, reasons,
            )

        # ══════════════════════════════════════════════════════════════
        # V5: REMOVED — Slope Gate, ADX Directional Gate
        # These were triple-redundant with EMA alignment (Layer 1) and
        # ADX filter above. Three independent hard zero-gates checking
        # the same thing (direction) made entry probability near zero.
        # ══════════════════════════════════════════════════════════════

        # ══════════════════════════════════════════════════════════════
        # STOPS — ATR-adaptive, per-timeframe R:R
        # ══════════════════════════════════════════════════════════════
        sl = max(atr_pct * p.sl_atr_mult, p.sl_min_pct)
        tp = max(atr_pct * p.tp_atr_mult, sl * p.tp_min_rr)

        trail = -1.0 if p.disable_trailing else max(
            atr_pct * cfg.trail_atr_mult, sl
        )

        return self._build_signal(
            long_score, short_score, reasons, cfg,
            has_long, has_short, sl, tp, entry_price, price, trail,
            min_score_override=p.min_score,
            confidence_divisor=p.conf_divisor,
            min_score_margin=p.min_score_margin,
        )

    # ── MTF helper (keeps evaluate readable) ───────────────────────────

    @staticmethod
    def _apply_mtf_scores(
        mtf_context: Dict,
        p: ScalperParams,
        long_score: int,
        short_score: int,
        has_rsi_extreme_entry: bool,
        reasons: list[str],
    ) -> tuple[int, int]:
        """Apply multi-timeframe trend alignment and S/R proximity.

        Returns updated (long_score, short_score).
        """
        htf_trend = mtf_context.get("trend", "unknown")
        mtf_bonus = p.mtf_trend_bonus
        mtf_penalty = p.mtf_against_penalty

        # --- Trend alignment ---
        if htf_trend == "bullish":
            if long_score > short_score:
                long_score += mtf_bonus
                if mtf_bonus:
                    reasons.append(
                        f"MTF trend aligned bullish (+{mtf_bonus})"
                    )
            elif short_score > long_score and mtf_penalty > 0:
                short_score = max(0, short_score - mtf_penalty)
                reasons.append(
                    f"MTF trend opposes short (-{mtf_penalty})"
                )
        elif htf_trend == "bearish":
            if short_score > long_score:
                short_score += mtf_bonus
                if mtf_bonus:
                    reasons.append(
                        f"MTF trend aligned bearish (+{mtf_bonus})"
                    )
            elif long_score > short_score and mtf_penalty > 0:
                long_score = max(0, long_score - mtf_penalty)
                reasons.append(
                    f"MTF trend opposes long (-{mtf_penalty})"
                )
        elif htf_trend in ("neutral", "unknown"):
            if p.mtf_require_trend and not has_rsi_extreme_entry:
                long_score = 0
                short_score = 0
                reasons.append("MTF trend unclear — entries blocked")

        # --- S/R proximity filter ---
        sr = mtf_context.get("support_resistance")
        if sr and p.mtf_sr_proximity_pct > 0 and p.mtf_sr_penalty > 0:
            r_dist = sr.get("resistance_distance_pct")
            if (
                r_dist is not None
                and r_dist < p.mtf_sr_proximity_pct
                and long_score > short_score
            ):
                long_score = max(0, long_score - p.mtf_sr_penalty)
                reasons.append(
                    f"MTF S/R: resistance {r_dist:.2f}% away "
                    f"(-{p.mtf_sr_penalty})"
                )

            s_dist = sr.get("support_distance_pct")
            if (
                s_dist is not None
                and s_dist < p.mtf_sr_proximity_pct
                and short_score > long_score
            ):
                short_score = max(0, short_score - p.mtf_sr_penalty)
                reasons.append(
                    f"MTF S/R: support {s_dist:.2f}% away "
                    f"(-{p.mtf_sr_penalty})"
                )

        # --- HTF ADX boost ---
        htf_adx = mtf_context.get("adx", 0)
        if htf_adx > 30 and mtf_bonus > 0:
            if htf_trend == "bullish" and long_score > short_score:
                long_score += 1
                reasons.append(
                    f"HTF ADX strong ({htf_adx:.0f}) — trend boost"
                )
            elif htf_trend == "bearish" and short_score > long_score:
                short_score += 1
                reasons.append(
                    f"HTF ADX strong ({htf_adx:.0f}) — trend boost"
                )

        return long_score, short_score
