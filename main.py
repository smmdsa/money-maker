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
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from backend.database import get_db, init_db
from backend.models.database import TradingAgent, Portfolio, Trade, Decision, NewsEvent, PortfolioSnapshot
from backend.services.market_data import MarketDataService
from backend.services.trading_agent import TradingAgentService
from backend.services.news_service import NewsService
from backend.services.llm_service import LLMService
from backend.services.strategies import STRATEGIES
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
        "portfolio": portfolio_items,
        "created_at": agent.created_at.isoformat()
    }


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


@app.on_event("startup")
async def startup_event():
    """Initialize database and start scheduler"""
    logger.info("Starting Money Maker application...")
    
    # Initialize database
    init_db()
    
    # Start background scheduler (run every 60 seconds)
    scheduler.add_job(run_trading_cycle, 'interval', seconds=60)
    scheduler.start()
    
    logger.info("Application started successfully")


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
