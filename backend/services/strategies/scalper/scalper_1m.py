"""Scalper 1-Minute — Ultra-fast microstructure scalper (V5).

V5 fixes V4's mathematical impossibility: V4 had min_score=8 with
max achievable ~5 after penalty stacking → 0 trades in 14 days.

V5 philosophy: high frequency + small edge = consistent profits.
  • min_score=5 (was 8) — achievable with 4-5 aligned layers
  • min_score_margin=2 (was 3) — less directional gap required
  • EMA restored (full=2) — even at 1m, alignment matters
  • Leading conflict requires ≥2 indicators (was ≥1)
  • CVD gate REMOVED (redundant with OFI penalty)
  • Slope gate REMOVED (redundant with EMA alignment)
  • ADX directional gate REMOVED (redundant with ADX filter)
  • Candlestick patterns ADD +1-3 points (new alpha source)
  • VWAP alignment ADD +1 point
  • Cooldown reduced: 30 candles = 30min (was 120 = 2hr)
  • R:R rebalanced: tighter TP for higher win rate
"""
from __future__ import annotations

from backend.services.strategies.scalper.base_scalper import BaseScalperStrategy
from backend.services.strategies.scalper.params import ScalperParams

PARAMS = ScalperParams(
    # ── Entry quality ──────────────────────────────────────────────
    min_score=5,                 # V5: achievable (V4 had 8 = impossible)
    conf_divisor=10.0,           # Más generoso para confianza
    min_score_margin=1,          # V5: gap mínimo para máxima frecuencia
    # ── EMA (restaurado — alineación SÍ importa) ──────────────────
    ema_spread_threshold=0.04,
    ema_full_score=2,            # V5: restaurado de 1 a 2
    ema_partial_score=1,         # V5: restaurado de 0 a 1
    # ── RSI ────────────────────────────────────────────────────────
    rsi_oversold=22,
    rsi_overbought=78,
    rsi_pullback_range=(38, 55),
    rsi_bounce_range=(45, 62),
    # ── Bollinger ──────────────────────────────────────────────────
    bb_entry_low=0.15,
    bb_entry_high=0.85,
    bb_extreme_low=0.05,
    bb_extreme_high=0.95,
    # ── Momentum ───────────────────────────────────────────────────
    momentum_threshold=0.12,
    # ── Risk management ────────────────────────────────────────────
    sl_atr_mult=1.8,             # Ajustado para 1m
    tp_atr_mult=2.5,             # V5: TP más cercano = mayor win rate
    sl_min_pct=0.30,
    tp_min_rr=1.3,               # V5: R:R 1.3:1 (win rate > R:R en 1m)
    # ── Filters (V5: todos reducidos) ──────────────────────────────
    counter_trend_penalty=1,     # V5: reducido de 2 a 1
    require_volume=True,
    require_adx_trending=False,  # V5: nunca hard gate
    adx_soft_dampen=1,           # V5: reducido de 3 a 1
    leading_conflict_penalty=2,  # V5: reducido de 4 a 2
    disable_squeeze_score=False, # V5: squeeze puede dar señal
    squeeze_requires_volume=True,
    disable_trailing=True,       # 1m too fast for trailing
    # ── Order flow ─────────────────────────────────────────────────
    ofi_against_penalty=2,       # V5: reducido de 4 a 2
    ema_slope_bonus=1.0,
    # ── Candlestick patterns (V5) ──────────────────────────────────
    pattern_weight=1.0,          # Full weight: patrones son alpha en 1m
    vwap_bonus=1,
    # ── Execution ──────────────────────────────────────────────────
    execution_mode="maker_only",
    max_slippage_tolerance=0.0003,
    # ── CVD REMOVED in V5 (redundant with OFI) ────────────────────
    cvd_alignment_required=False,
    # ── Volatility block (aflojado) ────────────────────────────────
    volatility_block_atr_mult=3.0,  # V5: de 2.0 a 3.0 (solo flash crashes)
    daily_circuit_breaker_pct=2.5,
    # ── Cooldown (30 × 1m = 30min) ────────────────────────────────
    cooldown_candles=30,         # V5: reducido de 120 a 30
    # ── MTF ────────────────────────────────────────────────────────
    mtf_trend_bonus=1,           # V5: bonus positivo (era 0)
    mtf_against_penalty=2,       # V5: reducido de 5 a 2
    mtf_sr_proximity_pct=0.15,
    mtf_sr_penalty=1,            # V5: reducido de 3 a 1
    mtf_require_trend=False,     # V5: NO bloquear por MTF neutral
)


class Scalper1M(BaseScalperStrategy):
    """1-minute scalper (V5).

    High frequency, small edge per trade. 10-layer scoring with
    candlestick patterns and VWAP. No redundant hard gates.
    Target: 3-10 trades/day with 55-65% win rate.
    """

    def __init__(self) -> None:
        super().__init__("scalper_1m", PARAMS)
