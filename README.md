# Money Maker - AI Trading Simulation Platform

Una aplicación web de simulación de trading de criptomonedas en tiempo real con agentes de trading inteligentes basados en IA.

## Características

- 🤖 **Agentes de Trading con IA**: Crea agentes autónomos que toman decisiones de trading inteligentes
- 📊 **Dashboard en Tiempo Real**: Monitorea el rendimiento de tus agentes en tiempo real
- 💹 **Datos de Mercado Reales**: Utiliza datos públicos de CoinGecko API para precios actuales
- 📰 **Análisis de Noticias**: Los agentes consideran noticias y sentimiento del mercado
- 📈 **Indicadores Técnicos**: Análisis con momentum, volatilidad y otros indicadores
- 💼 **Gestión de Portfolio**: Seguimiento completo de posiciones y rendimiento
- 🔄 **Actualizaciones WebSocket**: Notificaciones en vivo de trades y decisiones

## Cómo Funciona

1. **Crear Agentes**: Define un nombre y monto inicial para tu agente de trading
2. **Trading Autónomo**: El agente analiza el mercado cada 60 segundos y toma decisiones
3. **Análisis Inteligente**: Considera indicadores técnicos, sentimiento de noticias, y gestión de riesgo
4. **Visualización**: Observa todas las decisiones, trades, y noticias consideradas en tiempo real

## Instalación

### Requisitos

- Python 3.8 o superior
- pip (gestor de paquetes de Python)

### Pasos de Instalación

1. Clona el repositorio:
```bash
git clone https://github.com/smmdsa/money-maker.git
cd money-maker
```

2. Crea un entorno virtual (recomendado):
```bash
python -m venv venv
source venv/bin/activate  # En Windows: venv\Scripts\activate
```

3. Instala las dependencias:
```bash
pip install -r requirements.txt
```

4. Crea el archivo de configuración:
```bash
cp .env.example .env
```

## Uso

### Iniciar la Aplicación

```bash
python main.py
```

O usando uvicorn directamente:
```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

La aplicación estará disponible en: **http://localhost:8000**

### Crear un Agente de Trading

1. Abre la aplicación en tu navegador
2. Haz clic en "Create New Agent"
3. Define un nombre y balance inicial (por defecto $10,000)
4. El agente comenzará a operar automáticamente

### Monitorear el Rendimiento

- **Panel de Agentes**: Ve todos tus agentes y su rendimiento general
- **Detalles del Agente**: Selecciona un agente para ver su portfolio detallado
- **Historial de Trades**: Observa todos los trades ejecutados
- **Decisiones de IA**: Ve el razonamiento detrás de cada decisión
- **Noticias del Mercado**: Mantente informado sobre eventos que afectan el mercado

### Controlar Agentes

- **Pausar**: Detiene temporalmente el trading automático
- **Reanudar**: Reactiva el trading automático
- **Eliminar**: Borra permanentemente el agente y su historial

## Arquitectura

### Backend (FastAPI + Python)

- **`main.py`**: Aplicación principal FastAPI con endpoints de API
- **`backend/models/database.py`**: Modelos de base de datos SQLAlchemy
- **`backend/database.py`**: Configuración de conexión a base de datos
- **`backend/services/`**: Servicios de negocio
  - `market_data.py`: Obtención de datos de mercado de CoinGecko
  - `trading_agent.py`: Lógica de IA para decisiones de trading
  - `news_service.py`: Gestión de noticias y análisis de sentimiento

### Frontend (HTML/CSS/JavaScript)

- **`static/index.html`**: Dashboard interactivo con todas las funcionalidades

### Base de Datos

- SQLite para almacenamiento persistente
- Modelos: TradingAgent, Portfolio, Trade, Decision, NewsEvent

## API Endpoints

### Agentes
- `POST /api/agents` - Crear nuevo agente
- `GET /api/agents` - Listar todos los agentes
- `GET /api/agents/{id}` - Obtener detalles de un agente
- `PATCH /api/agents/{id}` - Actualizar estado del agente
- `DELETE /api/agents/{id}` - Eliminar agente

### Trading
- `GET /api/agents/{id}/trades` - Historial de trades
- `GET /api/agents/{id}/decisions` - Historial de decisiones

### Mercado
- `GET /api/market/prices` - Precios actuales de todas las criptomonedas
- `GET /api/market/{coin}` - Datos detallados de una criptomoneda

### Noticias
- `GET /api/news` - Noticias recientes y análisis de sentimiento

### WebSocket
- `WS /ws` - Conexión WebSocket para actualizaciones en tiempo real

## Lógica de Trading de IA

Los agentes utilizan un sistema de puntuación basado en múltiples señales:

### Señales de Compra
- Momentum positivo (>2% o >5%)
- Cambio de precio positivo en 24h (>5%)
- Sentimiento positivo de noticias
- No tiene posición existente

### Señales de Venta
- Momentum negativo (<-2% o <-5%)
- Profit-taking en ganancias >10%
- Stop-loss en pérdidas >5%
- Sentimiento negativo de noticias

### Gestión de Riesgo
- Máximo 20% del balance en una sola moneda
- Balance mínimo de $100 para operar
- Tamaño de posición: 10% del balance por trade
- Diversificación automática

## Criptomonedas Soportadas

- Bitcoin (BTC)
- Ethereum (ETH)
- Binance Coin (BNB)
- Cardano (ADA)
- Solana (SOL)
- Ripple (XRP)
- Polkadot (DOT)
- Dogecoin (DOGE)

## Configuración Avanzada

Edita el archivo `.env` para personalizar:

```env
# Intervalo de trading (segundos)
TRADING_INTERVAL_SECONDS=60

# Balance inicial por defecto
DEFAULT_INITIAL_BALANCE=10000

# Tamaño máximo de posición (% del balance)
MAX_POSITION_SIZE=0.2
```

## Limitaciones

⚠️ **IMPORTANTE**: Esta es una plataforma de SIMULACIÓN. No se ejecutan trades reales ni se utiliza dinero real.

- Los datos de mercado son reales (de CoinGecko)
- Las decisiones son simuladas
- No se conecta a exchanges reales
- Las noticias son simuladas (en producción se conectarían a APIs de noticias reales)

## Desarrollo Futuro

- [ ] Integración con APIs de noticias reales (NewsAPI, CryptoPanic)
- [ ] Modelos de ML más avanzados (LSTM, Transformer)
- [ ] Backtesting con datos históricos
- [ ] Más indicadores técnicos (RSI, MACD, Bollinger Bands)
- [ ] Estrategias de trading personalizables
- [ ] Modo paper trading con exchanges reales
- [ ] Análisis de sentimiento de redes sociales
- [ ] Alertas y notificaciones

## Tecnologías Utilizadas

- **Backend**: Python, FastAPI, SQLAlchemy
- **Frontend**: HTML5, CSS3, JavaScript (Vanilla)
- **Base de Datos**: SQLite
- **APIs**: CoinGecko API (datos de mercado)
- **WebSockets**: Para actualizaciones en tiempo real
- **Scheduler**: APScheduler para tareas en background

## Licencia

MIT License

## Contribuciones

¡Las contribuciones son bienvenidas! Por favor, abre un issue o pull request.

## Soporte

Si encuentras algún problema o tienes preguntas, por favor abre un issue en GitHub. 
