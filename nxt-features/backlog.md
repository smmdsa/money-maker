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

### 3. 🤖 LLM para Análisis de Noticias + Razonamiento del Agente

**Impacto**: Alto  
**Área**: Inteligencia / IA  
**Dependencias**: API key externa (OpenAI, Anthropic, o modelo local)

Integrar un LLM económico para:

- **Análisis de sentimiento profundo**: Leer la noticia completa, no solo keywords del título
- **Razonamiento en lenguaje natural**: Explicar cada decisión en un texto comprensible
  - Ejemplo: *"Vendí SOL porque Abu Dhabi redujo su exposición a altcoins según CoinDesk, combinado con RSI 72 (sobrecompra) y MACD bearish"*
- **Resumen diario**: Generar un briefing matutino del mercado

**Opciones de modelo** (de menor a mayor costo):
| Modelo | Costo aprox. | Ventaja |
|--------|-------------|---------|
| Llama 3 (local) | $0 | Sin costo, privacidad total |
| GPT-4o-mini | ~$0.15/1M tokens | Muy barato, rápido |
| Claude Haiku | ~$0.25/1M tokens | Buen análisis |
| Gemini Flash | Gratis (tier free) | Sin costo inicial |

**Implementación**: Servicio modular `llm_service.py` con interfaz agnóstica del proveedor.

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
1. Gráficos Candlestick ──→ ✅ COMPLETADO (2026-02-18)
1b. Fix Rate-Limit Blocking ──→ ✅ COMPLETADO (2026-02-18)
1c. Binance Primary Provider ──→ ✅ COMPLETADO (2026-02-18)
2. Estrategias Elite + Futuros ──→ ✅ COMPLETADO (2026-02-19)
3. LLM Análisis ──→ requiere API key externa
4. Backtesting ──→ depende de que estrategias estén definidas ✅
5. Notificaciones ──→ add-on independiente, se puede hacer en paralelo con 3-4
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

### Estructura de archivos (~5,900+ líneas)

| Archivo | Líneas | Responsabilidad |
|---------|--------|-----------------|
| `main.py` | 524 | Endpoints, scheduler, WebSocket |
| `backend/services/strategies.py` | 1140 | Indicadores técnicos, 6 estrategias, position sizing |
| `backend/services/market_data.py` | 652 | RateLimiter, BinanceProvider, MarketDataService |
| `backend/services/trading_agent.py` | 486 | Futures lifecycle, strategy engine integration |
| `backend/services/news_service.py` | 313 | RSS feeds, sentimiento por keywords |
| `backend/models/database.py` | ~110 | 6 modelos SQLAlchemy (con campos futures) |
| `static/index.html` | 1100+ | Dashboard completo con strategy picker + futures UI |
| `static/charts.js` | 359 | Módulo de charts TradingView |

---

## Notas

- Todas las features deben ser compatibles con balances pequeños ($50-$100)
- Priorizar APIs gratuitas o de muy bajo costo
- Mantener la app funcional en cada paso (no romper el MVP)
- **Binance es el proveedor primario** — CoinGecko solo se usa como fallback
- **No bloquear el event loop** — toda I/O síncrona va en `asyncio.to_thread()`
- DoD: features completas funcionales, code review al finalizar (no unit tests)
