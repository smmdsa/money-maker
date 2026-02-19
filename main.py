"""
Main FastAPI application
"""
from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timedelta
import logging
import asyncio
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
from pydantic import BaseModel

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(title="Money Maker - AI Trading Bot", version="1.0.0")

# Initialize services
market_service = MarketDataService()
llm_service = LLMService()
trading_service = TradingAgentService(market_service, llm_service)
news_service = NewsService()
backtester = Backtester()

# Scheduler for background tasks
scheduler = AsyncIOScheduler()

# WebSocket connections manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.warning(f"Error broadcasting to WebSocket: {e}")

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


class AgentUpdate(BaseModel):
    status: Optional[str] = None


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
            "open_positions": len([p for p in agent.portfolio if p.amount > 0]),
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
        result = trading_service.close_position_manual(agent, pos, db)
        return {"status": "closed", **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/agents/{agent_id}/positions/close-all")
def close_all_positions(agent_id: int, db: Session = Depends(get_db)):
    """Manually close all open positions for an agent"""
    agent = db.query(TradingAgent).filter(TradingAgent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
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
    return {"status": "closed", "count": len(results), "results": results}


@app.patch("/api/agents/{agent_id}")
def update_agent(agent_id: int, update: AgentUpdate, db: Session = Depends(get_db)):
    """Update agent status (pause/resume/stop)"""
    agent = db.query(TradingAgent).filter(TradingAgent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    if update.status:
        if update.status not in ["active", "paused", "stopped"]:
            raise HTTPException(status_code=400, detail="Invalid status")
        agent.status = update.status
        agent.updated_at = datetime.utcnow()
    
    db.commit()
    db.refresh(agent)
    
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
def get_agent_trades(agent_id: int, limit: int = 50, db: Session = Depends(get_db)):
    """Get trading history for an agent"""
    trades = db.query(Trade).filter(Trade.agent_id == agent_id).order_by(
        Trade.timestamp.desc()
    ).limit(limit).all()
    
    return [{
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
    } for t in trades]


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
            # Keep connection alive
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        manager.disconnect(websocket)


# Background tasks

async def run_risk_monitor():
    """Lightweight risk check every 5 seconds.
    Only checks SL/TP/liquidation on open positions — no indicators, no strategies.
    """
    def _sync_risk_check():
        try:
            db = next(get_db())
            actions = trading_service.check_risk_all_agents(db)
            db.close()
            return actions
        except Exception as e:
            logger.error(f"Risk monitor error: {e}")
            return []

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
        "market_service": market_service.health_check(),
        "llm_service": llm_service.health_check(),
        "timestamp": datetime.utcnow().isoformat()
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


@app.post("/api/backtest")
async def run_backtest(req: BacktestRequest):
    """Run a backtest simulation. This may take several seconds."""
    if req.strategy not in STRATEGIES:
        raise HTTPException(status_code=400, detail=f"Unknown strategy: {req.strategy}")
    if req.coin not in ["bitcoin", "ethereum", "binancecoin", "cardano",
                        "solana", "ripple", "polkadot", "dogecoin"]:
        raise HTTPException(status_code=400, detail=f"Unsupported coin: {req.coin}")
    if req.period_days not in [1, 3, 7, 14, 30, 90, 180, 365]:
        raise HTTPException(status_code=400, detail="Period must be 7, 14, 30, 90, 180, or 365 days")
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
        )
        return result.__dict__
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Backtest failed: {e}")
        raise HTTPException(status_code=500, detail=f"Backtest error: {str(e)}")


@app.on_event("startup")
async def startup_event():
    """Initialize database and start scheduler"""
    logger.info("Starting Money Maker application...")
    
    # Initialize database
    init_db()
    
    # Start background scheduler
    scheduler.add_job(run_trading_cycle, 'interval', seconds=60, id='trading_cycle')
    scheduler.add_job(run_risk_monitor, 'interval', seconds=5, id='risk_monitor')
    scheduler.start()
    
    logger.info("Application started — Trading cycle: 60s | Risk monitor: 5s")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("Shutting down...")
    scheduler.shutdown()


# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
