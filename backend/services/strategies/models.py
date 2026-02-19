"""
Data models for the strategy system.
Signal, StrategyConfig, and the STRATEGIES registry.
"""
from dataclasses import dataclass, field
from typing import Dict


# ── Signal (output of every strategy evaluation) ────────────────────────────

@dataclass
class Signal:
    """Trading signal produced by a strategy evaluation."""
    direction: str          # "long", "short", "close_long", "close_short", "neutral"
    confidence: float       # 0.0 – 1.0
    leverage: int           # suggested leverage multiplier
    stop_loss_pct: float    # % distance from entry for stop-loss
    take_profit_pct: float  # % distance from entry for take-profit
    reasoning: str          # human-readable explanation
    scores: Dict[str, float] = field(default_factory=dict)
    trail_pct: float = 0.0  # ATR-based trailing distance %; 0 = use stop_loss_pct


# ── Strategy Configuration ──────────────────────────────────────────────────

@dataclass
class StrategyConfig:
    key: str
    name: str
    description: str
    style: str                # trend, mean_reversion, momentum, scalping, grid, confluence
    default_leverage: int
    max_leverage: int
    max_positions: int        # max concurrent open positions
    risk_per_trade_pct: float # % of capital risked per trade
    min_confidence: float     # minimum confidence to open position
    trail_atr_mult: float = 2.5   # Chandelier exit: K × ATR for trailing distance


STRATEGIES: Dict[str, StrategyConfig] = {
    "trend_rider": StrategyConfig(
        key="trend_rider",
        name="Trend Rider",
        description="Follows strong trends using EMA alignment + ADX + pullback entries. "
                    "6-layer signal architecture with 3:1 R:R. Best in trending markets.",
        style="trend",
        default_leverage=3,
        max_leverage=5,
        max_positions=3,
        risk_per_trade_pct=2.5,
        min_confidence=0.55,
        trail_atr_mult=3.0,
    ),
    "mean_reversion": StrategyConfig(
        key="mean_reversion",
        name="Mean Reversion",
        description="Exploits overextended moves using Bollinger Bands + RSI extremes. "
                    "Longs oversold, shorts overbought. Best in ranging markets.",
        style="mean_reversion",
        default_leverage=2,
        max_leverage=3,
        max_positions=4,
        risk_per_trade_pct=1.5,
        min_confidence=0.50,
        trail_atr_mult=2.0,
    ),
    "momentum_sniper": StrategyConfig(
        key="momentum_sniper",
        name="Momentum Sniper",
        description="Catches explosive moves on MACD crossovers backed by volume surges. "
                    "High leverage on confirmed momentum. Best in volatile markets.",
        style="momentum",
        default_leverage=4,
        max_leverage=7,
        max_positions=2,
        risk_per_trade_pct=2.5,
        min_confidence=0.60,
        trail_atr_mult=2.5,
    ),
    "scalper": StrategyConfig(
        key="scalper",
        name="Scalper Pro",
        description="Trend-following pullback scalping (1h candles). Enters pullbacks within "
                    "short-term trends using EMA alignment + RSI + BB confluence. "
                    "ATR-adaptive stops. Profits in any market.",
        style="scalping",
        default_leverage=5,
        max_leverage=10,
        max_positions=5,
        risk_per_trade_pct=4.0,
        min_confidence=0.50,
        trail_atr_mult=2.5,
    ),
    "scalper_1m": StrategyConfig(
        key="scalper_1m",
        name="Scalper Pro 1m",
        description="Ultra-fast 1-minute scalper. Same 6-layer trend-pullback logic "
                    "on 1m candles. Extremely tight ATR stops. Best for high-frequency.",
        style="scalping",
        default_leverage=10,
        max_leverage=20,
        max_positions=5,
        risk_per_trade_pct=2.0,
        min_confidence=0.50,
        trail_atr_mult=1.5,
    ),
    "scalper_3m": StrategyConfig(
        key="scalper_3m",
        name="Scalper Pro 3m",
        description="Fast 3-minute scalper. 6-layer trend-pullback logic on 3m candles. "
                    "Good balance between speed and signal quality.",
        style="scalping",
        default_leverage=8,
        max_leverage=15,
        max_positions=5,
        risk_per_trade_pct=2.5,
        min_confidence=0.50,
        trail_atr_mult=1.8,
    ),
    "scalper_5m": StrategyConfig(
        key="scalper_5m",
        name="Scalper Pro 5m",
        description="Classic 5-minute scalper. 6-layer trend-pullback logic on 5m candles. "
                    "Standard daytrading timeframe with solid signal quality.",
        style="scalping",
        default_leverage=7,
        max_leverage=12,
        max_positions=5,
        risk_per_trade_pct=3.0,
        min_confidence=0.50,
        trail_atr_mult=2.0,
    ),
    "scalper_15m": StrategyConfig(
        key="scalper_15m",
        name="Scalper Pro 15m",
        description="Swing scalper on 15-minute candles. Same 6-layer logic with wider ATR stops. "
                    "Fewer trades, higher quality entries.",
        style="scalping",
        default_leverage=6,
        max_leverage=10,
        max_positions=5,
        risk_per_trade_pct=3.5,
        min_confidence=0.50,
        trail_atr_mult=2.2,
    ),
    "grid_trader": StrategyConfig(
        key="grid_trader",
        name="Grid Trader",
        description="Systematic buy/sell at predefined price levels. "
                    "Profits from oscillation. Best in sideways markets.",
        style="grid",
        default_leverage=2,
        max_leverage=3,
        max_positions=8,
        risk_per_trade_pct=1.0,
        min_confidence=0.40,
        trail_atr_mult=2.0,
    ),
    "confluence_master": StrategyConfig(
        key="confluence_master",
        name="Confluence Master",
        description="Only trades when 5+ indicators align. Fewest trades, highest win rate. "
                    "High leverage justified by overwhelming evidence.",
        style="confluence",
        default_leverage=5,
        max_leverage=10,
        max_positions=2,
        risk_per_trade_pct=3.0,
        min_confidence=0.70,
        trail_atr_mult=2.5,
    ),
}
