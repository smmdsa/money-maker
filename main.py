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
from backend.models.database import TradingAgent, Portfolio, Trade, Decision, NewsEvent
from backend.services.market_data import MarketDataService
from backend.services.trading_agent import TradingAgentService
from backend.services.news_service import NewsService
from pydantic import BaseModel

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(title="Money Maker - AI Trading Bot", version="1.0.0")

# Initialize services
market_service = MarketDataService()
trading_service = TradingAgentService(market_service)
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
    existing = db.query(TradingAgent).filter(TradingAgent.name == agent.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Agent name already exists")
    
    new_agent = TradingAgent(
        name=agent.name,
        initial_balance=agent.initial_balance,
        current_balance=agent.initial_balance,
        status="active"
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
        "created_at": new_agent.created_at.isoformat()
    }


@app.get("/api/agents")
def list_agents(db: Session = Depends(get_db)):
    """List all trading agents"""
    agents = db.query(TradingAgent).all()
    result = []
    
    for agent in agents:
        # Calculate total portfolio value
        portfolio_value = 0
        for item in agent.portfolio:
            current_price = market_service.get_coin_price(item.cryptocurrency)
            if current_price:
                item.current_price = current_price
                portfolio_value += item.amount * current_price
        
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
    
    # Update portfolio prices
    portfolio_items = []
    portfolio_value = 0
    
    for item in agent.portfolio:
        current_price = market_service.get_coin_price(item.cryptocurrency)
        if current_price:
            item.current_price = current_price
            value = item.amount * current_price
            portfolio_value += value
            profit_loss = (current_price - item.avg_buy_price) * item.amount
            
            portfolio_items.append({
                "cryptocurrency": item.cryptocurrency,
                "symbol": item.symbol,
                "amount": item.amount,
                "avg_buy_price": item.avg_buy_price,
                "current_price": current_price,
                "value": value,
                "profit_loss": profit_loss,
                "profit_loss_pct": (profit_loss / (item.avg_buy_price * item.amount) * 100) if item.avg_buy_price > 0 else 0
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
        "timestamp": t.timestamp.isoformat()
    } for t in trades]


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
        "action_taken": d.action_taken,
        "confidence": d.confidence,
        "indicators": d.indicators,
        "news_considered": d.news_considered,
        "timestamp": d.timestamp.isoformat()
    } for d in decisions]


@app.get("/api/market/prices")
def get_market_prices():
    """Get current market prices"""
    prices = market_service.get_current_prices()
    result = []
    
    for coin, price in prices.items():
        market_data = market_service.get_market_data(coin)
        if market_data:
            result.append(market_data)
    
    return result


@app.get("/api/market/{coin}")
def get_coin_data(coin: str):
    """Get detailed data for a specific coin"""
    data = market_service.get_market_data(coin)
    if not data:
        raise HTTPException(status_code=404, detail="Coin not found")
    return data


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
    """Background task to run trading for all active agents"""
    logger.info("Running trading cycle...")
    
    try:
        db = next(get_db())
        
        # Generate some news
        news_service.generate_simulated_news(db)
        
        # Get all active agents
        agents = db.query(TradingAgent).filter(TradingAgent.status == "active").all()
        
        for agent in agents:
            try:
                # Make trading decision
                decision = trading_service.make_trading_decision(agent, db)
                
                if decision:
                    # Broadcast update via WebSocket
                    await manager.broadcast({
                        "type": "trade_update",
                        "agent_id": agent.id,
                        "agent_name": agent.name,
                        "decision": decision,
                        "timestamp": datetime.utcnow().isoformat()
                    })
                
            except Exception as e:
                logger.error(f"Error processing agent {agent.id}: {e}")
        
        db.close()
        
    except Exception as e:
        logger.error(f"Error in trading cycle: {e}")


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
    uvicorn.run(app, host="0.0.0.0", port=8000)
