"""Scalper 5-Minute — Core scalper (V5).

V5 rebalances the 5m scalper for profitability + frequency.
5m is the "sweet spot" TF: fast enough for frequent trades,
slow enough for indicators to have meaning.

V5 changes:
  • min_score=5 (was 7)
  • min_score_margin=2 (was 3)
  • EMA restored (full=2, partial=1)
  • CVD gate, slope gate, ADX directional gate REMOVED
  • Candlestick patterns + VWAP as new alpha layers
  • R:R rebalanced: TP 2.8×ATR (was 3.8) for higher win rate
  • Cooldown: 8 candles = 40min (was 20 = 100min)
  • Trailing stop enabled with better parameters
"""
from __future__ import annotations

from backend.services.strategies.scalper.base_scalper import BaseScalperStrategy
from backend.services.strategies.scalper.params import ScalperParams

PARAMS = ScalperParams(
    # ── Entry quality ──────────────────────────────────────────────
    min_score=4,                 # V5: lower threshold, quality via R:R
    conf_divisor=10.0,
    min_score_margin=1,          # V5: gap mínimo para frecuencia
    # ── EMA (restaurado) ───────────────────────────────────────────
    ema_spread_threshold=0.08,
    ema_full_score=2,            # V5: restaurado
    ema_partial_score=1,         # V5: restaurado
    # ── RSI ────────────────────────────────────────────────────────
    rsi_oversold=25,
    rsi_overbought=75,
    rsi_pullback_range=(35, 52),
    rsi_bounce_range=(48, 65),
    # ── Bollinger ──────────────────────────────────────────────────
    bb_entry_low=0.20,
    bb_entry_high=0.80,
    bb_extreme_low=0.06,
    bb_extreme_high=0.94,
    # ── Momentum ───────────────────────────────────────────────────
    momentum_threshold=0.22,
    # ── Risk management ────────────────────────────────────────────
    sl_atr_mult=1.5,
    tp_atr_mult=2.8,             # V5: TP más cercano para win rate
    sl_min_pct=0.40,
    tp_min_rr=1.8,               # V5: R:R 1.8:1
    # ── Filters (V5: reducidos) ────────────────────────────────────
    counter_trend_penalty=1,     # V5: de 2 a 1
    require_volume=True,
    require_adx_trending=False,
    adx_soft_dampen=1,           # V5: de 2 a 1
    leading_conflict_penalty=2,  # V5: de 4 a 2
    disable_squeeze_score=False, # V5: squeeze habilitado
    squeeze_requires_volume=True,
    disable_trailing=False,      # Trailing ON: 5m puede capturar extensiones
    # ── Order flow ─────────────────────────────────────────────────
    ofi_against_penalty=2,       # V5: de 3 a 2
    ema_slope_bonus=1.0,
    # ── Candlestick patterns (V5) ──────────────────────────────────
    pattern_weight=1.0,
    vwap_bonus=1,
    # ── Execution ──────────────────────────────────────────────────
    execution_mode="maker_only",
    max_slippage_tolerance=0.0005,
    # ── CVD REMOVED in V5 ─────────────────────────────────────────
    cvd_alignment_required=False,
    # ── Volatility block (aflojado) ────────────────────────────────
    volatility_block_atr_mult=3.5,  # V5: de 2.5 a 3.5
    daily_circuit_breaker_pct=3.0,
    # ── Cooldown (8 × 5m = 40min) ─────────────────────────────────
    cooldown_candles=8,          # V5: de 20 a 8
    # ── MTF ────────────────────────────────────────────────────────
    mtf_trend_bonus=1,           # V5: bonus positivo
    mtf_against_penalty=2,
    mtf_sr_proximity_pct=0.20,
    mtf_sr_penalty=1,            # V5: de 3 a 1
    mtf_require_trend=False,     # V5: NO bloquear
)


class Scalper5M(BaseScalperStrategy):
    """5-minute core scalper (V5).

    Sweet spot timeframe. Pattern recognition + indicator confluence.
    Trailing stop captures extended moves.
    Target: 2-6 trades/day with 55-65% win rate.
    """

    def __init__(self) -> None:
        super().__init__("scalper_5m", PARAMS)
