"""Scalper 1-Hour — Swing scalper (V5).

V5 keeps 1h as the most conservative variant while fixing frequency.
1h is the most forgiving TF: taker fees are negligible, indicators reliable.

V5 changes:
  • min_score=4 (was 6) — 1h moves are forgiving
  • min_score_margin=2 (was 3)
  • CVD gate, slope gate, ADX directional gate REMOVED
  • Candlestick patterns + VWAP as new alpha layers
  • Trailing stop KEPT ON — essential at 1h
  • R:R extended: TP 3.5×ATR with trailing for trend capture
  • Cooldown: 2 candles = 2hr (was 4 = 4hr)
  • Squeeze scoring enabled (1h squeezes are very reliable)
"""
from __future__ import annotations

from backend.services.strategies.scalper.base_scalper import BaseScalperStrategy
from backend.services.strategies.scalper.params import ScalperParams

PARAMS = ScalperParams(
    # ── Entry quality ──────────────────────────────────────────────
    min_score=4,                 # V5: 1h moves forgive imperfect entries
    conf_divisor=10.0,
    min_score_margin=1,          # V5: gap mínimo para frecuencia
    # ── EMA ────────────────────────────────────────────────────────
    ema_spread_threshold=0.12,
    ema_full_score=2,            # 1h EMA alignment es altamente confiable
    ema_partial_score=1,
    # ── RSI (wider bands — 1h mean reversion works) ────────────────
    rsi_oversold=30,
    rsi_overbought=70,
    rsi_pullback_range=(35, 50),
    rsi_bounce_range=(50, 65),
    # ── Bollinger ──────────────────────────────────────────────────
    bb_entry_low=0.22,
    bb_entry_high=0.78,
    bb_extreme_low=0.08,
    bb_extreme_high=0.92,
    # ── Momentum ───────────────────────────────────────────────────
    momentum_threshold=0.30,
    # ── Risk management ────────────────────────────────────────────
    sl_atr_mult=1.5,
    tp_atr_mult=3.5,             # V5: amplio para capturar swings
    sl_min_pct=0.60,
    tp_min_rr=2.3,
    # ── Filters (V5: reducidos) ────────────────────────────────────
    counter_trend_penalty=1,     # V5: de 2 a 1
    require_volume=False,        # V5: 1h no necesita volumen obligatorio
    require_adx_trending=False,
    adx_soft_dampen=1,           # V5: de 3 a 1
    leading_conflict_penalty=2,  # V5: de 3 a 2
    disable_squeeze_score=False, # V5: squeeze habilitado (potente en 1h)
    squeeze_requires_volume=False,
    disable_trailing=False,      # Trailing ON — esencial para 1h
    # ── Order flow ─────────────────────────────────────────────────
    ofi_against_penalty=1,       # V5: de 2 a 1 (1h es swing, no flow)
    ema_slope_bonus=1.0,
    # ── Candlestick patterns (V5) ──────────────────────────────────
    pattern_weight=1.0,
    vwap_bonus=1,
    # ── Volatility block (muy relajado) ────────────────────────────
    volatility_block_atr_mult=4.0,  # V5: de 3.5 a 4.0 (solo extremos)
    daily_circuit_breaker_pct=3.0,
    # ── Cooldown (2 × 1h = 2hr) ───────────────────────────────────
    cooldown_candles=2,          # V5: de 4 a 2
    # ── MTF ────────────────────────────────────────────────────────
    mtf_trend_bonus=1,           # V5: bonus positivo
    mtf_against_penalty=1,       # V5: de 2 a 1
    mtf_sr_proximity_pct=0.30,
    mtf_sr_penalty=1,
    mtf_require_trend=False,
)


class Scalper1H(BaseScalperStrategy):
    """1-hour swing scalper (V5).

    Most conservative variant. Trailing stop + squeeze breakouts.
    Pattern recognition + reliable indicators = quality entries.
    Target: 1-2 trades/day with 55-65% win rate.

    Note: strategy_key is ``'scalper'`` (not ``'scalper_1h'``) for
    backward compatibility with the STRATEGIES registry.
    """

    def __init__(self) -> None:
        super().__init__("scalper", PARAMS)
