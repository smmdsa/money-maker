"""
Scalper 1-Minute — Ultra-fast scalper with RSI(7), MACD(5,13,4), BB(10).

V3d-validated configuration:
  • min_score=7 (very high bar — only strong confluence entries)
  • Soft ADX dampen(4) — 1m ADX is too noisy for hard gate
  • OFI penalty=2 (strong order-flow defence)
  • No EMA slope bonus (bonuses break scalpers)
  • SL 2.5×ATR, TP 6.0×ATR (very wide stops for 1m noise)
  • 120-candle cooldown (2 hours after SL)
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
    ema_spread_threshold=0.04,
    ema_full_score=2,
    ema_partial_score=1,
    # ── RSI ────────────────────────────────────────────────────────
    rsi_oversold=20,
    rsi_overbought=80,
    rsi_pullback_range=(35, 47),
    rsi_bounce_range=(53, 65),
    # ── Bollinger ──────────────────────────────────────────────────
    bb_entry_low=0.12,
    bb_entry_high=0.88,
    bb_extreme_low=0.05,
    bb_extreme_high=0.95,
    # ── Momentum ───────────────────────────────────────────────────
    momentum_threshold=0.15,
    # ── Risk management ────────────────────────────────────────────
    sl_atr_mult=2.5,
    tp_atr_mult=6.0,
    sl_min_pct=0.35,
    tp_min_rr=2.5,
    # ── Filters ────────────────────────────────────────────────────
    counter_trend_penalty=1,
    require_volume=False,
    require_adx_trending=False,
    adx_soft_dampen=4,
    leading_conflict_penalty=4,
    disable_squeeze_score=True,
    squeeze_requires_volume=True,
    disable_trailing=True,
    # ── Order flow ─────────────────────────────────────────────────
    ofi_against_penalty=2,
    ema_slope_bonus=0,
    # ── Cooldown (120 × 1m = 2hr) ─────────────────────────────────
    cooldown_candles=120,
    # ── MTF — defensive only ───────────────────────────────────────
    mtf_trend_bonus=0,
    mtf_against_penalty=3,
    mtf_sr_proximity_pct=0.15,
    mtf_sr_penalty=2,
    mtf_require_trend=False,
)


class Scalper1M(BaseScalperStrategy):
    """1-minute ultra-fast scalper.

    Highest min_score (7) + soft ADX dampen + strong OFI defence.
    Designed for Post-Only maker execution via MakerExecutionManager.
    """

    def __init__(self) -> None:
        super().__init__("scalper_1m", PARAMS)
