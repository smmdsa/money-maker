# Money Maker — Feature Backlog

> Última actualización: 2026-02-19 (sesión 5)

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
| 📊 Positions full-width | Posiciones abiertas como cards full-width con SL/TP/Liq/progress bar | 2026-02-19 |
| 💵 Expected P&L | Profit esperado en TP y pérdida esperada en SL debajo de cada precio | 2026-02-19 |
| ✕ Manual close buttons | Botones para cerrar posiciones individuales o todas a la vez | 2026-02-19 |
| 📈 Chart price sync | Último candle se actualiza cada 15s con precio real | 2026-02-19 |
| 🎯 Account profiles | 4 presets (Micro/Small/Standard/Large) con auto-suggest por balance | 2026-02-19 |
| 🕐 Market clocks | 8 mercados mundiales con hora real, alertas y trading context | 2026-02-19 |

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
| **Scalper Pro 1h** | Scalping | 5x | 10x | 5 | 4.0% | 0.30 | Market Makers |
| **Scalper Pro 1m** | Scalping | 10x | 20x | 5 | 2.0% | 0.25 | HFT |
| **Scalper Pro 3m** | Scalping | 8x | 15x | 5 | 2.5% | 0.25 | HFT |
| **Scalper Pro 5m** | Scalping | 7x | 12x | 5 | 3.0% | 0.25 | Daytrading |
| **Scalper Pro 15m** | Scalping | 6x | 10x | 5 | 3.5% | 0.30 | Swing Scalping |
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

### 5. ⚡ Risk Monitor — Monitoreo de Posiciones Abiertas en Tiempo Real

**Impacto**: Crítico (gestión de riesgo)  
**Área**: Trading / Risk Management  
**Dependencias**: Feature #2 (futuros con SL/TP/liquidación)

**Problema**: El ciclo de trading cada 60s deja posiciones abiertas sin supervisar durante largos períodos. Un flash crash de BTC del 5% en 10 segundos con apalancamiento 5x = -25% antes de que el sistema reaccione. En crypto (mercado 24/7), esto es un riesgo real.

**Solución**: Dos loops independientes con responsabilidades separadas.

| Loop | Frecuencia | Responsabilidad |
|------|-----------|----------------|
| **Decision Loop** (existente) | 60s | Análisis técnico completo, señales, abrir/cerrar por estrategia |
| **Risk Monitor** (nuevo) | 5s | SOLO verificar SL/TP/liquidación en posiciones abiertas |

#### Fase 1: Polling Risk Monitor (5s) — COMPLETADO

**Estado**: ✅ Implementado  
**Fecha**: 2026-02-19

Loop ligero que cada 5 segundos:
1. Obtiene lista de agentes activos con posiciones abiertas
2. Consulta precio actual de cada coin con posición (`GET /fapi/v1/ticker/price`)
3. Verifica: `precio <= stop_loss` → cierra, `precio >= take_profit` → cierra, `precio <= liquidation` → cierra urgente
4. **NO** calcula indicadores ni evalúa estrategias — es puramente defensivo
5. Notifica por WebSocket si cierra alguna posición

**Frecuencia 5s — justificación:**
- ✅ Detecta flash crashes (un crash de 30s se detecta al menos 6 veces)
- ✅ Binance-friendly (~12 req/min por posición, bien dentro del límite de 1200)
- ✅ No genera ruido (no toma decisiones, solo protege)
- ❌ 1s sería excesivo (rate limits, CPU, false alerts por micro-ticks)

**Archivos modificados:**

| Archivo | Cambio |
|---------|--------|
| `backend/services/trading_agent.py` | `check_risk()` — método ligero de verificación SL/TP/liquidación |
| `main.py` | Segundo job APScheduler cada 5s, `_sync_risk_check()` |

#### Fase 2: Binance WebSocket Streams (futura)

**Estado**: 📋 Planificado  
**Impacto**: Latencia de monitoreo de ~5s → ~100ms

Reemplazar el polling de Fase 1 por WebSocket push de Binance Futures:

```
wss://fstream.binance.com/ws/btcusdt@ticker
```

**Ventajas vs polling:**
- **Zero polling**: Binance envía el precio cuando cambia, no necesitamos preguntar
- **Latencia ~100ms**: Detección casi instantánea de SL/TP/liquidación
- **Menos requests**: No consume el rate limit de REST API
- **Multi-stream**: Un solo WebSocket puede suscribirse a múltiples símbolos

**Implementación planificada:**
- `backend/services/ws_monitor.py` — Manager de WebSocket connections
- Suscripción dinámica: cuando un agente abre posición en BTCUSDT → subscribe al stream
- Cuando cierra → unsubscribe
- Reconnect automático con backoff exponencial
- Fallback a polling (Fase 1) si WebSocket se desconecta

**Complejidad**: Media-Alta (gestión de conexiones async, reconexión, estado compartido)

---

### 5b. 📊 Open Positions UI — Rediseño Full-Width — COMPLETADO

**Estado**: ✅ Implementado  
**Fecha**: 2026-02-19  
**Área**: UX / Dashboard

**Problema**: Las posiciones abiertas se mostraban como una tabla pequeña dentro del card de Agent Details, difícil de leer y sin datos de riesgo.

**Solución implementada:**

- **Sección full-width independiente** entre Charts y Equity Curve (como una sección propia)
- **Position cards** (`.pos-card`) con layout grid 4 columnas:
  - Col 1: Coin + badges (LONG/SHORT, leverage)
  - Col 2: Precios SL/TP/Liquidación con **profit/loss esperado** debajo de cada uno
  - Col 3: P&L actual (valor + %)
  - Col 4: Botón Close individual
- **Barra de progreso SL↔TP**: Colored bar (rojo→naranja→verde) mostrando posición actual entre SL y TP
- **Botón "Close All"**: En el header de la sección, cierra todas las posiciones del agente
- **Expected Profit/Loss**: Debajo de SL muestra pérdida esperada, debajo de TP muestra ganancia esperada

**Endpoints nuevos:**
- `POST /api/agents/{id}/positions/{pos_id}/close` — Cierre manual individual
- `POST /api/agents/{id}/positions/close-all` — Cierre masivo

**Método nuevo en trading agent:**
- `close_position_manual()` — Obtiene precio actual, llama a `_close_position()` con razón "🖐 Manual close by user"

**Archivos modificados:**

| Archivo | Cambio |
|---------|--------|
| `static/index.html` | Sección `.positions-section` full-width, `renderPositions()`, `closePosition()`, `closeAllPositions()`, CSS pos-cards |
| `main.py` | 2 endpoints nuevos (close position, close all) |
| `backend/services/trading_agent.py` | `close_position_manual()` método público |

---

### 5c. 📈 Chart Price Sync — COMPLETADO

**Estado**: ✅ Implementado  
**Fecha**: 2026-02-19  
**Área**: UX / Charts

**Problema**: El chart de candlestick solo cargaba datos OHLC al iniciar o cambiar de coin/timeframe. El último candle nunca se actualizaba con el precio en tiempo real.

**Solución implementada:**

- `Charts.updateLastPrice(coin, price)` — Actualiza el close/high/low del último candle vía `candlestickSeries.update()`
- Llamado cada 15 segundos desde `refreshPrices()` usando el precio de `/api/market/{coin}`
- `lastOhlcData` state tracking para mantener referencia al último dato

**Archivos modificados:**

| Archivo | Cambio |
|---------|--------|
| `static/charts.js` | `lastOhlcData` array, `updateLastPrice()` método público |
| `static/index.html` | `refreshPrices()` llama a `Charts.updateLastPrice()` |

---

### 5d. 🎯 Account Profiles — Configuración de Leverage/Risk por Agente — COMPLETADO

**Estado**: ✅ Implementado  
**Fecha**: 2026-02-19  
**Área**: Trading / Configuración

**Problema**: Cuentas pequeñas ($50-100) con strategy defaults (3x leverage, 2.5% risk) generan margins de $4 y necesitan movimientos de 33%+ para alcanzar TP. Resultado: semanas/meses sin trades rentables.

**Solución implementada:**

#### 4 Perfiles de Cuenta

| Perfil | Balance | Lev Min | Lev Max | Risk Min | Risk Max | Concepto |
|--------|:-------:|:-------:|:-------:|:--------:|:--------:|----------|
| ⚡ **Micro** | $50–100 | 10x | 25x | 5% | 10% | High leverage + high risk = $1-2 profit por trade |
| 🔥 **Small** | $100–500 | 5x | 15x | 3% | 7% | Balance entre riesgo y crecimiento |
| 📊 **Standard** | $500–2k | 1x | 10x | Auto | Auto | Usa defaults de la estrategia |
| 🏦 **Large** | $2k+ | 1x | 5x | 1% | 3% | Conservador, protege capital |

#### Auto-sugerencia
- `suggestProfile()` evalúa el balance ingresado y pre-selecciona el perfil recomendado
- El usuario puede cambiar libremente entre perfiles o ajustar sliders manualmente

#### Integración en Trading Agent
- `min_leverage` se aplica como **floor**: `leverage = max(signal.leverage, agent.min_leverage)`
- `risk_pct_min/max` se pasa a `calculate_position_size()` que clampea el `effective_risk`

#### DB Migration
- 3 columnas nuevas en `TradingAgent`: `min_leverage` (INT, default 1), `risk_pct_min` (FLOAT, default 0.0), `risk_pct_max` (FLOAT, default 0.0)
- Migración con `ALTER TABLE ADD COLUMN` — sin borrar datos

**Archivos modificados:**

| Archivo | Cambio |
|---------|--------|
| `backend/models/database.py` | 3 columnas nuevas en TradingAgent |
| `backend/services/strategies.py` | `calculate_position_size()` acepta `risk_pct_min/max` overrides |
| `backend/services/trading_agent.py` | `_open_position()` aplica min_leverage + pasa risk bounds |
| `main.py` | AgentCreate expandido, validación, agent detail response |
| `static/index.html` | Modal rediseñado: 4 profile buttons, leverage range sliders, risk % sliders, auto-suggest, agent details badges |

---

### 7. 🕐 Market Clocks — Relojes de Mercados Mundiales — COMPLETADO

**Estado**: ✅ Implementado  
**Fecha**: 2026-02-19  
**Área**: UX / Trading Context

**Implementación entregada:**

#### Sección UI (Market Clocks Bar)
- Barra oscura en la parte superior del dashboard debajo del nav
- **8 mercados** monitoreados: NYSE, NASDAQ, London (LSE), Frankfurt (Xetra), Tokyo (TSE), Shanghai (SSE), Hong Kong (HKEX), Sydney (ASX)
- **Tarjeta local**: Detecta timezone del usuario, muestra hora local con nombre de ciudad
- **Cada tarjeta muestra**: Bandera/código de país, nombre del mercado, hora local en tiempo real (actualiza cada segundo), estado (OPEN/PRE-MKT/CLOSED), countdown hasta próxima apertura o cierre, barra de progreso de la sesión
- **Colores por estado**: Verde (open), naranja (pre-market), rojo (closed) con bordes y opacidad diferenciados
- Scroll horizontal para pantallas pequeñas

#### Alertas de Apertura/Cierre
- **Browser Notifications**: Pide permiso al cargar la app; notifica cuando un mercado abre o cierra
- **Toast in-app**: Notificación animada (slide-in desde la derecha) con borde verde (apertura) o rojo (cierre), desaparece en 6 segundos
- **Anti-duplicados**: `marketAlertFired` object trackea estado previo de cada mercado

#### Backend
- **`GET /api/market/hours`**: Retorna array con status de los 8 mercados (id, name, status, local_time, session_pct)
- **`get_market_hours_context()`**: Función reutilizable por trading agent

#### Integración con Trading Agent
- **`_get_market_context()`**: Calcula qué mercados están abiertos, % de sesión, cuáles abren pronto (<30 min)
- **Ajuste de confianza**:
  - +2% durante sesión US (mayor correlación con crypto)
  - -2% en off-hours (menor liquidez tradicional)
- **Advertencia de volatilidad**: Si NYSE abre en <30 min → warning en el razonamiento del signal
- **Contexto para LLM (Gemini)**: `market_session`, `open_markets`, `volatility_hint`, `markets_opening_soon` enviados al modelo para análisis más informados

**Mercados y horarios:**

| Mercado | Timezone | Apertura | Cierre | Pre-Market |
|---------|----------|:--------:|:------:|:----------:|
| NYSE | America/New_York | 09:30 | 16:00 | 04:00 |
| NASDAQ | America/New_York | 09:30 | 16:00 | 04:00 |
| London (LSE) | Europe/London | 08:00 | 16:30 | 07:00 |
| Frankfurt (Xetra) | Europe/Berlin | 09:00 | 17:30 | 08:00 |
| Tokyo (TSE) | Asia/Tokyo | 09:00 | 15:00 | 08:00 |
| Shanghai (SSE) | Asia/Shanghai | 09:30 | 15:00 | 09:15 |
| Hong Kong (HKEX) | Asia/Hong_Kong | 09:30 | 16:00 | 09:00 |
| Sydney (ASX) | Australia/Sydney | 10:00 | 16:00 | 07:00 |

**Archivos creados / modificados:**

| Archivo | Cambio |
|---------|--------|
| `static/index.html` | CSS market clocks (cards, estados, toast, animaciones), HTML market clocks bar, JS engine (MARKETS array, getMarketStatus, renderMarketClocks, checkMarketAlert, fireMarketAlert, showMarketToast, requestNotificationPermission), 1s interval |
| `main.py` | `from zoneinfo import ZoneInfo`, `WORLD_MARKETS` data, `get_market_hours_context()`, `GET /api/market/hours` endpoint (antes de `/{coin}` para evitar catch-all) |
| `backend/services/trading_agent.py` | `from zoneinfo import ZoneInfo`, `WORLD_MARKETS`, `_get_market_context()`, `_adjust_signal_for_market_hours()`, integración en `_scan_for_best_signal()` y `_get_llm_analysis()` |

---

### 8. 🔧 Scalper Strategy Overhaul — Corrección Crítica Trade Generation — COMPLETADO

**Estado**: ✅ Implementado  
**Fecha**: 2026-02-19  
**Área**: Trading / Estrategias / Market Data

**Problema detectado**: Tras 24+ horas de ejecución con agentes scalper activos, **0 trades se abrieron**. Análisis profundo reveló 6 bloqueadores críticos actuando en conjunto.

#### 6 Bloqueadores Encontrados y Corregidos

| # | Bloqueador | Impacto | Solución |
|---|-----------|---------|----------|
| 1 | **OHLC usaba velas DIARIAS** para todas las estrategias — RSI/EMA/BB calculados sobre datos diarios no se mueven para scalping | 🔴 Crítico | `kline_interval` por estrategia + `get_ohlc_interval()` para velas 1m/3m/5m/15m/1h |
| 2 | **Umbral de entrada score ≥ 3 hardcodeado** con `confidence = score/10` — casi imposible alcanzar en datos diarios | 🔴 Crítico | Scalping usa `min_score_to_act = 2` y `confidence = score/8` |
| 3 | **Solo 8 large-cap coins** (BTC, ETH, etc.) — las menos volátiles de crypto | 🟡 Alto | +15 tokens volátiles mid-cap (AVAX, LINK, NEAR, SUI, PEPE, APT, ARB, FIL, RENDER, INJ, FET, BONK, FLOKI, SEI, WIF) |
| 4 | **Solo top 6 coins escaneadas** por ciclo | 🟡 Alto | `scan_limit` configurable por estrategia — scalpers escanean 15 coins |
| 5 | **Cache OHLC = 900s** (15 min) | 🟡 Medio | Cache adaptativo: 30s (1m), 60s (3m), 90s (5m), 180s (15m), 300s (1h) |
| 6 | **Condiciones RSI demasiado estrechas** + penalización counter-trend | 🟡 Medio | RSI ampliado, entradas mean-reversion, sin penalización counter-trend |

#### Cambios en StrategyConfig

Nuevos campos añadidos a `StrategyConfig`:

| Campo | Tipo | Default | Descripción |
|-------|------|---------|-------------|
| `kline_interval` | str | `""` | Intervalo Binance (1m/3m/5m/15m/1h). Vacío = daily |
| `scan_limit` | int | 6 | Cuántos coins escanear por ciclo |

Valores por variante scalper:

| Variante | Interval | Scan | min_confidence |
|----------|:--------:|:----:|:--------------:|
| scalper (1h) | `1h` | 15 | 0.30 |
| scalper_1m | `1m` | 15 | 0.25 |
| scalper_3m | `3m` | 15 | 0.25 |
| scalper_5m | `5m` | 15 | 0.25 |
| scalper_15m | `15m` | 15 | 0.30 |

#### Reescritura del Scalper Strategy (7 capas)

| Capa | Antes | Después |
|------|-------|--------|
| 1. EMA Trend | EMA 9>21 (+1) | EMA 9>21 con **spread bonus** (+1 extra si spread > 0.1%) |
| 2. RSI | Solo pullback 30-48 en uptrend | **Múltiples zonas**: pullback (35-55), extremos (<30/>70), zona suave (<40/>60) |
| 3. BB | Solo con trend confirmado | **Posición absoluta** + squeeze breakout anticipation |
| 4. MACD | Crossover o histogram | Crossover + **histogram acceleration** (momentum building) |
| 5. StochRSI | Solo cross from extreme | Cross from extreme + **mid-zone momentum** |
| 6. Momentum | No existía | **Precio vs SMA7** (±0.3% threshold) |
| 7. Volume | Solo "increasing" | **Spike detection** (2x avg) como confirmación fuerte |
| Penalty | -2 counter-trend | **Ninguna** — scalping tradea en ambas direcciones |
| R:R | 3:1 (ATR×1 SL, ATR×3 TP) | **2:1** (ATR×0.8 SL, ATR×1.6 TP) — salidas más rápidas |

#### 15 Tokens Volátiles Añadidos

| Token | ID CoinGecko | Binance Futures | ATR% 5m típico |
|-------|-------------|:---------------:|:--------------:|
| Avalanche | avalanche-2 | AVAXUSDT | ~0.19% |
| Chainlink | chainlink | LINKUSDT | ~0.20% |
| NEAR | near | NEARUSDT | ~0.27% |
| SUI | sui | SUIUSDT | ~0.25% |
| PEPE | pepe | 1000PEPEUSDT | ~0.26% |
| Aptos | aptos | APTUSDT | ~0.27% |
| Arbitrum | arbitrum | ARBUSDT | ~0.40% |
| Filecoin | filecoin | FILUSDT | ~0.32% |
| Render | render-token | RENDERUSDT | ~0.34% |
| Injective | injective-protocol | INJUSDT | ~0.68% |
| Fetch.ai | fetch-ai | FETUSDT | ~0.25% |
| BONK | bonk | 1000BONKUSDT | ~0.22% |
| FLOKI | floki | 1000FLOKIUSDT | ~0.23% |
| SEI | sei-network | SEIUSDT | ~0.31% |
| WIF | wif | WIFUSDT | ~0.26% |

**Nota**: PEPE, BONK y FLOKI usan formato `1000XXXUSDT` en Binance Futures (precios escalados ×1000).

#### Market Data: `get_ohlc_interval()`

Nuevo método en `BinanceProvider` y `MarketDataService`:

```python
# Fetch 200 velas de 5 minutos para SUI
ohlc = market_service.get_ohlc_interval("sui", "5m", 200)
```

Cache TTL por intervalo:

| Intervalo | Cache TTL |
|:---------:|:---------:|
| 1m | 30s |
| 3m | 60s |
| 5m | 90s |
| 15m | 180s |
| 1h | 300s |

#### Resultado del Fix

**Test con datos reales** (5m candles, momento del fix):

| Antes | Después |
|:-----:|:-------:|
| 0/8 coins con señal | **21/23 coins con señal actionable** |
| 0 trades en 24h | Señales long y short generándose cada ciclo |
| RSI ~50 en daily (sin movimiento) | RSI varía 25-75 en 5m candles |
| Score máx ~2 (nunca llega a 3) | Scores de 3-10 frecuentemente |

**Archivos creados / modificados:**

| Archivo | Cambio |
|---------|--------|
| `backend/services/strategies/scalper.py` | **REESCRITO** — 7 capas agresivas, sin counter-trend penalty, 2:1 R:R |
| `backend/services/strategies/models.py` | +`kline_interval`, +`scan_limit` en StrategyConfig; `min_confidence` reducido en scalpers |
| `backend/services/strategies/base.py` | `_build_signal()` — threshold dinámico para scalping (score≥2, conf=score/8) |
| `backend/services/trading_agent.py` | `_compute_indicators()` acepta `strategy_key`, usa `get_ohlc_interval()` para scalping; `_scan_for_best_signal()` usa `scan_limit` |
| `backend/services/market_data.py` | +15 tokens en SYMBOL_MAP/supported_coins, `SCALP_INTERVALS`, `get_ohlc_interval()` en BinanceProvider y MarketDataService, cache TTL adaptativo |

---

### 6. 🔔 Notificaciones + Alertas (Telegram / Email)

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
| A1 | Fear & Greed Index (alternative.me) | **Alto** | 🔜 Next (rápido, API gratuita, dato valioso para agente + LLM) |
| A2 | On-chain data (whale movements, exchange flows) | **Alto** | 🔜 Planificado (#5 del próximo ciclo) |
| A3 | Correlación entre monedas para diversificación | Medio | Pendiente |
| A4 | Pattern recognition (double bottom, H&S, etc.) | Medio | Pendiente |
| A5 | Social sentiment (X/Reddit scraping) | Medio | Deprioritizado (ya tenemos LLM + RSS news) |
| A6 | Multi-timeframe analysis (1H, 4H, 1D) | Alto | ✅ Completado (kline_interval por estrategia + 5 variantes Scalper) |

### Trading / Estrategia

| ID | Feature | Impacto | Estado |
|----|---------|---------|--------|
| B1 | DCA automático como estrategia standalone | Medio | Pendiente |
| B2 | Detección de oportunidades sin ejecución (alert-only mode) | Medio | ✅ Parcial (Risk Monitor + Market Clock alerts) |
| B3 | Preparar arquitectura para trading real (Binance/Coinbase API) | **Alto** | Pendiente (requiere madurez previa) |
| B4 | Portfolio rebalancing automático | Medio | Pendiente |
| B5 | Trailing stop-loss dinámico (ATR-based) | **Muy Alto** | 🔜 Next (#1 del próximo ciclo) |
| B6 | Trailing take-profit (lock in gains) | **Muy Alto** | 🔜 Next (#1 — junto con B5) |

### UX / Dashboard

| ID | Feature | Impacto | Estado |
|----|---------|---------|--------|
| C1 | Comparación lado a lado de múltiples agentes | Medio | Pendiente |
| C2 | Dark mode | Bajo | Pendiente |
| C3 | Mobile responsive mejorado | Medio | Pendiente |
| C4 | Export CSV de trades (análisis externo / impuestos) | **Medio-Alto** | 🔜 Planificado (#4 del próximo ciclo) |
| C5 | Leaderboard / ranking de agentes | Medio | Pendiente |

### Configuración / Sistema

| ID | Feature | Impacto | Estado |
|----|---------|---------|--------|
| D1 | Panel de configuración global (no hardcodeado) | Medio | Deprioritizado (Account Profiles resolvió lo urgente) |
| D2 | Sistema de usuarios / autenticación | Medio | Pendiente |
| D3 | Persistir configuraciones en DB | Medio | ✅ Parcial (leverage/risk en DB) |
| D4 | API rate-limit dashboard (ver uso de APIs) | Bajo | ✅ Parcial (health endpoint muestra estado de ambos proveedores) |

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
5.  Risk Monitor (5s polling) ──→ ✅ COMPLETADO (2026-02-19)
5b. Open Positions UI (full-width) ──→ ✅ COMPLETADO (2026-02-19)
5c. Chart Price Sync ──→ ✅ COMPLETADO (2026-02-19)
5d. Account Profiles (Micro/Small/Std/Large) ──→ ✅ COMPLETADO (2026-02-19)
7.  Market Clocks (World Markets) ──→ ✅ COMPLETADO (2026-02-19)
8.  Scalper Strategy Overhaul ──→ ✅ COMPLETADO (2026-02-19)
─── Próximo ciclo (Top 5) ───────────────────────────────
9.  Trailing SL + Trailing TP (B5+B6) ──→ 🔜 next
10. Fear & Greed Index (A1) ──→ 🔜 next
11. Notificaciones Telegram (#6) ──→ 🔜 next
12. Export CSV de Trades (C4) ──→ 🔜 next
13. On-chain / Whale Alerts (A2) ──→ 🔜 next
─── Futuro ──────────────────────────────────────────────
5e. Risk Monitor (WebSocket) ──→ planificado (Fase 2)
```

---

## Arquitectura Actual

| Componente | Tecnología | Detalle |
|------------|-----------|---------|
| Backend | FastAPI + uvicorn | Puerto 8001, 21+ endpoints + WebSocket |
| Base de datos | SQLite + SQLAlchemy | 6 modelos (TradingAgent, Portfolio, Trade, Decision, PortfolioSnapshot, NewsEvent) |
| Market Data (primary) | **Binance API** | 1200 req/min, sin API key, precios + OHLC + históricos + volumen + kline intervals (1m-1h) |
| Market Data (fallback) | CoinGecko API | 10 req/min free tier, RateLimiter con 5s max wait |
| Noticias | RSS feeds | CoinDesk, CoinTelegraph, Bitcoin Magazine + CryptoPanic (opcional) |
| Charts | TradingView Lightweight Charts v4 | CDN, open source, candlestick + indicadores + price sync |
| Indicadores | RSI, MACD, BB, EMA, SMA, ATR, ADX, StochRSI, Volume | Library completa en strategies.py |
| Estrategias | 10 (trend/mean_rev/momentum/scalper×5/grid/confluence) | StrategyEngine con scoring + signal generation, timeframe-aware |
| Tokens | 23 (8 large-cap + 15 mid-cap volátiles) | BTC, ETH, BNB, ADA, SOL, XRP, DOT, DOGE + AVAX, LINK, NEAR, SUI, PEPE, APT, ARB, FIL, RENDER, INJ, FET, BONK, FLOKI, SEI, WIF |
| Backtesting | Motor completo con commission model | Replay de klines, dual balance (gross/net), funding rate |
| CLI | backtest_cli.py | Comparativas rápidas, --compare, --scalpers |
| Futuros | LONG/SHORT, leverage 1-125x, liquidation, SL/TP | Position sizing profesional |
| Market Clocks | 8 mercados mundiales | Hora real, alertas open/close, integración con agent decisions |
| Account Profiles | 4 presets (Micro/Small/Standard/Large) | Auto-suggest por balance, leverage/risk ranges |
| Scheduler | APScheduler | Ciclo de trading 60s + Risk monitor 5s |
| Async | asyncio.to_thread() | Trading cycle nunca bloquea el event loop |

### Estructura de archivos (~11,000+ líneas)

| Archivo | Líneas | Responsabilidad |
|---------|--------|----------------|
| `main.py` | 735+ | Endpoints, scheduler, WebSocket, backtest API, market hours |
| `backend/services/strategies.py` | 1410+ | Indicadores técnicos, 10 estrategias, position sizing con risk overrides |
| `backend/services/backtester.py` | 700+ | Motor de backtesting, commission model, sliding window |
| `backend/services/market_data.py` | 905+ | RateLimiter, BinanceProvider (Futures+Spot), MarketDataService, get_fresh_prices, get_ohlc_interval, 23 tokens |
| `backend/services/trading_agent.py` | 770+ | Futures lifecycle, strategy engine, LLM integration, risk monitor, market hours context |
| `backend/services/llm_service.py` | 270 | Gemini 2.0 Flash, LLMAnalysis, rate limiting |
| `backend/services/news_service.py` | 313 | RSS feeds, sentimiento por keywords |
| `backend/models/database.py` | 130+ | 6 modelos SQLAlchemy (con campos futures + LLM + decision_id + account profiles) |
| `static/index.html` | 2600+ | Dashboard + Backtesting SPA, strategy picker, futures UI, LLM blocks, market clocks, account profiles, position cards |
| `static/charts.js` | 390+ | Módulo de charts TradingView con price sync |
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
