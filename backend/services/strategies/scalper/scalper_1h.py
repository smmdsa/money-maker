"""
Scalper 1-Hour — Swing scalper with RSI(14), MACD(12,26,9), BB(20).

V3d-validated configuration:
  • min_score=6 + soft ADX dampen(3) + OFI penalty=1
  • EMA slope bonus=1 (ONLY TF where slope bonus works — 1h slope is meaningful)
  • SL 1.6×ATR, TP 4.0×ATR (slightly wider TP for 1h swing moves)
  • 4-candle cooldown (4 hours after SL)
  • MTF defensive with light penalties
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
    ema_spread_threshold=0.12,
    ema_full_score=2,
    ema_partial_score=1,
    # ── RSI ────────────────────────────────────────────────────────
    rsi_oversold=28,
    rsi_overbought=72,
    rsi_pullback_range=(35, 52),
    rsi_bounce_range=(48, 65),
    # ── Bollinger ──────────────────────────────────────────────────
    bb_entry_low=0.22,
    bb_entry_high=0.78,
    bb_extreme_low=0.08,
    bb_extreme_high=0.92,
    # ── Momentum ───────────────────────────────────────────────────
    momentum_threshold=0.35,
    # ── Risk management ────────────────────────────────────────────
    sl_atr_mult=1.6,
    tp_atr_mult=4.0,
    sl_min_pct=0.65,
    tp_min_rr=2.3,
    # ── Filters ────────────────────────────────────────────────────
    counter_trend_penalty=1,
    require_volume=False,
    require_adx_trending=False,  # soft dampen instead
    adx_soft_dampen=3,
    leading_conflict_penalty=3,
    disable_squeeze_score=True,
    squeeze_requires_volume=True,
    disable_trailing=True,
    # ── Order flow — OFI + slope bonus ─────────────────────────────
    ofi_against_penalty=1,
    ema_slope_bonus=1,           # ONLY TF where slope bonus works
    # ── Cooldown (4 × 1h = 4 hours) ───────────────────────────────
    cooldown_candles=4,
    # ── MTF — defensive with light penalties ───────────────────────
    mtf_trend_bonus=0,
    mtf_against_penalty=1,
    mtf_sr_proximity_pct=0.30,
    mtf_sr_penalty=1,
    mtf_require_trend=False,
)


class Scalper1H(BaseScalperStrategy):
    """1-hour swing scalper.

    Soft ADX dampen + OFI defence + EMA slope bonus (unique to 1h).
    The only timeframe where bonuses are safe.

    Note: strategy_key is ``'scalper'`` (not ``'scalper_1h'``) for
    backward compatibility with the STRATEGIES registry.
    """

    def __init__(self) -> None:
        super().__init__("scalper", PARAMS)
