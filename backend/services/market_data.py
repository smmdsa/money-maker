"""
Market data service - fetches real cryptocurrency prices from multiple API providers
Primary: Binance (1200 req/min, no key required)
Fallback: CoinGecko (10 req/min free tier)
"""
import requests
import logging
import time
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from threading import Lock

logger = logging.getLogger(__name__)

# ── Maximum time we'll ever block waiting for rate-limit ──────────────────
MAX_WAIT_SECONDS = 5


class RateLimiter:
    """Simple rate limiter for API calls — never blocks longer than MAX_WAIT_SECONDS"""

    def __init__(self, max_calls: int = 10, period: float = 60.0):
        self.max_calls = max_calls
        self.period = period
        self._calls: List[float] = []
        self._lock = Lock()

    def wait_if_needed(self) -> bool:
        """Wait if needed. Returns True if we can proceed, False if rate-limited."""
        with self._lock:
            now = time.time()
            self._calls = [t for t in self._calls if now - t < self.period]

            if len(self._calls) >= self.max_calls:
                sleep_time = self.period - (now - self._calls[0]) + 0.1
                if sleep_time > MAX_WAIT_SECONDS:
                    logger.warning(
                        f"Rate limit would require {sleep_time:.1f}s wait "
                        f"(max {MAX_WAIT_SECONDS}s) — skipping this call"
                    )
                    return False
                if sleep_time > 0:
                    logger.info(f"Rate limit: waiting {sleep_time:.1f}s")
                    time.sleep(sleep_time)

            self._calls.append(time.time())
            return True


class CacheEntry:
    """Cache entry with TTL"""

    def __init__(self, data, ttl_seconds: int):
        self.data = data
        self.expires_at = datetime.now() + timedelta(seconds=ttl_seconds)

    @property
    def is_valid(self) -> bool:
        return datetime.now() < self.expires_at


# ── Binance provider (fallback) ───────────────────────────────────────

class BinanceProvider:
    """Fallback API provider using Binance public API — 1200 req/min, no key."""

    BASE_URL = "https://api.binance.com/api/v3"

    # CoinGecko ID → Binance symbol mapping
    SYMBOL_MAP = {
        "bitcoin": "BTCUSDT",
        "ethereum": "ETHUSDT",
        "binancecoin": "BNBUSDT",
        "cardano": "ADAUSDT",
        "solana": "SOLUSDT",
        "ripple": "XRPUSDT",
        "polkadot": "DOTUSDT",
        "dogecoin": "DOGEUSDT",
    }

    # Reverse map
    REVERSE_MAP = {v: k for k, v in SYMBOL_MAP.items()}

    # Symbol → human-readable name
    NAMES = {
        "bitcoin": "Bitcoin", "ethereum": "Ethereum", "binancecoin": "BNB",
        "cardano": "Cardano", "solana": "Solana", "ripple": "XRP",
        "polkadot": "Polkadot", "dogecoin": "Dogecoin",
    }

    # Kline interval mapping (days → Binance interval)
    INTERVAL_MAP = {
        1: ("1h", 24),      # 1 day  → 1h candles × 24
        7: ("4h", 42),      # 7 days → 4h candles × 42
        14: ("4h", 84),     # 14 days → 4h candles × 84
        30: ("1d", 30),     # 30 days → daily
        90: ("1d", 90),
        365: ("1d", 365),
    }

    def __init__(self):
        self._session = requests.Session()
        self._session.headers.update({
            "Accept": "application/json",
            "User-Agent": "MoneyMaker/1.0"
        })

    def get_prices(self, coins: List[str]) -> Dict[str, float]:
        """Fetch current prices from Binance."""
        try:
            symbols = [self.SYMBOL_MAP[c] for c in coins if c in self.SYMBOL_MAP]
            if not symbols:
                return {}

            resp = self._session.get(
                f"{self.BASE_URL}/ticker/price",
                timeout=10
            )
            resp.raise_for_status()

            prices = {}
            ticker_map = {t["symbol"]: float(t["price"]) for t in resp.json()}
            for coin in coins:
                sym = self.SYMBOL_MAP.get(coin)
                if sym and sym in ticker_map:
                    prices[coin] = ticker_map[sym]

            if prices:
                logger.info(f"Binance fallback: got {len(prices)} prices")
            return prices

        except Exception as e:
            logger.warning(f"Binance prices failed: {e}")
            return {}

    def get_market_data(self, coins: List[str]) -> List[Dict]:
        """Fetch market data from Binance 24hr ticker."""
        try:
            symbols = [self.SYMBOL_MAP[c] for c in coins if c in self.SYMBOL_MAP]
            if not symbols:
                return []

            resp = self._session.get(
                f"{self.BASE_URL}/ticker/24hr",
                timeout=10
            )
            resp.raise_for_status()

            ticker_map = {t["symbol"]: t for t in resp.json()}

            result = []
            for coin in coins:
                sym = self.SYMBOL_MAP.get(coin)
                if not sym or sym not in ticker_map:
                    continue
                t = ticker_map[sym]
                try:
                    result.append({
                        "id": coin,
                        "symbol": sym.replace("USDT", ""),
                        "name": self.NAMES.get(coin, coin.capitalize()),
                        "current_price": float(t.get("lastPrice", 0)),
                        "market_cap": None,  # Binance doesn't provide market cap
                        "volume_24h": float(t.get("quoteVolume", 0)),
                        "price_change_24h": float(t.get("priceChangePercent", 0)),
                        "price_change_7d": None,
                        "high_24h": float(t.get("highPrice", 0)),
                        "low_24h": float(t.get("lowPrice", 0)),
                        "circulating_supply": None,
                        "total_supply": None,
                        "image": None,
                    })
                except (ValueError, TypeError):
                    continue

            if result:
                logger.info(f"Binance fallback: got market data for {len(result)} coins")
            return result

        except Exception as e:
            logger.warning(f"Binance market data failed: {e}")
            return []

    def get_historical_prices(self, coin: str, days: int = 30) -> List[Dict]:
        """Fetch historical prices from Binance klines."""
        try:
            sym = self.SYMBOL_MAP.get(coin)
            if not sym:
                return []

            # Pick best interval for the requested days
            interval, limit = self.INTERVAL_MAP.get(days, ("1d", min(days, 365)))

            resp = self._session.get(
                f"{self.BASE_URL}/klines",
                params={"symbol": sym, "interval": interval, "limit": limit},
                timeout=15
            )
            resp.raise_for_status()

            prices = []
            for k in resp.json():
                prices.append({
                    "timestamp": datetime.fromtimestamp(k[0] / 1000),
                    "price": float(k[4])  # close price
                })

            if prices:
                logger.info(f"Binance fallback: got {len(prices)} historical prices for {coin}")
            return prices

        except Exception as e:
            logger.warning(f"Binance historical data failed for {coin}: {e}")
            return []

    def get_ohlc(self, coin: str, days: int = 14) -> List[Dict]:
        """Fetch OHLC klines data from Binance."""
        try:
            sym = self.SYMBOL_MAP.get(coin)
            if not sym:
                return []

            interval, limit = self.INTERVAL_MAP.get(days, ("1d", min(days, 365)))

            resp = self._session.get(
                f"{self.BASE_URL}/klines",
                params={"symbol": sym, "interval": interval, "limit": limit},
                timeout=15
            )
            resp.raise_for_status()

            ohlc = []
            for k in resp.json():
                ohlc.append({
                    "timestamp": datetime.fromtimestamp(k[0] / 1000),
                    "open": float(k[1]),
                    "high": float(k[2]),
                    "low": float(k[3]),
                    "close": float(k[4]),
                    "volume": float(k[5])
                })

            if ohlc:
                logger.info(f"Binance fallback: got {len(ohlc)} OHLC candles for {coin}")
            return ohlc

        except Exception as e:
            logger.warning(f"Binance OHLC failed for {coin}: {e}")
            return []


# ── Main Market Data Service ─────────────────────────────────────────────

class MarketDataService:
    """Service to fetch real cryptocurrency market data.
    Primary: Binance (1200 req/min, no key)
    Fallback: CoinGecko (10 req/min free tier)
    """

    PRICES_TTL = 15
    MARKET_DATA_TTL = 15
    HISTORICAL_TTL = 900
    TRENDING_TTL = 600

    def __init__(self):
        self._coingecko_url = "https://api.coingecko.com/api/v3"
        self.supported_coins = [
            "bitcoin", "ethereum", "binancecoin", "cardano",
            "solana", "ripple", "polkadot", "dogecoin"
        ]
        self._cache: Dict[str, CacheEntry] = {}
        self._cg_rate_limiter = RateLimiter(max_calls=10, period=60)
        self._cg_session = requests.Session()
        self._cg_session.headers.update({
            "Accept": "application/json",
            "User-Agent": "MoneyMaker/1.0"
        })
        self._consecutive_failures = 0
        self._max_retries = 3
        self._last_known_prices: Dict[str, float] = {}
        self._coingecko_blocked_until: float = 0
        self._current_provider: str = "Binance"

        # Primary provider
        self._binance = BinanceProvider()

    # ── Cache helpers ─────────────────────────────────────────────────────

    def _get_cache(self, key: str):
        entry = self._cache.get(key)
        if entry and entry.is_valid:
            return entry.data
        return None

    def _set_cache(self, key: str, data, ttl: int):
        self._cache[key] = CacheEntry(data, ttl)

    def _is_coingecko_blocked(self) -> bool:
        """Check if CoinGecko is temporarily blocked due to heavy rate limiting."""
        if time.time() < self._coingecko_blocked_until:
            remaining = self._coingecko_blocked_until - time.time()
            logger.debug(f"CoinGecko blocked for {remaining:.0f}s more, using fallback")
            return True
        return False

    # ── Core API request with retry + rate‑limiting ───────────────────────

    def _cg_api_request(self, endpoint: str, params: dict = None, timeout: int = 15) -> Optional[dict]:
        """Make a CoinGecko API request (fallback). Returns None if blocked or failed."""
        if self._is_coingecko_blocked():
            return None

        url = f"{self._coingecko_url}{endpoint}"

        for attempt in range(self._max_retries):
            # Check rate limiter — returns False if we'd wait too long
            if not self._cg_rate_limiter.wait_if_needed():
                return None

            try:
                response = self._cg_session.get(url, params=params, timeout=timeout)

                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 60))
                    if retry_after > MAX_WAIT_SECONDS:
                        # CoinGecko is heavily rate-limiting us — back off for a while
                        # but NEVER block the thread
                        block_duration = min(retry_after, 300)  # max 5 min block
                        self._coingecko_blocked_until = time.time() + block_duration
                        logger.warning(
                            f"CoinGecko 429 with Retry-After={retry_after}s. "
                            f"Blocking CoinGecko for {block_duration}s, using fallback."
                        )
                        return None
                    else:
                        logger.info(f"CoinGecko 429, short retry in {retry_after}s")
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
                wait = min(2 ** (attempt + 1), MAX_WAIT_SECONDS)
                logger.info(f"Retrying in {wait}s...")
                time.sleep(wait)

        self._consecutive_failures += 1
        logger.error(f"CoinGecko API failed after {self._max_retries} retries "
                      f"(consecutive failures: {self._consecutive_failures})")
        return None

    # ── Prices ────────────────────────────────────────────────────────────

    def get_current_prices(self) -> Dict[str, float]:
        """Get current USD prices for all supported coins."""
        cached = self._get_cache("prices")
        if cached:
            return cached

        # Primary: Binance
        prices = self._binance.get_prices(self.supported_coins)
        if prices:
            self._current_provider = "Binance"
            for coin, price in prices.items():
                self._last_known_prices[coin] = price
            self._set_cache("prices", prices, self.PRICES_TTL)
            return prices

        # Fallback: CoinGecko
        logger.info("Falling back to CoinGecko for prices")
        data = self._cg_api_request("/simple/price", params={
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
                self._current_provider = "CoinGecko"
                self._set_cache("prices", prices, self.PRICES_TTL)
                return prices

        # Last resort: cached prices
        if self._last_known_prices:
            self._current_provider = "Cache"
            logger.warning("Using last known prices as fallback")
            return dict(self._last_known_prices)

        logger.error("No price data available — all providers failed")
        return {}

    def get_coin_price(self, coin: str) -> Optional[float]:
        """Get current price for a specific coin"""
        prices = self.get_current_prices()
        return prices.get(coin)

    # ── Market Data ───────────────────────────────────────────────────────

    def get_all_market_data(self) -> List[Dict]:
        """Get market data for all supported coins."""
        cache_key = "market_data_all"
        cached = self._get_cache(cache_key)
        if cached:
            return cached

        # Primary: Binance
        result = self._binance.get_market_data(self.supported_coins)
        if result:
            self._current_provider = "Binance"
            self._set_cache(cache_key, result, self.MARKET_DATA_TTL)
            for entry in result:
                if entry["current_price"]:
                    self._last_known_prices[entry["id"]] = entry["current_price"]
                self._set_cache(f"market_data_{entry['id']}", entry, self.MARKET_DATA_TTL)
            return result

        # Fallback: CoinGecko
        logger.info("Falling back to CoinGecko for market data")
        data = self._cg_api_request("/coins/markets", params={
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

            self._current_provider = "CoinGecko"
            self._set_cache(cache_key, result, self.MARKET_DATA_TTL)
            for entry in result:
                self._set_cache(f"market_data_{entry['id']}", entry, self.MARKET_DATA_TTL)
            return result

        logger.warning("Failed to fetch market data from any provider")
        return {}

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

        data = self._cg_api_request(f"/coins/{coin}", params={
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
        """Get historical price data."""
        cache_key = f"historical_{coin}_{days}"
        cached = self._get_cache(cache_key)
        if cached:
            return cached

        # Primary: Binance
        prices = self._binance.get_historical_prices(coin, days)
        if prices:
            self._set_cache(cache_key, prices, self.HISTORICAL_TTL)
            return prices

        # Fallback: CoinGecko
        logger.info(f"Falling back to CoinGecko for historical data ({coin})")
        data = self._cg_api_request(f"/coins/{coin}/market_chart", params={
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

        # Primary: Binance klines (real OHLC data)
        ohlc = self._binance.get_ohlc(coin, days)
        if ohlc:
            self._set_cache(cache_key, ohlc, self.HISTORICAL_TTL)
            return ohlc

        # Fallback: CoinGecko
        logger.info(f"Falling back to CoinGecko for OHLC data ({coin})")
        data = self._cg_api_request(f"/coins/{coin}/ohlc", params={
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

        logger.warning(f"Failed to fetch OHLC data for {coin} from any provider")
        return []

    # ── Trending ──────────────────────────────────────────────────────────

    def get_trending_coins(self) -> List[Dict]:
        """Get trending cryptocurrencies"""
        cached = self._get_cache("trending")
        if cached:
            return cached

        data = self._cg_api_request("/search/trending")

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

    def get_provider(self) -> str:
        """Return the name of the currently active provider."""
        return self._current_provider

    def health_check(self) -> Dict:
        """Check API connectivity and return status"""
        # Quick Binance check (primary)
        binance_ok = bool(self._binance.get_prices(["bitcoin"]))

        cg_blocked = self._is_coingecko_blocked()
        if not cg_blocked:
            data = self._cg_api_request("/ping")
            cg_ok = data is not None
        else:
            cg_ok = False

        return {
            "status": "ok" if binance_ok or cg_ok or self._last_known_prices else "degraded",
            "binance": "ok" if binance_ok else "down",
            "coingecko": "ok" if cg_ok else ("blocked" if cg_blocked else "down"),
            "consecutive_failures": self._consecutive_failures,
            "cache_entries": len(self._cache),
            "provider": self._current_provider
        }
