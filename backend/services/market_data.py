"""
Market data service - fetches real cryptocurrency prices from CoinGecko API
"""
import requests
import logging
import time
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from threading import Lock

logger = logging.getLogger(__name__)


class RateLimiter:
    """Simple rate limiter for API calls"""

    def __init__(self, max_calls: int = 10, period: float = 60.0):
        self.max_calls = max_calls
        self.period = period
        self._calls: List[float] = []
        self._lock = Lock()

    def wait_if_needed(self):
        """Block until we can make another API call"""
        with self._lock:
            now = time.time()
            self._calls = [t for t in self._calls if now - t < self.period]

            if len(self._calls) >= self.max_calls:
                sleep_time = self.period - (now - self._calls[0]) + 0.1
                if sleep_time > 0:
                    logger.info(f"Rate limit reached, waiting {sleep_time:.1f}s")
                    time.sleep(sleep_time)

            self._calls.append(time.time())


class CacheEntry:
    """Cache entry with TTL"""

    def __init__(self, data, ttl_seconds: int):
        self.data = data
        self.expires_at = datetime.now() + timedelta(seconds=ttl_seconds)

    @property
    def is_valid(self) -> bool:
        return datetime.now() < self.expires_at


class MarketDataService:
    """Service to fetch real cryptocurrency market data from CoinGecko"""

    PRICES_TTL = 60
    MARKET_DATA_TTL = 120
    HISTORICAL_TTL = 900
    TRENDING_TTL = 600

    def __init__(self):
        self.base_url = "https://api.coingecko.com/api/v3"
        self.supported_coins = [
            "bitcoin", "ethereum", "binancecoin", "cardano",
            "solana", "ripple", "polkadot", "dogecoin"
        ]
        self._cache: Dict[str, CacheEntry] = {}
        self._rate_limiter = RateLimiter(max_calls=10, period=60)
        self._session = requests.Session()
        self._session.headers.update({
            "Accept": "application/json",
            "User-Agent": "MoneyMaker/1.0"
        })
        self._consecutive_failures = 0
        self._max_retries = 3
        self._last_known_prices: Dict[str, float] = {}

    # ── Cache helpers ─────────────────────────────────────────────────────

    def _get_cache(self, key: str):
        entry = self._cache.get(key)
        if entry and entry.is_valid:
            return entry.data
        return None

    def _set_cache(self, key: str, data, ttl: int):
        self._cache[key] = CacheEntry(data, ttl)

    # ── Core API request with retry + rate‑limiting ───────────────────────

    def _api_request(self, endpoint: str, params: dict = None, timeout: int = 15) -> Optional[dict]:
        url = f"{self.base_url}{endpoint}"

        for attempt in range(self._max_retries):
            try:
                self._rate_limiter.wait_if_needed()
                response = self._session.get(url, params=params, timeout=timeout)

                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 60))
                    logger.warning(f"CoinGecko rate limited (429). Waiting {retry_after}s...")
                    time.sleep(retry_after)
                    continue

                response.raise_for_status()
                self._consecutive_failures = 0
                return response.json()

            except requests.exceptions.Timeout:
                logger.warning(f"CoinGecko timeout (attempt {attempt + 1}/{self._max_retries})")
            except requests.exceptions.ConnectionError:
                logger.warning(f"CoinGecko connection error (attempt {attempt + 1}/{self._max_retries})")
            except requests.exceptions.HTTPError as e:
                logger.warning(f"CoinGecko HTTP error: {e} (attempt {attempt + 1}/{self._max_retries})")
            except Exception as e:
                logger.error(f"Unexpected error calling CoinGecko: {e}")
                break

            if attempt < self._max_retries - 1:
                wait = 2 ** (attempt + 1)
                logger.info(f"Retrying in {wait}s...")
                time.sleep(wait)

        self._consecutive_failures += 1
        logger.error(f"CoinGecko API failed after {self._max_retries} retries "
                      f"(consecutive failures: {self._consecutive_failures})")
        return None

    # ── Prices ────────────────────────────────────────────────────────────

    def get_current_prices(self) -> Dict[str, float]:
        """Get current USD prices for all supported coins (single API call)."""
        cached = self._get_cache("prices")
        if cached:
            return cached

        data = self._api_request("/simple/price", params={
            "ids": ",".join(self.supported_coins),
            "vs_currencies": "usd"
        })

        if data:
            prices = {}
            for coin in self.supported_coins:
                if coin in data and "usd" in data[coin]:
                    prices[coin] = data[coin]["usd"]
                    self._last_known_prices[coin] = data[coin]["usd"]

            if prices:
                self._set_cache("prices", prices, self.PRICES_TTL)
                return prices

        if self._last_known_prices:
            logger.warning("Using last known real prices as fallback")
            return dict(self._last_known_prices)

        logger.error("No price data available — API failed and no cached prices exist")
        return {}

    def get_coin_price(self, coin: str) -> Optional[float]:
        """Get current price for a specific coin"""
        prices = self.get_current_prices()
        return prices.get(coin)

    # ── Market Data ───────────────────────────────────────────────────────

    def get_all_market_data(self) -> List[Dict]:
        """Get market data for all supported coins in a single API call."""
        cache_key = "market_data_all"
        cached = self._get_cache(cache_key)
        if cached:
            return cached

        data = self._api_request("/coins/markets", params={
            "vs_currency": "usd",
            "ids": ",".join(self.supported_coins),
            "order": "market_cap_desc",
            "sparkline": "false",
            "price_change_percentage": "24h,7d"
        })

        if data:
            result = []
            for coin in data:
                entry = {
                    "id": coin.get("id"),
                    "symbol": (coin.get("symbol") or "").upper(),
                    "name": coin.get("name"),
                    "current_price": coin.get("current_price"),
                    "market_cap": coin.get("market_cap"),
                    "volume_24h": coin.get("total_volume"),
                    "price_change_24h": coin.get("price_change_percentage_24h"),
                    "price_change_7d": coin.get("price_change_percentage_7d_in_currency"),
                    "high_24h": coin.get("high_24h"),
                    "low_24h": coin.get("low_24h"),
                    "circulating_supply": coin.get("circulating_supply"),
                    "total_supply": coin.get("total_supply"),
                    "image": coin.get("image"),
                }
                if entry["current_price"]:
                    self._last_known_prices[entry["id"]] = entry["current_price"]
                result.append(entry)

            self._set_cache(cache_key, result, self.MARKET_DATA_TTL)
            for entry in result:
                self._set_cache(f"market_data_{entry['id']}", entry, self.MARKET_DATA_TTL)
            return result

        logger.warning("Failed to fetch market data from CoinGecko")
        return []

    def get_market_data(self, coin: str) -> Optional[Dict]:
        """Get detailed market data for a single coin."""
        cache_key = f"market_data_{coin}"
        cached = self._get_cache(cache_key)
        if cached:
            return cached

        all_data = self.get_all_market_data()
        for entry in all_data:
            if entry["id"] == coin:
                return entry

        data = self._api_request(f"/coins/{coin}", params={
            "localization": "false",
            "tickers": "false",
            "community_data": "false",
            "developer_data": "false"
        })

        if data:
            md = data.get("market_data", {})
            result = {
                "id": data.get("id"),
                "symbol": (data.get("symbol") or "").upper(),
                "name": data.get("name"),
                "current_price": md.get("current_price", {}).get("usd"),
                "market_cap": md.get("market_cap", {}).get("usd"),
                "volume_24h": md.get("total_volume", {}).get("usd"),
                "price_change_24h": md.get("price_change_percentage_24h"),
                "price_change_7d": md.get("price_change_percentage_7d"),
                "high_24h": md.get("high_24h", {}).get("usd"),
                "low_24h": md.get("low_24h", {}).get("usd"),
            }
            if result["current_price"]:
                self._last_known_prices[coin] = result["current_price"]
            self._set_cache(cache_key, result, self.MARKET_DATA_TTL)
            return result

        price = self._last_known_prices.get(coin)
        if price:
            logger.warning(f"Returning minimal market data for {coin} from last known price")
            return {
                "id": coin,
                "symbol": coin[:3].upper(),
                "name": coin.capitalize(),
                "current_price": price,
                "market_cap": None,
                "volume_24h": None,
                "price_change_24h": None,
                "price_change_7d": None,
                "high_24h": None,
                "low_24h": None,
            }

        return None

    # ── Historical Prices ─────────────────────────────────────────────────

    def get_historical_prices(self, coin: str, days: int = 30) -> List[Dict]:
        """Get historical price data from CoinGecko."""
        cache_key = f"historical_{coin}_{days}"
        cached = self._get_cache(cache_key)
        if cached:
            return cached

        data = self._api_request(f"/coins/{coin}/market_chart", params={
            "vs_currency": "usd",
            "days": days,
            "interval": "daily" if days > 1 else "hourly"
        })

        if data and "prices" in data:
            prices = []
            for price_data in data["prices"]:
                prices.append({
                    "timestamp": datetime.fromtimestamp(price_data[0] / 1000),
                    "price": price_data[1]
                })

            if prices:
                self._set_cache(cache_key, prices, self.HISTORICAL_TTL)
                return prices

        logger.warning(f"Failed to fetch historical prices for {coin}")
        return []

    # ── OHLC Data (for technical analysis) ────────────────────────────────

    def get_ohlc(self, coin: str, days: int = 14) -> List[Dict]:
        """Get OHLC candlestick data for technical analysis."""
        cache_key = f"ohlc_{coin}_{days}"
        cached = self._get_cache(cache_key)
        if cached:
            return cached

        data = self._api_request(f"/coins/{coin}/ohlc", params={
            "vs_currency": "usd",
            "days": days
        })

        if data:
            ohlc = []
            for candle in data:
                ohlc.append({
                    "timestamp": datetime.fromtimestamp(candle[0] / 1000),
                    "open": candle[1],
                    "high": candle[2],
                    "low": candle[3],
                    "close": candle[4]
                })

            if ohlc:
                self._set_cache(cache_key, ohlc, self.HISTORICAL_TTL)
                return ohlc

        logger.warning(f"Failed to fetch OHLC data for {coin}")
        return []

    # ── Trending ──────────────────────────────────────────────────────────

    def get_trending_coins(self) -> List[Dict]:
        """Get trending cryptocurrencies"""
        cached = self._get_cache("trending")
        if cached:
            return cached

        data = self._api_request("/search/trending")

        if data:
            trending = []
            for item in data.get("coins", [])[:10]:
                coin = item.get("item", {})
                trending.append({
                    "id": coin.get("id"),
                    "symbol": coin.get("symbol"),
                    "name": coin.get("name"),
                    "market_cap_rank": coin.get("market_cap_rank")
                })

            self._set_cache("trending", trending, self.TRENDING_TTL)
            return trending

        return []

    # ── Health Check ──────────────────────────────────────────────────────

    def health_check(self) -> Dict:
        """Check API connectivity and return status"""
        data = self._api_request("/ping")
        if data:
            return {
                "status": "ok",
                "api": "CoinGecko",
                "consecutive_failures": self._consecutive_failures,
                "cache_entries": len(self._cache)
            }
        return {
            "status": "degraded",
            "api": "CoinGecko",
            "consecutive_failures": self._consecutive_failures,
            "cache_entries": len(self._cache),
            "message": "API unreachable, using cached data"
        }
