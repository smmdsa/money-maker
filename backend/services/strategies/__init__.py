"""
Strategies Package — re-exports all public symbols for backward compatibility.

External code can still do:
    from backend.services.strategies import StrategyEngine, Indicators, STRATEGIES, ...
"""
from backend.services.strategies.models import Signal, StrategyConfig, STRATEGIES
from backend.services.strategies.indicators import Indicators
from backend.services.strategies.engine import (
    StrategyEngine,
    calculate_position_size,
    calculate_liquidation_price,
)

__all__ = [
    "Signal",
    "StrategyConfig",
    "STRATEGIES",
    "Indicators",
    "StrategyEngine",
    "calculate_position_size",
    "calculate_liquidation_price",
]
