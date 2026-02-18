"""
AI Trading Agent - Makes intelligent trading decisions
"""
import logging
from typing import Dict, List, Optional, Tuple
import random
from datetime import datetime
from sqlalchemy.orm import Session

from backend.models.database import TradingAgent, Portfolio, Trade, Decision, NewsEvent
from backend.services.market_data import MarketDataService

logger = logging.getLogger(__name__)


class TradingAgentService:
    """AI Trading Agent that makes autonomous trading decisions"""
    
    def __init__(self, market_service: MarketDataService):
        self.market_service = market_service
    
    def calculate_technical_indicators(self, coin: str) -> Dict:
        """Calculate technical indicators for decision making"""
        market_data = self.market_service.get_market_data(coin)
        if not market_data:
            return {}
        
        # Get historical data
        historical = self.market_service.get_historical_prices(coin, days=7)
        if len(historical) < 2:
            return {}
        
        # Calculate basic indicators
        current_price = market_data.get("current_price", 0)
        price_change_24h = market_data.get("price_change_24h", 0)
        price_change_7d = market_data.get("price_change_7d", 0)
        volume_24h = market_data.get("volume_24h", 0)
        
        # Simple momentum indicator
        prices = [h["price"] for h in historical[-7:]]
        avg_price_7d = sum(prices) / len(prices) if prices else current_price
        momentum = ((current_price - avg_price_7d) / avg_price_7d * 100) if avg_price_7d > 0 else 0
        
        # Volatility (simple standard deviation)
        if len(prices) > 1:
            mean = sum(prices) / len(prices)
            variance = sum((p - mean) ** 2 for p in prices) / len(prices)
            volatility = variance ** 0.5
        else:
            volatility = 0
        
        return {
            "current_price": current_price,
            "price_change_24h": price_change_24h,
            "price_change_7d": price_change_7d,
            "volume_24h": volume_24h,
            "momentum": momentum,
            "volatility": volatility,
            "avg_price_7d": avg_price_7d
        }
    
    def make_trading_decision(self, agent: TradingAgent, db: Session) -> Optional[Dict]:
        """
        AI decision making process:
        1. Analyze market conditions
        2. Check portfolio
        3. Consider news/sentiment
        4. Make buy/sell/hold decision
        """
        try:
            # Select a random coin to analyze (simulating AI scanning the market)
            coins_to_analyze = self.market_service.supported_coins
            coin = random.choice(coins_to_analyze)
            
            # Get technical indicators
            indicators = self.calculate_technical_indicators(coin)
            if not indicators:
                return None
            
            current_price = indicators.get("current_price", 0)
            if current_price == 0:
                return None
            
            # Get agent's current portfolio for this coin
            portfolio_item = db.query(Portfolio).filter(
                Portfolio.agent_id == agent.id,
                Portfolio.cryptocurrency == coin
            ).first()
            
            # Get recent news sentiment
            recent_news = db.query(NewsEvent).filter(
                NewsEvent.cryptocurrency == coin
            ).order_by(NewsEvent.timestamp.desc()).limit(5).all()
            
            avg_sentiment_score = 0
            if recent_news:
                sentiment_scores = {"positive": 0.3, "neutral": 0, "negative": -0.3}
                avg_sentiment_score = sum(sentiment_scores.get(n.sentiment, 0) for n in recent_news) / len(recent_news)
            
            # AI Decision Logic
            decision = self._analyze_and_decide(
                agent, coin, indicators, portfolio_item, avg_sentiment_score, current_price
            )
            
            if decision:
                # Log the decision
                self._log_decision(db, agent.id, coin, decision, indicators, recent_news)
                
                # Execute trade if needed
                if decision["action"] in ["buy", "sell"]:
                    self._execute_trade(db, agent, coin, decision, current_price)
            
            return decision
            
        except Exception as e:
            logger.error(f"Error in trading decision: {e}")
            return None
    
    def _analyze_and_decide(
        self, 
        agent: TradingAgent, 
        coin: str, 
        indicators: Dict, 
        portfolio_item: Optional[Portfolio],
        sentiment_score: float,
        current_price: float
    ) -> Dict:
        """Core AI logic for trading decisions"""
        
        # Calculate signals
        momentum = indicators.get("momentum", 0)
        price_change_24h = indicators.get("price_change_24h", 0)
        volatility = indicators.get("volatility", 0)
        
        # Scoring system
        buy_score = 0
        sell_score = 0
        
        # Momentum-based signals
        if momentum > 5:
            buy_score += 2
        elif momentum > 2:
            buy_score += 1
        elif momentum < -5:
            sell_score += 2
        elif momentum < -2:
            sell_score += 1
        
        # Price change signals
        if price_change_24h > 5:
            buy_score += 1
        elif price_change_24h < -5:
            sell_score += 1
        
        # Sentiment signals
        if sentiment_score > 0.1:
            buy_score += 1
        elif sentiment_score < -0.1:
            sell_score += 1
        
        # Portfolio management
        has_position = portfolio_item is not None and portfolio_item.amount > 0
        
        if has_position:
            # Check for profit-taking or stop-loss
            if portfolio_item.avg_buy_price > 0:
                profit_pct = ((current_price - portfolio_item.avg_buy_price) / portfolio_item.avg_buy_price * 100)
                
                if profit_pct > 10:  # Take profit at 10%
                    sell_score += 3
                elif profit_pct < -5:  # Stop loss at -5%
                    sell_score += 2
        
        # Risk management - don't invest more than 20% in single coin
        max_investment = agent.current_balance * 0.2
        
        # Make decision
        action = "hold"
        confidence = 0.5
        reasoning = "Market conditions unclear, holding position"
        
        if buy_score > sell_score and buy_score >= 2 and not has_position:
            if agent.current_balance > 100:  # Minimum balance check
                action = "buy"
                confidence = min(buy_score / 5, 0.9)
                amount_to_invest = min(agent.current_balance * 0.1, max_investment)
                reasoning = f"Strong buy signals: momentum={momentum:.2f}%, sentiment={sentiment_score:.2f}"
                
                return {
                    "action": "buy",
                    "amount_usd": amount_to_invest,
                    "confidence": confidence,
                    "reasoning": reasoning
                }
        
        elif sell_score > buy_score and sell_score >= 2 and has_position:
            action = "sell"
            confidence = min(sell_score / 5, 0.9)
            reasoning = f"Sell signals detected: momentum={momentum:.2f}%, taking action"
            
            return {
                "action": "sell",
                "amount": portfolio_item.amount,
                "confidence": confidence,
                "reasoning": reasoning
            }
        
        return {
            "action": "hold",
            "confidence": 0.5,
            "reasoning": reasoning
        }
    
    def _log_decision(
        self, 
        db: Session, 
        agent_id: int, 
        coin: str, 
        decision: Dict, 
        indicators: Dict,
        news: List
    ):
        """Log AI decision to database"""
        news_data = [{"title": n.title, "sentiment": n.sentiment} for n in news[:3]] if news else None
        
        decision_log = Decision(
            agent_id=agent_id,
            decision_type="analysis",
            cryptocurrency=coin,
            reasoning=decision["reasoning"],
            indicators=indicators,
            news_considered=news_data,
            action_taken=decision["action"],
            confidence=decision["confidence"]
        )
        db.add(decision_log)
        db.commit()
    
    def _execute_trade(
        self, 
        db: Session, 
        agent: TradingAgent, 
        coin: str, 
        decision: Dict, 
        current_price: float
    ):
        """Execute a buy or sell trade"""
        market_data = self.market_service.get_market_data(coin)
        symbol = market_data.get("symbol", coin[:3].upper()) if market_data else coin[:3].upper()
        
        if decision["action"] == "buy":
            amount_usd = decision["amount_usd"]
            amount_coin = amount_usd / current_price
            
            # Update agent balance
            agent.current_balance -= amount_usd
            
            # Update or create portfolio item
            portfolio_item = db.query(Portfolio).filter(
                Portfolio.agent_id == agent.id,
                Portfolio.cryptocurrency == coin
            ).first()
            
            if portfolio_item:
                # Update existing position
                total_value = (portfolio_item.amount * portfolio_item.avg_buy_price) + amount_usd
                portfolio_item.amount += amount_coin
                portfolio_item.avg_buy_price = total_value / portfolio_item.amount
                portfolio_item.current_price = current_price
            else:
                # Create new position
                portfolio_item = Portfolio(
                    agent_id=agent.id,
                    cryptocurrency=coin,
                    symbol=symbol,
                    amount=amount_coin,
                    avg_buy_price=current_price,
                    current_price=current_price
                )
                db.add(portfolio_item)
            
            # Create trade record
            trade = Trade(
                agent_id=agent.id,
                cryptocurrency=coin,
                symbol=symbol,
                trade_type="buy",
                amount=amount_coin,
                price=current_price,
                total_value=amount_usd,
                profit_loss=0
            )
            db.add(trade)
            
        elif decision["action"] == "sell":
            portfolio_item = db.query(Portfolio).filter(
                Portfolio.agent_id == agent.id,
                Portfolio.cryptocurrency == coin
            ).first()
            
            if portfolio_item and portfolio_item.amount > 0:
                amount_coin = decision["amount"]
                sell_value = amount_coin * current_price
                profit_loss = (current_price - portfolio_item.avg_buy_price) * amount_coin
                
                # Update agent balance
                agent.current_balance += sell_value
                
                # Update portfolio
                portfolio_item.amount -= amount_coin
                if portfolio_item.amount < 0.0001:  # Close position if negligible
                    db.delete(portfolio_item)
                else:
                    portfolio_item.current_price = current_price
                
                # Create trade record
                trade = Trade(
                    agent_id=agent.id,
                    cryptocurrency=coin,
                    symbol=symbol,
                    trade_type="sell",
                    amount=amount_coin,
                    price=current_price,
                    total_value=sell_value,
                    profit_loss=profit_loss
                )
                db.add(trade)
        
        db.commit()
