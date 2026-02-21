"""
ExchangeAdapter — Abstract interface for trade execution.
=========================================================
Strategy Pattern: the TradingAgentService delegates all balance-mutating
operations to an adapter.  Concrete implementations:

  • PaperExchangeAdapter  — DB-only simulation (current behaviour)
  • CCXTExchangeAdapter   — real orders on Binance Futures via CCXT (future)

The agent computes pricing, sizing, SL/TP, and LLM enrichment;
the adapter only *executes* the order and records it.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from backend.models.database import TradingAgent, Portfolio


# ── Dataclasses ─────────────────────────────────────────────────────────────


@dataclass
class OrderResult:
    """Standardised result returned by every adapter after execution."""
    success: bool
    order_id: Optional[str] = None
    fill_price: float = 0.0
    filled_qty: float = 0.0
    commission: float = 0.0
    pnl: float = 0.0                # populated on close
    cash_returned: float = 0.0      # populated on close
    trade_db_id: Optional[int] = None   # Trade row id in local DB
    portfolio_db_id: Optional[int] = None  # Portfolio row id (open only)
    error: Optional[str] = None
    raw_response: Optional[Dict] = None


@dataclass
class PositionInfo:
    """Exchange-agnostic representation of an open position."""
    symbol: str
    side: str                       # "long" | "short"
    size: float
    entry_price: float
    mark_price: float
    unrealized_pnl: float
    leverage: int
    margin: float
    liquidation_price: float


@dataclass
class BalanceInfo:
    """Exchange-agnostic account balance snapshot."""
    total: float
    available: float
    margin_used: float
    unrealized_pnl: float
    # Per-asset breakdown: {"USDT": {"total": ..., "free": ..., "used": ...}, ...}
    assets: Dict[str, Dict[str, float]] = field(default_factory=dict)


# ── Abstract Base Class ─────────────────────────────────────────────────────


class ExchangeAdapter(ABC):
    """Interface every execution adapter must implement.

    All methods are **synchronous** to match the current trading-agent
    thread model.  The future CCXT adapter will bridge to async internally
    via ``asyncio.run()`` / ``loop.run_until_complete()``.
    """

    # ── Core execution ──────────────────────────────────────────────────

    @abstractmethod
    def open_position(
        self, *,
        db: Session,
        agent: TradingAgent,
        coin: str,
        symbol: str,
        direction: str,
        amount_coins: float,
        entry_price: float,
        margin: float,
        leverage: int,
        position_value: float,
        liq_price: float,
        sl_price: float,
        tp_price: float,
        trail_pct: float,
        price_extreme: float,
    ) -> OrderResult:
        """Execute an open-position order and persist state."""
        ...

    @abstractmethod
    def close_position(
        self, *,
        db: Session,
        agent: TradingAgent,
        pos: Portfolio,
        current_price: float,
        force_loss: Optional[float] = None,
    ) -> OrderResult:
        """Execute a close-position order and persist state."""
        ...

    # ── Queries ─────────────────────────────────────────────────────────

    @abstractmethod
    def get_balance(self, agent: TradingAgent) -> BalanceInfo:
        """Return the agent's current balance info."""
        ...

    @abstractmethod
    def get_positions(self, db: Session, agent: TradingAgent) -> List[PositionInfo]:
        """Return all open positions for *agent*."""
        ...

    # ── Configuration ───────────────────────────────────────────────────

    @abstractmethod
    def set_leverage(self, symbol: str, leverage: int) -> bool:
        """Configure leverage for a symbol (no-op in paper)."""
        ...

    # ── Reconciliation ──────────────────────────────────────────────────

    @abstractmethod
    def sync_state(self, db: Session, agent: TradingAgent) -> Dict:
        """Reconcile local DB with exchange state.  Paper returns empty."""
        ...

    # ── Metadata ────────────────────────────────────────────────────────

    @property
    @abstractmethod
    def mode(self) -> str:
        """Return ``'paper'``, ``'testnet'``, or ``'live'``."""
        ...
