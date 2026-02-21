# Money Maker — Copilot Instructions

## Project Overview

Crypto futures trading **simulation** platform (no real money for now). FastAPI backend + vanilla JS SPA dashboard. SQLite database, Binance Futures API for market data, optional Gemini LLM for sentiment. All code and comments may be in English or Spanish.

## Architecture

- **`main.py`** — FastAPI app: all API endpoints, Pydantic request models, scheduler jobs (trading cycle 60s, risk monitor 5s, WS broadcast 3s), WebSocket connection manager, and the global `_trading_lock` (threading.Lock) that serializes all balance-mutating operations.
- **`backend/models/database.py`** — SQLAlchemy ORM models: `TradingAgent`, `Portfolio`, `Trade`, `Decision`, `PortfolioSnapshot`, `NewsEvent`. All on a single SQLite DB (`trading.db`) with WAL mode.
- **`backend/database.py`** — Engine setup, `get_db()` generator, and `_run_migrations()` for safe `ALTER TABLE ADD COLUMN` migrations (idempotent, no migration framework).
- **`backend/services/trading_agent.py`** — `TradingAgentService`: the 60s decision loop. Checks existing positions → scans coins for signals → opens/closes via `StrategyEngine`. Always acquire `_trading_lock` before calling.
- **`backend/services/risk_monitor.py`** — `ReactiveRiskMonitor`: event-driven (1s WS ticks) + 5s polling fallback. Uses non-blocking `_trading_lock.acquire(blocking=False)` to skip ticks when the trading cycle holds the lock.
- **`backend/services/ws_monitor.py`** — `BinanceWSManager`: persistent WebSocket to `fstream.binance.com` for mark prices (1s) and dynamic kline subscriptions. Thread-safe caches read by sync threads.
- **`backend/services/market_data.py`** — `MarketDataService` with provider chain: WS cache → REST cache → Binance Futures API → Binance Spot API → CoinGecko. Coin IDs use CoinGecko format (`"bitcoin"`, `"ethereum"`).
- **`backend/services/strategies/`** — Strategy package. Public API re-exported from `__init__.py` for backward-compatible imports.

## Strategy System (Open/Closed Principle)

All strategies inherit `BaseStrategy` ([backend/services/strategies/base.py](backend/services/strategies/base.py)):

1. Override `evaluate(indicators, current_price, has_long, has_short, entry_price) → Signal`
2. Optionally override `_check_exit_signal()` for custom exit timing (see `TrendRiderStrategy`)
3. Use `_build_signal()` (inherited) to convert raw long/short scores into a `Signal` dataclass
4. Register in `STRATEGIES` dict ([backend/services/strategies/models.py](backend/services/strategies/models.py)) with a `StrategyConfig`
5. Add instance to `StrategyEngine._instances` dict ([backend/services/strategies/engine.py](backend/services/strategies/engine.py))

**Scalper variants** use a Factory pattern: `ScalperFactory` in `backend/services/strategies/scalper/factory.py` maps keys to concrete subclasses (`Scalper1M`…`Scalper1H`). Each subclass only provides a `ScalperParams` dataclass — the scoring engine lives in `BaseScalperStrategy`.

### Key data types

- **`Signal`** — dataclass: `direction` (long/short/close_long/close_short/neutral), `confidence`, `leverage`, `stop_loss_pct`, `take_profit_pct`, `reasoning`, `scores`, `trail_pct`
- **`StrategyConfig`** — dataclass: `key`, `style`, `default_leverage`, `max_positions`, `risk_per_trade_pct`, `min_confidence`, `trail_atr_mult`, `kline_interval`, `scan_limit`
- **`Indicators`** — stateless class with static methods (`ema_series`, `rsi_series`, `compute_all`, etc.). Timeframe-specific periods via `SCALP_PROFILES` dict.

## Concurrency Model

- **`_trading_lock`** (threading.Lock in `main.py`) must be held before any balance/portfolio mutation. Both the 60s trading cycle and 5s risk monitor acquire it.
- `ReactiveRiskMonitor` uses `blocking=False` lock acquisition — skips the tick if locked (retries in 1s).
- SQLite runs in WAL mode with `busy_timeout=5000` to handle concurrent readers/writers.
- `BinanceWSManager` caches are protected by their own `threading.Lock`.

## Running & Testing

```bash
# Start server (port 8001)
python3 main.py

# Backtesting CLI (requires server running)
python3 backtest_cli.py --compare              # all strategies vs BTC 90d
python3 backtest_cli.py -s scalper -c BTC -p 30
python3 backtest_cli.py --scalpers             # all scalper variants
```

No test framework is configured. Validate changes by:
1. Starting the server and checking `http://localhost:8001/api/health`
2. Running backtests with `backtest_cli.py` to verify strategy changes
3. Checking the dashboard at `http://localhost:8001`

## Conventions

- **Coin identifiers**: Always use CoinGecko IDs internally (`"bitcoin"`, `"solana"`). `BinanceProvider.SYMBOL_MAP` converts to Binance symbols (`BTCUSDT`).
- **DB migrations**: Add new columns via `_run_migrations()` in `backend/database.py` using `ALTER TABLE ADD COLUMN` wrapped in try/except. No Alembic.
- **Imports**: External code imports from `backend.services.strategies` (the package `__init__.py`), never from submodules directly.
- **Position types**: `"long"` / `"short"` strings. Trade types: `"open_long"`, `"close_long"`, `"open_short"`, `"close_short"`.
- **Trailing stops**: 2-phase system — breakeven at +1R, then Chandelier (K×ATR). Controlled per-strategy via `trail_atr_mult` in `StrategyConfig`.
- **Backtester**: Simulates fees (taker 0.05%, maker 0.02%), slippage (0.05%), funding rates, and has circuit breaker (3% daily loss halt).
- **Frontend**: Single-file SPA in `static/index.html` + `static/charts.js`. Uses TradingView Lightweight Charts. Dark mode with CSS custom properties.
- **Environment variables**: `DATABASE_URL` (default `sqlite:///./trading.db`), `GEMINI_API_KEY` (optional, enables LLM sentiment), `CRYPTOPANIC_API_KEY` (optional, for news).


# Copilot Skill Instructions
- Follow the skills written in .claude/skills/personality/SKILL.md, they are the personality of the agent, how it should act, and the rules it should follow when generating code. Always follow those instructions when writing code for this project.