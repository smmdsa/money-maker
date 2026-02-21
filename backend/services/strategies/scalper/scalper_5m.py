"""
Scalper 5-Minute — Classic scalper with RSI(10), MACD(8,21,7), BB(16).

V3d-validated configuration:
  • min_score=6 (moderate bar — reliable 5m candles)
  • Hard ADX gate (proven in V2 — soft ADX caused regression)
  • OFI penalty=1 (moderate order-flow defence)
  • No EMA slope bonus (bonuses break scalpers)
  • SL 1.6×ATR, TP 3.8×ATR (standard stops)
  • 20-candle cooldown (~100 min after SL)
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
    rsi_pullback_range=(35, 50),
    rsi_bounce_range=(50, 65),
    # ── Bollinger ──────────────────────────────────────────────────
    bb_entry_low=0.18,
    bb_entry_high=0.82,
    bb_extreme_low=0.05,
    bb_extreme_high=0.95,
    # ── Momentum ───────────────────────────────────────────────────
    momentum_threshold=0.25,
    # ── Risk management ────────────────────────────────────────────
    sl_atr_mult=1.6,
    tp_atr_mult=3.8,
    sl_min_pct=0.40,
    tp_min_rr=2.3,
    # ── Filters ────────────────────────────────────────────────────
    counter_trend_penalty=1,
    require_volume=False,
    require_adx_trending=True,   # hard gate — proven V2
    leading_conflict_penalty=4,
    disable_squeeze_score=True,
    squeeze_requires_volume=True,
    disable_trailing=True,
    # ── Order flow ─────────────────────────────────────────────────
    ofi_against_penalty=1,
    ema_slope_bonus=0,
    # ── Cooldown (20 × 5m ≈ 100 min) ──────────────────────────────
    cooldown_candles=20,
    # ── MTF — defensive ───────────────────────────────────────────
    mtf_trend_bonus=0,
    mtf_against_penalty=2,
    mtf_sr_proximity_pct=0.25,
    mtf_sr_penalty=2,
    mtf_require_trend=False,
)


class Scalper5M(BaseScalperStrategy):
    """5-minute classic scalper.

    Moderate min_score (6) + hard ADX gate + OFI defence.
    Standard taker execution.
    """

    def __init__(self) -> None:
        super().__init__("scalper_5m", PARAMS)
