# Money Maker — Crypto Futures Trading Simulation

Plataforma de simulación de trading de futuros de criptomonedas con 10 estrategias cuantitativas, backtesting histórico y trailing stops adaptativos basados en ATR.

## Características

- **10 Estrategias Cuantitativas** — Trend Rider, Mean Reversion, Momentum Sniper, Scalper Pro (1h/1m/3m/5m/15m), Grid Trader, Confluence Master
- **Exit Timing por Estrategia** — Cada estrategia puede implementar su propia lógica de salida via override de `_check_exit_signal()` (Open/Closed Principle)
- **Futuros con Apalancamiento** — Long/Short con leverage configurable por estrategia
- **Backtesting Histórico** — CLI con comparación multi-estrategia y multi-coin
- **Trailing Stop ATR + Breakeven** — Sistema de trailing en 2 fases (breakeven at +1R, luego Chandelier K×ATR)
- **Risk Monitor** — Polling cada 5s para gestión de riesgo en tiempo real
- **4 Perfiles de Cuenta** — Conservative, Moderate, Aggressive, Degen
- **Market Clocks** — 8 mercados mundiales con estado abierto/cerrado
- **Dashboard Web** — Gráficos candlestick (TradingView Lightweight Charts), posiciones, PnL en vivo
- **LLM Integration** — Gemini 2.0 Flash para análisis de sentimiento
- **Datos de Mercado** — Binance Futures API (primary), Spot (fallback), CoinGecko (fallback)

## Inicio Rápido

```bash
# Instalar dependencias
pip install -r requirements.txt

# Iniciar servidor (puerto 8001)
python3 main.py
```

Abrir **http://localhost:8001** en el navegador.

### Backtesting CLI

```bash
# Comparar todas las estrategias
python3 backtest_cli.py --compare

# Estrategia específica
python3 backtest_cli.py -s trend_rider scalper -c BTC ETH -p 30 90

# Sin trailing (baseline)
python3 backtest_cli.py --compare --no-trailing

# Solo scalpers
python3 backtest_cli.py --scalpers
```

---

## Arquitectura

```
money-maker/
├── main.py                          # FastAPI app, API endpoints, Pydantic models
├── backtest_cli.py                  # CLI para backtesting
├── requirements.txt
├── backend/
│   ├── database.py                  # SQLite config + migraciones
│   ├── models/
│   │   └── database.py              # SQLAlchemy models (TradingAgent, Portfolio, Trade, Decision)
│   └── services/
│       ├── market_data.py           # Binance Futures/Spot + CoinGecko
│       ├── news_service.py          # Noticias + Gemini LLM
│       ├── trading_agent.py         # Motor de trading en vivo (60s cycle + 5s risk monitor)
│       ├── backtester.py            # Motor de backtesting histórico
│       └── strategies/              # ← Paquete de estrategias (refactorizado)
│           ├── __init__.py          #    Re-exports públicos
│           ├── models.py            #    Signal, StrategyConfig, STRATEGIES dict
│           ├── indicators.py        #    Indicators (RSI, MACD, BB, ATR, ADX, StochRSI, Volume)
│           ├── base.py              #    BaseStrategy + _build_signal + _check_exit_signal (overridable)
│           ├── engine.py            #    StrategyEngine (dispatcher) + position sizing
│           ├── trend_rider.py       #    Trend Rider v3.1 (8 layers + custom exit timing)
│           ├── mean_reversion.py    #    Mean Reversion (BB + RSI extremes)
│           ├── momentum_sniper.py   #    Momentum Sniper (MACD + volume spike)
│           ├── scalper.py           #    Scalper Pro (all timeframes: 1h/1m/3m/5m/15m)
│           ├── grid_trader.py       #    Grid Trader (SMA deviation levels)
│           └── confluence_master.py #    Confluence Master (5+ indicators aligned)
└── static/
    └── index.html                   # Dashboard SPA (vanilla JS + TradingView Charts)
```

### Imports — Backward Compatible

Todos los imports externos siguen funcionando sin cambios:

```python
from backend.services.strategies import (
    StrategyEngine, Indicators, STRATEGIES,
    calculate_position_size, calculate_liquidation_price, Signal
)
```

---

## Estrategias

| Estrategia | Estilo | Leverage | R:R | Trail ATR Mult | Descripción |
|---|---|---|---|---|---|
| **Trend Rider** | Trend | 3-5x | 2.25:1 | 3.0 | 8 layers: EMA alignment + slope + ADX/DI + RSI pullback + MACD + BB + StochRSI + Volume. Custom exit: winners run en tendencia alineada |
| **Mean Reversion** | Mean Rev | 2-3x | 1.7:1 | 2.0 | BB extremes + RSI oversold/overbought |
| **Momentum Sniper** | Momentum | 4-7x | 2.7:1 | 2.5 | MACD crossover + volume spike |
| **Scalper Pro 1h** | Scalping | 5-10x | 3:1 | 2.5 | Trend-pullback (6 layers) |
| **Scalper Pro 1m** | Scalping | 10-20x | 3:1 | 1.5 | Ultra-fast, tight stops |
| **Scalper Pro 3m** | Scalping | 8-15x | 3:1 | 1.8 | Fast, balanced |
| **Scalper Pro 5m** | Scalping | 7-12x | 3:1 | 2.0 | Standard daytrading |
| **Scalper Pro 15m** | Scalping | 6-10x | 3:1 | 2.2 | Swing scalper |
| **Grid Trader** | Grid | 2-3x | 0.5:1 | 2.0 | SMA21 deviation levels |
| **Confluence Master** | Multi-factor | 5-10x | 2.5:1 | 2.5 | 5+ indicators aligned |

### Trailing Stop — 2 Fases

1. **Breakeven (Phase 1)**: Cuando el precio se mueve +1R a favor (1× distancia SL desde entry), el SL se mueve a entry price → trade sin riesgo.
2. **Chandelier (Phase 2)**: Cuando el precio se mueve ≥ trail_pct desde entry, el SL trailing sigue al precio a `K × ATR` de distancia del mejor precio alcanzado.

### Exit Timing por Estrategia (Override Pattern)

Cada estrategia puede personalizar cuándo cerrar posiciones sobreescribiendo `_check_exit_signal()` en su clase:

- **Default (base.py):** cierra en reversal (score opuesto ≥ 3) o SL/TP
- **Trend Rider:** exit timing adaptativo — si está ganando Y la tendencia EMA sigue alineada, requiere score ≥ 5 con ventaja ≥ +2 para cerrar (deja correr ganadores). Posiciones perdedoras o sin alineación usan el threshold default

Esto sigue el **Open/Closed Principle**: base.py no se modifica, cada estrategia extiende su comportamiento.

---

## Cómo Crear una Nueva Estrategia

### Paso 1: Crear el archivo de estrategia

Crear `backend/services/strategies/mi_estrategia.py`:

```python
"""
Mi Estrategia — breve descripción del enfoque.
"""
from typing import Dict

from backend.services.strategies.base import BaseStrategy
from backend.services.strategies.models import STRATEGIES, Signal


class MiEstrategiaStrategy(BaseStrategy):

    def evaluate(self, ind: Dict, price: float,
                 has_long: bool = False, has_short: bool = False,
                 entry_price: float = 0.0) -> Signal:

        reasons = []
        long_score = 0
        short_score = 0
        cfg = STRATEGIES["mi_estrategia"]  # debe coincidir con la key del paso 2

        # ── Leer indicadores del dict ──
        rsi = ind.get("rsi")
        macd = ind.get("macd")
        bb = ind.get("bb")
        atr_pct = ind.get("atr_pct") or 2.0
        # ... otros: ema_9, ema_21, ema_55, adx, stoch_rsi, volume, momentum

        # ── Lógica de scoring ──
        # Suma puntos a long_score o short_score según condiciones
        if rsi is not None and rsi < 30:
            long_score += 2
            reasons.append(f"RSI oversold ({rsi:.0f})")

        if rsi is not None and rsi > 70:
            short_score += 2
            reasons.append(f"RSI overbought ({rsi:.0f})")

        # ... más capas de análisis ...

        # ── Stops ATR-adaptativos ──
        sl = max(atr_pct * 1.5, 1.0)           # Stop-loss
        tp = max(atr_pct * 3.0, sl * 2.0)       # Take-profit
        trail = max(atr_pct * cfg.trail_atr_mult, sl)  # Chandelier trailing

        # ── Delegar a _build_signal (heredado de BaseStrategy) ──
        return self._build_signal(
            long_score, short_score, reasons, cfg,
            has_long, has_short, sl, tp, entry_price, price, trail
        )
```

**Notas sobre `_build_signal`:**
- Requiere `min_score_to_act = 3` para abrir posición
- Calcula confidence como `max_score / 10.0` (capped 0.95)
- Verifica `confidence >= cfg.min_confidence` antes de emitir señal
- Delega exit checks a `_check_exit_signal()` (overridable per-strategy)
- Pasa `trail_pct` al Signal para el sistema de trailing

### Paso 1.5 (Opcional): Override de Exit Timing

Para personalizar cuándo cerrar posiciones, sobreescribir `_check_exit_signal()`:

```python
from typing import Optional

class MiEstrategiaStrategy(BaseStrategy):

    def _check_exit_signal(self, has_long, has_short, long_score, short_score,
                           entry_price, current_price, stop_loss_pct, take_profit_pct,
                           confidence, leverage, reasoning_str, trail_pct) -> Optional[Signal]:
        """Custom exit: solo cerrar winners si el reversal es fuerte."""
        # Retornar Signal para cerrar, o None para mantener abierto
        # Ver trend_rider.py como ejemplo completo
        ...
        return None  # delega al default
```

### Paso 2: Registrar la configuración

En `backend/services/strategies/models.py`, agregar al dict `STRATEGIES`:

```python
"mi_estrategia": StrategyConfig(
    key="mi_estrategia",
    name="Mi Estrategia",
    description="Descripción visible en la UI.",
    style="trend",          # trend, mean_reversion, momentum, scalping, grid, confluence
    default_leverage=3,
    max_leverage=5,
    max_positions=3,
    risk_per_trade_pct=2.0, # % del capital arriesgado por trade
    min_confidence=0.50,    # mínimo para abrir posición (0.0-1.0)
    trail_atr_mult=2.5,     # K para Chandelier exit (K × ATR)
),
```

### Paso 3: Registrar en el engine

En `backend/services/strategies/engine.py`:

```python
# 1. Import
from backend.services.strategies.mi_estrategia import MiEstrategiaStrategy

# 2. Agregar al dict _instances en __init__
self._instances = {
    # ... existentes ...
    "mi_estrategia": MiEstrategiaStrategy(),
}
```

### Paso 4: Verificar

```bash
# Test de imports
python3 -c "from backend.services.strategies import STRATEGIES, StrategyEngine; \
    e = StrategyEngine(); print(list(e._instances.keys()))"

# Backtest
python3 backtest_cli.py -s mi_estrategia -c BTC -p 90
```

**No se requiere** modificar `main.py`, `trading_agent.py`, `backtester.py` ni el frontend. Todo se descubre automáticamente a través del dict `STRATEGIES`.

---

## Indicadores Disponibles

El dict `indicators` que recibe `evaluate()` contiene:

| Key | Tipo | Descripción |
|---|---|---|
| `rsi` | `float` | RSI (14), 0-100 |
| `macd` | `dict` | `{macd, signal, histogram, crossover, prev_histogram}` |
| `bb` | `dict` | `{upper, middle, lower, width_pct, pct_b, squeeze}` |
| `atr` | `float` | ATR absoluto (14) |
| `atr_pct` | `float` | ATR como % del precio |
| `adx` | `dict` | `{adx, plus_di, minus_di, trending, strong_trend, di_crossover}` |
| `stoch_rsi` | `dict` | `{k, d, oversold, overbought}` |
| `volume` | `dict` | `{ratio, increasing, spike, avg_volume}` |
| `ema_9` | `float` | EMA 9 periodos |
| `ema_21` | `float` | EMA 21 periodos |
| `ema_55` | `float` | EMA 55 periodos |
| `sma_7` | `float` | SMA 7 periodos |
| `sma_21` | `float` | SMA 21 periodos |
| `sma_50` | `float` | SMA 50 periodos |
| `ema21_slope` | `float` | Pendiente EMA 21 (% cambio últimas 5 velas) |
| `ema55_slope` | `float` | Pendiente EMA 55 (% cambio últimas 5 velas) |
| `momentum` | `float` | `(price - SMA7) / SMA7 * 100` |

---

## Modelo de Comisiones

- **Taker fee**: 0.05% por trade (open + close)
- **Funding rate**: 0.01% cada 8h (para futuros)

## Stack Tecnológico

- **Backend**: Python 3.10, FastAPI, SQLAlchemy, APScheduler
- **Frontend**: HTML5, CSS3, JavaScript (Vanilla), TradingView Lightweight Charts v4.1.3
- **Base de Datos**: SQLite
- **APIs**: Binance Futures (primary), Binance Spot (fallback), CoinGecko (fallback)
- **LLM**: Google Gemini 2.0 Flash (análisis de sentimiento)

## Limitaciones

⚠️ **SIMULACIÓN** — No se ejecutan trades reales ni se usa dinero real. Los datos de mercado son reales (Binance), pero las posiciones son simuladas.

## Licencia

MIT License
