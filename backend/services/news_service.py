"""
News service - Simulates fetching and analyzing news/events
In a real implementation, this would connect to news APIs
"""
import logging
from typing import List, Dict
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
import random

from backend.models.database import NewsEvent

logger = logging.getLogger(__name__)


class NewsService:
    """Service to fetch and analyze crypto news"""
    
    def __init__(self):
        # Simulated news templates for demo
        self.news_templates = [
            {
                "title_template": "{coin} shows strong adoption in {region}",
                "sentiment": "positive",
                "impact": 0.3
            },
            {
                "title_template": "{coin} faces regulatory concerns in {region}",
                "sentiment": "negative",
                "impact": -0.4
            },
            {
                "title_template": "Major institution announces {coin} integration",
                "sentiment": "positive",
                "impact": 0.5
            },
            {
                "title_template": "{coin} network upgrade scheduled",
                "sentiment": "positive",
                "impact": 0.2
            },
            {
                "title_template": "Market analysis: {coin} consolidating",
                "sentiment": "neutral",
                "impact": 0.0
            },
            {
                "title_template": "{coin} trading volume increases significantly",
                "sentiment": "positive",
                "impact": 0.3
            },
            {
                "title_template": "Security concerns raised about {coin}",
                "sentiment": "negative",
                "impact": -0.3
            },
            {
                "title_template": "{coin} developers release new roadmap",
                "sentiment": "positive",
                "impact": 0.2
            }
        ]
        
        self.regions = ["Asia", "Europe", "North America", "Global Markets"]
        self.coins = ["Bitcoin", "Ethereum", "Binance Coin", "Cardano", "Solana", "Ripple"]
    
    def generate_simulated_news(self, db: Session, coin: str = None):
        """
        Generate simulated news events
        In production, this would fetch from real news APIs
        """
        # Generate 1-3 news items
        num_news = random.randint(1, 3)
        
        for _ in range(num_news):
            template = random.choice(self.news_templates)
            selected_coin = coin if coin else random.choice(self.coins)
            region = random.choice(self.regions)
            
            title = template["title_template"].format(
                coin=selected_coin,
                region=region
            )
            
            # Check if similar news already exists recently
            existing = db.query(NewsEvent).filter(
                NewsEvent.title == title,
                NewsEvent.timestamp > datetime.utcnow() - timedelta(hours=24)
            ).first()
            
            if not existing:
                news = NewsEvent(
                    title=title,
                    description=f"Market update regarding {selected_coin}",
                    source="CryptoNews",
                    cryptocurrency=selected_coin.lower().replace(" ", ""),
                    sentiment=template["sentiment"],
                    impact_score=template["impact"],
                    url=f"https://news.example.com/{selected_coin.lower()}"
                )
                db.add(news)
        
        db.commit()
    
    def get_recent_news(self, db: Session, hours: int = 24, coin: str = None) -> List[NewsEvent]:
        """Get recent news events"""
        query = db.query(NewsEvent).filter(
            NewsEvent.timestamp > datetime.utcnow() - timedelta(hours=hours)
        )
        
        if coin:
            query = query.filter(NewsEvent.cryptocurrency == coin)
        
        return query.order_by(NewsEvent.timestamp.desc()).limit(20).all()
    
    def analyze_sentiment(self, news_items: List[NewsEvent]) -> Dict:
        """Analyze overall sentiment from news"""
        if not news_items:
            return {"overall": "neutral", "score": 0.0, "positive": 0, "negative": 0, "neutral": 0}
        
        sentiment_counts = {"positive": 0, "negative": 0, "neutral": 0}
        total_impact = 0
        
        for news in news_items:
            sentiment_counts[news.sentiment] += 1
            total_impact += news.impact_score
        
        avg_impact = total_impact / len(news_items)
        
        if avg_impact > 0.1:
            overall = "positive"
        elif avg_impact < -0.1:
            overall = "negative"
        else:
            overall = "neutral"
        
        return {
            "overall": overall,
            "score": avg_impact,
            "positive": sentiment_counts["positive"],
            "negative": sentiment_counts["negative"],
            "neutral": sentiment_counts["neutral"]
        }
