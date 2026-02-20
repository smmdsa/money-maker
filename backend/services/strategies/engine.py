"""
Strategy Engine — dispatcher + position sizing utilities.

Routes strategy evaluation to the correct strategy class.
"""
import logging
from typing import Dict

from backend.services.strategies.models import STRATEGIES, Signal, StrategyConfig
from backend.services.strategies.trend_rider import TrendRiderStrategy
from backend.services.strategies.mean_reversion import MeanReversionStrategy
from backend.services.strategies.momentum_sniper import MomentumSniperStrategy
from backend.services.strategies.scalper import ScalperStrategy
from backend.services.strategies.grid_trader import GridTraderStrategy
from backend.services.strategies.confluence_master import ConfluenceMasterStrategy

logger = logging.getLogger(__name__)


class StrategyEngine:
    """Evaluates market conditions and emits trading signals per strategy."""

    def __init__(self):
        self._instances = {
            "trend_rider": TrendRiderStrategy(),
            "mean_reversion": MeanReversionStrategy(),
            "momentum_sniper": MomentumSniperStrategy(),
            "scalper": ScalperStrategy("scalper"),
            "scalper_1m": ScalperStrategy("scalper_1m"),
            "scalper_3m": ScalperStrategy("scalper_3m"),
            "scalper_5m": ScalperStrategy("scalper_5m"),
            "scalper_15m": ScalperStrategy("scalper_15m"),
            "grid_trader": GridTraderStrategy(),
            "confluence_master": ConfluenceMasterStrategy(),
        }

    def evaluate(self, strategy_key: str, indicators: Dict,
                 current_price: float, has_long: bool = False,
                 has_short: bool = False,
                 entry_price: float = 0.0,
                 mtf_context: Dict = None) -> Signal:
        """Route evaluation to the correct strategy.

        mtf_context — optional higher-timeframe context dict produced by
        Indicators.compute_htf_context().  Passed through to strategies
        that support it (currently ScalperStrategy).
        """
        strategy = self._instances.get(strategy_key,
                                       self._instances["confluence_master"])
        try:
            # Pass mtf_context to scalper variants that accept it
            if mtf_context and hasattr(strategy, 'evaluate') and strategy_key.startswith("scalper"):
                return strategy.evaluate(indicators, current_price,
                                         has_long, has_short, entry_price,
                                         mtf_context=mtf_context)
            return strategy.evaluate(indicators, current_price,
                                     has_long, has_short, entry_price)
        except Exception as e:
            logger.error(f"Strategy {strategy_key} error: {e}")
            return Signal("neutral", 0.0, 1, 5.0, 10.0, f"Strategy error: {e}")


# ── Position Sizing ─────────────────────────────────────────────────────────

def calculate_position_size(
    balance: float,
    strategy_key: str,
    leverage: int,
    stop_loss_pct: float,
    current_price: float,
    risk_pct_min: float = 0,
    risk_pct_max: float = 0,
) -> float:
    """
    Professional risk-based position sizing.

    Agent-level overrides:
        risk_pct_min/max — clamp the strategy's risk_per_trade_pct.

    Returns: margin (USD to commit)
    """
    cfg = STRATEGIES.get(strategy_key)
    if not cfg:
        return 0.0

    effective_risk = cfg.risk_per_trade_pct
    if risk_pct_min > 0:
        effective_risk = max(effective_risk, risk_pct_min)
    if risk_pct_max > 0:
        effective_risk = min(effective_risk, risk_pct_max)

    risk_pct = effective_risk / 100.0
    risk_amount = balance * risk_pct

    if stop_loss_pct <= 0 or leverage <= 0:
        return 0.0

    margin = risk_amount / (stop_loss_pct / 100 * leverage)
    margin = min(margin, balance * 0.25)

    min_margin = max(balance * 0.01, 1.0)
    if margin < min_margin:
        return 0.0

    return round(margin, 2)


def calculate_liquidation_price(
    entry_price: float, leverage: int, direction: str
) -> float:
    """Calculate liquidation price for a futures position."""
    if leverage <= 0:
        return 0.0
    if direction == "long":
        return entry_price * (1 - 0.9 / leverage)
    else:
        return entry_price * (1 + 0.9 / leverage)
