"""
AI Trading Agent - Makes intelligent trading decisions using real market data
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
    """AI Trading Agent that makes autonomous trading decisions using real data"""
    
    def __init__(self, market_service: MarketDataService):
        self.market_service = market_service
    
    # ── Technical Analysis ────────────────────────────────────────────────

    def _compute_rsi(self, prices: List[float], period: int = 14) -> Optional[float]:
        """Compute RSI (Relative Strength Index)"""
        if len(prices) < period + 1:
            return None
        
        deltas = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
        gains = [d if d > 0 else 0 for d in deltas]
        losses = [-d if d < 0 else 0 for d in deltas]
        
        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period
        
        if avg_loss == 0:
            return 100.0
        
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))

    def _compute_sma(self, prices: List[float], period: int) -> Optional[float]:
        """Simple Moving Average"""
        if len(prices) < period:
            return None
        return sum(prices[-period:]) / period

    def _compute_ema(self, prices: List[float], period: int) -> Optional[float]:
        """Exponential Moving Average"""
        if len(prices) < period:
            return None
        
        multiplier = 2 / (period + 1)
        ema = sum(prices[:period]) / period  # Start with SMA
        
        for price in prices[period:]:
            ema = (price - ema) * multiplier + ema
        
        return ema

    def _compute_macd(self, prices: List[float]) -> Optional[Dict]:
        """MACD (12, 26, 9)"""
        if len(prices) < 26:
            return None
        
        ema12 = self._compute_ema(prices, 12)
        ema26 = self._compute_ema(prices, 26)
        
        if ema12 is None or ema26 is None:
            return None
        
        macd_line = ema12 - ema26
        # Simplified signal line
        return {
            "macd": macd_line,
            "signal": macd_line * 0.8,  # Approximation
            "histogram": macd_line * 0.2
        }

    def _compute_bollinger_bands(self, prices: List[float], period: int = 20) -> Optional[Dict]:
        """Bollinger Bands"""
        if len(prices) < period:
            return None
        
        recent = prices[-period:]
        sma = sum(recent) / period
        std = (sum((p - sma) ** 2 for p in recent) / period) ** 0.5
        
        return {
            "upper": sma + 2 * std,
            "middle": sma,
            "lower": sma - 2 * std,
            "width": (4 * std / sma * 100) if sma > 0 else 0
        }

    def calculate_technical_indicators(self, coin: str) -> Dict:
        """Calculate real technical indicators for decision making"""
        market_data = self.market_service.get_market_data(coin)
        if not market_data:
            return {}
        
        current_price = market_data.get("current_price")
        if not current_price:
            return {}

        # Get historical data for indicator calculations
        historical = self.market_service.get_historical_prices(coin, days=30)
        prices = [h["price"] for h in historical] if historical else []
        
        # Get OHLC for more detailed analysis
        ohlc_data = self.market_service.get_ohlc(coin, days=14)
        close_prices = [c["close"] for c in ohlc_data] if ohlc_data else prices
        
        # Build indicators dict
        indicators = {
            "current_price": current_price,
            "price_change_24h": market_data.get("price_change_24h", 0) or 0,
            "price_change_7d": market_data.get("price_change_7d", 0) or 0,
            "volume_24h": market_data.get("volume_24h", 0) or 0,
            "market_cap": market_data.get("market_cap", 0) or 0,
            "high_24h": market_data.get("high_24h"),
            "low_24h": market_data.get("low_24h"),
        }

        if len(close_prices) >= 2:
            avg_7 = self._compute_sma(close_prices, min(7, len(close_prices)))
            indicators["momentum"] = (
                ((current_price - avg_7) / avg_7 * 100) if avg_7 and avg_7 > 0 else 0
            )

            mean = sum(close_prices) / len(close_prices)
            variance = sum((p - mean) ** 2 for p in close_prices) / len(close_prices)
            indicators["volatility"] = variance ** 0.5
            indicators["avg_price_7d"] = avg_7 or mean
        else:
            indicators["momentum"] = 0
            indicators["volatility"] = 0
            indicators["avg_price_7d"] = current_price

        # RSI
        rsi = self._compute_rsi(close_prices)
        indicators["rsi"] = rsi

        # MACD
        macd = self._compute_macd(close_prices)
        indicators["macd"] = macd

        # Bollinger Bands
        bb = self._compute_bollinger_bands(close_prices)
        indicators["bollinger"] = bb

        # SMA crossover signals
        sma_short = self._compute_sma(close_prices, 7)
        sma_long = self._compute_sma(close_prices, 21)
        if sma_short and sma_long:
            indicators["sma_7"] = sma_short
            indicators["sma_21"] = sma_long
            indicators["sma_crossover"] = "bullish" if sma_short > sma_long else "bearish"

        return indicators

    # ── Coin Selection ────────────────────────────────────────────────────

    def _select_coin_to_analyze(self) -> str:
        """
        Select a coin to analyze based on market activity.
        Prioritize coins with highest 24h price change (either direction = opportunity).
        """
        all_market = self.market_service.get_all_market_data()
        
        if not all_market:
            # Fallback to random from supported list
            return random.choice(self.market_service.supported_coins)

        # Sort by absolute price change (most volatile = most opportunity)
        scored = []
        for coin in all_market:
            change = abs(coin.get("price_change_24h") or 0)
            volume = coin.get("volume_24h") or 0
            scored.append((coin["id"], change, volume))

        # Weighted random selection favoring high-activity coins
        scored.sort(key=lambda x: x[1], reverse=True)
        
        # Top half gets higher probability
        weights = [2.0 if i < len(scored) / 2 else 1.0 for i in range(len(scored))]
        total = sum(weights)
        weights = [w / total for w in weights]
        
        r = random.random()
        cumulative = 0
        for i, w in enumerate(weights):
            cumulative += w
            if r <= cumulative:
                return scored[i][0]
        
        return scored[0][0]

    # ── Decision Making ───────────────────────────────────────────────────
    
    def make_trading_decision(self, agent: TradingAgent, db: Session) -> Optional[Dict]:
        """
        AI decision making process:
        1. Select the most interesting coin to analyze
        2. Calculate real technical indicators
        3. Check portfolio
        4. Consider real news sentiment
        5. Make buy/sell/hold decision
        """
        try:
            coin = self._select_coin_to_analyze()
            
            indicators = self.calculate_technical_indicators(coin)
            if not indicators:
                return None
            
            current_price = indicators.get("current_price", 0)
            if current_price == 0:
                return None
            
            portfolio_item = db.query(Portfolio).filter(
                Portfolio.agent_id == agent.id,
                Portfolio.cryptocurrency == coin
            ).first()
            
            # Get real news sentiment
            recent_news = db.query(NewsEvent).filter(
                NewsEvent.cryptocurrency == coin
            ).order_by(NewsEvent.timestamp.desc()).limit(5).all()
            
            avg_sentiment_score = 0
            if recent_news:
                scores = []
                for n in recent_news:
                    scores.append(n.impact_score)
                avg_sentiment_score = sum(scores) / len(scores)
            
            # AI Decision Logic with real indicators
            decision = self._analyze_and_decide(
                agent, coin, indicators, portfolio_item, avg_sentiment_score, current_price
            )
            
            if decision:
                self._log_decision(db, agent.id, coin, decision, indicators, recent_news)
                
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
        """Core AI logic using real technical indicators"""
        
        momentum = indicators.get("momentum", 0)
        price_change_24h = indicators.get("price_change_24h", 0)
        rsi = indicators.get("rsi")
        macd = indicators.get("macd")
        bb = indicators.get("bollinger")
        sma_crossover = indicators.get("sma_crossover")
        
        buy_score = 0
        sell_score = 0
        reasons = []
        
        # ── RSI signals ──
        if rsi is not None:
            if rsi < 30:
                buy_score += 3
                reasons.append(f"RSI oversold ({rsi:.1f})")
            elif rsi < 40:
                buy_score += 1
                reasons.append(f"RSI low ({rsi:.1f})")
            elif rsi > 70:
                sell_score += 3
                reasons.append(f"RSI overbought ({rsi:.1f})")
            elif rsi > 60:
                sell_score += 1
                reasons.append(f"RSI high ({rsi:.1f})")

        # ── MACD signals ──
        if macd:
            if macd["histogram"] > 0:
                buy_score += 1
                reasons.append("MACD bullish")
            else:
                sell_score += 1
                reasons.append("MACD bearish")

        # ── Bollinger Band signals ──
        if bb:
            if current_price <= bb["lower"]:
                buy_score += 2
                reasons.append("Price at lower Bollinger Band")
            elif current_price >= bb["upper"]:
                sell_score += 2
                reasons.append("Price at upper Bollinger Band")

        # ── SMA crossover ──
        if sma_crossover == "bullish":
            buy_score += 1
            reasons.append("SMA 7/21 bullish crossover")
        elif sma_crossover == "bearish":
            sell_score += 1
            reasons.append("SMA 7/21 bearish crossover")
        
        # ── Momentum ──
        if momentum > 5:
            buy_score += 2
            reasons.append(f"Strong momentum (+{momentum:.1f}%)")
        elif momentum > 2:
            buy_score += 1
        elif momentum < -5:
            sell_score += 2
            reasons.append(f"Negative momentum ({momentum:.1f}%)")
        elif momentum < -2:
            sell_score += 1
        
        # ── 24h price change ──
        if price_change_24h > 5:
            buy_score += 1
        elif price_change_24h < -5:
            sell_score += 1
        
        # ── News sentiment ──
        if sentiment_score > 0.1:
            buy_score += 1
            reasons.append(f"Positive news sentiment ({sentiment_score:.2f})")
        elif sentiment_score < -0.1:
            sell_score += 1
            reasons.append(f"Negative news sentiment ({sentiment_score:.2f})")
        
        # ── Portfolio management ──
        has_position = portfolio_item is not None and portfolio_item.amount > 0
        
        if has_position and portfolio_item.avg_buy_price > 0:
            profit_pct = ((current_price - portfolio_item.avg_buy_price) / portfolio_item.avg_buy_price * 100)
            
            if profit_pct > 10:
                sell_score += 3
                reasons.append(f"Take profit ({profit_pct:.1f}%)")
            elif profit_pct > 5:
                sell_score += 1
                reasons.append(f"Moderate profit ({profit_pct:.1f}%)")
            elif profit_pct < -5:
                sell_score += 2
                reasons.append(f"Stop loss ({profit_pct:.1f}%)")
        
        max_investment = agent.current_balance * 0.2
        reasoning = "; ".join(reasons) if reasons else "Market conditions unclear"
        
        # ── Final decision ──
        if buy_score > sell_score and buy_score >= 3 and not has_position:
            if agent.current_balance > 50:
                confidence = min(buy_score / 8, 0.95)
                amount_to_invest = min(agent.current_balance * 0.1, max_investment)
                
                return {
                    "action": "buy",
                    "coin": coin,
                    "amount_usd": amount_to_invest,
                    "confidence": round(confidence, 2),
                    "reasoning": f"BUY {coin}: {reasoning}",
                    "buy_score": buy_score,
                    "sell_score": sell_score,
                }
        
        elif sell_score > buy_score and sell_score >= 3 and has_position:
            confidence = min(sell_score / 8, 0.95)
            
            return {
                "action": "sell",
                "coin": coin,
                "amount": portfolio_item.amount,
                "confidence": round(confidence, 2),
                "reasoning": f"SELL {coin}: {reasoning}",
                "buy_score": buy_score,
                "sell_score": sell_score,
            }
        
        return {
            "action": "hold",
            "coin": coin,
            "confidence": 0.5,
            "reasoning": f"HOLD {coin}: {reasoning} (buy={buy_score}, sell={sell_score})",
            "buy_score": buy_score,
            "sell_score": sell_score,
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
        
        # Sanitize indicators for JSON storage (remove non‑serializable objects)
        safe_indicators = {}
        for k, v in indicators.items():
            if isinstance(v, (int, float, str, bool, type(None))):
                safe_indicators[k] = v
            elif isinstance(v, dict):
                safe_indicators[k] = {
                    sk: sv for sk, sv in v.items()
                    if isinstance(sv, (int, float, str, bool, type(None)))
                }
        
        decision_log = Decision(
            agent_id=agent_id,
            decision_type="analysis",
            cryptocurrency=coin,
            reasoning=decision["reasoning"],
            indicators=safe_indicators,
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
