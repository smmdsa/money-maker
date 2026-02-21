"""Scalper 3-Minute — Micro-scalper (V5).

V5 fixes V4's over-filtering: V4 had min_score=8 + CVD gate + OFI(4)
+ leading_conflict(4) = mathematically impossible to trade.

V5 philosophy: more trades, controlled risk, pattern recognition.
  • min_score=5 (was 8)
  • min_score_margin=2 (was 3)
  • EMA restored (full=2, partial=1)
  • All hard zero-gates removed (CVD, slope, ADX directional)
  • Candlestick patterns + VWAP as new scoring layers
  • Cooldown reduced: 12 candles = 36min (was 40 = 2hr)
  • R:R rebalanced for win rate focus
"""
from __future__ import annotations

from backend.services.strategies.scalper.base_scalper import BaseScalperStrategy
from backend.services.strategies.scalper.params import ScalperParams

PARAMS = ScalperParams(
    # ── Entry quality ──────────────────────────────────────────────
    min_score=4,                 # V5: más permisivo (3m necesita volumen)
    conf_divisor=10.0,
    min_score_margin=1,          # V5: gap mínimo para frecuencia
    # ── EMA (restaurado) ───────────────────────────────────────────
    ema_spread_threshold=0.06,
    ema_full_score=2,            # V5: restaurado
    ema_partial_score=1,         # V5: restaurado
    # ── RSI ────────────────────────────────────────────────────────
    rsi_oversold=24,
    rsi_overbought=76,
    rsi_pullback_range=(38, 55),
    rsi_bounce_range=(45, 62),
    # ── Bollinger ──────────────────────────────────────────────────
    bb_entry_low=0.18,
    bb_entry_high=0.82,
    bb_extreme_low=0.05,
    bb_extreme_high=0.95,
    # ── Momentum ───────────────────────────────────────────────────
    momentum_threshold=0.18,
    # ── Risk management ────────────────────────────────────────────
    sl_atr_mult=1.6,
    tp_atr_mult=2.5,             # V5: TP cercano → win rate
    sl_min_pct=0.35,
    tp_min_rr=1.5,               # V5: R:R 1.5:1
    # ── Filters (V5: reducidos) ────────────────────────────────────
    counter_trend_penalty=1,     # V5: de 2 a 1
    require_volume=True,
    require_adx_trending=False,
    adx_soft_dampen=1,           # V5: de 3 a 1
    leading_conflict_penalty=2,  # V5: de 4 a 2
    disable_squeeze_score=False, # V5: squeeze habilitado
    squeeze_requires_volume=True,
    disable_trailing=True,       # 3m demasiado rápido
    # ── Order flow ─────────────────────────────────────────────────
    ofi_against_penalty=2,       # V5: de 4 a 2
    ema_slope_bonus=1.0,
    # ── Candlestick patterns (V5) ──────────────────────────────────
    pattern_weight=1.0,
    vwap_bonus=1,
    # ── Execution ──────────────────────────────────────────────────
    execution_mode="maker_only",
    max_slippage_tolerance=0.0003,
    # ── CVD REMOVED in V5 ─────────────────────────────────────────
    cvd_alignment_required=False,
    # ── Volatility block (aflojado) ────────────────────────────────
    volatility_block_atr_mult=3.0,  # V5: de 2.0 a 3.0
    daily_circuit_breaker_pct=2.5,
    # ── Cooldown (12 × 3m = 36min) ────────────────────────────────
    cooldown_candles=12,         # V5: de 40 a 12
    # ── MTF ────────────────────────────────────────────────────────
    mtf_trend_bonus=1,           # V5: bonus positivo
    mtf_against_penalty=2,       # V5: de 5 a 2
    mtf_sr_proximity_pct=0.15,
    mtf_sr_penalty=1,            # V5: de 2 a 1
    mtf_require_trend=False,     # V5: NO bloquear
)


class Scalper3M(BaseScalperStrategy):
    """3-minute scalper (V5).

    Pattern-driven micro-scalping with soft risk filters.
    Target: 2-8 trades/day with 55-65% win rate.
    """

    def __init__(self) -> None:
        super().__init__("scalper_3m", PARAMS)
