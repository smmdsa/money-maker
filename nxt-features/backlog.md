# Money Maker — Feature Backlog

> Última actualización: 2026-02-18

---

## Top 5 — Próximas Features (priorizadas)

### 1. 📊 Gráficos de Precios con Candlesticks e Indicadores

**Impacto**: Muy Alto  
**Área**: UX / Dashboard  
**Dependencias**: Ninguna (100% frontend)

Integrar [TradingView Lightweight Charts](https://github.com/nickvdyck/lightweight-charts) (open source, ~40KB) para mostrar:

- Candlesticks reales con datos OHLC del endpoint existente `get_ohlc()`
- Indicadores superpuestos: SMA 7/21, Bollinger Bands
- RSI en panel secundario
- Equity curve del portfolio del agente (valor total a lo largo del tiempo)
- Selector de timeframe: 1D, 7D, 14D, 30D

**Transformación**: De "lista de números" → "herramienta visual de trading real".

---

### 2. ⚙️ Estrategias Configurables por Agente

**Impacto**: Alto  
**Área**: Trading / Core Logic  
**Dependencias**: Ninguna

Perfiles de estrategia seleccionables al crear un agente:

| Estrategia | RSI Buy | RSI Sell | Max Posición | Stop-Loss | Take-Profit | Descripción |
|------------|---------|----------|-------------|-----------|-------------|-------------|
| **Conservador** | < 25 | > 75 | 10% | -3% | +8% | Pocas operaciones, alta confianza |
| **Moderado** | < 35 | > 65 | 15% | -5% | +10% | Balance riesgo/retorno (default actual) |
| **Agresivo** | < 40 | > 60 | 25% | -8% | +15% | Más operaciones, más riesgo |
| **Momentum** | — | — | 20% | -5% | +12% | Sigue tendencias fuertes |
| **DCA** | — | — | fijo | — | — | Dollar Cost Averaging automático |
| **Mean Reversion** | < 25 | > 75 | 15% | -4% | +6% | Compra en caídas, vende en rebotes |

Configuraciones adicionales por agente:
- **Monedas permitidas**: El usuario elige en qué monedas puede operar cada agente
- **Stop-loss / Take-profit** personalizables
- **Intervalo de análisis** configurable (30s, 60s, 5min, etc.)
- **Balance mínimo**: $50 USD (accesible para usuarios con sumas pequeñas)

---

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
| B1 | DCA automático como estrategia standalone | Medio | Incluido en #2 |
| B2 | Detección de oportunidades sin ejecución (alert-only mode) | Medio | Incluido en #5 |
| B3 | Preparar arquitectura para trading real (Binance/Coinbase API) | Alto | Pendiente |
| B4 | Portfolio rebalancing automático | Medio | Pendiente |

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
| D4 | API rate-limit dashboard (ver uso de CoinGecko) | Bajo | Pendiente |

---

## Configuración de Producto

### Límites de Balance

| Parámetro | Valor |
|-----------|-------|
| Balance mínimo por agente | **$50 USD** |
| Balance default al crear agente | $10,000 USD |
| Inversión mínima por trade | $10 USD |
| Máximo % por posición individual | 20% (configurable en #2) |

---

## Orden de Implementación

```
1. Gráficos Candlestick ──→ 100% frontend, no bloquea nada
2. Estrategias Configurables ──→ mejora lógica core + habilita backtesting
3. LLM Análisis ──→ requiere API key externa
4. Backtesting ──→ depende de que estrategias estén definidas
5. Notificaciones ──→ add-on independiente, se puede hacer en paralelo con 3-4
```

---

## Notas

- Todas las features deben ser compatibles con balances pequeños ($50-$100)
- Priorizar APIs gratuitas o de muy bajo costo
- Mantener la app funcional en cada paso (no romper el MVP)
