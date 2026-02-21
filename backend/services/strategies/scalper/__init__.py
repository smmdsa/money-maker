"""
Scalper Strategy Package — Polymorphic architecture for per-timeframe scalpers.

Public API:
  • ``ScalperFactory.create(key)`` — instantiate a scalper by strategy key
  • ``BaseScalperStrategy``       — abstract base for custom scalper variants
  • ``ScalperParams``             — frozen dataclass for per-TF configuration
  • ``Scalper1M`` … ``Scalper1H`` — concrete subclasses with V3d-validated params

Backward Compatibility:
  • ``TIMEFRAME_PARAMS`` — dict-of-dicts derived from subclass params
    (consumed by ``backtester.py`` for cooldown tracking)
  • ``ScalperStrategy``  — alias for factory-based creation (drop-in for
    legacy ``ScalperStrategy("scalper_15m")`` calls)
"""
from __future__ import annotations

from typing import Dict

from backend.services.strategies.scalper.params import ScalperParams
from backend.services.strategies.scalper.base_scalper import BaseScalperStrategy
from backend.services.strategies.scalper.scalper_1m import Scalper1M, PARAMS as _P1M
from backend.services.strategies.scalper.scalper_3m import Scalper3M, PARAMS as _P3M
from backend.services.strategies.scalper.scalper_5m import Scalper5M, PARAMS as _P5M
from backend.services.strategies.scalper.scalper_15m import Scalper15M, PARAMS as _P15M
from backend.services.strategies.scalper.scalper_1h import Scalper1H, PARAMS as _P1H
from backend.services.strategies.scalper.factory import ScalperFactory


# ── Backward-compat: TIMEFRAME_PARAMS dict-of-dicts ────────────────────────

TIMEFRAME_PARAMS: Dict[str, Dict] = {
    "scalper_1m": _P1M.to_dict(),
    "scalper_3m": _P3M.to_dict(),
    "scalper_5m": _P5M.to_dict(),
    "scalper_15m": _P15M.to_dict(),
    "scalper": _P1H.to_dict(),
}


# ── Backward-compat: ScalperStrategy("key") → factory wrapper ──────────────

class ScalperStrategy(BaseScalperStrategy):
    """Legacy compatibility wrapper.

    Supports the old ``ScalperStrategy("scalper_15m")`` instantiation pattern.
    Prefer ``ScalperFactory.create("scalper_15m")`` for new code.
    """

    def __init__(self, strategy_key: str = "scalper") -> None:
        instance = ScalperFactory.create(strategy_key)
        super().__init__(instance.strategy_key, instance.params)


__all__ = [
    # Core OOP API
    "BaseScalperStrategy",
    "ScalperFactory",
    "ScalperParams",
    # Concrete subclasses
    "Scalper1M",
    "Scalper3M",
    "Scalper5M",
    "Scalper15M",
    "Scalper1H",
    # Backward compat
    "ScalperStrategy",
    "TIMEFRAME_PARAMS",
]
