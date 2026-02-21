# Money Maker — Feature Backlog

> Última actualización: 2026-02-21 (sesión 9)

---

## ✅ Completado

### 🌙 Dark Mode (Sesión 9) — COMPLETADO

**Estado**: ✅ Implementado  
**Fecha**: 2026-02-21  
**Área**: UX / Dashboard  
**ID Backlog**: C2  

**Descripción**: Sistema completo de dark mode con toggle en la barra de navegación, persistencia en localStorage, detección automática de preferencia del OS (`prefers-color-scheme`), y actualización dinámica de gráficos TradingView.

**Cambios implementados:**

1. **`static/index.html`** — Sistema de temas CSS + toggle UI:
   - ~60 CSS custom properties en `:root` (light) y `[data-theme="dark"]` (dark)
   - Paleta dark: backgrounds `#0d1117`/`#161b22`, text `#e6edf3`/`#8b949e`, borders `#30363d`
   - ~120+ reemplazos de colores hardcoded → `var(--xxx)` en CSS rules
   - Inline styles en HTML body convertidos (backtesting selects, profile buttons, leverage labels, badges)
   - JS template literals actualizados (backtest metrics, trades table, agent cards, data source badge)
   - Botón toggle 🌙/☀️ en nav bar con `onclick="toggleTheme()"`
   - JS: `getPreferredTheme()`, `applyTheme(theme)`, `toggleTheme()`, listener `prefers-color-scheme`
   - Dark overrides para: profile buttons, API docs, modals, inputs, selects, status badges
   - `body` y `.card` con `color: var(--text-primary)` / `var(--text-on-card)` para texto visible

2. **`static/charts.js`** — Gráficos theme-aware:
   - Objeto `THEMES` con paletas light/dark (bg, grid, text, border)
   - `_currentTheme` state variable
   - `chartLayoutOptions(height)` usa `THEMES[_currentTheme]` dinámicamente
   - Método público `applyTheme(theme)` — actualiza `candlestickChart`, `rsiChart`, `equityChart` en vivo
   - `showChartMessage()` usa color adaptado al tema

**Elementos preservados intencionalmente oscuros** (no afectados por toggle):
- LLM Reasoning blocks (`#1a1a2e` bg)
- Decision Detail Modal (`#1a1a2e` bg)
- Trade History Modal (`#1a1a2e` bg)
- Market Clocks bar (ya era dark)
- Nav bar y footer (gradiente dark constante)

---

### 0. 🚀 Per-Timeframe Scalper Optimization (Sesión 6) — COMPLETADO

**Estado**: ✅ Implementado  
**Fecha**: 2026-02-19  
**Área**: Strategies + Backtesting + Profitability  

**Problema**: Todos los scalpers (1m, 3m, 5m, 15m, 1h) usaban la misma lógica idéntica de indicadores, scoring, y gestión de riesgo. Resultado: 0 de 5 rentables, pérdidas de -50% a -96%, win rate 10-39%, demasiados trades (168-732), trailing stops destruyendo posiciones.

**Resultados ANTES / DESPUÉS** (BTC 30d, 3x leverage):
| TF | Net Antes | Net Después | Trades Antes | Después | WR Antes | Después |
|----|-----------|-------------|--------------|---------|----------|---------|
| 1h | -89.9% | **+9.5%** ✅ | 237 | 65 | 10% | 42% |
| 15m | -96.0% | -7.4% | 530 | 79 | 12% | 34% |
| 5m | -96.0% | -10.9% | 732 | 173 | 20% | 34% |
| 3m | -96.0% | -13.6% | 710 | 161 | 21% | 32% |
| 1m | -50.7% | -7.7% | 168 | 92 | 39% | 38% |

**Multi-coin validation** (30d, 3x leverage):
| Estrategia | BTC | ETH | SOL | XRP | BNB |
|-----------|-----|-----|-----|-----|-----|
| 1h net | +9.5% | **+18.0%** | -12.7% | **+5.7%** | **+0.7%** |
| 15m net | -7.4% | **+11.8%** | -8.0% | -7.0% | -10.8% |

**1h rentable en 4/5 coins.** 15m rentable en ETH (+11.8%, 48% WR, 1.41 PF, +46.6% alpha).
**Todos los scalpers superan Buy & Hold** (alpha positivo en todos los casos).

**Cambios implementados (8 archivos):**

1. **`indicators.py`** — Perfiles de indicadores por timeframe (SCALP_PROFILES):
   - 1m: RSI(7), MACD(5,13,4), BB(10,1.8), EMA(5,13,21)
   - 3m: RSI(9), MACD(8,17,6), BB(14,2.0), EMA(7,17,34)
   - 5m: RSI(10), MACD(8,21,7), BB(16,2.0), EMA(8,21,50)
   - 15m: RSI(12), MACD(10,22,8), BB(18,2.0), EMA(9,21,50)
   - 1h: RSI(14), MACD(12,26,9), BB(20,2.0), EMA(9,21,55) (estándar)
   - `compute_all()` acepta parámetro `profile` opcional
   - `volume_analysis()` acepta ventanas customizables

2. **`scalper.py`** — Reescritura completa con 8 capas de scoring optimizado:
   - Layer 1: EMA 3-line alignment (0-3 pts — S>M>L para full alignment)
   - Layer 2: RSI (extremos +2, pullback en tendencia +1)
   - Layer 3: Bollinger Bands (extremo +2, zona de entrada +1, squeeze +1)
   - Layer 4: MACD (crossover +2, histograma acelerando +1)
   - Layer 5: StochRSI (extremo + cruce +2, mid-zone +1)
   - Layer 6: ADX trend strength (+1 si trending + DI alineado)
   - Layer 7: Momentum (+1 si > threshold)
   - Layer 8: Volumen (spike +2, increasing +1)
   - **Counter-trend penalty**: -1 a -3 puntos por ir contra EMA alignment
   - **ADX dampener**: Scores -2 cuando ADX < 25 (mercado lateral)
   - **Volume gate**: Scores ÷2 sin confirmación de volumen (1m/3m/5m)
   - Per-timeframe TIMEFRAME_PARAMS con: min_score, R:R, SL/TP, cooldown
   - Trailing stop desactivado para todos los scalpers (trail_pct = -1)

3. **`models.py`** — Configs actualizados:
   - Leverage reducido: 3x default, 5x max (antes 5-10x default, 10-20x max)
   - Risk reducido: 1.5-3.0% (antes 2.0-4.0%)
   - Min confidence: 0.30-0.35 (antes 0.25-0.30)
   - Max positions: 3 (antes 5)
   - Trail ATR mult: 3.0-3.5 (no aplicable con trailing desactivado)

4. **`base.py`** — `_build_signal()` ampliado:
   - `min_score_override`: threshold mínimo de score (por timeframe)
   - `confidence_divisor`: divisor para confianza (12-16 según TF)
   - `min_score_margin`: margen mínimo entre long/short scores (≥3)

5. **`backtester.py`** — Mejoras al motor de backtest:
   - Import SCALP_PROFILES y pasa perfil a `compute_all()`
   - Trailing stop desactivado cuando signal.trail_pct < 0
   - **Cooldown mechanism**: N candles sin operar después de SL hit
   - Cooldown per-timeframe: 30 (1m), 20 (3m), 30 (5m), 15 (15m), 2 (1h)

6. **`trading_agent.py`** — Indicadores por timeframe en live trading:
   - Import SCALP_PROFILES y pasa perfil a `compute_all()`

7. **`backtest_cli.py`** — Default leverage cambiado de 10x a 3x

**Root causes de las pérdidas anteriores** (identificados y corregidos):
- Trailing stop Phase 1 (breakeven at +1R) cerraba 44% de trades prematuramente → **Trailing desactivado**
- Indicadores con períodos estándar (RSI-14) no adecuados para 1m (→ RSI-7) → **Períodos por TF**
- min_score=2 generaba señal en casi cada vela → **min_score 5-8 por TF**
- Sin penalización contra-tendencia → **Counter-trend penalty -1 a -3**
- Sin filtro ADX → **ADX dampener en mercados laterales**
- Leverage 10x amplificaba comisiones → **Leverage 3x**
- Sin cooldown post-SL → **Cooldown 2-30 velas según TF**

---

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

#### Fase 2: Binance WebSocket Streams — COMPLETADO

**Estado**: ✅ Implementado  
**Fecha**: 2026-02-20  
**Impacto**: Latencia de monitoreo de ~5s → ~1s (mark price stream cada 1s)

Reemplaza el polling REST por WebSocket push de Binance Futures para datos de mercado en tiempo real.

**Stream principal:**
```
wss://fstream.binance.com/stream?streams=!markPrice@arr@1s
```

**Datos recibidos en tiempo real (cada 1 segundo):**
- **Mark Price** para ~687 símbolos de futuros (todos los pares USDT-M)
- **Funding Rate** actualizado en cada mensaje
- **Index Price** (precio promedio de múltiples exchanges)
- **Kline updates** (suscripción dinámica por posición abierta)

**Ventajas vs polling REST:**

| Aspecto | Antes (REST) | Después (WebSocket) |
|---------|:------------:|:-------------------:|
| Latencia de precio | ~5s (polling interval) | **~1s** (push stream) |
| Requests API para precios | ~12/min por posición | **0** (single WS connection) |
| Cobertura de símbolos | 23 (configurados) | **687** (todos los futuros) |
| Datos de funding rate | REST cada 15s (cached) | **1s** (real-time push) |
| Kline updates | REST cached 30-300s | **Real-time** (cada trade) |
| Reconexión | N/A (stateless) | **Auto-reconnect** (1-60s backoff) |

**Arquitectura implementada:**

```
BinanceWSManager (async, event loop)
├── _connection_loop()        # Auto-reconnect con exponential backoff
├── _connect_and_listen()     # Conexión WS + procesamiento de mensajes
├── _on_mark_price_batch()    # Procesa !markPrice@arr@1s
├── _on_kline()               # Procesa kline updates dinámicos
├── get_mark_price(sym)       # Lectura thread-safe (Lock)
├── get_all_mark_prices()     # Todos los precios, una sola lectura
├── get_funding_rate(sym)     # Funding rate en tiempo real
├── subscribe_klines(sym, i)  # Suscripción dinámica a klines
├── unsubscribe_klines()      # Desuscripción
├── sync_kline_subscriptions()# Sync con posiciones abiertas
└── health_check()            # Estado de conexión + stats
```

**Integración con MarketDataService (4 niveles de prioridad):**

| Método | Prioridad | Detalle |
|--------|:---------:|--------|
| `get_coin_price()` | WS → REST → Cache | Lectura directa de WS para precio individual |
| `get_current_prices()` | WS → Cache → REST → CoinGecko → Last Known | Si WS cubre ≥50% de coins, retorna inmediatamente |
| `get_fresh_prices()` | WS → REST → Last Known | Risk monitor usa WS sin REST si disponible |
| `get_ohlc_interval()` | Cache/REST + WS kline enrichment | Última vela actualizada con datos WS en tiempo real |

**Jobs de background añadidos:**

| Job | Frecuencia | Responsabilidad |
|-----|:----------:|----------------|
| `broadcast_ws_prices` | 3s | Push precios + funding rates al frontend vía WebSocket |
| `sync_kline_subscriptions` | 60s | Suscribe klines para símbolos con posiciones abiertas |

**Frontend (real-time price updates):**
- Handler `price_update` en WebSocket: actualiza precios en price cards sin reload
- Flash animation (cyan) cuando un precio cambia
- Badge `WS ✓` (verde) / `WS ✗` (rojo) junto al data source badge
- Funding rates actualizados en real-time
- Chart candle actualizado cada 3s vía WS

**Endpoints nuevos:**
- `GET /api/ws/status` — Estado de conexión WebSocket + estadísticas

**Health check actualizado:**
```json
{
  "websocket": {
    "status": "connected",
    "messages_received": 245,
    "price_symbols_tracked": 687,
    "kline_streams_active": 0,
    "last_message_age_s": 0.2,
    "prices_fresh": true
  }
}
```

**Archivos creados / modificados:**

| Archivo | Cambio |
|---------|--------|
| `backend/services/ws_monitor.py` | **NUEVO** (~300 líneas) — BinanceWSManager completo |
| `backend/services/market_data.py` | WS como L0 cache en get_coin_price/get_current_prices/get_fresh_prices, kline enrichment en get_ohlc_interval, WS en health_check |
| `main.py` | Import + init WS manager, broadcast_ws_prices (3s), sync_kline_subscriptions (60s), /api/ws/status, startup/shutdown WS lifecycle |
| `static/index.html` | Handler price_update, WS badge, flash animation, funding rate real-time |

**Complejidad**: Media-Alta (gestión de conexiones async, thread-safety, reconexión)

---

### 5e-bis. 🔄 PriceBus — Frontend Reactive Architecture — COMPLETADO

**Estado**: ✅ Implementado  
**Fecha**: 2026-02-20  
**Área**: Frontend / Arquitectura Reactiva

**Problema**: Tras implementar WebSocket (5e), el frontend mantenía dos fuentes de verdad (WS push + REST polling 15s) y múltiples componentes actualizaban precios de forma independiente. Los timers, badges, P&L de posiciones y agent list estaban desincronizados.

**Solución implementada**: **PriceBus** — un singleton pub/sub event dispatcher que centraliza todos los datos de precio del WebSocket como única fuente de verdad.

**Componentes reactivos (6 listeners):**

| Listener | Evento | Responsabilidad |
|----------|:------:|----------------|
| `_onTickUpdatePriceGrid` | tick | Actualiza price cards con `data-coin-id` (O(1) lookup) |
| `_onTickUpdateChart` | tick | Actualiza último candle del chart vía `Charts.updateLastPrice()` |
| `_onTickUpdateAllAgents` | tick | Recalcula P&L de TODOS los agentes en la lista (no solo el seleccionado) |
| `_onTickUpdatePositions` | tick | Actualiza cards de posiciones del agente seleccionado (PnL, progress bar) |
| `_onTickUpdateFreshness` | tick | Muestra barra "LIVE" verde cuando WS activo, countdown cuando REST fallback |
| `_onWsStatusChange` | wsStatus | Actualiza badge WS y badge de data source |

**Cambios clave:**
- **REST polling condicional**: `refreshPrices()` salta REST cuando `PriceBus.wsConnected && PriceBus.freshnessSec < 10`
- **`_cachedAgents`**: Todos los agentes cacheados desde `loadAgents()` con datos de posiciones para P&L reactivo
- **`data-agent-id`**: Atributo DOM para O(1) targeting de agent items
- **`data-coin-id`**: Atributo DOM para O(1) targeting de price cards
- **`_symbolToCoinId`**: Reverse map (`BTC` → `bitcoin`) para matching de posiciones

**Backend (`/api/agents` endpoint ampliado):**
- Cada agente ahora incluye array `positions[]` con: `symbol`, `amount`, `avg_buy_price`, `position_type`, `margin`, `leverage`
- Permite al frontend recalcular P&L reactivamente sin llamadas adicionales

**Archivos modificados:**

| Archivo | Cambio |
|---------|--------|
| `static/index.html` | PriceBus singleton, 6 listeners, `_cachedAgents`, `_symbolToCoinId`, REST condicional, `data-agent-id`/`data-coin-id` atributos |
| `main.py` | `/api/agents` incluye `positions[]` por agente |

---

### 5f. ⚡ Event-Driven Reactive Risk Monitor — COMPLETADO

**Estado**: ✅ Implementado  
**Fecha**: 2026-02-20  
**Área**: Trading / Risk Management / Performance Crítica

**Problema**: El risk monitor polling (5s) tenía dos problemas graves:
1. **Latencia**: SL/TP detection cada 5s — en mercados volátiles con apalancamiento, un gap de 5s puede significar pérdidas significativas
2. **Blind spot**: Durante el trading cycle (5-30s de duración), el risk monitor se skipea completamente porque `_trading_lock.acquire(blocking=False)` falla — creando un blind spot de hasta 30s

**Solución implementada**: `ReactiveRiskMonitor` — clase event-driven que se suscribe al callback de precio del WebSocket y reacciona a cada tick (1s).

**Arquitectura:**

```
WS tick (1s) → _on_mark_price_batch → fire callbacks → watchlist filter O(n) → thread pool → risk check → DB commit
```

**Mejoras de latencia:**

| Métrica | Antes (polling) | Después (reactivo) |
|---------|:---------------:|:------------------:|
| Detección SL/TP | 5s (skip durante trading cycle → hasta 30s) | **~1s** event-driven |
| Retry tras lock skip | 5s | **1s** |
| Duración del check | ~5ms (todas las posiciones) | **~2.5ms** (solo símbolos con cambio) |

**Componentes:**

1. **Callback system en `BinanceWSManager`**:
   - `on_price_tick(callback)` / `remove_price_tick(callback)` — registro de callbacks
   - Callbacks se disparan FUERA del lock (después de actualizar `_mark_prices`)
   - Cada callback recibe `Dict[str, float]` con precios actualizados

2. **`ReactiveRiskMonitor` class** ([backend/services/risk_monitor.py](backend/services/risk_monitor.py)):
   - **Watchlist**: `Dict[str, List[Tuple[agent_id, pos_id, coin_id]]]` indexada por Binance symbol
   - **O(n) filter**: Solo procesa posiciones cuyo símbolo cambió en el tick
   - **Thread pool dispatch**: `asyncio.to_thread()` para no bloquear event loop
   - **`threading.Event` idle flag**: Previene stacking de checks concurrentes
   - **Non-blocking lock**: `_trading_lock.acquire(blocking=False)` — nunca bloquea trading cycle
   - **Fresh DB session per tick**: Sin referencias stale
   - **Single commit per tick batch**: Trailing stop updates batched
   - **Immediate watchlist refresh**: Tras cada position open/close/agent status change
   - **Periodic refresh**: Cada 30s como safety net

3. **Health endpoint** (`/api/health` → `reactive_risk`):
   ```json
   {
     "active": true,
     "watchlist_symbols": 3,
     "watchlist_positions": 3,
     "watched_symbols": ["DOTUSDT", "ADAUSDT", "RENDERUSDT"],
     "ticks_processed": 154,
     "last_check_ms": 2.58,
     "ticks_skipped_locked": 37,
     "actions_taken": 0
   }
   ```

**Defense-in-depth:**
- El scheduler de 5s **permanece activo** como safety net (backup)
- Si el WS se desconecta o los callbacks fallan, el poller 5s sigue funcionando
- Ambos sistemas usan `_trading_lock non-blocking` — nunca interfieren con el trading cycle

**Watchlist refresh triggers:**
- `POST /api/agents/{id}/positions/{pos_id}/close` — cierre manual
- `POST /api/agents/{id}/positions/close-all` — cierre masivo
- `PATCH /api/agents/{id}` — cambio de status (paused/stopped)
- `run_trading_cycle()` completion — puede haber abierto/cerrado posiciones
- Periodic 30s refresh — defense-in-depth

**Archivos creados / modificados:**

| Archivo | Cambio |
|---------|--------|
| `backend/services/risk_monitor.py` | **NUEVO** (~280 líneas) — ReactiveRiskMonitor class completo |
| `backend/services/ws_monitor.py` | Callback system: `_price_callbacks`, `on_price_tick()`, `remove_price_tick()`, `_on_mark_price_batch()` dispara callbacks fuera del lock, `_loop` reference, health check con `price_callbacks` count |
| `main.py` | Import + init ReactiveRiskMonitor, `_broadcast_risk_action()`, startup/shutdown lifecycle, health endpoint con `reactive_risk`, watchlist refresh en close/close-all/update-agent/trading-cycle endpoints |

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
| B3 | Preparar arquitectura para trading real (CCXT + Binance/Coinbase) | **Alto** | 🔜 NEXT (#1 del próximo ciclo) |
| B4 | Portfolio rebalancing automático | Medio | Pendiente |
| B5 | Trailing stop-loss dinámico (ATR-based) | **Muy Alto** | 🔜 Next (#1 del próximo ciclo) |
| B6 | Trailing take-profit (lock in gains) | **Muy Alto** | 🔜 Next (#1 — junto con B5) |

### UX / Dashboard

| ID | Feature | Impacto | Estado |
|----|---------|---------|--------|
| C1 | Comparación lado a lado de múltiples agentes | Medio | Pendiente |
| C2 | Dark mode | Bajo | ✅ Completado (sesión 9) |
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
5e. Binance WebSocket Streams ──→ ✅ COMPLETADO (2026-02-20)
5e². PriceBus Frontend Reactive ──→ ✅ COMPLETADO (2026-02-20)
5f. Event-Driven Reactive Risk Monitor ──→ ✅ COMPLETADO (2026-02-20)
C2. Dark Mode ──→ ✅ COMPLETADO (2026-02-21)
─── Próximo ciclo (Top 6) ───────────────────────────────
**14. CCXT — Trading Real (B3) ──→ 🔜 NEXT (#1)**
9.  Trailing SL + Trailing TP (B5+B6) ──→ 🔜 next
10. Fear & Greed Index (A1) ──→ 🔜 next
11. Notificaciones Telegram (#6) ──→ 🔜 next
12. Export CSV de Trades (C4) ──→ 🔜 next
13. On-chain / Whale Alerts (A2) ──→ 🔜 next
```

---

## Arquitectura Actual

| Componente | Tecnología | Detalle |
|------------|-----------|---------|
| Backend | FastAPI + uvicorn | Puerto 8001, 21+ endpoints + WebSocket |
| Base de datos | SQLite + SQLAlchemy | 6 modelos (TradingAgent, Portfolio, Trade, Decision, PortfolioSnapshot, NewsEvent) |
| Market Data (primary) | **Binance API** | REST + **WebSocket** (real-time mark prices, funding rates, klines) |
| Market Data (WS) | **Binance Futures WebSocket** | `!markPrice@arr@1s` — 687 símbolos, ~1s latencia, auto-reconnect, price tick callbacks |
| Risk Monitor (reactive) | **ReactiveRiskMonitor** | Event-driven SL/TP/liquidación, ~1s latencia, watchlist O(n), ~2.5ms/check |
| Frontend reactivo | **PriceBus** | Singleton pub/sub, 6 listeners, REST condicional, data-* atributos O(1) |
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
| Scheduler | APScheduler | Trading 60s + Risk 5s (fallback) + WS broadcast 3s + Kline sync 60s |
| Async | asyncio.to_thread() + WebSocket | Trading cycle en thread, WS en event loop |

### Estructura de archivos (~14,000+ líneas)

| Archivo | Líneas | Responsabilidad |
|---------|--------|----------------|
| `main.py` | 1090+ | Endpoints, scheduler, WebSocket, backtest API, market hours, WS broadcast, reactive risk monitor |
| `backend/services/strategies.py` | 1410+ | Indicadores técnicos, 10 estrategias, position sizing con risk overrides |
| `backend/services/backtester.py` | 700+ | Motor de backtesting, commission model, sliding window |
| `backend/services/market_data.py` | 960+ | RateLimiter, BinanceProvider, MarketDataService, WS integration, 23 tokens |
| `backend/services/trading_agent.py` | 770+ | Futures lifecycle, strategy engine, LLM integration, risk monitor, market hours context |
| `backend/services/ws_monitor.py` | 450+ | BinanceWSManager, real-time mark prices/funding/klines, auto-reconnect, price tick callbacks |
| `backend/services/risk_monitor.py` | 360+ | ReactiveRiskMonitor, event-driven SL/TP/liquidación, watchlist management |
| `backend/services/llm_service.py` | 270 | Gemini 2.0 Flash, LLMAnalysis, rate limiting |
| `backend/services/news_service.py` | 313 | RSS feeds, sentimiento por keywords |
| `backend/models/database.py` | 130+ | 6 modelos SQLAlchemy (con campos futures + LLM + decision_id + account profiles) |
| `static/index.html` | 4290+ | Dashboard + Backtesting SPA, strategy picker, futures UI, LLM blocks, market clocks, account profiles, position cards, PriceBus reactive architecture, WS price updates |
| `static/charts.js` | 390+ | Módulo de charts TradingView con price sync |
| `backtest_cli.py` | 320+ | CLI de backtesting, comparativas, colores |

---

## 🔜 NEXT: B3 — Integración CCXT para Trading Real

> **Prioridad**: #1 del próximo ciclo  
> **ID Backlog**: B3  
> **Estimación**: 1-2 sesiones  
> **Dependencia**: `pip install ccxt` (añadir a requirements.txt)  
> **Documentación CCXT**: https://docs.ccxt.com/ | https://github.com/ccxt/ccxt

### Objetivo

Abstraer el sistema de ejecución de trades para soportar **dos modos**:
1. **Paper Trading** (actual) — simulación sin dinero real, balance virtual en DB
2. **Live Trading** (nuevo) — órdenes reales en Binance Futures vía CCXT

El agente NO debe saber si está en modo paper o live. La abstracción ocurre en la capa de ejecución.

### Arquitectura Propuesta: ExchangeAdapter (Strategy Pattern)

```
┌─────────────────────┐
│   TradingAgentService│
│   (NO cambia)       │
│   _open_position()  │
│   _close_position() │
└──────────┬──────────┘
           │ usa
           ▼
┌─────────────────────┐
│   ExchangeAdapter   │ ← ABC / Protocol
│   (nueva interfaz)  │
│   open_position()   │
│   close_position()  │
│   get_balance()     │
│   get_positions()   │
│   sync_state()      │
└──────┬───────┬──────┘
       │       │
       ▼       ▼
┌──────────┐ ┌──────────────┐
│ Paper    │ │ CCXT Live    │
│ Adapter  │ │ Adapter      │
│(actual)  │ │(nuevo)       │
│DB-only   │ │Binance API   │
└──────────┘ └──────────────┘
```

### Interfaz `ExchangeAdapter` (ABC)

```python
# backend/services/execution/exchange_adapter.py

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Dict, List

@dataclass
class OrderResult:
    """Resultado estandarizado de una orden ejecutada."""
    success: bool
    order_id: Optional[str] = None
    fill_price: float = 0.0         # precio promedio de fill
    filled_qty: float = 0.0         # cantidad llenada
    commission: float = 0.0         # fee pagado
    error: Optional[str] = None
    raw_response: Optional[Dict] = None  # respuesta cruda del exchange

@dataclass
class PositionInfo:
    """Posición abierta en el exchange."""
    symbol: str
    side: str                       # "long" | "short"
    size: float                     # cantidad en coins
    entry_price: float
    mark_price: float
    unrealized_pnl: float
    leverage: int
    margin: float
    liquidation_price: float

@dataclass
class BalanceInfo:
    """Balance de la cuenta."""
    total: float                    # balance total (wallet)
    available: float                # disponible para nuevas órdenes
    margin_used: float              # margen en uso
    unrealized_pnl: float

class ExchangeAdapter(ABC):
    """Interfaz abstracta para ejecución de trades."""

    @abstractmethod
    async def open_position(
        self,
        symbol: str,            # "BTCUSDT"
        side: str,              # "long" | "short"
        margin: float,          # USD de margen
        leverage: int,
        stop_loss: float,       # precio SL
        take_profit: float,     # precio TP
    ) -> OrderResult:
        """Abrir posición con SL/TP."""
        ...

    @abstractmethod
    async def close_position(
        self,
        symbol: str,
        side: str,
        quantity: float,        # cantidad de coins a cerrar
    ) -> OrderResult:
        """Cerrar posición (total o parcial)."""
        ...

    @abstractmethod
    async def get_balance(self) -> BalanceInfo:
        """Obtener balance actual de la cuenta."""
        ...

    @abstractmethod
    async def get_positions(self) -> List[PositionInfo]:
        """Obtener todas las posiciones abiertas."""
        ...

    @abstractmethod
    async def set_leverage(self, symbol: str, leverage: int) -> bool:
        """Configurar leverage para un símbolo."""
        ...

    @abstractmethod
    async def sync_state(self) -> Dict:
        """Sincronizar estado DB ↔ Exchange. Retorna diff."""
        ...

    @property
    @abstractmethod
    def mode(self) -> str:
        """'paper' | 'live' | 'testnet'"""
        ...
```

### Implementación 1: `PaperExchangeAdapter`

Extrae la lógica actual de `_open_position()` y `_close_position()` de `trading_agent.py` (líneas 557-770). Encapsula el flujo actual:
- `open_position()`: Calcula margin, deduce de `agent.current_balance`, crea `Portfolio` + `Trade` en DB
- `close_position()`: Calcula PnL, suma a balance, crea `Trade`, elimina `Portfolio`
- `get_balance()`: Lee `agent.current_balance` desde DB
- `get_positions()`: Lee `Portfolio` items del agente
- `sync_state()`: No-op (DB es la fuente de verdad)

**No hay cambio funcional** — solo mover código existente al adapter.

### Implementación 2: `CCXTExchangeAdapter`

```python
# backend/services/execution/ccxt_adapter.py

import ccxt.async_support as ccxt   # versión async
from .exchange_adapter import ExchangeAdapter, OrderResult, PositionInfo, BalanceInfo

class CCXTExchangeAdapter(ExchangeAdapter):
    """Adapter para trading real vía CCXT (Binance Futures)."""

    def __init__(self, config: dict):
        self.exchange = ccxt.binance({
            'apiKey': config['api_key'],
            'secret': config['api_secret'],
            'sandbox': config.get('testnet', True),  # SIEMPRE testnet primero
            'options': {
                'defaultType': 'future',              # Binance Futures (USDT-M)
                'adjustForTimeDifference': True,
            },
            'enableRateLimit': True,
        })

    async def open_position(self, symbol, side, margin, leverage, stop_loss, take_profit):
        try:
            # 1. Set leverage
            await self.exchange.set_leverage(leverage, symbol)

            # 2. Set margin mode (isolated)
            await self.exchange.set_margin_mode('isolated', symbol)

            # 3. Calcular cantidad
            price = (await self.exchange.fetch_ticker(symbol))['last']
            amount = (margin * leverage) / price

            # 4. Abrir posición (market order)
            order_side = 'buy' if side == 'long' else 'sell'
            order = await self.exchange.create_market_order(
                symbol, order_side, amount
            )

            # 5. Colocar SL/TP como órdenes condicionales
            sl_side = 'sell' if side == 'long' else 'buy'
            await self.exchange.create_order(
                symbol, 'stop_market', sl_side, amount,
                params={'stopPrice': stop_loss, 'closePosition': True}
            )
            await self.exchange.create_order(
                symbol, 'take_profit_market', sl_side, amount,
                params={'stopPrice': take_profit, 'closePosition': True}
            )

            return OrderResult(
                success=True,
                order_id=order['id'],
                fill_price=float(order.get('average', price)),
                filled_qty=float(order.get('filled', amount)),
                commission=float(order.get('fee', {}).get('cost', 0)),
                raw_response=order,
            )
        except Exception as e:
            return OrderResult(success=False, error=str(e))

    async def close_position(self, symbol, side, quantity):
        try:
            close_side = 'sell' if side == 'long' else 'buy'
            order = await self.exchange.create_market_order(
                symbol, close_side, quantity, params={'reduceOnly': True}
            )
            # Cancelar SL/TP pendientes
            open_orders = await self.exchange.fetch_open_orders(symbol)
            for o in open_orders:
                if o['type'] in ('stop_market', 'take_profit_market'):
                    await self.exchange.cancel_order(o['id'], symbol)

            return OrderResult(
                success=True,
                order_id=order['id'],
                fill_price=float(order.get('average', 0)),
                filled_qty=float(order.get('filled', quantity)),
                commission=float(order.get('fee', {}).get('cost', 0)),
                raw_response=order,
            )
        except Exception as e:
            return OrderResult(success=False, error=str(e))

    async def get_balance(self):
        bal = await self.exchange.fetch_balance()
        usdt = bal.get('USDT', {})
        return BalanceInfo(
            total=float(usdt.get('total', 0)),
            available=float(usdt.get('free', 0)),
            margin_used=float(usdt.get('used', 0)),
            unrealized_pnl=0,  # calcular de posiciones
        )

    async def get_positions(self):
        positions = await self.exchange.fetch_positions()
        result = []
        for p in positions:
            if float(p.get('contracts', 0)) > 0:
                result.append(PositionInfo(
                    symbol=p['symbol'],
                    side=p['side'],
                    size=float(p['contracts']),
                    entry_price=float(p.get('entryPrice', 0)),
                    mark_price=float(p.get('markPrice', 0)),
                    unrealized_pnl=float(p.get('unrealizedPnl', 0)),
                    leverage=int(p.get('leverage', 1)),
                    margin=float(p.get('initialMargin', 0)),
                    liquidation_price=float(p.get('liquidationPrice', 0)),
                ))
        return result

    async def set_leverage(self, symbol, leverage):
        try:
            await self.exchange.set_leverage(leverage, symbol)
            return True
        except:
            return False

    async def sync_state(self):
        """Sincronizar posiciones del exchange con la DB local."""
        exchange_positions = await self.get_positions()
        # TODO: Comparar con Portfolio DB, resolver discrepancias
        return {"exchange_positions": len(exchange_positions)}

    @property
    def mode(self):
        return 'testnet' if self.exchange.sandbox else 'live'
```

### Archivos a Modificar/Crear

| Archivo | Acción | Detalle |
|---------|--------|---------|
| `backend/services/execution/exchange_adapter.py` | **CREAR** | ABC `ExchangeAdapter` + dataclasses `OrderResult`, `PositionInfo`, `BalanceInfo` |
| `backend/services/execution/paper_adapter.py` | **CREAR** | `PaperExchangeAdapter` — extraer lógica de `trading_agent.py` L557-770 |
| `backend/services/execution/ccxt_adapter.py` | **CREAR** | `CCXTExchangeAdapter` — implementación CCXT para Binance Futures |
| `backend/services/execution/__init__.py` | **MODIFICAR** | Exportar nuevos adapters |
| `backend/services/trading_agent.py` | **MODIFICAR** | Recibir `ExchangeAdapter` en constructor, delegar `_open_position` / `_close_position` al adapter |
| `backend/models/database.py` | **MODIFICAR** | Añadir campo `execution_mode` a `TradingAgent` ("paper" \| "live" \| "testnet") y `exchange_order_id` a `Trade` |
| `main.py` | **MODIFICAR** | Inyectar adapter correcto al crear `TradingAgentService`. Nueva ruta API para configurar credenciales |
| `requirements.txt` | **MODIFICAR** | Añadir `ccxt>=4.0.0` |
| `.env` | **CREAR** | `BINANCE_API_KEY`, `BINANCE_API_SECRET`, `BINANCE_TESTNET=true` |
| `static/index.html` | **MODIFICAR** | Indicador de modo (paper/live/testnet) en UI, badge de estado, safety warnings |

### Mapeo de Símbolos: CoinGecko ID → Binance Futures Symbol

El sistema usa CoinGecko IDs internamente (`bitcoin`, `ethereum`, etc.). Para CCXT necesitamos el símbolo Binance Futures:

```python
SYMBOL_MAP = {
    # ── Large-cap (8 originales) ──
    "bitcoin":    "BTC/USDT:USDT",
    "ethereum":   "ETH/USDT:USDT",
    "binancecoin":"BNB/USDT:USDT",
    "cardano":    "ADA/USDT:USDT",
    "solana":     "SOL/USDT:USDT",
    "ripple":     "XRP/USDT:USDT",
    "polkadot":   "DOT/USDT:USDT",
    "dogecoin":   "DOGE/USDT:USDT",
    # ── Mid-cap volátiles (15 añadidos sesión 7) ──
    "avalanche-2":        "AVAX/USDT:USDT",
    "chainlink":          "LINK/USDT:USDT",
    "near":               "NEAR/USDT:USDT",
    "sui":                "SUI/USDT:USDT",
    "pepe":               "1000PEPE/USDT:USDT",  # x1000 en Binance
    "aptos":              "APT/USDT:USDT",
    "arbitrum":           "ARB/USDT:USDT",
    "filecoin":           "FIL/USDT:USDT",
    "render-token":       "RENDER/USDT:USDT",
    "injective-protocol": "INJ/USDT:USDT",
    "fetch-ai":           "FET/USDT:USDT",
    "bonk":               "1000BONK/USDT:USDT",  # x1000 en Binance
    "floki":              "1000FLOKI/USDT:USDT",  # x1000 en Binance
    "sei-network":        "SEI/USDT:USDT",
    "wif":                "WIF/USDT:USDT",
}
```

> **IMPORTANTE**: PEPE, BONK y FLOKI usan formato `1000XXX` en Binance Futures. El adapter debe manejar el scaling x1000 (dividir cantidad, multiplicar precio).

### Formato de Símbolos CCXT

CCXT usa formato unificado para futures perpetuos: `BASE/QUOTE:SETTLE`
- `BTC/USDT:USDT` = Perpetuo USDT-margined BTC  
- El `:USDT` al final indica que es un contrato perpetuo (linear) settlado en USDT
- Documentación: https://docs.ccxt.com/#/README?id=perpetual-swap-futures

### Integración con MakerExecutionManager (ya existente)

El `MakerExecutionManager` en `backend/services/execution/maker_engine.py` ya usa **callback-based Protocol** (líneas 104-133):

```python
class PlaceOrderFn(Protocol):
    async def __call__(self, symbol, side, quantity, price, post_only=True) -> Dict: ...

class CancelOrderFn(Protocol):
    async def __call__(self, symbol, order_id) -> bool: ...

class GetOrderStatusFn(Protocol):
    async def __call__(self, symbol, order_id) -> Dict: ...

class GetBestPriceFn(Protocol):
    async def __call__(self, symbol) -> Dict[str, float]: ...
```

Estas callbacks se mapean directamente a métodos CCXT:
- `place_order` → `exchange.create_limit_order()`
- `cancel_order` → `exchange.cancel_order()`
- `get_order_status` → `exchange.fetch_order()`
- `get_best_price` → `exchange.fetch_order_book()` → `{'bid': best_bid, 'ask': best_ask}`

El `CCXTExchangeAdapter` puede instanciar `MakerExecutionManager` internamente para scalpers 1m/3m que necesitan maker orders.

### Fases de Implementación

| Fase | Descripción | Riesgo |
|------|-------------|--------|
| **X1** | Crear `ExchangeAdapter` ABC + `OrderResult`/`PositionInfo`/`BalanceInfo` dataclasses | Ninguno |
| **X2** | Crear `PaperExchangeAdapter` extrayendo lógica de `_open_position` / `_close_position` | Bajo — refactor, sin cambio funcional |
| **X3** | Modificar `TradingAgentService.__init__()` para recibir adapter; delegar ejecución | Medio — punto de integración |
| **X4** | Verificar que paper trading sigue funcionando idéntico con el adapter | Bajo — test manual |
| **X5** | Añadir `ccxt` a requirements, crear `CCXTExchangeAdapter` básico | Bajo |
| **X6** | Implementar `open_position` + `close_position` con market orders | Medio — interacción con exchange real |
| **X7** | Añadir SL/TP como órdenes condicionales en Binance | Medio — sintaxis específica de Binance |
| **X8** | Implementar `sync_state()` — reconciliación DB ↔ Exchange | Alto — lógica compleja de diff |
| **X9** | UI: Badge de modo, safety confirm para live, config de API keys | Bajo |
| **X10** | Testing completo en Binance Testnet antes de ir a Mainnet | **Crítico** |

### Configuración Binance Testnet

- **URL Testnet Futures**: `https://testnet.binancefuture.com`
- **Crear cuenta**: https://testnet.binancefuture.com/
- **API Keys de testnet**: Generar en la misma web de testnet
- **CCXT Sandbox Mode**: `exchange.set_sandbox_mode(True)` o `sandbox: True` en config
- **Balance testnet**: Se resetea automáticamente, incluye fondos de prueba

```python
# Activar testnet en CCXT:
exchange = ccxt.binance({
    'apiKey': 'TESTNET_API_KEY',
    'secret': 'TESTNET_API_SECRET',
    'sandbox': True,                    # ← esto activa testnet automáticamente
    'options': {'defaultType': 'future'},
})
```

### Modelo de Datos: Cambios en DB

```python
# TradingAgent — nuevo campo:
execution_mode = Column(String, default="paper")  # "paper" | "testnet" | "live"

# Trade — nuevo campo:
exchange_order_id = Column(String, nullable=True)  # ID de la orden en el exchange real
exchange_fill_price = Column(Float, nullable=True)  # precio real de fill (puede diferir del mark price)
exchange_commission = Column(Float, default=0.0)    # comisión real pagada al exchange
```

### Safety Guards (prioritarios)

1. **NUNCA modo live sin confirmación explícita** — doble confirm en UI + backend
2. **Testnet primero SIEMPRE** — blocker: no se puede pasar a live sin X horas en testnet
3. **Max position size en live** — hard limit configurable (e.g., $50 max por trade)
4. **Kill switch global** — endpoint para cerrar TODAS las posiciones inmediatamente
5. **Rate limiting CCXT** — `enableRateLimit: True` (CCXT maneja esto automáticamente)
6. **API keys en .env** — NUNCA en código, NUNCA en DB, NUNCA en frontend
7. **Logs detallados** — toda interacción con exchange loggeada con request/response
8. **Balance reconciliation** — verificar saldo real antes de cada trade
9. **Circuit breaker** — si 3 trades consecutivos fallan, pausar el agente automáticamente
10. **Paper shadow mode** — poder ejecutar live + paper en paralelo para comparar

### Referencia Rápida CCXT para Binance Futures

```python
import ccxt.async_support as ccxt

# Crear instancia
exchange = ccxt.binance({'options': {'defaultType': 'future'}})

# Market order (abrir long)
order = await exchange.create_market_order('BTC/USDT:USDT', 'buy', 0.001)

# Limit order (maker)
order = await exchange.create_limit_order('BTC/USDT:USDT', 'buy', 0.001, 64000)

# Set leverage
await exchange.set_leverage(10, 'BTC/USDT:USDT')

# Set margin mode
await exchange.set_margin_mode('isolated', 'BTC/USDT:USDT')

# Stop Loss order
await exchange.create_order('BTC/USDT:USDT', 'stop_market', 'sell', 0.001,
    params={'stopPrice': 63000, 'closePosition': True})

# Take Profit order
await exchange.create_order('BTC/USDT:USDT', 'take_profit_market', 'sell', 0.001,
    params={'stopPrice': 67000, 'closePosition': True})

# Cerrar posición (reduce only)
await exchange.create_market_order('BTC/USDT:USDT', 'sell', 0.001,
    params={'reduceOnly': True})

# Obtener posiciones
positions = await exchange.fetch_positions()

# Obtener balance
balance = await exchange.fetch_balance()

# Cancelar todas las órdenes
await exchange.cancel_all_orders('BTC/USDT:USDT')

# Order book (para MakerExecutionManager)
book = await exchange.fetch_order_book('BTC/USDT:USDT', limit=5)
best_bid = book['bids'][0][0]
best_ask = book['asks'][0][0]
```

### Contexto del Codebase Actual (para el agente implementador)

**Flujo actual de ejecución (Paper Trading)**:

1. `main.py` scheduler llama `run_trading_cycle()` cada 60s
2. → `TradingAgentService.make_trading_decision(agent, db)`
3. → Evaluación de estrategia → genera `Signal`
4. → `_open_position(agent, coin, signal, strategy_key, db)` (L557)
   - Calcula margin vía `calculate_position_size()`
   - Deduce de `agent.current_balance` (L614)
   - Crea `Portfolio` item en DB (L616-630)
   - Crea `Trade` record en DB (L632-643)
   - `db.commit()`
5. Para cerrar: `_close_position(agent, pos, price, db)` (L707)
   - Calcula PnL (L714-718)
   - Suma a `agent.current_balance` (L720)
   - Crea `Trade` record
   - `db.delete(pos)`
   - `db.commit()`

**Punto de inyección**: El adapter se inyecta en `TradingAgentService.__init__()`. Los métodos `_open_position` y `_close_position` delegan al adapter en vez de manipular la DB directamente.

**ReactiveRiskMonitor** (L1-365 de `risk_monitor.py`): Usa WS ticks para detectar SL/TP/liquidación cada ~1s. En modo live, el exchange ya tiene SL/TP como órdenes condicionales, pero el monitor sigue siendo necesario para:
- Trailing stop updates (el exchange no tiene trailing nativo en futuros)
- Detección de liquidación y sync con DB
- Estado visual en el dashboard

**MakerExecutionManager** (L1-479 de `maker_engine.py`): Ya listo para CCXT. Solo necesita recibir las callbacks CCXT en vez de mocks.

---

- Todas las features deben ser compatibles con balances pequeños ($50-$100)
- Priorizar APIs gratuitas o de muy bajo costo
- Mantener la app funcional en cada paso (no romper el MVP)
- **Binance Futures es el proveedor primario** — Spot y CoinGecko solo se usan como fallback
- **Mark Price** como precio principal (usado para liquidaciones reales en Binance)
- **Funding Rate** disponible en dashboard y en indicadores del trading agent
- **No bloquear el event loop** — toda I/O síncrona va en `asyncio.to_thread()`
- DoD: features completas funcionales, code review al finalizar (no unit tests)
