"""
Market data service - fetches cryptocurrency prices and data
"""
import requests
import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class MarketDataService:
    """Service to fetch cryptocurrency market data"""
    
    def __init__(self):
        self.base_url = "https://api.coingecko.com/api/v3"
        self.supported_coins = ["bitcoin", "ethereum", "binancecoin", "cardano", "solana", "ripple", "polkadot", "dogecoin"]
        self._price_cache = {}
        self._cache_timestamp = None
    
    def get_current_prices(self) -> Dict[str, float]:
        """Get current prices for supported cryptocurrencies"""
        try:
            # Cache for 30 seconds to avoid API rate limits
            if self._cache_timestamp and (datetime.now() - self._cache_timestamp).seconds < 30:
                return self._price_cache
            
            coins = ",".join(self.supported_coins)
            url = f"{self.base_url}/simple/price"
            params = {
                "ids": coins,
                "vs_currencies": "usd"
            }
            
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            prices = {}
            for coin in self.supported_coins:
                if coin in data:
                    prices[coin] = data[coin]["usd"]
            
            self._price_cache = prices
            self._cache_timestamp = datetime.now()
            
            return prices
        except Exception as e:
            logger.error(f"Error fetching prices: {e}")
            return self._price_cache if self._price_cache else {}
    
    def get_coin_price(self, coin: str) -> Optional[float]:
        """Get current price for a specific coin"""
        prices = self.get_current_prices()
        return prices.get(coin)
    
    def get_market_data(self, coin: str) -> Optional[Dict]:
        """Get detailed market data for a coin"""
        try:
            url = f"{self.base_url}/coins/{coin}"
            params = {
                "localization": "false",
                "tickers": "false",
                "community_data": "false",
                "developer_data": "false"
            }
            
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            return {
                "id": data.get("id"),
                "symbol": data.get("symbol", "").upper(),
                "name": data.get("name"),
                "current_price": data.get("market_data", {}).get("current_price", {}).get("usd"),
                "market_cap": data.get("market_data", {}).get("market_cap", {}).get("usd"),
                "volume_24h": data.get("market_data", {}).get("total_volume", {}).get("usd"),
                "price_change_24h": data.get("market_data", {}).get("price_change_percentage_24h"),
                "price_change_7d": data.get("market_data", {}).get("price_change_percentage_7d"),
                "high_24h": data.get("market_data", {}).get("high_24h", {}).get("usd"),
                "low_24h": data.get("market_data", {}).get("low_24h", {}).get("usd"),
            }
        except Exception as e:
            logger.error(f"Error fetching market data for {coin}: {e}")
            return None
    
    def get_historical_prices(self, coin: str, days: int = 30) -> List[Dict]:
        """Get historical price data"""
        try:
            url = f"{self.base_url}/coins/{coin}/market_chart"
            params = {
                "vs_currency": "usd",
                "days": days,
                "interval": "daily" if days > 1 else "hourly"
            }
            
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            prices = []
            for price_data in data.get("prices", []):
                prices.append({
                    "timestamp": datetime.fromtimestamp(price_data[0] / 1000),
                    "price": price_data[1]
                })
            
            return prices
        except Exception as e:
            logger.error(f"Error fetching historical data for {coin}: {e}")
            return []
    
    def get_trending_coins(self) -> List[Dict]:
        """Get trending cryptocurrencies"""
        try:
            url = f"{self.base_url}/search/trending"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            trending = []
            for item in data.get("coins", [])[:10]:
                coin = item.get("item", {})
                trending.append({
                    "id": coin.get("id"),
                    "symbol": coin.get("symbol"),
                    "name": coin.get("name"),
                    "market_cap_rank": coin.get("market_cap_rank")
                })
            
            return trending
        except Exception as e:
            logger.error(f"Error fetching trending coins: {e}")
            return []
