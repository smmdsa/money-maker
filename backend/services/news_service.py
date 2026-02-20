"""
News service - Fetches real crypto news from public APIs
Primary: CryptoPanic API (free tier)
Fallback: RSS feeds from major crypto news sites
"""
import logging
import requests
import os
import xml.etree.ElementTree as ET
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from dotenv import load_dotenv

from backend.models.database import NewsEvent

load_dotenv()

logger = logging.getLogger(__name__)


# ── Simple keyword‑based sentiment analyser ──────────────────────────────

POSITIVE_KEYWORDS = {
    "surge", "surges", "rally", "rallies", "bullish", "soar", "soars",
    "gains", "gain", "adoption", "partnership", "upgrade", "launch",
    "breakout", "growth", "record", "high", "integration", "milestone",
    "approval", "approved", "etf", "institutional", "invest", "investment",
    "positive", "boost", "rise", "rises", "recovery", "profit", "upside",
}

NEGATIVE_KEYWORDS = {
    "crash", "crashes", "bear", "bearish", "plunge", "plunges", "drop",
    "drops", "hack", "hacked", "scam", "fraud", "ban", "banned",
    "regulation", "fine", "fined", "lawsuit", "vulnerability", "exploit",
    "decline", "loss", "losses", "sell-off", "selloff", "warning",
    "fear", "panic", "collapse", "risk", "negative", "crackdown",
    "layoff", "layoffs", "bankrupt", "bankruptcy", "investigation",
}

COIN_KEYWORDS = {
    "bitcoin": ["bitcoin", "btc"],
    "ethereum": ["ethereum", "eth"],
    "binancecoin": ["binance", "bnb"],
    "cardano": ["cardano", "ada"],
    "solana": ["solana", "sol"],
    "ripple": ["ripple", "xrp"],
    "polkadot": ["polkadot", "dot"],
    "dogecoin": ["dogecoin", "doge"],
}


def _analyse_sentiment(text: str) -> tuple[str, float]:
    """Return (sentiment, impact_score) based on keyword matching."""
    words = set(text.lower().split())
    pos = len(words & POSITIVE_KEYWORDS)
    neg = len(words & NEGATIVE_KEYWORDS)

    if pos > neg:
        return "positive", min(0.1 + pos * 0.15, 0.8)
    elif neg > pos:
        return "negative", max(-0.1 - neg * 0.15, -0.8)
    return "neutral", 0.0


def _detect_coin(text: str) -> Optional[str]:
    """Detect which supported cryptocurrency a text refers to."""
    lower = text.lower()
    for coin_id, keywords in COIN_KEYWORDS.items():
        for kw in keywords:
            if kw in lower:
                return coin_id
    return None


# ── RSS Feed URLs ────────────────────────────────────────────────────────

RSS_FEEDS = [
    {
        "name": "CoinDesk",
        "url": "https://www.coindesk.com/arc/outboundfeeds/rss/",
    },
    {
        "name": "CoinTelegraph",
        "url": "https://cointelegraph.com/rss",
    },
    {
        "name": "Bitcoin Magazine",
        "url": "https://bitcoinmagazine.com/.rss/full/",
    },
]


class NewsService:
    """Service to fetch and analyze real crypto news"""

    def __init__(self):
        self.cryptopanic_token = os.getenv("CRYPTOPANIC_API_TOKEN", "")
        self.cryptopanic_base = "https://cryptopanic.com/api/free/v1"
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": "MoneyMaker/1.0"})
        self._last_fetch: Optional[datetime] = None
        self._fetch_interval = timedelta(minutes=5)  # Don't fetch more often than every 5 min

    # ── Public interface (called from main.py) ────────────────────────────

    def fetch_and_store_news(self, db: Session):
        """
        Fetch real news from APIs and store new items in the database.
        Replaces the old generate_simulated_news().
        """
        # Rate‑limit fetching
        now = datetime.utcnow()
        if self._last_fetch and (now - self._last_fetch) < self._fetch_interval:
            return

        self._last_fetch = now

        news_items: List[Dict] = []

        # Try CryptoPanic first (best source, includes sentiment)
        if self.cryptopanic_token:
            news_items = self._fetch_cryptopanic()

        # Fallback / supplement with RSS feeds
        if len(news_items) < 5:
            rss_items = self._fetch_rss_feeds()
            news_items.extend(rss_items)

        if not news_items:
            logger.warning("No news fetched from any source")
            return

        stored = 0
        for item in news_items:
            # Deduplicate by title (within the last 24h)
            existing = db.query(NewsEvent).filter(
                NewsEvent.title == item["title"],
                NewsEvent.timestamp > now - timedelta(hours=24)
            ).first()

            if not existing:
                news = NewsEvent(
                    title=item["title"],
                    description=item.get("description", ""),
                    source=item["source"],
                    cryptocurrency=item.get("cryptocurrency"),
                    sentiment=item["sentiment"],
                    impact_score=item["impact_score"],
                    timestamp=now,
                    url=item.get("url", ""),
                )
                db.add(news)
                stored += 1

        if stored:
            db.commit()
            logger.info(f"Stored {stored} new news items")

    def get_recent_news(self, db: Session, hours: int = 24, coin: str = None) -> List[NewsEvent]:
        """Get recent news events from database"""
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
            "score": round(avg_impact, 3),
            "positive": sentiment_counts["positive"],
            "negative": sentiment_counts["negative"],
            "neutral": sentiment_counts["neutral"],
        }

    # ── CryptoPanic API ──────────────────────────────────────────────────

    def _fetch_cryptopanic(self) -> List[Dict]:
        """Fetch news from CryptoPanic free API"""
        items = []
        try:
            url = f"{self.cryptopanic_base}/posts/"
            params = {
                "auth_token": self.cryptopanic_token,
                "kind": "news",
                "filter": "important",
                "public": "true",
            }
            resp = self._session.get(url, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            for post in data.get("results", [])[:20]:
                title = post.get("title", "")
                coin = _detect_coin(title)

                # CryptoPanic provides votes for sentiment
                votes = post.get("votes", {})
                pos_votes = votes.get("positive", 0) + votes.get("important", 0)
                neg_votes = votes.get("negative", 0) + votes.get("toxic", 0)

                if pos_votes > neg_votes:
                    sentiment = "positive"
                    impact = min(0.1 + (pos_votes - neg_votes) * 0.05, 0.8)
                elif neg_votes > pos_votes:
                    sentiment = "negative"
                    impact = max(-0.1 - (neg_votes - pos_votes) * 0.05, -0.8)
                else:
                    sentiment, impact = _analyse_sentiment(title)

                # Use currencies from API if available
                currencies = post.get("currencies", [])
                if currencies and not coin:
                    slug = currencies[0].get("slug", "")
                    coin = slug if slug in COIN_KEYWORDS else None

                items.append({
                    "title": title,
                    "description": post.get("metadata", {}).get("description", ""),
                    "source": post.get("source", {}).get("title", "CryptoPanic"),
                    "cryptocurrency": coin,
                    "sentiment": sentiment,
                    "impact_score": impact,
                    "url": post.get("url", ""),
                })

            logger.info(f"Fetched {len(items)} news from CryptoPanic")

        except Exception as e:
            logger.warning(f"CryptoPanic fetch failed: {e}")

        return items

    # ── RSS Feeds fallback ───────────────────────────────────────────────

    def _fetch_rss_feeds(self) -> List[Dict]:
        """Fetch and parse RSS feeds from major crypto news sites"""
        items = []

        for feed_info in RSS_FEEDS:
            try:
                resp = self._session.get(feed_info["url"], timeout=15)
                resp.raise_for_status()

                root = ET.fromstring(resp.content)

                # Handle both RSS 2.0 and Atom
                ns = {"atom": "http://www.w3.org/2005/Atom"}
                entries = root.findall(".//item")  # RSS 2.0
                if not entries:
                    entries = root.findall(".//atom:entry", ns)  # Atom

                for entry in entries[:10]:
                    title_el = entry.find("title")
                    if title_el is None:
                        title_el = entry.find("atom:title", ns)
                    title = (title_el.text or "").strip() if title_el is not None else ""

                    if not title:
                        continue

                    desc_el = entry.find("description")
                    desc = (desc_el.text or "")[:300] if desc_el is not None else ""

                    link_el = entry.find("link")
                    if link_el is None:
                        link_el = entry.find("atom:link", ns)
                        link = link_el.get("href", "") if link_el is not None else ""
                    else:
                        link = (link_el.text or "").strip()

                    coin = _detect_coin(title + " " + desc)
                    sentiment, impact = _analyse_sentiment(title + " " + desc)

                    items.append({
                        "title": title,
                        "description": desc,
                        "source": feed_info["name"],
                        "cryptocurrency": coin,
                        "sentiment": sentiment,
                        "impact_score": impact,
                        "url": link,
                    })

                logger.info(f"Fetched {min(len(entries), 10)} items from {feed_info['name']} RSS")

            except Exception as e:
                logger.warning(f"RSS fetch failed for {feed_info['name']}: {e}")

        return items
