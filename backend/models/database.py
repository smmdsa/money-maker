"""
Database models for the trading application.
Supports futures trading: long/short positions with leverage.
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, JSON, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()


class TradingAgent(Base):
    """AI Trading Agent model"""
    __tablename__ = "trading_agents"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    initial_balance = Column(Float)
    current_balance = Column(Float)
    status = Column(String, default="active")  # active, paused, stopped
    strategy = Column(String, default="confluence_master")  # strategy key
    max_leverage = Column(Integer, default=10)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    portfolio = relationship("Portfolio", back_populates="agent", cascade="all, delete-orphan")
    trades = relationship("Trade", back_populates="agent", cascade="all, delete-orphan")
    decisions = relationship("Decision", back_populates="agent", cascade="all, delete-orphan")
    snapshots = relationship("PortfolioSnapshot", back_populates="agent", cascade="all, delete-orphan")


class Portfolio(Base):
    """Portfolio positions (spot and futures) for each agent"""
    __tablename__ = "portfolio"
    
    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(Integer, ForeignKey("trading_agents.id"))
    cryptocurrency = Column(String)  # e.g., "bitcoin", "ethereum"
    symbol = Column(String)          # e.g., "BTC", "ETH"
    amount = Column(Float)           # coin quantity (virtual for shorts)
    avg_buy_price = Column(Float)    # entry price
    current_price = Column(Float)
    position_type = Column(String, default="long")    # "long" or "short"
    leverage = Column(Integer, default=1)
    margin = Column(Float, default=0.0)               # USD committed as collateral
    liquidation_price = Column(Float, default=0.0)
    stop_loss_price = Column(Float, default=0.0)
    take_profit_price = Column(Float, default=0.0)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    agent = relationship("TradingAgent", back_populates="portfolio")


class Trade(Base):
    """Trade history"""
    __tablename__ = "trades"
    
    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(Integer, ForeignKey("trading_agents.id"))
    decision_id = Column(Integer, ForeignKey("decisions.id"), nullable=True)
    cryptocurrency = Column(String)
    symbol = Column(String)
    trade_type = Column(String)      # open_long, close_long, open_short, close_short
    amount = Column(Float)
    price = Column(Float)
    total_value = Column(Float)
    profit_loss = Column(Float, default=0.0)
    leverage = Column(Integer, default=1)
    margin = Column(Float, default=0.0)
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    agent = relationship("TradingAgent", back_populates="trades")
    decision = relationship("Decision", backref="trade")


class Decision(Base):
    """AI decision log"""
    __tablename__ = "decisions"
    
    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(Integer, ForeignKey("trading_agents.id"))
    decision_type = Column(String)  # analysis, trade, hold
    cryptocurrency = Column(String)
    reasoning = Column(String)
    llm_reasoning = Column(String, nullable=True)   # LLM-generated natural language analysis
    llm_sentiment_adj = Column(Float, default=0.0)  # confidence adjustment from LLM
    indicators = Column(JSON)
    news_considered = Column(JSON, nullable=True)
    action_taken = Column(String)   # long, short, close_long, close_short, hold
    confidence = Column(Float)
    strategy = Column(String, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    agent = relationship("TradingAgent", back_populates="decisions")


class PortfolioSnapshot(Base):
    """Periodic snapshot of agent portfolio value for equity curve"""
    __tablename__ = "portfolio_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(Integer, ForeignKey("trading_agents.id"))
    total_value = Column(Float)          # cash + portfolio market value
    cash_balance = Column(Float)
    portfolio_value = Column(Float)      # market value of holdings
    timestamp = Column(DateTime, default=datetime.utcnow)

    agent = relationship("TradingAgent", back_populates="snapshots")


class NewsEvent(Base):
    """News and market events"""
    __tablename__ = "news_events"
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String)
    description = Column(String, nullable=True)
    source = Column(String)
    cryptocurrency = Column(String, nullable=True)
    sentiment = Column(String)  # positive, negative, neutral
    impact_score = Column(Float, default=0.0)
    timestamp = Column(DateTime, default=datetime.utcnow)
    url = Column(String, nullable=True)
