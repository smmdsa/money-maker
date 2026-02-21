"""
Main FastAPI application
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, distinct
from typing import List, Optional
from datetime import datetime, timedelta
import logging
import asyncio
import threading
import fcntl
import sys
import os
import atexit
from zoneinfo import ZoneInfo
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from backend.database import get_db, init_db
from backend.models.database import TradingAgent, Portfolio, Trade, Decision, NewsEvent, PortfolioSnapshot
from backend.services.market_data import MarketDataService
from backend.services.trading_agent import TradingAgentService
from backend.services.news_service import NewsService
from backend.services.llm_service import LLMService
from backend.services.strategies import STRATEGIES
from backend.services.backtester import Backtester
from backend.services.ws_monitor import BinanceWSManager
from backend.services.market_data import BinanceProvider
from backend.services.risk_monitor import ReactiveRiskMonitor
from backend.services.execution import PaperExchangeAdapter, CCXTExchangeAdapter
from pydantic import BaseModel

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ── Adapter factory (reads EXECUTION_MODE from env) ─────────────────────

def _build_exchange_adapter():
    """Create the appropriate ExchangeAdapter based on EXECUTION_MODE env var.

    Values: 'paper' (default) | 'testnet' | 'live'
    testnet/live require BINANCE_API_KEY and BINANCE_API_SECRET.
    """
    mode = os.getenv("EXECUTION_MODE", "paper").lower().strip()

    if mode == "paper":
        logger.info("Execution mode: PAPER (simulated)")
        return PaperExchangeAdapter()

    api_key = os.getenv("BINANCE_API_KEY", "")
    api_secret = os.getenv("BINANCE_API_SECRET", "")

    if not api_key or not api_secret:
        logger.warning(
            f"EXECUTION_MODE={mode} but BINANCE_API_KEY/SECRET not set — "
            f"falling back to paper mode"
        )
        return PaperExchangeAdapter()

    if mode == "testnet":
        logger.info("Execution mode: TESTNET (Binance Futures testnet)")
        return CCXTExchangeAdapter(api_key, api_secret, testnet=True)

    if mode == "live":
        logger.info("⚠️  Execution mode: LIVE — REAL MONEY ⚠️")
        return CCXTExchangeAdapter(api_key, api_secret, testnet=False)

    logger.warning(f"Unknown EXECUTION_MODE '{mode}' — falling back to paper")
    return PaperExchangeAdapter()


# Initialize services
market_service = MarketDataService()
llm_service = LLMService()
exchange_adapter = _build_exchange_adapter()
trading_service = TradingAgentService(market_service, llm_service, exchange_adapter=exchange_adapter)
news_service = NewsService()
backtester = Backtester()
ws_manager = BinanceWSManager()
market_service.set_ws_manager(ws_manager)

# Scheduler for background tasks
scheduler = AsyncIOScheduler()

# Reactive risk monitor (initialized at startup, needs trading_lock)
reactive_monitor: Optional[ReactiveRiskMonitor] = None

# Global lock: serializes ALL trading/risk operations so the trading cycle
# (60s) and risk monitor (5s) never modify agent balances concurrently.
# Both threads MUST hold this lock before reading or writing any agent
# balance or portfolio data.
_trading_lock = threading.Lock()

# WebSocket connections manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)

    async def broadcast(self, message: dict):
        """Send message to all live connections, pruning dead ones."""
        dead = []
        for ws in self.active_connections:
            try:
                if ws.client_state.name != "CONNECTED":
                    dead.append(ws)
                    continue
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.active_connections.discard(ws)

manager = ConnectionManager()


# Pydantic models for API
class AgentCreate(BaseModel):
    name: str
    initial_balance: float = 10000.0
    strategy: str = "confluence_master"
    max_leverage: int = 10
    min_leverage: int = 1
    risk_pct_min: float = 0.0
    risk_pct_max: float = 0.0
    trailing_enabled: bool = True


class AgentUpdate(BaseModel):
    status: Optional[str] = None
    name: Optional[str] = None
    strategy: Optional[str] = None
    max_leverage: Optional[int] = None
    min_leverage: Optional[int] = None
    risk_pct_min: Optional[float] = None
    risk_pct_max: Optional[float] = None
    trailing_enabled: Optional[bool] = None
    allowed_symbols: Optional[List[str]] = None


# ── Lifespan (replaces deprecated @app.on_event) ───────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup → yield → shutdown."""
    global reactive_monitor

    # ── Startup ─────────────────────────────────────────────────────
    _acquire_instance_lock()
    logger.info("Starting Money Maker application...")

    init_db()
    _repair_agent_balances()

    await ws_manager.start()

    async def _broadcast_risk_action(action: dict):
        """Broadcast reactive risk actions to frontend clients."""
        await manager.broadcast({
            "type": "risk_alert",
            "decision": action,
            "source": "reactive",
            "timestamp": datetime.utcnow().isoformat()
        })

    reactive_monitor = ReactiveRiskMonitor(
        trading_service=trading_service,
        ws_manager=ws_manager,
        get_db=get_db,
        trading_lock=_trading_lock,
        broadcast_fn=_broadcast_risk_action,
    )
    await reactive_monitor.start()

    scheduler.add_job(run_trading_cycle, 'interval', seconds=60, id='trading_cycle')
    scheduler.add_job(run_risk_monitor, 'interval', seconds=5, id='risk_monitor')
    scheduler.add_job(broadcast_ws_prices, 'interval', seconds=3, id='ws_price_broadcast')
    scheduler.add_job(sync_kline_subscriptions, 'interval', seconds=60, id='kline_sync',
                      next_run_time=datetime.utcnow() + timedelta(seconds=10))
    scheduler.start()

    logger.info(
        "Application started — Trading: 60s | Risk: 5s (fallback) | "
        "Reactive risk: 1s (event-driven) | WS broadcast: 3s | Kline sync: 60s"
    )

    yield

    # ── Shutdown ────────────────────────────────────────────────────
    logger.info("Shutting down...")
    if reactive_monitor:
        reactive_monitor.stop()
    await ws_manager.stop()
    scheduler.shutdown()


# Initialize FastAPI app with lifespan
app = FastAPI(title="Money Maker - AI Trading Bot", version="1.0.0", lifespan=lifespan)


# API Endpoints

@app.get("/")
async def read_root():
    """Serve the main dashboard"""
    with open("static/index.html", "r") as f:
        return HTMLResponse(content=f.read())


@app.post("/api/agents", response_model=dict)
def create_agent(agent: AgentCreate, db: Session = Depends(get_db)):
    """Create a new trading agent"""
    # Check if agent name already exists
    if agent.initial_balance < 50:
        raise HTTPException(status_code=400, detail="Minimum initial balance is $50 USD")
    if agent.strategy not in STRATEGIES:
        raise HTTPException(status_code=400, detail=f"Unknown strategy: {agent.strategy}")
    if agent.max_leverage < 1 or agent.max_leverage > 125:
        raise HTTPException(status_code=400, detail="Max leverage must be 1-125")
    if agent.min_leverage < 1 or agent.min_leverage > agent.max_leverage:
        raise HTTPException(status_code=400, detail="Min leverage must be 1 to max_leverage")
    if agent.risk_pct_max > 0 and agent.risk_pct_min > agent.risk_pct_max:
        raise HTTPException(status_code=400, detail="risk_pct_min must be <= risk_pct_max")
    
    existing = db.query(TradingAgent).filter(TradingAgent.name == agent.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Agent name already exists")
    
    new_agent = TradingAgent(
        name=agent.name,
        initial_balance=agent.initial_balance,
        current_balance=agent.initial_balance,
        status="active",
        strategy=agent.strategy,
        max_leverage=agent.max_leverage,
        min_leverage=agent.min_leverage,
        risk_pct_min=agent.risk_pct_min,
        risk_pct_max=agent.risk_pct_max,
        trailing_enabled=agent.trailing_enabled,
    )
    db.add(new_agent)
    db.commit()
    db.refresh(new_agent)
    
    return {
        "id": new_agent.id,
        "name": new_agent.name,
        "initial_balance": new_agent.initial_balance,
        "current_balance": new_agent.current_balance,
        "status": new_agent.status,
        "strategy": new_agent.strategy,
        "max_leverage": new_agent.max_leverage,
        "min_leverage": new_agent.min_leverage,
        "risk_pct_min": new_agent.risk_pct_min,
        "risk_pct_max": new_agent.risk_pct_max,
        "trailing_enabled": getattr(new_agent, 'trailing_enabled', True),
        "allowed_symbols": getattr(new_agent, 'allowed_symbols', None),
        "created_at": new_agent.created_at.isoformat()
    }


@app.get("/api/agents")
def list_agents(db: Session = Depends(get_db)):
    """List all trading agents"""
    agents = db.query(TradingAgent).all()
    result = []
    
    for agent in agents:
        # Calculate total portfolio value (unrealized PnL)
        portfolio_value = 0
        for item in agent.portfolio:
            current_price = market_service.get_coin_price(item.cryptocurrency)
            if current_price:
                item.current_price = current_price
                if item.position_type == "long":
                    unrealized = item.amount * (current_price - item.avg_buy_price)
                else:
                    unrealized = item.amount * (item.avg_buy_price - current_price)
                portfolio_value += item.margin + unrealized
        
        total_value = agent.current_balance + portfolio_value
        profit_loss = total_value - agent.initial_balance
        profit_loss_pct = (profit_loss / agent.initial_balance * 100) if agent.initial_balance > 0 else 0
        
        # Lightweight positions for frontend reactive PnL recalculation
        positions = []
        for item in agent.portfolio:
            if item.amount > 0:
                positions.append({
                    "symbol": item.symbol,
                    "amount": item.amount,
                    "avg_buy_price": item.avg_buy_price,
                    "position_type": item.position_type,
                    "margin": item.margin,
                    "leverage": item.leverage,
                })

        result.append({
            "id": agent.id,
            "name": agent.name,
            "initial_balance": agent.initial_balance,
            "current_balance": agent.current_balance,
            "portfolio_value": portfolio_value,
            "total_value": total_value,
            "profit_loss": profit_loss,
            "profit_loss_pct": profit_loss_pct,
            "status": agent.status,
            "strategy": agent.strategy,
            "max_leverage": agent.max_leverage,
            "execution_mode": exchange_adapter.mode,
            "open_positions": len(positions),
            "positions": positions,
            "created_at": agent.created_at.isoformat(),
            "updated_at": agent.updated_at.isoformat()
        })
    
    db.commit()
    return result


@app.get("/api/agents/{agent_id}")
def get_agent(agent_id: int, db: Session = Depends(get_db)):
    """Get detailed information about a specific agent"""
    agent = db.query(TradingAgent).filter(TradingAgent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    # Update portfolio prices and calculate unrealized PnL
    portfolio_items = []
    portfolio_value = 0
    
    for item in agent.portfolio:
        current_price = market_service.get_coin_price(item.cryptocurrency)
        if current_price:
            item.current_price = current_price
            if item.position_type == "long":
                unrealized = item.amount * (current_price - item.avg_buy_price)
            else:
                unrealized = item.amount * (item.avg_buy_price - current_price)
            position_equity = item.margin + unrealized
            portfolio_value += position_equity
            pnl_pct = (unrealized / item.margin * 100) if item.margin > 0 else 0
            
            portfolio_items.append({
                "id": item.id,
                "cryptocurrency": item.cryptocurrency,
                "symbol": item.symbol,
                "amount": item.amount,
                "avg_buy_price": item.avg_buy_price,
                "current_price": current_price,
                "position_type": item.position_type,
                "leverage": item.leverage,
                "margin": item.margin,
                "value": position_equity,
                "profit_loss": unrealized,
                "profit_loss_pct": pnl_pct,
                "liquidation_price": item.liquidation_price,
                "stop_loss_price": item.stop_loss_price,
                "take_profit_price": item.take_profit_price,
                "trailing_stop_pct": getattr(item, 'trailing_stop_pct', 0) or 0,
                "price_extreme": getattr(item, 'price_extreme', 0) or 0,
            })
    
    total_value = agent.current_balance + portfolio_value
    
    db.commit()
    
    return {
        "id": agent.id,
        "name": agent.name,
        "initial_balance": agent.initial_balance,
        "current_balance": agent.current_balance,
        "portfolio_value": portfolio_value,
        "total_value": total_value,
        "profit_loss": total_value - agent.initial_balance,
        "profit_loss_pct": ((total_value - agent.initial_balance) / agent.initial_balance * 100) if agent.initial_balance > 0 else 0,
        "status": agent.status,
        "strategy": agent.strategy,
        "max_leverage": agent.max_leverage,
        "min_leverage": getattr(agent, 'min_leverage', 1),
        "risk_pct_min": getattr(agent, 'risk_pct_min', 0),
        "risk_pct_max": getattr(agent, 'risk_pct_max', 0),
        "trailing_enabled": getattr(agent, 'trailing_enabled', True),
        "allowed_symbols": getattr(agent, 'allowed_symbols', None),
        "execution_mode": exchange_adapter.mode,
        "portfolio": portfolio_items,
        "created_at": agent.created_at.isoformat()
    }


@app.post("/api/agents/{agent_id}/positions/{position_id}/close")
def close_position(agent_id: int, position_id: int, db: Session = Depends(get_db)):
    """Manually close a single position"""
    agent = db.query(TradingAgent).filter(TradingAgent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    pos = db.query(Portfolio).filter(
        Portfolio.id == position_id, Portfolio.agent_id == agent_id
    ).first()
    if not pos:
        raise HTTPException(status_code=404, detail="Position not found")
    try:
        with _trading_lock:
            db.refresh(agent)
            db.refresh(pos)
            result = trading_service.close_position_manual(agent, pos, db)
        # Refresh reactive watchlist immediately after close
        if reactive_monitor:
            reactive_monitor.refresh()
        return {"status": "closed", **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/agents/{agent_id}/positions/close-all")
def close_all_positions(agent_id: int, db: Session = Depends(get_db)):
    """Manually close all open positions for an agent"""
    agent = db.query(TradingAgent).filter(TradingAgent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    with _trading_lock:
        db.refresh(agent)
        positions = [p for p in agent.portfolio if p.amount > 0]
        if not positions:
            raise HTTPException(status_code=400, detail="No open positions")
        results = []
        for pos in positions:
            try:
                result = trading_service.close_position_manual(agent, pos, db)
                results.append(result)
            except Exception as e:
                results.append({"coin": pos.cryptocurrency, "error": str(e)})
    # Refresh reactive watchlist immediately after close-all
    if reactive_monitor:
        reactive_monitor.refresh()
    return {"status": "closed", "count": len(results), "results": results}


@app.patch("/api/agents/{agent_id}")
def update_agent(agent_id: int, update: AgentUpdate, db: Session = Depends(get_db)):
    """Update agent settings (status, strategy, leverage, risk, tokens, etc.)"""
    agent = db.query(TradingAgent).filter(TradingAgent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    if update.status is not None:
        if update.status not in ["active", "paused", "stopped"]:
            raise HTTPException(status_code=400, detail="Invalid status")
        agent.status = update.status

    if update.name is not None:
        existing = db.query(TradingAgent).filter(
            TradingAgent.name == update.name, TradingAgent.id != agent_id
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="Agent name already exists")
        agent.name = update.name

    if update.strategy is not None:
        if update.strategy not in STRATEGIES:
            raise HTTPException(status_code=400, detail=f"Unknown strategy: {update.strategy}")
        agent.strategy = update.strategy

    if update.max_leverage is not None:
        if update.max_leverage < 1 or update.max_leverage > 125:
            raise HTTPException(status_code=400, detail="Max leverage must be 1-125")
        agent.max_leverage = update.max_leverage

    if update.min_leverage is not None:
        if update.min_leverage < 1:
            raise HTTPException(status_code=400, detail="Min leverage must be >= 1")
        agent.min_leverage = update.min_leverage

    if update.risk_pct_min is not None:
        agent.risk_pct_min = update.risk_pct_min

    if update.risk_pct_max is not None:
        agent.risk_pct_max = update.risk_pct_max

    if update.trailing_enabled is not None:
        agent.trailing_enabled = update.trailing_enabled

    if update.allowed_symbols is not None:
        agent.allowed_symbols = update.allowed_symbols if update.allowed_symbols else None

    agent.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(agent)

    # Agent status/settings change may affect reactive watchlist
    if reactive_monitor:
        reactive_monitor.refresh()

    return {"message": "Agent updated successfully", "status": agent.status}


@app.delete("/api/agents/{agent_id}")
def delete_agent(agent_id: int, db: Session = Depends(get_db)):
    """Delete a trading agent"""
    agent = db.query(TradingAgent).filter(TradingAgent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    db.delete(agent)
    db.commit()
    
    return {"message": "Agent deleted successfully"}


@app.get("/api/agents/{agent_id}/trades")
def get_agent_trades(
    agent_id: int,
    limit: int = 50,
    offset: int = 0,
    symbol: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get trading history for an agent with optional filters"""
    query = db.query(Trade).filter(Trade.agent_id == agent_id)
    
    # Apply filters
    if symbol:
        query = query.filter(Trade.symbol == symbol)
    if from_date:
        try:
            fd = datetime.fromisoformat(from_date)
            query = query.filter(Trade.timestamp >= fd)
        except ValueError:
            pass
    if to_date:
        try:
            td = datetime.fromisoformat(to_date)
            # Include the entire end day
            td = td.replace(hour=23, minute=59, second=59)
            query = query.filter(Trade.timestamp <= td)
        except ValueError:
            pass
    
    # Get total count and PnL summary before pagination
    total = query.count()
    summary_row = query.with_entities(
        func.sum(Trade.profit_loss),
        func.count(Trade.id)
    ).first()
    
    total_pnl = summary_row[0] or 0.0
    
    # Winning / losing trades (only count closing trades with non-zero PnL)
    winning = query.filter(Trade.profit_loss > 0).count()
    losing = query.filter(Trade.profit_loss < 0).count()
    
    # Fetch paginated trades
    trades = query.order_by(
        Trade.timestamp.desc()
    ).offset(offset).limit(limit).all()
    
    return {
        "trades": [{
            "id": t.id,
            "cryptocurrency": t.cryptocurrency,
            "symbol": t.symbol,
            "trade_type": t.trade_type,
            "amount": t.amount,
            "price": t.price,
            "total_value": t.total_value,
            "profit_loss": t.profit_loss,
            "leverage": t.leverage,
            "margin": t.margin,
            "decision_id": t.decision_id,
            "timestamp": t.timestamp.isoformat()
        } for t in trades],
        "total": total,
        "summary": {
            "total_pnl": round(total_pnl, 4),
            "winning_trades": winning,
            "losing_trades": losing,
            "total_trades": total
        }
    }


@app.get("/api/agents/{agent_id}/traded-tokens")
def get_traded_tokens(agent_id: int, db: Session = Depends(get_db)):
    """Get list of unique tokens traded by an agent"""
    tokens = db.query(distinct(Trade.symbol)).filter(
        Trade.agent_id == agent_id
    ).order_by(Trade.symbol).all()
    return [t[0] for t in tokens]


@app.get("/api/decisions/{decision_id}")
def get_decision_detail(decision_id: int, db: Session = Depends(get_db)):
    """Get a single decision by ID (for trade → decision modal)"""
    d = db.query(Decision).filter(Decision.id == decision_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Decision not found")
    return {
        "id": d.id,
        "agent_id": d.agent_id,
        "cryptocurrency": d.cryptocurrency,
        "decision_type": d.decision_type,
        "reasoning": d.reasoning,
        "llm_reasoning": d.llm_reasoning,
        "llm_sentiment_adj": d.llm_sentiment_adj,
        "action_taken": d.action_taken,
        "confidence": d.confidence,
        "indicators": d.indicators,
        "news_considered": d.news_considered,
        "strategy": d.strategy,
        "timestamp": d.timestamp.isoformat()
    }


@app.get("/api/agents/{agent_id}/decisions")
def get_agent_decisions(agent_id: int, limit: int = 50, db: Session = Depends(get_db)):
    """Get AI decision history for an agent"""
    decisions = db.query(Decision).filter(Decision.agent_id == agent_id).order_by(
        Decision.timestamp.desc()
    ).limit(limit).all()
    
    return [{
        "id": d.id,
        "cryptocurrency": d.cryptocurrency,
        "decision_type": d.decision_type,
        "reasoning": d.reasoning,
        "llm_reasoning": d.llm_reasoning,
        "llm_sentiment_adj": d.llm_sentiment_adj,
        "action_taken": d.action_taken,
        "confidence": d.confidence,
        "indicators": d.indicators,
        "news_considered": d.news_considered,
        "strategy": d.strategy,
        "timestamp": d.timestamp.isoformat()
    } for d in decisions]


@app.get("/api/supported-coins")
def get_supported_coins():
    """Get list of all supported coins with their symbols"""
    from backend.services.market_data import BinanceProvider
    result = []
    for coin_id in market_service.supported_coins:
        sym = BinanceProvider.SYMBOL_MAP.get(coin_id, "")
        ticker = sym.replace("USDT", "").replace("1000", "") if sym else coin_id[:3].upper()
        result.append({
            "id": coin_id,
            "symbol": ticker,
            "name": coin_id.replace("-", " ").replace("2", "").title().strip(),
        })
    return result


@app.get("/api/market/prices")
def get_market_prices():
    """Get current market prices for all supported coins"""
    # Use batch endpoint — single API call for all coins
    result = market_service.get_all_market_data()
    provider = market_service.get_provider()

    if result:
        return {"provider": provider, "data": result}
    
    # Fallback: build from individual prices
    prices = market_service.get_current_prices()
    return {"provider": provider, "data": [
        {"id": coin, "current_price": price, "symbol": coin[:3].upper()}
        for coin, price in prices.items()
    ]}


@app.get("/api/strategies")
def get_strategies():
    """Get all available trading strategies"""
    return {
        key: {
            "key": cfg.key,
            "name": cfg.name,
            "description": cfg.description,
            "style": cfg.style,
            "default_leverage": cfg.default_leverage,
            "max_leverage": cfg.max_leverage,
            "max_positions": cfg.max_positions,
            "risk_per_trade_pct": cfg.risk_per_trade_pct,
            "min_confidence": cfg.min_confidence,
        }
        for key, cfg in STRATEGIES.items()
    }


@app.get("/api/ws/status")
def ws_status():
    """Binance WebSocket connection status and statistics"""
    return ws_manager.health_check()


@app.get("/api/market/hours")
def market_hours():
    """Get current status of major world stock markets"""
    return get_market_hours_context()


@app.get("/api/market/{coin}")
def get_coin_data(coin: str):
    """Get detailed data for a specific coin"""
    data = market_service.get_market_data(coin)
    if not data:
        raise HTTPException(status_code=404, detail="Coin not found")
    return data


@app.get("/api/market/{coin}/ohlc")
def get_coin_ohlc(coin: str, days: int = 14):
    """Get OHLC candlestick data for charting"""
    data = market_service.get_ohlc(coin, days=days)
    if not data:
        raise HTTPException(status_code=404, detail="No OHLC data available")
    return [{"time": int(d["timestamp"].timestamp()), "open": d["open"],
             "high": d["high"], "low": d["low"], "close": d["close"]} for d in data]


@app.get("/api/market/{coin}/ohlc-interval")
def get_coin_ohlc_interval(coin: str, interval: str = "5m", limit: int = 100):
    """Get OHLC candlestick data by specific interval (1m, 3m, 5m, 15m, 1h, 4h, 1d)."""
    allowed = {"1m", "3m", "5m", "15m", "1h", "4h", "1d"}
    if interval not in allowed:
        raise HTTPException(status_code=400, detail=f"Invalid interval. Allowed: {', '.join(sorted(allowed))}")
    limit = max(10, min(limit, 500))
    data = market_service.get_ohlc_interval(coin, interval=interval, limit=limit)
    if not data:
        raise HTTPException(status_code=404, detail="No OHLC data available")
    return [{"time": int(d["timestamp"].timestamp()), "open": d["open"],
             "high": d["high"], "low": d["low"], "close": d["close"]} for d in data]


@app.get("/api/market/{coin}/history")
def get_coin_history(coin: str, days: int = 30):
    """Get historical price data for line charts"""
    data = market_service.get_historical_prices(coin, days=days)
    if not data:
        raise HTTPException(status_code=404, detail="No historical data available")
    return [{"time": int(d["timestamp"].timestamp()), "value": d["price"]} for d in data]


@app.get("/api/agents/{agent_id}/equity")
def get_agent_equity(agent_id: int, db: Session = Depends(get_db)):
    """Get equity curve data for an agent"""
    snapshots = db.query(PortfolioSnapshot).filter(
        PortfolioSnapshot.agent_id == agent_id
    ).order_by(PortfolioSnapshot.timestamp.asc()).all()

    return [{
        "time": int(s.timestamp.timestamp()),
        "value": s.total_value,
        "cash": s.cash_balance,
        "portfolio": s.portfolio_value
    } for s in snapshots]


@app.get("/api/news")
def get_news(hours: int = 24, coin: Optional[str] = None, db: Session = Depends(get_db)):
    """Get recent news events"""
    news_items = news_service.get_recent_news(db, hours=hours, coin=coin)
    sentiment = news_service.analyze_sentiment(news_items)
    
    return {
        "sentiment": sentiment,
        "news": [{
            "id": n.id,
            "title": n.title,
            "description": n.description,
            "source": n.source,
            "cryptocurrency": n.cryptocurrency,
            "sentiment": n.sentiment,
            "impact_score": n.impact_score,
            "timestamp": n.timestamp.isoformat(),
            "url": n.url
        } for n in news_items]
    }


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket for real-time updates"""
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        manager.disconnect(websocket)


# Background tasks

async def broadcast_ws_prices():
    """Push real-time prices to frontend via WebSocket every 3 seconds.
    Only runs when Binance WS is connected AND frontend clients are connected.
    """
    if not ws_manager.is_connected or not manager.active_connections:
        return

    all_prices = ws_manager.get_all_mark_prices()
    if not all_prices:
        return

    # Convert Binance symbols → coin IDs for the frontend
    prices = {}
    funding = {}
    for coin in market_service.supported_coins:
        sym = BinanceProvider.SYMBOL_MAP.get(coin)
        if sym and sym in all_prices:
            prices[coin] = all_prices[sym]
            fr = ws_manager.get_funding_rate(sym)
            if fr is not None:
                funding[coin] = fr

    if prices:
        await manager.broadcast({
            "type": "price_update",
            "prices": prices,
            "funding_rates": funding,
            "source": "websocket",
            "timestamp": datetime.utcnow().isoformat()
        })


async def sync_kline_subscriptions():
    """Subscribe to kline WebSocket streams for symbols with open positions.
    Runs every 60s to keep subscriptions aligned with active trading.
    """
    if not ws_manager.is_connected:
        return

    try:
        db = next(get_db())
        agents = db.query(TradingAgent).filter(
            TradingAgent.status == "active"
        ).all()

        needed = set()
        for agent in agents:
            cfg = STRATEGIES.get(agent.strategy)
            interval = cfg.kline_interval if cfg else ""
            if not interval:
                continue

            for pos in agent.portfolio:
                if pos.amount > 0:
                    sym = BinanceProvider.SYMBOL_MAP.get(pos.cryptocurrency)
                    if sym:
                        needed.add(f"{sym}_{interval}")

        await ws_manager.sync_kline_subscriptions(needed)
        db.close()
    except Exception as e:
        logger.error(f"Kline subscription sync error: {e}")


async def run_risk_monitor():
    """Lightweight risk check every 5 seconds.
    Only checks SL/TP/liquidation on open positions — no indicators, no strategies.
    """
    def _sync_risk_check():
        if not _trading_lock.acquire(blocking=False):
            # Trading cycle is running — skip this tick, we'll check in 5s
            return []
        try:
            db = next(get_db())
            actions = trading_service.check_risk_all_agents(db)
            db.close()
            return actions
        except Exception as e:
            logger.error(f"Risk monitor error: {e}")
            return []
        finally:
            _trading_lock.release()

    actions = await asyncio.to_thread(_sync_risk_check)

    # Broadcast any closes triggered by the risk monitor
    for action in (actions or []):
        await manager.broadcast({
            "type": "risk_alert",
            "decision": action,
            "timestamp": datetime.utcnow().isoformat()
        })


async def run_trading_cycle():
    """Background task to run trading for all active agents.
    All blocking market/DB calls are offloaded to a thread pool
    so the asyncio event loop is never blocked.
    """
    logger.info("Running trading cycle...")

    def _sync_trading_cycle():
        """Synchronous work executed in a thread pool."""
        with _trading_lock:
            try:
                db = next(get_db())

                # Fetch real news from APIs
                news_service.fetch_and_store_news(db)

                # Get all active agents
                agents = db.query(TradingAgent).filter(TradingAgent.status == "active").all()

                decisions_made = []
                for agent in agents:
                    try:
                        # Make trading decision
                        decision = trading_service.make_trading_decision(agent, db)
                        if decision:
                            decisions_made.append((agent.id, agent.name, decision))

                        # Record portfolio snapshot for equity curve
                        portfolio_value = 0
                        for item in agent.portfolio:
                            price = market_service.get_coin_price(item.cryptocurrency)
                            if price:
                                if item.position_type == "long":
                                    unrealized = item.amount * (price - item.avg_buy_price)
                                else:
                                    unrealized = item.amount * (item.avg_buy_price - price)
                                portfolio_value += item.margin + unrealized

                        snapshot = PortfolioSnapshot(
                            agent_id=agent.id,
                            total_value=agent.current_balance + portfolio_value,
                            cash_balance=agent.current_balance,
                            portfolio_value=portfolio_value
                        )
                        db.add(snapshot)

                    except Exception as e:
                        logger.error(f"Error processing agent {agent.id}: {e}")

                db.commit()
                db.close()
                return decisions_made

            except Exception as e:
                logger.error(f"Error in trading cycle: {e}")
                return []

    # Run all blocking I/O in a thread so we don't block the event loop
    decisions = await asyncio.to_thread(_sync_trading_cycle)

    # Refresh reactive watchlist — trading cycle may have opened/closed positions
    if reactive_monitor:
        reactive_monitor.refresh()

    # Broadcast results back on the event loop
    for agent_id, agent_name, decision in (decisions or []):
        await manager.broadcast({
            "type": "trade_update",
            "agent_id": agent_id,
            "agent_name": agent_name,
            "decision": decision,
            "timestamp": datetime.utcnow().isoformat()
        })


@app.get("/api/health")
def health_check():
    """Check API and service health"""
    return {
        "status": "ok",
        "execution_mode": exchange_adapter.mode,
        "market_service": market_service.health_check(),
        "llm_service": llm_service.health_check(),
        "websocket": ws_manager.health_check(),
        "reactive_risk": reactive_monitor.health_check() if reactive_monitor else None,
        "timestamp": datetime.utcnow().isoformat()
    }


# ── Balance Repair ────────────────────────────────────────────────────────


# ── Exchange Balance & Connection ─────────────────────────────────────────

@app.get("/api/exchange/balance")
def exchange_balance():
    """Return detailed exchange balance with per-asset breakdown.

    In paper mode, returns the aggregate of local agent balances.
    In testnet/live, fetches real data from Binance Futures.
    """
    mode = exchange_adapter.mode
    if mode == "paper":
        db = next(get_db())
        try:
            from backend.models.database import TradingAgent as TA
            agents = db.query(TA).all()
            total_bal = sum(a.current_balance for a in agents)
            total_margin = sum(
                sum(p.margin for p in a.portfolio if p.amount > 0)
                for a in agents
            )
            return {
                "mode": "paper",
                "total": round(total_bal + total_margin, 2),
                "available": round(total_bal, 2),
                "margin_used": round(total_margin, 2),
                "unrealized_pnl": 0.0,
                "assets": {},
            }
        finally:
            db.close()

    try:
        # Use a dummy agent — real CCXT adapter reads from exchange, not DB
        dummy = type('A', (), {'portfolio': [], 'current_balance': 0})()
        bal = exchange_adapter.get_balance(dummy)
        return {
            "mode": mode,
            "total": round(bal.total, 4),
            "available": round(bal.available, 4),
            "margin_used": round(bal.margin_used, 4),
            "unrealized_pnl": round(bal.unrealized_pnl, 4),
            "assets": bal.assets,
        }
    except Exception as exc:
        return {"mode": mode, "error": str(exc)}


@app.get("/api/exchange/status")
def exchange_status():
    """Return current execution mode and connection status."""
    return {
        "mode": exchange_adapter.mode,
        "testnet": getattr(exchange_adapter, '_testnet', None),
        "has_api_keys": bool(getattr(exchange_adapter, '_api_key', '')),
    }


@app.post("/api/exchange/test-connection")
def test_exchange_connection():
    """Test connectivity to the configured exchange.

    Only meaningful in testnet/live mode. In paper mode returns OK immediately.
    """
    mode = exchange_adapter.mode
    if mode == "paper":
        return {"status": "ok", "mode": "paper", "message": "Paper mode — no exchange connection needed"}

    try:
        balance = exchange_adapter.get_balance(
            type('FakeAgent', (), {'portfolio': [], 'current_balance': 0})()
        )
        return {
            "status": "ok",
            "mode": mode,
            "balance": {
                "total": balance.total,
                "available": balance.available,
                "margin_used": balance.margin_used,
                "unrealized_pnl": balance.unrealized_pnl,
                "assets": balance.assets,
            },
            "message": f"Connected to Binance Futures ({'testnet' if mode == 'testnet' else 'mainnet'})",
        }
    except Exception as exc:
        return {
            "status": "error",
            "mode": mode,
            "message": str(exc),
        }


# ── Kill Switch ───────────────────────────────────────────────────────────

@app.post("/api/exchange/kill-switch")
def kill_switch(db: Session = Depends(get_db)):
    """EMERGENCY: Close ALL positions across ALL agents immediately.

    Works in any execution mode. In testnet/live, also sends market close
    orders to the exchange.
    """
    with _trading_lock:
        agents = db.query(TradingAgent).filter(
            TradingAgent.status == "active"
        ).all()

        total_closed = 0
        errors = []

        for agent in agents:
            db.refresh(agent)
            positions = [p for p in agent.portfolio if p.amount > 0]
            for pos in positions:
                try:
                    current_price = market_service.get_coin_price(pos.cryptocurrency)
                    if not current_price:
                        current_price = pos.current_price or pos.avg_buy_price
                    trading_service._close_position(
                        agent, pos, current_price, db,
                        reason="🚨 KILL SWITCH — emergency close",
                        strategy_key=agent.strategy or "confluence_master",
                    )
                    total_closed += 1
                except Exception as exc:
                    errors.append({
                        "agent": agent.name,
                        "coin": pos.cryptocurrency,
                        "error": str(exc),
                    })

    # Refresh reactive watchlist after mass close
    if reactive_monitor:
        reactive_monitor.refresh()

    logger.warning(
        f"🚨 KILL SWITCH activated — closed {total_closed} position(s), "
        f"{len(errors)} error(s)"
    )

    return {
        "status": "executed",
        "positions_closed": total_closed,
        "errors": errors,
    }

def _repair_agent_balances():
    """Replay all trades to detect and fix agent balances corrupted by
    past race conditions between the trading-cycle and risk-monitor threads.
    Safe to run on every startup — it only touches agents whose computed
    balance diverges from the stored value.
    """
    db = next(get_db())
    try:
        agents = db.query(TradingAgent).all()
        for agent in agents:
            trades = db.query(Trade).filter(
                Trade.agent_id == agent.id
            ).order_by(Trade.timestamp.asc(), Trade.id.asc()).all()

            balance = agent.initial_balance
            for t in trades:
                if t.trade_type.startswith("open_"):
                    balance -= t.margin
                else:
                    balance += max(t.margin + t.profit_loss, 0)

            diff = abs(balance - agent.current_balance)
            if diff > 0.01:
                logger.warning(
                    f"Balance repair: {agent.name} — "
                    f"stored ${agent.current_balance:.4f} → "
                    f"correct ${balance:.4f} (Δ ${diff:.2f})"
                )
                agent.current_balance = balance

        db.commit()
    except Exception as e:
        logger.error(f"Balance repair failed: {e}")
    finally:
        db.close()


@app.post("/api/repair-balances")
def repair_balances_endpoint(db: Session = Depends(get_db)):
    """Manually trigger balance repair for all agents."""
    agents = db.query(TradingAgent).all()
    results = []

    for agent in agents:
        trades = db.query(Trade).filter(
            Trade.agent_id == agent.id
        ).order_by(Trade.timestamp.asc(), Trade.id.asc()).all()

        balance = agent.initial_balance
        for t in trades:
            if t.trade_type.startswith("open_"):
                balance -= t.margin
            else:
                balance += max(t.margin + t.profit_loss, 0)

        diff = abs(balance - agent.current_balance)
        if diff > 0.01:
            results.append({
                "agent": agent.name,
                "old_balance": round(agent.current_balance, 4),
                "correct_balance": round(balance, 4),
                "difference": round(diff, 2),
                "status": "repaired",
            })
            agent.current_balance = balance
        else:
            results.append({
                "agent": agent.name,
                "balance": round(agent.current_balance, 4),
                "status": "ok",
            })

    db.commit()
    repaired = [r for r in results if r["status"] == "repaired"]
    return {
        "total_agents": len(results),
        "repaired": len(repaired),
        "details": results,
    }


# ── Market Hours ──────────────────────────────────────────────────────────

WORLD_MARKETS = [
    {"id": "nyse",   "name": "NYSE",      "tz": "America/New_York",  "open": (9,30),  "close": (16,0),  "pre": (4,0)},
    {"id": "nasdaq", "name": "NASDAQ",    "tz": "America/New_York",  "open": (9,30),  "close": (16,0),  "pre": (4,0)},
    {"id": "lse",    "name": "London",    "tz": "Europe/London",     "open": (8,0),   "close": (16,30), "pre": (7,0)},
    {"id": "xetra",  "name": "Frankfurt", "tz": "Europe/Berlin",     "open": (9,0),   "close": (17,30), "pre": (8,0)},
    {"id": "tse",    "name": "Tokyo",     "tz": "Asia/Tokyo",        "open": (9,0),   "close": (15,0),  "pre": (8,0)},
    {"id": "sse",    "name": "Shanghai",  "tz": "Asia/Shanghai",     "open": (9,30),  "close": (15,0),  "pre": (9,15)},
    {"id": "hkex",   "name": "Hong Kong", "tz": "Asia/Hong_Kong",    "open": (9,30),  "close": (16,0),  "pre": (9,0)},
    {"id": "asx",    "name": "Sydney",    "tz": "Australia/Sydney",  "open": (10,0),  "close": (16,0),  "pre": (7,0)},
]


def get_market_hours_context() -> list:
    """Return current status of all major markets. Used by trading agent for context."""
    results = []
    for mkt in WORLD_MARKETS:
        tz = ZoneInfo(mkt["tz"])
        now = datetime.now(tz)
        weekday = now.weekday()  # 0=Mon, 5=Sat, 6=Sun
        now_min = now.hour * 60 + now.minute
        open_min = mkt["open"][0] * 60 + mkt["open"][1]
        close_min = mkt["close"][0] * 60 + mkt["close"][1]
        pre_min = mkt["pre"][0] * 60 + mkt["pre"][1]

        is_weekend = weekday >= 5

        if is_weekend:
            status = "closed"
            session_pct = 0
        elif open_min <= now_min < close_min:
            status = "open"
            session_pct = round((now_min - open_min) / (close_min - open_min) * 100)
        elif pre_min <= now_min < open_min:
            status = "pre-market"
            session_pct = 0
        else:
            status = "closed"
            session_pct = 0

        results.append({
            "id": mkt["id"],
            "name": mkt["name"],
            "status": status,
            "local_time": now.strftime("%H:%M"),
            "session_pct": session_pct,
        })
    return results


# ── Backtesting ───────────────────────────────────────────────────────────

class BacktestRequest(BaseModel):
    strategy: str
    coin: str
    period_days: int = 90
    leverage: int = 0          # 0 = use strategy default
    initial_balance: float = 10000.0
    trailing_enabled: bool = True


@app.post("/api/backtest")
async def run_backtest(req: BacktestRequest):
    """Run a backtest simulation. This may take several seconds."""
    if req.strategy not in STRATEGIES:
        raise HTTPException(status_code=400, detail=f"Unknown strategy: {req.strategy}")
    if req.coin not in ["bitcoin", "ethereum", "binancecoin", "cardano",
                        "solana", "ripple", "polkadot", "dogecoin"]:
        raise HTTPException(status_code=400, detail=f"Unsupported coin: {req.coin}")
    if not (1 <= req.period_days <= 365):
        raise HTTPException(status_code=400, detail="Period must be between 1 and 365 days")
    if req.initial_balance < 50:
        raise HTTPException(status_code=400, detail="Minimum balance is $50")

    try:
        result = await asyncio.to_thread(
            backtester.run,
            strategy_key=req.strategy,
            coin=req.coin,
            period_days=req.period_days,
            leverage=req.leverage,
            initial_balance=req.initial_balance,
            trailing_enabled=req.trailing_enabled,
        )
        return result.__dict__
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Backtest failed: {e}")
        raise HTTPException(status_code=500, detail=f"Backtest error: {str(e)}")


# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")


_lock_file = None

def _acquire_instance_lock():
    """Ensure only ONE server process runs at a time using an OS-level file lock."""
    global _lock_file
    lock_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".server.lock")
    _lock_file = open(lock_path, "w")
    try:
        fcntl.flock(_lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _lock_file.write(str(os.getpid()))
        _lock_file.flush()
        atexit.register(_release_instance_lock)
    except OSError:
        print(f"ERROR: Another server instance is already running. "
              f"Kill it first or delete {lock_path}")
        sys.exit(1)

def _release_instance_lock():
    global _lock_file
    if _lock_file:
        try:
            fcntl.flock(_lock_file, fcntl.LOCK_UN)
            _lock_file.close()
        except Exception:
            pass


if __name__ == "__main__":
    import uvicorn
    _acquire_instance_lock()
    uvicorn.run(app, host="0.0.0.0", port=8001)
