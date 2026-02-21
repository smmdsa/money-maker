/**
 * charts.js — Chart module for Money Maker dashboard
 * Uses TradingView Lightweight Charts v4
 * Responsibilities: candlestick chart, indicators overlay, RSI sub-chart, equity curve
 */

const Charts = (() => {
    // ── State ────────────────────────────────────────────────────────────
    let candlestickChart = null;
    let candlestickSeries = null;
    let sma7Series = null;
    let sma21Series = null;
    let bbUpperSeries = null;
    let bbLowerSeries = null;

    let rsiChart = null;
    let rsiSeries = null;
    let rsiUpperLine = null;
    let rsiLowerLine = null;

    let equityChart = null;
    let equitySeries = null;

    let currentCoin = 'bitcoin';
    let currentDays = 14;
    let currentInterval = null;  // null = days mode, string = interval mode (1m, 3m, 5m, 15m)

    let lastOhlcData = [];   // Keep reference to last loaded OHLC data

    // ── Position overlay state ───────────────────────────────────────────
    let _entryLine = null;
    let _slLine = null;
    let _tpLine = null;
    let _posOverlay = null;  // { entry, sl, tp, isLong, amount, margin }

    const CHART_BG = '#ffffff';
    const GRID_COLOR = '#f0f0f0';
    const CANDLE_UP = '#26a69a';
    const CANDLE_DOWN = '#ef5350';

    const THEMES = {
        light: {
            bg: '#ffffff',
            grid: '#f0f0f0',
            text: '#666',
            border: '#e0e0e0',
        },
        dark: {
            bg: '#161b22',
            grid: '#21262d',
            text: '#8b949e',
            border: '#30363d',
        },
    };

    let _currentTheme = 'light';

    // ── Helpers ──────────────────────────────────────────────────────────

    function computeSMA(data, period) {
        const result = [];
        for (let i = 0; i < data.length; i++) {
            if (i < period - 1) continue;
            let sum = 0;
            for (let j = 0; j < period; j++) {
                sum += data[i - j].close;
            }
            result.push({ time: data[i].time, value: sum / period });
        }
        return result;
    }

    function computeRSI(data, period = 14) {
        const result = [];
        if (data.length < period + 1) return result;

        const deltas = [];
        for (let i = 1; i < data.length; i++) {
            deltas.push(data[i].close - data[i - 1].close);
        }

        let avgGain = 0, avgLoss = 0;
        for (let i = 0; i < period; i++) {
            if (deltas[i] > 0) avgGain += deltas[i];
            else avgLoss += Math.abs(deltas[i]);
        }
        avgGain /= period;
        avgLoss /= period;

        for (let i = period; i < deltas.length; i++) {
            if (i === period) {
                const rs = avgLoss === 0 ? 100 : avgGain / avgLoss;
                const rsi = 100 - (100 / (1 + rs));
                result.push({ time: data[i + 1].time, value: rsi });
            }
            const delta = deltas[i];
            avgGain = (avgGain * (period - 1) + (delta > 0 ? delta : 0)) / period;
            avgLoss = (avgLoss * (period - 1) + (delta < 0 ? Math.abs(delta) : 0)) / period;
            const rs = avgLoss === 0 ? 100 : avgGain / avgLoss;
            const rsi = 100 - (100 / (1 + rs));
            result.push({ time: data[i + 1].time, value: rsi });
        }
        return result;
    }

    function computeBB(data, period = 20) {
        const upper = [], lower = [];
        for (let i = period - 1; i < data.length; i++) {
            let sum = 0;
            for (let j = 0; j < period; j++) sum += data[i - j].close;
            const mean = sum / period;
            let variance = 0;
            for (let j = 0; j < period; j++) variance += Math.pow(data[i - j].close - mean, 2);
            const std = Math.sqrt(variance / period);
            upper.push({ time: data[i].time, value: mean + 2 * std });
            lower.push({ time: data[i].time, value: mean - 2 * std });
        }
        return { upper, lower };
    }

    function getPriceFormat(price) {
        let precision, minMove;
        if (price >= 1000)       { precision = 2; minMove = 0.01; }
        else if (price >= 100)   { precision = 2; minMove = 0.01; }
        else if (price >= 10)    { precision = 3; minMove = 0.001; }
        else if (price >= 1)     { precision = 4; minMove = 0.0001; }
        else if (price >= 0.01)  { precision = 5; minMove = 0.00001; }
        else                     { precision = 6; minMove = 0.000001; }
        return { type: 'price', precision, minMove };
    }

    function applyPriceFormat(price) {
        const fmt = getPriceFormat(price);
        candlestickSeries.applyOptions({ priceFormat: fmt });
        sma7Series.applyOptions({ priceFormat: fmt });
        sma21Series.applyOptions({ priceFormat: fmt });
        bbUpperSeries.applyOptions({ priceFormat: fmt });
        bbLowerSeries.applyOptions({ priceFormat: fmt });
    }

    function chartLayoutOptions(height) {
        const t = THEMES[_currentTheme] || THEMES.light;
        return {
            height: height,
            layout: { background: { color: t.bg }, textColor: t.text },
            grid: {
                vertLines: { color: t.grid },
                horzLines: { color: t.grid },
            },
            crosshair: { mode: 0 },
            rightPriceScale: { borderColor: t.border },
            timeScale: {
                borderColor: t.border,
                timeVisible: true,
                secondsVisible: false,
            },
        };
    }

    // ── Candlestick Chart ────────────────────────────────────────────────

    function initCandlestickChart(containerId) {
        const container = document.getElementById(containerId);
        if (!container) return;
        container.innerHTML = '';

        candlestickChart = LightweightCharts.createChart(container, {
            ...chartLayoutOptions(380),
            width: container.clientWidth,
        });

        candlestickSeries = candlestickChart.addCandlestickSeries({
            upColor: CANDLE_UP,
            downColor: CANDLE_DOWN,
            borderDownColor: CANDLE_DOWN,
            borderUpColor: CANDLE_UP,
            wickDownColor: CANDLE_DOWN,
            wickUpColor: CANDLE_UP,
        });

        sma7Series = candlestickChart.addLineSeries({
            color: '#2196F3',
            lineWidth: 1,
            title: 'SMA 7',
        });

        sma21Series = candlestickChart.addLineSeries({
            color: '#FF9800',
            lineWidth: 1,
            title: 'SMA 21',
        });

        bbUpperSeries = candlestickChart.addLineSeries({
            color: 'rgba(103, 58, 183, 0.35)',
            lineWidth: 1,
            lineStyle: 2,
            title: 'BB Upper',
        });

        bbLowerSeries = candlestickChart.addLineSeries({
            color: 'rgba(103, 58, 183, 0.35)',
            lineWidth: 1,
            lineStyle: 2,
            title: 'BB Lower',
        });

        // Responsive resize
        const resizeObserver = new ResizeObserver(entries => {
            for (const entry of entries) {
                candlestickChart.applyOptions({ width: entry.contentRect.width });
            }
        });
        resizeObserver.observe(container);
    }

    // ── RSI Chart ────────────────────────────────────────────────────────

    function initRSIChart(containerId) {
        const container = document.getElementById(containerId);
        if (!container) return;
        container.innerHTML = '';

        rsiChart = LightweightCharts.createChart(container, {
            ...chartLayoutOptions(150),
            width: container.clientWidth,
        });

        rsiSeries = rsiChart.addLineSeries({
            color: '#9C27B0',
            lineWidth: 1.5,
            title: 'RSI',
        });

        // Overbought / oversold reference lines
        rsiUpperLine = rsiChart.addLineSeries({
            color: 'rgba(239, 83, 80, 0.4)',
            lineWidth: 1,
            lineStyle: 2,
            title: '70',
        });

        rsiLowerLine = rsiChart.addLineSeries({
            color: 'rgba(38, 166, 154, 0.4)',
            lineWidth: 1,
            lineStyle: 2,
            title: '30',
        });

        const resizeObserver = new ResizeObserver(entries => {
            for (const entry of entries) {
                rsiChart.applyOptions({ width: entry.contentRect.width });
            }
        });
        resizeObserver.observe(container);
    }

    // ── Equity Curve ─────────────────────────────────────────────────────

    function initEquityChart(containerId) {
        const container = document.getElementById(containerId);
        if (!container) return;
        container.innerHTML = '';

        equityChart = LightweightCharts.createChart(container, {
            ...chartLayoutOptions(200),
            width: container.clientWidth,
        });

        equitySeries = equityChart.addAreaSeries({
            topColor: 'rgba(102, 126, 234, 0.4)',
            bottomColor: 'rgba(102, 126, 234, 0.05)',
            lineColor: '#667eea',
            lineWidth: 2,
        });

        const resizeObserver = new ResizeObserver(entries => {
            for (const entry of entries) {
                equityChart.applyOptions({ width: entry.contentRect.width });
            }
        });
        resizeObserver.observe(container);
    }

    // ── Data Loading ─────────────────────────────────────────────────────

    async function loadOHLC(coin, days) {
        currentCoin = coin;
        currentDays = days;
        currentInterval = null;  // reset interval mode

        try {
            const resp = await fetch(`/api/market/${coin}/ohlc?days=${days}`);
            if (!resp.ok) throw new Error('No OHLC data');
            const data = await resp.json();

            if (!data || data.length === 0) {
                showChartMessage('candlestickChartContainer', 'No OHLC data available');
                return;
            }

            // Deduplicate by time (CoinGecko can return duplicates)
            const seen = new Set();
            const cleanData = data.filter(d => {
                if (seen.has(d.time)) return false;
                seen.add(d.time);
                return true;
            }).sort((a, b) => a.time - b.time);

            // Apply dynamic precision based on price level
            const lastPrice = cleanData[cleanData.length - 1].close;
            applyPriceFormat(lastPrice);

            candlestickSeries.setData(cleanData);
            lastOhlcData = cleanData;   // Keep reference for live updates
            sma7Series.setData(computeSMA(cleanData, 7));
            sma21Series.setData(computeSMA(cleanData, 21));

            const bb = computeBB(cleanData, Math.min(20, cleanData.length));
            bbUpperSeries.setData(bb.upper);
            bbLowerSeries.setData(bb.lower);

            // RSI
            const rsiData = computeRSI(cleanData);
            rsiSeries.setData(rsiData);

            // Reference lines for RSI (70/30)
            if (rsiData.length > 0) {
                const rsiTimes = rsiData.map(d => d.time);
                rsiUpperLine.setData(rsiTimes.map(t => ({ time: t, value: 70 })));
                rsiLowerLine.setData(rsiTimes.map(t => ({ time: t, value: 30 })));
            }

            candlestickChart.timeScale().fitContent();
            candlestickChart.priceScale('right').applyOptions({ autoScale: true });
            rsiChart.timeScale().fitContent();

            // Sync crosshair between charts
            syncCharts(candlestickChart, rsiChart);

            updateActiveStates(coin, days, null);
        } catch (err) {
            console.error('Error loading OHLC:', err);
            showChartMessage('candlestickChartContainer', 'Failed to load chart data');
        }
    }

    async function loadOHLCInterval(coin, interval, limit = 100) {
        currentCoin = coin;
        currentInterval = interval;
        currentDays = null;  // reset days mode

        try {
            const resp = await fetch(`/api/market/${coin}/ohlc-interval?interval=${interval}&limit=${limit}`);
            if (!resp.ok) throw new Error('No OHLC data');
            const data = await resp.json();

            if (!data || data.length === 0) {
                showChartMessage('candlestickChartContainer', 'No OHLC data available');
                return;
            }

            const seen = new Set();
            const cleanData = data.filter(d => {
                if (seen.has(d.time)) return false;
                seen.add(d.time);
                return true;
            }).sort((a, b) => a.time - b.time);

            // Apply dynamic precision based on price level
            const lastPrice = cleanData[cleanData.length - 1].close;
            applyPriceFormat(lastPrice);

            candlestickSeries.setData(cleanData);
            lastOhlcData = cleanData;
            sma7Series.setData(computeSMA(cleanData, 7));
            sma21Series.setData(computeSMA(cleanData, 21));

            const bb = computeBB(cleanData, Math.min(20, cleanData.length));
            bbUpperSeries.setData(bb.upper);
            bbLowerSeries.setData(bb.lower);

            const rsiData = computeRSI(cleanData);
            rsiSeries.setData(rsiData);

            if (rsiData.length > 0) {
                const rsiTimes = rsiData.map(d => d.time);
                rsiUpperLine.setData(rsiTimes.map(t => ({ time: t, value: 70 })));
                rsiLowerLine.setData(rsiTimes.map(t => ({ time: t, value: 30 })));
            }

            candlestickChart.timeScale().fitContent();
            candlestickChart.priceScale('right').applyOptions({ autoScale: true });
            rsiChart.timeScale().fitContent();
            syncCharts(candlestickChart, rsiChart);

            updateActiveStates(coin, null, interval);
        } catch (err) {
            console.error('Error loading OHLC interval:', err);
            showChartMessage('candlestickChartContainer', 'Failed to load chart data');
        }
    }

    async function loadEquity(agentId) {
        if (!equityChart) return;

        try {
            const resp = await fetch(`/api/agents/${agentId}/equity`);
            if (!resp.ok) throw new Error('No equity data');
            const data = await resp.json();

            if (!data || data.length === 0) {
                showChartMessage('equityChartContainer', 'No equity data yet — agent needs to run a few cycles');
                return;
            }

            // Deduplicate
            const seen = new Set();
            const cleanData = data.filter(d => {
                if (seen.has(d.time)) return false;
                seen.add(d.time);
                return true;
            }).sort((a, b) => a.time - b.time);

            equitySeries.setData(cleanData);
            equityChart.timeScale().fitContent();
        } catch (err) {
            console.error('Error loading equity:', err);
        }
    }

    // ── Utilities ────────────────────────────────────────────────────────

    function syncCharts(chart1, chart2) {
        chart1.timeScale().subscribeVisibleLogicalRangeChange(range => {
            if (range) chart2.timeScale().setVisibleLogicalRange(range);
        });
        chart2.timeScale().subscribeVisibleLogicalRangeChange(range => {
            if (range) chart1.timeScale().setVisibleLogicalRange(range);
        });
    }

    function showChartMessage(containerId, msg) {
        const el = document.getElementById(containerId);
        const c = _currentTheme === 'dark' ? '#6e7681' : '#999';
        if (el) el.innerHTML = `<div style="display:flex;align-items:center;justify-content:center;height:100%;color:${c};font-style:italic;">${msg}</div>`;
    }

    // CoinGecko ID → display symbol for chart title
    const COIN_SYMBOLS = {
        'bitcoin': 'BTC', 'ethereum': 'ETH', 'binancecoin': 'BNB',
        'cardano': 'ADA', 'solana': 'SOL', 'ripple': 'XRP',
        'polkadot': 'DOT', 'dogecoin': 'DOGE', 'avalanche-2': 'AVAX',
        'chainlink': 'LINK', 'near': 'NEAR', 'sui': 'SUI',
        'pepe': 'PEPE', 'aptos': 'APT', 'arbitrum': 'ARB',
        'filecoin': 'FIL', 'render-token': 'RENDER',
        'injective-protocol': 'INJ', 'fetch-ai': 'FET',
        'bonk': 'BONK', 'floki': 'FLOKI',
        'sei-network': 'SEI', 'wif': 'WIF',
    };

    function updateActiveStates(coin, days, interval) {
        // Update pair title
        const titleEl = document.getElementById('chartPairTitle');
        if (titleEl) {
            const symbol = COIN_SYMBOLS[coin] || coin.toUpperCase();
            const tf = interval || (days ? days + 'D' : '');
            titleEl.textContent = symbol + 'USDT' + (tf ? ' · ' + tf : '');
        }
        document.querySelectorAll('.tf-btn').forEach(btn => {
            if (interval) {
                btn.classList.toggle('active', btn.dataset.interval === interval);
            } else {
                btn.classList.toggle('active', btn.dataset.days && parseInt(btn.dataset.days) === days);
            }
        });
    }

    // ── Position Overlay ─────────────────────────────────────────────────

    function clearPositionOverlay() {
        if (candlestickSeries) {
            if (_entryLine) { try { candlestickSeries.removePriceLine(_entryLine); } catch(e){} _entryLine = null; }
            if (_slLine)    { try { candlestickSeries.removePriceLine(_slLine);    } catch(e){} _slLine = null; }
            if (_tpLine)    { try { candlestickSeries.removePriceLine(_tpLine);    } catch(e){} _tpLine = null; }
        }
        _posOverlay = null;
    }

    function _fmtPriceShort(price) {
        if (price >= 1000) return price.toFixed(2);
        if (price >= 100)  return price.toFixed(2);
        if (price >= 10)   return price.toFixed(3);
        if (price >= 1)    return price.toFixed(4);
        if (price >= 0.01) return price.toFixed(5);
        return price.toFixed(6);
    }

    function setPositionOverlay(pos) {
        clearPositionOverlay();
        if (!pos || !candlestickSeries) return;

        const entry = pos.entry;
        const sl = pos.sl;
        const tp = pos.tp;
        const isLong = pos.isLong;

        _posOverlay = pos;

        // Entry line (blue) — label includes PnL
        if (entry > 0) {
            _entryLine = candlestickSeries.createPriceLine({
                price: entry,
                color: '#2196F3',
                lineWidth: 2,
                lineStyle: LightweightCharts.LineStyle.Solid,
                axisLabelVisible: true,
                title: `Entry $${_fmtPriceShort(entry)}`,
            });
        }

        // Stop Loss line (red)
        if (sl > 0) {
            _slLine = candlestickSeries.createPriceLine({
                price: sl,
                color: '#f44336',
                lineWidth: 1,
                lineStyle: LightweightCharts.LineStyle.Dashed,
                axisLabelVisible: true,
                title: `SL $${_fmtPriceShort(sl)}`,
            });
        }

        // Take Profit line (green)
        if (tp > 0) {
            _tpLine = candlestickSeries.createPriceLine({
                price: tp,
                color: '#4caf50',
                lineWidth: 1,
                lineStyle: LightweightCharts.LineStyle.Dashed,
                axisLabelVisible: true,
                title: `TP $${_fmtPriceShort(tp)}`,
            });
        }
    }

    function updatePositionPnL(livePrice) {
        if (!_posOverlay || !_entryLine || !livePrice) return;
        const { entry, isLong, amount, margin } = _posOverlay;
        const diff = isLong ? (livePrice - entry) : (entry - livePrice);
        const pnl = diff * amount;
        const pnlPct = margin > 0 ? (pnl / margin) * 100 : 0;
        const sign = pnl >= 0 ? '+' : '';
        _entryLine.applyOptions({
            title: `Entry $${_fmtPriceShort(entry)} | ${sign}$${pnl.toFixed(2)} (${sign}${pnlPct.toFixed(1)}%)`,
        });
    }

    // ── Public API ───────────────────────────────────────────────────────

    return {
        init(candleContainer, rsiContainer, equityContainer) {
            initCandlestickChart(candleContainer);
            initRSIChart(rsiContainer);
            initEquityChart(equityContainer);
        },
        loadOHLC,
        loadOHLCInterval,
        loadEquity,
        getCurrentCoin() { return currentCoin; },
        getCurrentDays() { return currentDays; },
        getCurrentInterval() { return currentInterval; },
        /**
         * Update the last candle's close (and high/low) with a fresh price.
         * Called every 15s from the price-refresh cycle so the chart stays
         * in sync with the Market Prices section.
         */
        updateLastPrice(coin, price) {
            if (!candlestickSeries || coin !== currentCoin || !price) return;
            if (lastOhlcData.length === 0) return;

            const lastBar = lastOhlcData[lastOhlcData.length - 1];

            const updated = {
                time: lastBar.time,
                open: lastBar.open,
                high: Math.max(lastBar.high, price),
                low: Math.min(lastBar.low, price),
                close: price,
            };

            // Update in-memory reference too
            lastOhlcData[lastOhlcData.length - 1] = updated;
            candlestickSeries.update(updated);
        },
        // Position overlay API
        setPositionOverlay,
        clearPositionOverlay,
        updatePositionPnL,

        // Theme API
        applyTheme(theme) {
            _currentTheme = (theme === 'dark') ? 'dark' : 'light';
            if (candlestickChart) {
                candlestickChart.applyOptions(chartLayoutOptions(380));
            }
            if (rsiChart) {
                rsiChart.applyOptions(chartLayoutOptions(150));
            }
            if (equityChart) {
                equityChart.applyOptions(chartLayoutOptions(200));
            }
        },
    };
})();
