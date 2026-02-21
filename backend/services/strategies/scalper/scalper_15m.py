"""
Scalper 15-Minute — Swing scalper with RSI(12), MACD(10,22,8), BB(18).

V3d-validated *golden* configuration (the most profitable scalper variant):
  • min_score=6 + ADX hard gate + leading conflict penalty=4
  • OFI + EMA slope DISABLED (bonuses destroy the golden config)
  • MTF DISABLED (15m's native filters are sufficient; MTF costs +16% → +4%)
  • SL 1.6×ATR, TP 3.8×ATR, cooldown=10 (150 min)
  • Squeeze scoring disabled (near-zero predictive value at 15m)
"""
from __future__ import annotations

from backend.services.strategies.scalper.base_scalper import BaseScalperStrategy
from backend.services.strategies.scalper.params import ScalperParams

PARAMS = ScalperParams(
    # ── Entry quality ──────────────────────────────────────────────
    min_score=6,
    conf_divisor=12.0,
    min_score_margin=3,
    # ── EMA ────────────────────────────────────────────────────────
    ema_spread_threshold=0.08,
    ema_full_score=2,
    ema_partial_score=1,
    # ── RSI ────────────────────────────────────────────────────────
    rsi_oversold=25,
    rsi_overbought=75,
    rsi_pullback_range=(33, 48),
    rsi_bounce_range=(52, 67),
    # ── Bollinger ──────────────────────────────────────────────────
    bb_entry_low=0.18,
    bb_entry_high=0.82,
    bb_extreme_low=0.06,
    bb_extreme_high=0.94,
    # ── Momentum ───────────────────────────────────────────────────
    momentum_threshold=0.25,
    # ── Risk management ────────────────────────────────────────────
    sl_atr_mult=1.6,
    tp_atr_mult=3.8,
    sl_min_pct=0.50,
    tp_min_rr=2.3,
    # ── Filters ────────────────────────────────────────────────────
    counter_trend_penalty=1,
    require_volume=False,
    require_adx_trending=True,   # hard gate — golden config
    leading_conflict_penalty=4,  # heavy penalty (prevents worst trades)
    disable_squeeze_score=True,  # fires constantly on 15m, zero value
    squeeze_requires_volume=True,
    disable_trailing=True,
    # ── Order flow — DISABLED for 15m ──────────────────────────────
    ofi_against_penalty=0,
    ema_slope_bonus=0,
    # ── Cooldown (10 × 15m = 150 min) ─────────────────────────────
    cooldown_candles=10,
    # ── MTF — DISABLED (costs BTC 30d: +16% → +4%) ────────────────
    mtf_trend_bonus=0,
    mtf_against_penalty=0,
    mtf_sr_proximity_pct=0.0,
    mtf_sr_penalty=0,
    mtf_require_trend=False,
)


class Scalper15M(BaseScalperStrategy):
    """15-minute swing scalper — the golden configuration.

    Most profitable scalper variant. Hard ADX gate + leading conflict
    penalty + no bonuses/MTF. Do not modify without regression testing.
    """

    def __init__(self) -> None:
        super().__init__("scalper_15m", PARAMS)
