"""
Scalper 1-Minute — Ultra-fast "francotirador" with RSI(7), MACD(5,13,4), BB(10).

V3e-optimised configuration:
  • min_score=8 (highest bar — only operate with full confluence)
  • Soft ADX dampen(4) — 1m ADX too noisy for hard gate
  • OFI penalty=2, require_volume=True (volume mandatory at 1m)
  • EMA slope bonus=1.5 (filters dead/lateral markets)
  • SL 2.5×ATR, TP 2.2×ATR (conservative TP for 1m noise)
  • 120-candle cooldown (2 hours after SL)
  • MTF trend required — must align with 5m/15m tide
"""
from __future__ import annotations

from backend.services.strategies.scalper.base_scalper import BaseScalperStrategy
from backend.services.strategies.scalper.params import ScalperParams

PARAMS = ScalperParams(
    # ── Entry quality ──────────────────────────────────────────────
    min_score=8,
    conf_divisor=12.0,
    min_score_margin=3,
    # ── EMA ────────────────────────────────────────────────────────
    ema_spread_threshold=0.04,
    ema_full_score=2,
    ema_partial_score=1,
    # ── RSI ────────────────────────────────────────────────────────
    rsi_oversold=20,
    rsi_overbought=80,
    rsi_pullback_range=(45, 55),
    rsi_bounce_range=(45, 55),
    # ── Bollinger ──────────────────────────────────────────────────
    bb_entry_low=0.12,
    bb_entry_high=0.88,
    bb_extreme_low=0.05,
    bb_extreme_high=0.95,
    # ── Momentum ───────────────────────────────────────────────────
    momentum_threshold=0.15,
    # ── Risk management ────────────────────────────────────────────
    sl_atr_mult=2.5,
    tp_atr_mult=2.2,
    sl_min_pct=0.35,
    tp_min_rr=2.5,
    # ── Filters ────────────────────────────────────────────────────
    counter_trend_penalty=1,
    require_volume=True,
    require_adx_trending=False,
    adx_soft_dampen=4,
    leading_conflict_penalty=4,
    disable_squeeze_score=True,
    squeeze_requires_volume=True,
    disable_trailing=True,
    # ── Order flow ─────────────────────────────────────────────────
    ofi_against_penalty=2,
    ema_slope_bonus=1.5,
    # ── Cooldown (120 × 1m = 2hr) ─────────────────────────────────
    cooldown_candles=120,
    # ── MTF — defensive only ───────────────────────────────────────
    mtf_trend_bonus=0,
    mtf_against_penalty=5,
    mtf_sr_proximity_pct=0.15,
    mtf_sr_penalty=2,
    mtf_require_trend=True,
)


class Scalper1M(BaseScalperStrategy):
    """1-minute ultra-fast scalper (V3e — \"El Francotirador\").

    Strictest filters: min_score=8, mandatory volume, MTF trend gate.
    Slope bonus + ADX directional gate prevent lateral-market entries.
    """

    def __init__(self) -> None:
        super().__init__("scalper_1m", PARAMS)
