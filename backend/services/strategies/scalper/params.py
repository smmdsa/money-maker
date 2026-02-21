"""
ScalperParams — Immutable per-timeframe configuration dataclass.

Each scalper variant (1m, 3m, 5m, 15m, 1h) provides a frozen
ScalperParams instance with individually validated parameters
derived from extensive backtesting (V3d validated).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Tuple


@dataclass(frozen=True, slots=True)
class ScalperParams:
    """Immutable parameter set for a scalper timeframe variant.

    Attributes are grouped by function:
      • Entry quality — min_score, confidence divisor, score margin
      • EMA alignment — spread threshold, scoring caps
      • RSI zones — oversold/overbought, pullback/bounce ranges
      • Bollinger — entry zones, extremes, squeeze control
      • Momentum — threshold for momentum layer
      • Risk management — SL/TP multipliers, minimums
      • Filters — trend, volume, ADX, leading-conflict
      • Order flow — OFI penalty, EMA slope bonus
      • Cooldown — candles after SL before re-entry
      • Multi-timeframe — HTF trend/SR alignment
    """

    # ── Entry quality ──────────────────────────────────────────────────
    min_score: int
    conf_divisor: float
    min_score_margin: int

    # ── EMA 3-line alignment ───────────────────────────────────────────
    ema_spread_threshold: float
    ema_full_score: int
    ema_partial_score: int

    # ── RSI zones ──────────────────────────────────────────────────────
    rsi_oversold: int
    rsi_overbought: int
    rsi_pullback_range: Tuple[int, int]
    rsi_bounce_range: Tuple[int, int]

    # ── Bollinger Bands ────────────────────────────────────────────────
    bb_entry_low: float
    bb_entry_high: float
    bb_extreme_low: float
    bb_extreme_high: float

    # ── Momentum ───────────────────────────────────────────────────────
    momentum_threshold: float

    # ── Risk management ────────────────────────────────────────────────
    sl_atr_mult: float
    tp_atr_mult: float
    sl_min_pct: float
    tp_min_rr: float

    # ── Filters ────────────────────────────────────────────────────────
    counter_trend_penalty: int
    require_volume: bool
    require_adx_trending: bool
    adx_soft_dampen: int = 0
    leading_conflict_penalty: int = 0
    disable_squeeze_score: bool = True
    squeeze_requires_volume: bool = True
    disable_trailing: bool = True

    # ── Order flow / EMA slope ─────────────────────────────────────────
    ofi_against_penalty: int = 0
    ema_slope_bonus: float = 0.0

    # ── Cooldown ───────────────────────────────────────────────────────
    cooldown_candles: int = 0

    # ── Multi-timeframe ────────────────────────────────────────────────
    mtf_trend_bonus: int = 0
    mtf_against_penalty: int = 0
    mtf_sr_proximity_pct: float = 0.0
    mtf_sr_penalty: int = 0
    mtf_require_trend: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to plain dict (backward compat with TIMEFRAME_PARAMS)."""
        return asdict(self)
