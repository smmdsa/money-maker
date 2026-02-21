"""Scalper 15-Minute — Intraday trend scalper (V5).

V5 rebalances 15m for profitability + frequency.
15m is where indicators become genuinely reliable — ADX, MACD, EMA
all produce meaningful signals at this timeframe.

V5 changes:
  • min_score=5 (was 7)
  • min_score_margin=2 (was 3)
  • ADX hard gate REMOVED (V5 uses soft dampen only across all TFs)
  • CVD gate, slope gate, ADX directional gate REMOVED
  • Candlestick patterns + VWAP as new alpha layers
  • Trailing stop ENABLED (15m moves justify it)
  • Cooldown: 4 candles = 1hr (was 10 = 2.5hr)
  • Squeeze scoring enabled (15m squeezes are meaningful)
"""
from __future__ import annotations

from backend.services.strategies.scalper.base_scalper import BaseScalperStrategy
from backend.services.strategies.scalper.params import ScalperParams

PARAMS = ScalperParams(
    # ── Entry quality ──────────────────────────────────────────────
    min_score=4,                 # V5: probado con 5 = ~11 trades, bajamos a 4
    conf_divisor=10.0,
    min_score_margin=1,          # V5: gap mínimo para frecuencia
    # ── EMA ────────────────────────────────────────────────────────
    ema_spread_threshold=0.08,
    ema_full_score=2,            # 15m EMA alignment es confiable
    ema_partial_score=1,
    # ── RSI ────────────────────────────────────────────────────────
    rsi_oversold=28,
    rsi_overbought=72,
    rsi_pullback_range=(38, 52),
    rsi_bounce_range=(48, 62),
    # ── Bollinger ──────────────────────────────────────────────────
    bb_entry_low=0.20,
    bb_entry_high=0.80,
    bb_extreme_low=0.06,
    bb_extreme_high=0.94,
    # ── Momentum ───────────────────────────────────────────────────
    momentum_threshold=0.25,
    # ── Risk management ────────────────────────────────────────────
    sl_atr_mult=1.5,
    tp_atr_mult=3.0,             # V5: R:R 2:1 con trailing
    sl_min_pct=0.50,
    tp_min_rr=2.0,
    # ── Filters (V5: reducidos) ────────────────────────────────────
    counter_trend_penalty=1,     # V5: de 2 a 1
    require_volume=False,        # V5: 15m no necesita volumen obligatorio
    require_adx_trending=False,  # V5: ADX soft dampen only (era hard gate)
    adx_soft_dampen=1,           # V5: de 0 (hard gate) a 1 (soft)
    leading_conflict_penalty=2,  # V5: de 4 a 2
    disable_squeeze_score=False, # V5: squeeze habilitado
    squeeze_requires_volume=False,
    disable_trailing=False,      # V5: trailing ON (15m justifica)
    # ── Order flow ─────────────────────────────────────────────────
    ofi_against_penalty=1,       # V5: de 2 a 1 (15m es trend, no flow)
    ema_slope_bonus=1.0,
    # ── Candlestick patterns (V5) ──────────────────────────────────
    pattern_weight=1.0,
    vwap_bonus=1,
    # ── Volatility block (conservador) ─────────────────────────────
    volatility_block_atr_mult=3.5,  # V5: de 3.0 a 3.5
    daily_circuit_breaker_pct=3.0,
    # ── Cooldown (4 × 15m = 1hr) ──────────────────────────────────
    cooldown_candles=4,          # V5: de 10 a 4
    # ── MTF ────────────────────────────────────────────────────────
    mtf_trend_bonus=1,           # V5: bonus positivo
    mtf_against_penalty=2,       # V5: de 3 a 2
    mtf_sr_proximity_pct=0.20,
    mtf_sr_penalty=1,            # V5: de 2 a 1
    mtf_require_trend=False,     # V5: NO bloquear por MTF neutral
)


class Scalper15M(BaseScalperStrategy):
    """15-minute trend scalper (V5).

    Reliable indicators at this TF. Trailing stop captures swings.
    Squeeze breakouts enabled. Pattern recognition for entries.
    Target: 1-4 trades/day with 55-65% win rate.
    """

    def __init__(self) -> None:
        super().__init__("scalper_15m", PARAMS)
