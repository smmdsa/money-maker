"""
Scalper 1-Hour — Swing scalper with RSI(14), MACD(12,26,9), BB(20).

V3e-optimised configuration ("El Swing Scalper"):
  • min_score=6 + soft ADX dampen(3) + OFI penalty=1
  • EMA slope bonus=1.0 (1h slope is meaningful & reliable)
  • SL 1.6×ATR, TP 3.8×ATR (extended TP — 1h moves have real range)
  • Trailing stop ENABLED — protects profits in sustained trends
  • 4-candle cooldown (4 hours after SL)
  • MTF defensive — penalty=2, no hard trend gate
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
    rsi_pullback_range=(35, 50),
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
    tp_atr_mult=3.8,
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
    disable_trailing=False,   # trailing ON — protect profits in 1h swings
    # ── Order flow — OFI + slope bonus ─────────────────────────────
    ofi_against_penalty=1,
    ema_slope_bonus=1.0,
    # ── Cooldown (4 × 1h = 4 hours) ───────────────────────────────
    cooldown_candles=4,
    # ── MTF — defensive with light penalties ───────────────────────
    mtf_trend_bonus=0,
    mtf_against_penalty=2,
    mtf_sr_proximity_pct=0.30,
    mtf_sr_penalty=1,
    mtf_require_trend=False,
)


class Scalper1H(BaseScalperStrategy):
    """1-hour swing scalper (V3e — \"El Swing Scalper\").

    Soft ADX dampen + OFI defence + EMA slope bonus + trailing stop.
    Extended TP (3.8×ATR) with trailing captures sustained 1h trends.

    Note: strategy_key is ``'scalper'`` (not ``'scalper_1h'``) for
    backward compatibility with the STRATEGIES registry.
    """

    def __init__(self) -> None:
        super().__init__("scalper", PARAMS)
