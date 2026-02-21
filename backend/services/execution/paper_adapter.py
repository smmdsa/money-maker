"""
PaperExchangeAdapter — Simulated execution via local DB.
=========================================================
Extracts the balance / Portfolio / Trade mutation logic that previously
lived inside ``TradingAgentService._open_position`` and
``_close_position``.  Behaviour is **identical** to the original code;
this is a pure extraction refactor.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from backend.models.database import TradingAgent, Portfolio, Trade
from backend.services.execution.exchange_adapter import (
    ExchangeAdapter,
    OrderResult,
    PositionInfo,
    BalanceInfo,
)

logger = logging.getLogger(__name__)


class PaperExchangeAdapter(ExchangeAdapter):
    """DB-only paper trading — no real exchange interaction."""

    # ── Open ────────────────────────────────────────────────────────────

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
        # Deduct margin from virtual balance
        agent.current_balance -= margin

        portfolio_item = Portfolio(
            agent_id=agent.id,
            cryptocurrency=coin,
            symbol=symbol,
            amount=amount_coins,
            avg_buy_price=entry_price,
            current_price=entry_price,
            position_type=direction,
            leverage=leverage,
            margin=margin,
            liquidation_price=liq_price,
            stop_loss_price=sl_price,
            take_profit_price=tp_price,
            trailing_stop_pct=trail_pct,
            price_extreme=price_extreme,
        )
        db.add(portfolio_item)

        trade = Trade(
            agent_id=agent.id,
            cryptocurrency=coin,
            symbol=symbol,
            trade_type=f"open_{direction}",
            amount=amount_coins,
            price=entry_price,
            total_value=position_value,
            profit_loss=0,
            leverage=leverage,
            margin=margin,
        )
        db.add(trade)
        db.flush()  # materialise IDs before the caller links decision_id

        return OrderResult(
            success=True,
            fill_price=entry_price,
            filled_qty=amount_coins,
            commission=0.0,
            trade_db_id=trade.id,
            portfolio_db_id=portfolio_item.id,
        )

    # ── Close ───────────────────────────────────────────────────────────

    def close_position(
        self, *,
        db: Session,
        agent: TradingAgent,
        pos: Portfolio,
        current_price: float,
        force_loss: Optional[float] = None,
    ) -> OrderResult:
        # PnL calculation (mirrors original logic exactly)
        if force_loss is not None:
            pnl = force_loss
        elif pos.position_type == "long":
            pnl = pos.amount * (current_price - pos.avg_buy_price)
        else:
            pnl = pos.amount * (pos.avg_buy_price - current_price)

        cash_return = max(pos.margin + pnl, 0)
        agent.current_balance += cash_return

        trade_type = f"close_{pos.position_type}"

        trade = Trade(
            agent_id=agent.id,
            cryptocurrency=pos.cryptocurrency,
            symbol=pos.symbol,
            trade_type=trade_type,
            amount=pos.amount,
            price=current_price,
            total_value=pos.amount * current_price,
            profit_loss=pnl,
            leverage=pos.leverage,
            margin=pos.margin,
        )
        db.add(trade)
        db.flush()

        db.delete(pos)

        return OrderResult(
            success=True,
            fill_price=current_price,
            filled_qty=pos.amount,
            commission=0.0,
            pnl=pnl,
            cash_returned=cash_return,
            trade_db_id=trade.id,
        )

    # ── Queries ─────────────────────────────────────────────────────────

    def get_balance(self, agent: TradingAgent) -> BalanceInfo:
        margin_used = sum(p.margin for p in agent.portfolio if p.amount > 0)
        return BalanceInfo(
            total=agent.current_balance + margin_used,
            available=agent.current_balance,
            margin_used=margin_used,
            unrealized_pnl=0.0,  # would need live prices to compute
        )

    def get_positions(self, db: Session, agent: TradingAgent) -> List[PositionInfo]:
        return [
            PositionInfo(
                symbol=p.symbol,
                side=p.position_type,
                size=p.amount,
                entry_price=p.avg_buy_price,
                mark_price=p.current_price,
                unrealized_pnl=0.0,
                leverage=p.leverage,
                margin=p.margin,
                liquidation_price=p.liquidation_price,
            )
            for p in agent.portfolio
            if p.amount > 0
        ]

    # ── Config ──────────────────────────────────────────────────────────

    def set_leverage(self, symbol: str, leverage: int) -> bool:
        return True  # no-op in paper mode

    # ── Reconciliation ──────────────────────────────────────────────────

    def sync_state(self, db: Session, agent: TradingAgent) -> Dict:
        return {}  # DB is the single source of truth in paper mode

    # ── Metadata ────────────────────────────────────────────────────────

    @property
    def mode(self) -> str:
        return "paper"
