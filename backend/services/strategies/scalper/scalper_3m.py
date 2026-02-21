"""
Scalper 3-Minute — Fast "equilibrista" with RSI(9), MACD(8,17,6), BB(14).

V3e-optimised configuration:
  • min_score=8 (very strict — avoid noisy 3m false signals)
  • Soft ADX dampen(3) — 3m ADX can whipsaw
  • OFI penalty=3 (strong OFI — must see real order-book pressure)
  • EMA slope bonus=1.5 (filters lateral/exhausted markets)
  • SL 2.0×ATR, TP 2.2×ATR (conservative TP for 3m)
  • 40-candle cooldown (2 hours after SL)
  • MTF trend required — must align with 15m tide
"""
from __future__ import annotations

from backend.services.strategies.scalper.base_scalper import BaseScalperStrategy
from backend.services.strategies.scalper.params import ScalperParams

PARAMS = ScalperParams(
    # ── Entry quality ──────────────────────────────────────────────
    min_score=8,
    conf_divisor=12.0,
    min_score_margin=3,
    # ── EMA ────────────────────────────────────────────────────────
    ema_spread_threshold=0.06,
    ema_full_score=2,
    ema_partial_score=1,
    # ── RSI ────────────────────────────────────────────────────────
    rsi_oversold=22,
    rsi_overbought=78,
    rsi_pullback_range=(45, 55),
    rsi_bounce_range=(45, 55),
    # ── Bollinger ──────────────────────────────────────────────────
    bb_entry_low=0.15,
    bb_entry_high=0.85,
    bb_extreme_low=0.05,
    bb_extreme_high=0.95,
    # ── Momentum ───────────────────────────────────────────────────
    momentum_threshold=0.20,
    # ── Risk management ────────────────────────────────────────────
    sl_atr_mult=2.0,
    tp_atr_mult=2.2,
    sl_min_pct=0.40,
    tp_min_rr=2.5,
    # ── Filters ────────────────────────────────────────────────────
    counter_trend_penalty=1,
    require_volume=True,
    require_adx_trending=False,
    adx_soft_dampen=3,
    leading_conflict_penalty=4,
    disable_squeeze_score=True,
    squeeze_requires_volume=True,
    disable_trailing=True,
    # ── Order flow ─────────────────────────────────────────────────
    ofi_against_penalty=3,
    ema_slope_bonus=1.5,
    # ── Cooldown (40 × 3m = 2hr) ──────────────────────────────────
    cooldown_candles=40,
    # ── MTF — defensive ───────────────────────────────────────────
    mtf_trend_bonus=0,
    mtf_against_penalty=5,
    mtf_sr_proximity_pct=0.15,
    mtf_sr_penalty=1,
    mtf_require_trend=True,
)


class Scalper3M(BaseScalperStrategy):
    """3-minute fast scalper (V3e — \"El Equilibrista\").

    Strictest filters: min_score=8, OFI=3, mandatory volume, MTF trend gate.
    Hybrid TF — the most dangerous for false signals; maximum protection.
    """

    def __init__(self) -> None:
        super().__init__("scalper_3m", PARAMS)
