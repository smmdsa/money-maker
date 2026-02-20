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
    kline_interval: str = ""       # Binance kline interval for scalping (1m, 3m, 5m, 15m, 1h); empty = use default daily
    scan_limit: int = 6            # how many coins to scan per cycle


STRATEGIES: Dict[str, StrategyConfig] = {
    "trend_rider": StrategyConfig(
        key="trend_rider",
        name="Trend Rider",
        description="Follows strong trends using EMA alignment + slope + ADX/DI crossover + "
                    "pullback entries. 8-layer signal scoring with wider 2xATR stops. "
                    "Best with trailing OFF in trending markets.",
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
        description="Trend-following pullback scalping (1h candles). EMA 3-line alignment "
                    "with RSI/BB/MACD/StochRSI/ADX confluence + counter-trend penalty. "
                    "ATR-adaptive stops with 2.5:1 R:R. Reduced leverage for fee control.",
        style="scalping",
        default_leverage=3,
        max_leverage=5,
        max_positions=3,
        risk_per_trade_pct=3.0,
        min_confidence=0.30,
        trail_atr_mult=3.5,
        kline_interval="1h",
        scan_limit=15,
    ),
    "scalper_1m": StrategyConfig(
        key="scalper_1m",
        name="Scalper Pro 1m",
        description="Ultra-fast 1m scalper with RSI(7), MACD(5,13,4), BB(10). "
                    "Requires ≥5 score layers. No trailing (pure SL/TP). "
                    "Volume required. Strong counter-trend penalty.",
        style="scalping",
        default_leverage=3,
        max_leverage=5,
        max_positions=3,
        risk_per_trade_pct=1.5,
        min_confidence=0.35,
        trail_atr_mult=1.5,
        kline_interval="1m",
        scan_limit=15,
    ),
    "scalper_3m": StrategyConfig(
        key="scalper_3m",
        name="Scalper Pro 3m",
        description="Fast 3m scalper with RSI(9), MACD(8,17,6), BB(14). "
                    "Requires ≥5 score layers. No trailing (pure SL/TP). "
                    "Volume required. Strong counter-trend penalty.",
        style="scalping",
        default_leverage=3,
        max_leverage=5,
        max_positions=3,
        risk_per_trade_pct=2.0,
        min_confidence=0.35,
        trail_atr_mult=1.8,
        kline_interval="3m",
        scan_limit=15,
    ),
    "scalper_5m": StrategyConfig(
        key="scalper_5m",
        name="Scalper Pro 5m",
        description="Classic 5m scalper with RSI(10), MACD(8,21,7), BB(16). "
                    "Requires ≥4 score layers. Trail 3× ATR. "
                    "ADX filter + counter-trend penalty.",
        style="scalping",
        default_leverage=3,
        max_leverage=7,
        max_positions=3,
        risk_per_trade_pct=2.5,
        min_confidence=0.30,
        trail_atr_mult=3.0,
        kline_interval="5m",
        scan_limit=15,
    ),
    "scalper_15m": StrategyConfig(
        key="scalper_15m",
        name="Scalper Pro 15m",
        description="Swing scalper on 15m candles with RSI(12), MACD(10,22,8), BB(18). "
                    "Requires ≥4 score layers. Trail 3× ATR. "
                    "ADX filter + counter-trend penalty. 2.5:1 R:R.",
        style="scalping",
        default_leverage=3,
        max_leverage=5,
        max_positions=3,
        risk_per_trade_pct=2.5,
        min_confidence=0.30,
        trail_atr_mult=3.0,
        kline_interval="15m",
        scan_limit=15,
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
