# Money Maker — Feature Backlog

> Última actualización: 2026-02-19 (sesión 3)

---

## ✅ Completado

### 1. 📊 Gráficos de Precios con Candlesticks e Indicadores — COMPLETADO

**Estado**: ✅ Implementado  
**Fecha**: 2026-02-18  
**Área**: UX / Dashboard + Backend APIs

**Implementación entregada:**
- **Candlestick chart** con datos OHLC reales (TradingView Lightweight Charts v4)
- **Indicadores superpuestos**: SMA 7 (azul), SMA 21 (naranja), Bollinger Bands (violeta)
- **RSI sub-chart** (14 períodos) con líneas de referencia 70/30
- **Equity curve** del agente (área chart, aparece al seleccionar un agente)
- **Selector de monedas**: BTC, ETH, BNB, SOL, XRP, ADA, DOT, DOGE
- **Selector de timeframe**: 1D, 7D, 14D, 30D, 90D, 1Y
- **Responsive**: ResizeObserver adapta los charts al ancho del contenedor
- **Sincronización de crosshair** entre candlestick y RSI
- **Deduplicación** y ordenamiento de datos antes de renderizar

**Archivos creados / modificados:**
- `static/charts.js` — Módulo completo de charts (~360 líneas)
- `static/index.html` — Sección de charts con CSS + HTML + wiring JS
- `backend/models/database.py` — Modelo `PortfolioSnapshot` para equity curve
- `main.py` — Endpoints `/api/market/{coin}/ohlc`, `/api/market/{coin}/history`, `/api/agents/{agent_id}/equity`

---

### 1b. 🔧 Fix Rate-Limit Blocking — COMPLETADO

**Estado**: ✅ Implementado  
**Fecha**: 2026-02-18  
**Área**: Backend / Infraestructura

**Problema**: CoinGecko retornaba HTTP 429 (rate limit) y el `RateLimiter` hacía `time.sleep(10799)` (~3 horas), bloqueando completamente la app.

**Solución implementada:**
- `MAX_WAIT_SECONDS = 5` — el `RateLimiter` nunca espera más de 5 segundos
- **Bloqueo temporal de CoinGecko**: al recibir 429, se activa `_coingecko_blocked_until` (cooldown de 5 minutos) en vez de dormir
- **`asyncio.to_thread()`**: el ciclo de trading completo se ejecuta en un thread separado y nunca bloquea el event loop de FastAPI
- **Fallback chain**: Binance → CoinGecko → `last_known_prices` (precios en caché)

**Archivos modificados:**
- `backend/services/market_data.py` — RateLimiter con cap, CoinGecko block flag, asyncio wrapping
- `main.py` — `run_trading_cycle()` usa `asyncio.to_thread(_sync_trading_cycle)`

---

### 1c. 🔄 Binance como Proveedor Primario — COMPLETADO

**Estado**: ✅ Implementado  
**Fecha**: 2026-02-18  
**Área**: Backend / Market Data

**Cambio**: Binance API reemplazó a CoinGecko como fuente primaria de datos de mercado.

**Implementación:**
- **BinanceProvider** (clase nueva): `get_prices()`, `get_market_data()`, `get_historical_prices()`, `get_ohlc()`
- **1200 req/min** sin API key (vs 10 req/min de CoinGecko free tier)
- **Fallback chain**: Binance (primary) → CoinGecko (fallback) → caché local
- **`_current_provider`**: tracking interno del proveedor activo, expuesto vía `get_provider()`
- **Endpoint `/api/market/prices`** retorna `{"provider": "Binance", "data": [...]}`
- **Health endpoint** muestra estado de ambos proveedores: `{"binance": "ok", "coingecko": "ok", "provider": "Binance"}`
- **Badge en dashboard**: "via Binance" (naranja) / "via CoinGecko" (azul) junto al título de Market Prices

**Archivos modificados:**
- `backend/services/market_data.py` — BinanceProvider, reordenamiento de proveedores, renombrado interno (_cg_*)
- `main.py` — Response con provider info, health endpoint actualizado
- `static/index.html` — Badge dinámico de proveedor

---

### Mejoras UX Implementadas

| Mejora | Descripción | Fecha |
|--------|-------------|-------|
| ⏱️ Countdown timers | Barra de progreso de 60s para Market Prices y News | 2026-02-18 |
| 🔗 News clickables | Títulos de noticias son links `<a>` que abren en nueva pestaña | 2026-02-18 |
| 🔠 Crypto names uppercase | Nombres de criptomonedas en mayúsculas | 2026-02-18 |
| 💵 Balance mínimo $50 | Reducido de $100 a $50 para accesibilidad | 2026-02-18 |
| ⚡ Refresh 15s | Precios cada 15s (Binance lo permite), news y agents cada 60s | 2026-02-19 |
| 💰 Smart price formatting | Decimales variables según magnitud del precio (fmtPrice) | 2026-02-19 |
| 🔍 Trade → Decision modal | Click en un trade abre modal con el AI Decision completo que lo originó | 2026-02-19 |

---

### 2. ⚙️ Estrategias Elite + Futuros (LONG/SHORT con Apalancamiento) — COMPLETADO

**Estado**: ✅ Implementado  
**Fecha**: 2026-02-19  
**Área**: Trading / Core Logic + UX

**Implementación entregada:**

#### 6 Estrategias Elite (inspiradas en top traders mundiales)

| Estrategia | Estilo | Lev. Default | Lev. Max | Max Pos. | Risk/Trade | Min Conf. | Inspiración |
|------------|--------|:------------:|:--------:|:--------:|:----------:|:---------:|-------------|
| **Trend Rider v2** | Trend Following | 3x | 5x | 3 | 2.5% | 0.55 | Paul Tudor Jones |
| **Mean Reversion** | Mean Reversion | 2x | 3x | 4 | 1.5% | 0.50 | Jim Simons / RenTech |
| **Momentum Sniper** | Momentum | 4x | 7x | 2 | 2.5% | 0.60 | Jesse Livermore |
| **Scalper Pro 1h** | Scalping | 5x | 10x | 5 | 4.0% | 0.50 | Market Makers |
| **Scalper Pro 1m** | Scalping | 10x | 20x | 5 | 2.0% | 0.50 | HFT |
| **Scalper Pro 3m** | Scalping | 8x | 15x | 5 | 2.5% | 0.50 | HFT |
| **Scalper Pro 5m** | Scalping | 7x | 12x | 5 | 3.0% | 0.50 | Daytrading |
| **Scalper Pro 15m** | Scalping | 6x | 10x | 5 | 3.5% | 0.50 | Swing Scalping |
| **Grid Trader** | Grid / Systematic | 2x | 3x | 8 | 1.0% | 0.40 | Quant desks |
| **Confluence Master** | Multi-factor | 5x | 10x | 2 | 3.0% | 0.70 | Institutional |

#### Indicadores Técnicos Profesionales

| Indicador | Implementación | Uso |
|-----------|---------------|-----|
| EMA Series (9/21/55) | Full EMA con SMA seed | Trend Rider, Confluence |
| RSI (Wilder-smoothed) | Series completa + point values | Todas las estrategias |
| MACD (proper) | EMA-9 de MACD series como signal line | Momentum Sniper, Confluence |
| Bollinger Bands | %B + squeeze detection | Mean Reversion, Scalper |
| ATR (14-period Wilder) | Absoluto + % del precio | Stop-loss/Take-profit dinámicos |
| ADX (+DI/-DI) | Trending/Strong trend detection | Trend Rider, Mean Reversion |
| Stochastic RSI (%K/%D) | Oversold/Overbought zones | Scalper, Confluence |
| Volume Analysis | Ratio, spike, trend detection | Momentum Sniper, Confluence |

#### Futuros (LONG/SHORT con Apalancamiento)

- **Posiciones LONG y SHORT**: El agente puede abrir posiciones en ambas direcciones
- **Apalancamiento configurable**: 1x a 125x por agente (respetando max de estrategia)
- **Position sizing profesional**: Basado en % de capital por trade y distancia de stop-loss
- **Precio de liquidación**: `LONG = entry*(1-0.9/leverage)`, `SHORT = entry*(1+0.9/leverage)`
- **Stop-loss y Take-profit automáticos**: Calculados dinámicamente con ATR
- **Margin management**: Margin se deduce del balance, se retorna margin+PnL al cerrar
- **Liquidation check**: Cada ciclo verifica si el precio alcanzó liquidación
- **Scan-all-coins**: El agente escanea top 6 monedas por volatilidad y elige la mejor señal
- **News sentiment adjustment**: ±0.05 confidence basado en alineación de noticias

#### Frontend

- **Strategy Picker**: Cards visuales con descripción al crear agente
- **Leverage Slider**: 1-50x con valor visible
- **Badges**: LONG (verde), SHORT (rojo), leverage (naranja), strategy (morado)
- **Portfolio table**: Type, Leverage, Margin, P&L, Liquidation Price
- **Trade log**: OPEN_LONG/CLOSE_SHORT con colores, leverage badge, margin
- **Decision log**: Strategy badge, action con LONG/SHORT icons

**Archivos creados / modificados:**

| Archivo | Líneas | Cambio |
|---------|--------|--------|
| `backend/services/strategies.py` | ~1140 | **NUEVO** — Signal, StrategyConfig, Indicators, StrategyEngine, 6 estrategias, position sizing, liquidation calc |
| `backend/services/trading_agent.py` | ~486 | **REESCRITO** — Futures lifecycle, strategy engine, scan-all-coins |
| `backend/models/database.py` | ~110 | Campos futures (position_type, leverage, margin, liquidation, SL/TP) |
| `backend/services/market_data.py` | — | Volume añadido a OHLC data |
| `main.py` | ~524 | Endpoint `/api/strategies`, futures PnL, create con strategy/leverage |
| `static/index.html` | ~1100+ | Strategy picker, leverage slider, position badges, futures columns |

---

## Próximas Features (priorizadas)

### 3. 🤖 LLM para Análisis de Noticias + Razonamiento del Agente — COMPLETADO

**Estado**: ✅ Implementado  
**Fecha**: 2026-02-19  
**Área**: Inteligencia / IA  
**Modelo**: Gemini 2.0 Flash (free tier: 15 RPM, 1M tokens/min)

**Implementación entregada:**

- **`backend/services/llm_service.py`** (~270 líneas): Servicio modular con `LLMService` class
- **Análisis por trade**: Cuando el strategy engine genera una señal (LONG/SHORT), el LLM recibe indicadores técnicos + noticias recientes y produce:
  - **Razonamiento en lenguaje natural** (explicación comprensible de la decisión)
  - **Ajuste de confianza** (±15% máximo, basado en análisis holístico)
  - **Notas de riesgo**, resumen de noticias, contexto de mercado
- **Rate limiting inteligente**: 4.5s mínimo entre llamadas (≤15 RPM)
- **Auto-disable**: 3 fallos consecutivos → cooldown de 5 minutos → reintenta automáticamente
- **JSON estructurado**: `response_mime_type="application/json"`, temperature=0.3
- **Integración con trading agent**: `_get_llm_analysis()` enriquece cada trade, datos guardados en DB
- **Frontend**: Bloque "🧠 AI Analysis" con badge de ajuste de confianza (verde/rojo/neutral)
- **Health endpoint**: `llm_service: {status: "ok", model: "gemini-2.0-flash"}`

**Archivos creados / modificados:**

| Archivo | Cambio |
|---------|--------|
| `backend/services/llm_service.py` | **NUEVO** — LLMService, LLMAnalysis dataclass, rate limiting, auto-disable |
| `backend/services/trading_agent.py` | LLM integration (_get_llm_analysis, confidence adjustment) |
| `backend/models/database.py` | Campos `llm_reasoning`, `llm_sentiment_adj` en Decision |
| `main.py` | LLMService init, health check, decisions API update |
| `static/index.html` | LLM reasoning CSS/display blocks |
| `requirements.txt` | `google-generativeai>=0.4.0` |

---

### 3b. 📡 Migración a Binance Futures API — COMPLETADO

**Estado**: ✅ Implementado  
**Fecha**: 2026-02-19  
**Área**: Market Data / Infraestructura

**Problema**: Estábamos usando `api.binance.com/api/v3` (SPOT) para obtener precios, pero nuestra app simula trading de futuros con apalancamiento. Los precios de futuros difieren del spot.

**Solución implementada:**

- **Endpoint primario**: `fapi.binance.com/fapi/v1` (Binance Futures USDT-M)
- **Mark Price** como precio principal: Es el precio que Binance usa para calcular liquidaciones, más relevante para simulación de futuros
- **Funding Rate**: Tasa de financiamiento expuesta en API y mostrada en dashboard — indica sesgo del mercado (positivo = longs pagan, negativo = shorts pagan)
- **Fallback a Spot**: Si la API de futuros falla, se usa automáticamente `api.binance.com/api/v3`
- **Klines de futuros**: OHLC data también viene del mercado de futuros
- **Frontend**: Cada coin card muestra funding rate con color (verde = positivo, rojo = negativo)
- **Health**: `binance_futures: ok`, provider: `"Binance Futures"`

**Endpoints utilizados:**

| Endpoint | Datos |
|----------|-------|
| `/fapi/v1/premiumIndex` | Mark Price, Funding Rate, Next Funding Time |
| `/fapi/v1/ticker/24hr` | Last Price, Volume, 24h Change, High/Low |
| `/fapi/v1/klines` | OHLC candlestick data (futuros) |

**Archivos modificados:**

| Archivo | Cambio |
|---------|--------|
| `backend/services/market_data.py` | `FUTURES_URL`, `SPOT_URL`, `get_prices()` usa mark price, `get_market_data()` incluye funding rate, fallbacks a spot |
| `backend/services/trading_agent.py` | `funding_rate` y `mark_price` añadidos a indicators |
| `static/index.html` | Funding rate display en price cards, provider badge update |

---

### 3c. 🔍 Trade → Decision Tracking (Modal) — COMPLETADO

**Estado**: ✅ Implementado  
**Fecha**: 2026-02-19  
**Área**: UX / Traceability

**Problema**: Las decisiones de AI se perdían en el log al pasar el tiempo, sin forma de saber qué análisis originó cada trade.

**Solución implementada:**

- **`decision_id` FK en Trade**: Cada trade queda vinculado a la decisión que lo originó
- **API `GET /api/decisions/{id}`**: Endpoint para obtener detalles de una decisión individual
- **Trades clickeables**: En "Recent Trades", los trades con decisión asociada son clickeables (borde cyan al hover + hint "🔍 Click to see AI decision")
- **Modal de detalle**: Al hacer click se abre un modal oscuro con:
  - Header con moneda, dirección (LONG/SHORT), estrategia
  - Strategy Reasoning con confianza
  - Technical Indicators en grid
  - News Considered (si aplica)
  - 🧠 Gemini AI Analysis completa

**Archivos modificados:**

| Archivo | Cambio |
|---------|--------|
| `backend/models/database.py` | `decision_id` FK en Trade, relationship |
| `backend/services/trading_agent.py` | `_log_decision()` retorna ID, linkeo en `_open_position`/`_close_position` |
| `main.py` | `decision_id` en trades response, `GET /api/decisions/{id}` |
| `static/index.html` | Modal CSS/HTML/JS, trades clickeables |

---

### 4. 🔙 Backtesting con Datos Históricos — COMPLETADO

**Estado**: ✅ Implementado  
**Fecha**: 2026-02-19  
**Área**: Trading / Validación

**Implementación entregada:**

- **`backend/services/backtester.py`** (~700 líneas): Motor de backtesting completo
  - Replay de klines históricas de Binance a través del StrategyEngine
  - Simulación completa de futuros: LONG/SHORT, leverage, margin, liquidación, SL/TP
  - Indicadores computados con sliding window de 200 candles (O(n) vs O(n²))
  - Warmup de 100 candles antes de generar señales
  - Métricas: total return, max drawdown, Sharpe ratio, profit factor, win rate, R:R promedio
  - Equity curve con estrategia vs Buy & Hold
  
- **`POST /api/backtest`**: Endpoint con `asyncio.to_thread()` para no bloquear
- **Frontend**: Sección separada "Backtesting" con nav bar (Dashboard | Backtesting)
  - Selector de estrategia, moneda, período, balance, leverage
  - Metric cards: Gross Return, Net Return, Fees, B&H, DD, Sharpe, WR, PF, Trades, Balance
  - Equity curve con TradingView (Net + Gross + Buy & Hold)
  - Trades table con Fee column

**Períodos soportados**: 1, 3, 7, 14, 30, 90, 180, 365 días

---

### 4b. 📟 Backtest CLI Tool — COMPLETADO

**Estado**: ✅ Implementado  
**Fecha**: 2026-02-19  
**Área**: DevTools / Productividad

**`backtest_cli.py`** (~320 líneas): Herramienta CLI para backtesting rápido sin abrir el browser.

**Uso:**
```bash
# Single test
python3 backtest_cli.py -s scalper -c bitcoin -p 30

# Compare all 10 strategies vs BTC 90d
python3 backtest_cli.py --compare

# Run all 5 scalper variants with max periods
python3 backtest_cli.py --scalpers

# Multi-coin multi-period
python3 backtest_cli.py -s trend_rider scalper -c bitcoin ethereum solana -p 30 90
```

**Features:**
- Tabla comparativa con colores (verde/rojo)
- Columnas: Strategy, Coin, Days, Gross, Net, Fees, B&H, Alpha, Trades, WR, PF, DD
- Detalle individual: R:R, Sharpe, desglose Comm + Funding
- Labels de coins (BTC, ETH, SOL)
- `--scalpers` mode: ejecuta las 5 variantes de scalper con sus períodos óptimos
- HTTP timeout 300s

---

### 4c. ⏱️ Scalper Pro — Variantes de Timeframe — COMPLETADO

**Estado**: ✅ Implementado  
**Fecha**: 2026-02-19  
**Área**: Trading / Estrategias

4 nuevas variantes del Scalper Pro para diferentes timeframes, todas usando la misma arquitectura de 6 capas:

| Variante | Candle | Período Max | Leverage | Risk | Resultado BTC |
|----------|--------|:-----------:|:--------:|:----:|:-------------:|
| **Scalper Pro 1h** | 1h | 180d | 5x | 4.0% | **+37.8%** (30d) |
| **Scalper Pro 15m** | 15m | 90d | 6x | 3.5% | +11.6% (90d) |
| **Scalper Pro 1m** | 1m | 3d | 10x | 2.0% | +3.0% (3d) |
| **Scalper Pro 5m** | 5m | 30d | 7x | 3.0% | -6.9% (30d) |
| **Scalper Pro 3m** | 3m | 14d | 8x | 2.5% | -32.2% (14d) |

**Nota**: Timeframes más cortos generan más ruido. 1h y 15m son los más rentables.

**Arquitectura de 6 capas del Scalper Pro:**
1. **EMA Trend** (9>21>55): Filtro de dirección
2. **RSI Pullback**: Entrada en pullback dentro de la tendencia
3. **Bollinger Band**: Timing de entrada (pullback a soporte/resistencia)
4. **MACD Momentum**: Crossover como catalizador
5. **StochRSI**: Precisión de timing (cross from oversold/overbought)
6. **Volume**: Confirmación final

**Stops**: ATR×1.0 SL, ATR×3.0 TP (3:1 R:R mínimo)

**Optimización de rendimiento**: Sliding window de 200 candles para indicadores (evita O(n²) con miles de candles de 1m/3m/5m).

**Archivos modificados:**

| Archivo | Cambio |
|---------|--------|
| `backend/services/strategies.py` | 4 nuevas configs + dispatch al mismo `_scalper()` |
| `backend/services/backtester.py` | `_SCALPER_INTERVALS` mapping, close logic `startswith("scalper")` |
| `main.py` | Períodos 1, 3 añadidos a validación |
| `static/index.html` | Scalper 1m/3m/5m/15m en dropdown, 1d/3d en períodos |
| `backtest_cli.py` | `--scalpers` mode |

---

### 4d. 💰 Modelo de Comisiones y Fees — COMPLETADO

**Estado**: ✅ Implementado  
**Fecha**: 2026-02-19  
**Área**: Backtesting / Realismo

Simulación realista de costos de trading en Binance Futures:

| Fee | Tasa | Aplicación |
|-----|------|------------|
| **Taker Fee** | 0.05% | Por lado (open + close) sobre valor de posición |
| **Maker Fee** | 0.02% | (disponible, actualmente usa taker) |
| **Funding Rate** | 0.01% | Cada 8 horas sobre valor de posición abierta |

**Implementación:**

- **Balance dual**: `balance` (net, con fees) y `balance_gross` (sin fees) trackeados en paralelo
- **Fee por trade**: `_open_position()` retorna `(Position, open_fee)`, `_check_position_exit()` retorna `(cash_back, cash_back_gross, close_fee)`
- **Funding simulation**: Se acumula cada N candles según el intervalo (8h / candle_hours)
- **BacktestResult expandido**: `total_return_gross_pct`, `final_balance_gross`, `total_commissions`, `total_funding`, `total_fees`
- **Equity curve**: 3 líneas — Net (azul), Gross (púrpura punteada), Buy & Hold (naranja)
- **Trade records**: Campo `commission` por trade individual

**Ejemplo real (Scalper Pro 1h, BTC 30d, $1000):**
- Gross: **+18.4%** → Net: **+15.3%** (fees: $31.16 = $27.72 comm + $3.45 funding)

**Frontend:**
- Metric cards: Gross Return, Net Return, Total Fees (tooltip con desglose)
- Equity curve con línea Gross adicional
- Trades table con columna Fee

**CLI:**
- Líneas separadas: Gross, Net, Fees (Comm + Funding)
- Tabla comparativa con columnas Gross, Net, Fees

**Archivos modificados:**

| Archivo | Cambio |
|---------|--------|
| `backend/services/backtester.py` | Constantes de fees, BacktestResult expandido, dual balance tracking, funding simulation |
| `static/index.html` | Metric cards Gross/Net/Fees, equity curve gross line, trade Fee column |
| `backtest_cli.py` | print_result y print_compare_table con Gross/Net/Fees |

---

### 4e. 🔄 Trend Rider v2 — Optimización con 3:1 R:R — COMPLETADO

**Estado**: ✅ Implementado  
**Fecha**: 2026-02-19  
**Área**: Trading / Estrategias

Reescritura del Trend Rider aplicando los principios del Scalper Pro:

**Cambios vs v1:**

| Aspecto | v1 (antes) | v2 (después) |
|---------|:----------:|:------------:|
| R:R | 2:1 (ATR×2 SL, ATR×4 TP) | **3:1** (ATR×1.5 SL, ATR×4.5 TP) |
| Estructura | Flat scoring (4 indicadores) | **6 capas** (como Scalper Pro) |
| Pullback entry | No (entra en señal directa) | **Sí** (RSI 35-48 uptrend / 52-65 downtrend) |
| Counter-trend penalty | No | **-2 puntos** |
| Weak ADX penalty | Ninguno | **-2 puntos** (evita mercados choppy) |
| Volume confirmation | No | **Sí** |
| StochRSI timing | No | **Sí** |
| BB timing | No | **Sí** (pullback a soporte/resistencia) |
| **Hard gate** | Ninguno | **Requiere EMA 9>21>55 full alignment** para abrir |
| Overextended filter | No | **Sí** (RSI >72 / <28 penaliza chasing) |

**Resultados comparativos (Net, con comisiones):**

| Test | v1 | v2 | Delta |
|------|:--:|:--:|:-----:|
| BTC 30d | +15.9% | **+23.1%** | +7.2 |
| ETH 30d | +7.9% | **+16.6%** | +8.7 |
| SOL 30d | +7.3% | **+17.7%** | +10.4 |
| SOL 90d | +7.4% | **+17.6%** | +10.2 |
| BTC 90d | +11.3% | +0.7% | -10.6 |
| ETH 90d | +1.1% | -2.6% | -3.7 |
| **Promedio** | **+8.5%** | **+12.2%** | **+3.7** |

**Tradeoff**: 30d mejoró dramáticamente. 90d en BTC/ETH bajó porque el mercado fue fuertemente bajista y el 3:1 R:R con stops más tight genera más stopouts. SOL 90d mejoró +10.2%.

**Archivos modificados:**

| Archivo | Cambio |
|---------|--------|
| `backend/services/strategies.py` | `_trend_rider()` reescrito (6 capas + hard gate), config risk 2.5% |

---

### 5. 🔔 Notificaciones + Alertas (Telegram / Email)

**Impacto**: Alto  
**Área**: UX / Engagement  
**Dependencias**: Ninguna

Bot de Telegram y/o email para notificar:

- Trade ejecutado (buy/sell) con detalles
- Alerta de stop-loss activado
- Oportunidad detectada (sin auto-ejecutar)
- Resumen diario del portfolio
- Alertas de precio (Bitcoin cruza $X)

**Implementación**: `notification_service.py` con adaptadores para Telegram (python-telegram-bot) y email (SMTP).

---

## Backlog Completo — Otras Ideas

### Inteligencia / Análisis

| ID | Feature | Impacto | Estado |
|----|---------|---------|--------|
| A1 | Fear & Greed Index (alternative.me) | Medio | Pendiente |
| A2 | On-chain data (whale movements, exchange flows) | Alto | Pendiente |
| A3 | Correlación entre monedas para diversificación | Medio | Pendiente |
| A4 | Pattern recognition (double bottom, H&S, etc.) | Medio | Pendiente |
| A5 | Social sentiment (X/Reddit scraping) | Alto | Pendiente |
| A6 | Multi-timeframe analysis (1H, 4H, 1D) | Alto | Pendiente |

### Trading / Estrategia

| ID | Feature | Impacto | Estado |
|----|---------|---------|--------|
| B1 | DCA automático como estrategia standalone | Medio | Pendiente (no incluido en las 6 elite) |
| B2 | Detección de oportunidades sin ejecución (alert-only mode) | Medio | Incluido en #5 |
| B3 | Preparar arquitectura para trading real (Binance/Coinbase API) | Alto | Pendiente |
| B4 | Portfolio rebalancing automático | Medio | Pendiente |
| B5 | Trailing stop-loss dinámico (ATR-based) | Alto | Pendiente |
| B6 | Trailing take-profit (lock in gains) | Alto | Pendiente |

### UX / Dashboard

| ID | Feature | Impacto | Estado |
|----|---------|---------|--------|
| C1 | Comparación lado a lado de múltiples agentes | Medio | Pendiente |
| C2 | Dark mode | Bajo | Pendiente |
| C3 | Mobile responsive mejorado | Medio | Pendiente |
| C4 | Export CSV de trades (análisis externo / impuestos) | Medio | Pendiente |
| C5 | Leaderboard / ranking de agentes | Medio | Pendiente |

### Configuración / Sistema

| ID | Feature | Impacto | Estado |
|----|---------|---------|--------|
| D1 | Panel de configuración global (no hardcodeado) | Alto | Pendiente |
| D2 | Sistema de usuarios / autenticación | Medio | Pendiente |
| D3 | Persistir configuraciones en DB | Medio | Pendiente |
| D4 | API rate-limit dashboard (ver uso de APIs) | Bajo | Parcial (health endpoint muestra estado de ambos proveedores) |

---

## Configuración de Producto

### Límites de Balance

| Parámetro | Valor |
|-----------|-------|
| Balance mínimo por agente | **$50 USD** |
| Balance default al crear agente | $10,000 USD |
| Inversión mínima por trade (margin) | $10 USD |
| Máximo % por posición individual | 25% del balance |
| Apalancamiento máximo | 125x (configurable por agente) |
| Posiciones | LONG y SHORT |
| Risk management | Position sizing basado en % de capital y stop-loss distance |

---

## Orden de Implementación

```
1.  Gráficos Candlestick ──→ ✅ COMPLETADO (2026-02-18)
1b. Fix Rate-Limit Blocking ──→ ✅ COMPLETADO (2026-02-18)
1c. Binance Primary Provider ──→ ✅ COMPLETADO (2026-02-18)
2.  Estrategias Elite + Futuros ──→ ✅ COMPLETADO (2026-02-19)
3.  LLM Análisis (Gemini 2.0 Flash) ──→ ✅ COMPLETADO (2026-02-19)
3b. Migración a Binance Futures API ──→ ✅ COMPLETADO (2026-02-19)
3c. Trade → Decision Tracking ──→ ✅ COMPLETADO (2026-02-19)
4.  Backtesting ──→ ✅ COMPLETADO (2026-02-19)
4b. Backtest CLI Tool ──→ ✅ COMPLETADO (2026-02-19)
4c. Scalper Pro Variantes (1m/3m/5m/15m) ──→ ✅ COMPLETADO (2026-02-19)
4d. Modelo de Comisiones y Fees ──→ ✅ COMPLETADO (2026-02-19)
4e. Trend Rider v2 (3:1 R:R) ──→ ✅ COMPLETADO (2026-02-19)
5.  Notificaciones ──→ next (add-on independiente)
```

---

## Arquitectura Actual

| Componente | Tecnología | Detalle |
|------------|-----------|---------|
| Backend | FastAPI + uvicorn | Puerto 8001, 19 endpoints + WebSocket |
| Base de datos | SQLite + SQLAlchemy | 6 modelos (TradingAgent, Portfolio, Trade, Decision, PortfolioSnapshot, NewsEvent) |
| Market Data (primary) | **Binance API** | 1200 req/min, sin API key, precios + OHLC + históricos + volumen |
| Market Data (fallback) | CoinGecko API | 10 req/min free tier, RateLimiter con 5s max wait |
| Noticias | RSS feeds | CoinDesk, CoinTelegraph, Bitcoin Magazine + CryptoPanic (opcional) |
| Charts | TradingView Lightweight Charts v4 | CDN, open source, candlestick + indicadores |
| Indicadores | RSI, MACD, BB, EMA, SMA, ATR, ADX, StochRSI, Volume | Library completa en strategies.py |
| Estrategias | 10 (trend/mean_rev/momentum/scalper×5/grid/confluence) | StrategyEngine con scoring + signal generation |
| Backtesting | Motor completo con commission model | Replay de klines, dual balance (gross/net), funding rate |
| CLI | backtest_cli.py | Comparativas rápidas, --compare, --scalpers |
| Futuros | LONG/SHORT, leverage 1-125x, liquidation, SL/TP | Position sizing profesional |
| Scheduler | APScheduler | Ciclo de trading cada 60s |
| Async | asyncio.to_thread() | Trading cycle nunca bloquea el event loop |

### Estructura de archivos (~9,500+ líneas)

| Archivo | Líneas | Responsabilidad |
|---------|--------|----------------|
| `main.py` | 595+ | Endpoints, scheduler, WebSocket, backtest API |
| `backend/services/strategies.py` | 1400+ | Indicadores técnicos, 10 estrategias, position sizing |
| `backend/services/backtester.py` | 700+ | Motor de backtesting, commission model, sliding window |
| `backend/services/market_data.py` | 780+ | RateLimiter, BinanceProvider (Futures+Spot), MarketDataService |
| `backend/services/trading_agent.py` | 570+ | Futures lifecycle, strategy engine, LLM integration |
| `backend/services/llm_service.py` | 270 | Gemini 2.0 Flash, LLMAnalysis, rate limiting |
| `backend/services/news_service.py` | 313 | RSS feeds, sentimiento por keywords |
| `backend/models/database.py` | 130+ | 6 modelos SQLAlchemy (con campos futures + LLM + decision_id) |
| `static/index.html` | 1830+ | Dashboard + Backtesting SPA, strategy picker, futures UI, LLM blocks |
| `static/charts.js` | 359 | Módulo de charts TradingView |
| `backtest_cli.py` | 320+ | CLI de backtesting, comparativas, colores |

---

## Notas

- Todas las features deben ser compatibles con balances pequeños ($50-$100)
- Priorizar APIs gratuitas o de muy bajo costo
- Mantener la app funcional en cada paso (no romper el MVP)
- **Binance Futures es el proveedor primario** — Spot y CoinGecko solo se usan como fallback
- **Mark Price** como precio principal (usado para liquidaciones reales en Binance)
- **Funding Rate** disponible en dashboard y en indicadores del trading agent
- **No bloquear el event loop** — toda I/O síncrona va en `asyncio.to_thread()`
- DoD: features completas funcionales, code review al finalizar (no unit tests)
