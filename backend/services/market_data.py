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
        self._use_mock_data = False
        # Mock prices for when API is unavailable
        self._mock_prices = {
            "bitcoin": 45000.0,
            "ethereum": 2500.0,
            "binancecoin": 320.0,
            "cardano": 0.65,
            "solana": 105.0,
            "ripple": 0.55,
            "polkadot": 7.50,
            "dogecoin": 0.085
        }
    
    def get_current_prices(self) -> Dict[str, float]:
        """Get current prices for supported cryptocurrencies"""
        try:
            # Cache for 30 seconds to avoid API rate limits
            if self._cache_timestamp and (datetime.now() - self._cache_timestamp).total_seconds() < 30:
                return self._price_cache
            
            # Try real API first
            if not self._use_mock_data:
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
            logger.warning(f"API unavailable, using mock data: {e}")
            self._use_mock_data = True
            
        # Use mock data with slight random variations
        import random
        prices = {}
        for coin, base_price in self._mock_prices.items():
            # Add random variation of -2% to +2%
            variation = random.uniform(-0.02, 0.02)
            prices[coin] = base_price * (1 + variation)
        
        self._price_cache = prices
        self._cache_timestamp = datetime.now()
        return prices
    
    def get_coin_price(self, coin: str) -> Optional[float]:
        """Get current price for a specific coin"""
        prices = self.get_current_prices()
        return prices.get(coin)
    
    def get_market_data(self, coin: str) -> Optional[Dict]:
        """Get detailed market data for a coin"""
        if self._use_mock_data:
            # Return mock market data
            current_price = self._mock_prices.get(coin)
            if not current_price:
                return None
            
            import random
            return {
                "id": coin,
                "symbol": coin[:3].upper() if len(coin) >= 3 else coin.upper(),
                "name": coin.capitalize(),
                "current_price": current_price * (1 + random.uniform(-0.02, 0.02)),
                "market_cap": current_price * 1000000000,
                "volume_24h": current_price * 50000000,
                "price_change_24h": random.uniform(-5, 5),
                "price_change_7d": random.uniform(-10, 10),
                "high_24h": current_price * 1.03,
                "low_24h": current_price * 0.97,
            }
        
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
            logger.warning(f"Error fetching market data for {coin}, using mock: {e}")
            self._use_mock_data = True
            return self.get_market_data(coin)  # Retry with mock data
    
    def get_historical_prices(self, coin: str, days: int = 30) -> List[Dict]:
        """Get historical price data"""
        if self._use_mock_data:
            # Generate mock historical data
            import random
            base_price = self._mock_prices.get(coin, 100)
            prices = []
            current_time = datetime.now()
            
            for i in range(days):
                timestamp = current_time - timedelta(days=days-i)
                # Random walk
                variation = random.uniform(-0.05, 0.05)
                price = base_price * (1 + variation * (days - i) / days)
                prices.append({
                    "timestamp": timestamp,
                    "price": price
                })
            
            return prices
        
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
            logger.warning(f"Error fetching historical data for {coin}, using mock: {e}")
            self._use_mock_data = True
            return self.get_historical_prices(coin, days)  # Retry with mock data
    
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
