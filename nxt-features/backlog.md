# Money Maker — Feature Backlog

> Última actualización: 2026-02-19

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
| **Trend Rider** | Trend Following | 3x | 5x | 3 | 2.0% | 0.55 | Paul Tudor Jones |
| **Mean Reversion** | Mean Reversion | 2x | 3x | 4 | 1.5% | 0.50 | Jim Simons / RenTech |
| **Momentum Sniper** | Momentum | 4x | 7x | 2 | 2.5% | 0.60 | Jesse Livermore |
| **Scalper Pro** | Scalping | 5x | 10x | 5 | 0.5% | 0.45 | Market Makers |
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

### 4. 🔙 Backtesting con Datos Históricos

**Impacto**: Muy Alto  
**Área**: Trading / Validación  
**Dependencias**: Feature #2 (estrategias configurables)

Simular una estrategia contra datos históricos reales antes de activarla:

- El usuario selecciona: estrategia, moneda(s), período (30/90/365 días)
- El sistema ejecuta el loop de trading sobre datos históricos de CoinGecko
- Muestra resultados: rendimiento total, max drawdown, Sharpe ratio, # trades
- Gráfico comparativo: estrategia vs buy-and-hold
- Guardar resultados para comparar entre estrategias

**Datos**: CoinGecko ya provee datos históricos diarios hasta 365 días gratis.

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
4.  Backtesting ──→ next (dependencia: estrategias ✅)
5.  Notificaciones ──→ add-on independiente
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
| Estrategias | 6 elite (trend/mean_rev/momentum/scalper/grid/confluence) | StrategyEngine con scoring + signal generation |
| Futuros | LONG/SHORT, leverage 1-125x, liquidation, SL/TP | Position sizing profesional |
| Scheduler | APScheduler | Ciclo de trading cada 60s |
| Async | asyncio.to_thread() | Trading cycle nunca bloquea el event loop |

### Estructura de archivos (~7,200+ líneas)

| Archivo | Líneas | Responsabilidad |
|---------|--------|----------------|
| `main.py` | 540+ | Endpoints, scheduler, WebSocket |
| `backend/services/strategies.py` | 1140 | Indicadores técnicos, 6 estrategias, position sizing |
| `backend/services/market_data.py` | 780+ | RateLimiter, BinanceProvider (Futures+Spot), MarketDataService |
| `backend/services/trading_agent.py` | 570+ | Futures lifecycle, strategy engine, LLM integration |
| `backend/services/llm_service.py` | 270 | Gemini 2.0 Flash, LLMAnalysis, rate limiting |
| `backend/services/news_service.py` | 313 | RSS feeds, sentimiento por keywords |
| `backend/models/database.py` | 130+ | 6 modelos SQLAlchemy (con campos futures + LLM + decision_id) |
| `static/index.html` | 1450+ | Dashboard con strategy picker, futures UI, LLM blocks, decision modal |
| `static/charts.js` | 359 | Módulo de charts TradingView |

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
