"""
Scalper 15-Minute — Intraday trend scalper with RSI(12), MACD(10,22,8), BB(18).

V3e-optimised configuration ("La Tendencia Intradía"):
  • min_score=7 + ADX hard gate + leading conflict penalty=4
  • EMA slope bonus=1.0 (slope must be positive for longs)
  • MTF aligned against 1h — penalty=3 blocks counter-trend entries
  • SL 1.6×ATR, TP 3.0×ATR, cooldown=10 (150 min)
  • Squeeze scoring disabled — wait for BB expansion, not contraction
  • Volume required — no entries in dry/illiquid bars
"""
from __future__ import annotations

from backend.services.strategies.scalper.base_scalper import BaseScalperStrategy
from backend.services.strategies.scalper.params import ScalperParams

PARAMS = ScalperParams(
    # ── Entry quality ──────────────────────────────────────────────
    min_score=7,
    conf_divisor=12.0,
    min_score_margin=3,
    # ── EMA ────────────────────────────────────────────────────────
    ema_spread_threshold=0.08,
    ema_full_score=2,
    ema_partial_score=1,
    # ── RSI ────────────────────────────────────────────────────────
    rsi_oversold=25,
    rsi_overbought=75,
    rsi_pullback_range=(40, 50),
    rsi_bounce_range=(50, 60),
    # ── Bollinger ──────────────────────────────────────────────────
    bb_entry_low=0.18,
    bb_entry_high=0.82,
    bb_extreme_low=0.06,
    bb_extreme_high=0.94,
    # ── Momentum ───────────────────────────────────────────────────
    momentum_threshold=0.25,
    # ── Risk management ────────────────────────────────────────────
    sl_atr_mult=1.6,
    tp_atr_mult=3.0,
    sl_min_pct=0.50,
    tp_min_rr=2.3,
    # ── Filters ────────────────────────────────────────────────────
    counter_trend_penalty=1,
    require_volume=True,
    require_adx_trending=True,   # hard gate — golden config
    leading_conflict_penalty=4,  # heavy penalty (prevents worst trades)
    disable_squeeze_score=True,  # fires constantly on 15m, zero value
    squeeze_requires_volume=True,
    disable_trailing=True,
    # ── Order flow / EMA slope ─────────────────────────────────────
    ofi_against_penalty=0,
    ema_slope_bonus=1.0,
    # ── Cooldown (10 × 15m = 150 min) ─────────────────────────────
    cooldown_candles=10,
    # ── MTF — validate against 1h trend ────────────────────────────
    mtf_trend_bonus=0,
    mtf_against_penalty=3,
    mtf_sr_proximity_pct=0.20,
    mtf_sr_penalty=2,
    mtf_require_trend=True,
)


class Scalper15M(BaseScalperStrategy):
    """15-minute intraday trend scalper (V3e — \"La Tendencia Intradía\").

    Hard ADX gate + EMA slope bonus + MTF 1h alignment.
    BB squeeze ignored — waits for volatility expansion. Volume mandatory.
    """

    def __init__(self) -> None:
        super().__init__("scalper_15m", PARAMS)
