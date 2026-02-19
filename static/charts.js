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

    let lastOhlcData = [];   // Keep reference to last loaded OHLC data

    const CHART_BG = '#ffffff';
    const GRID_COLOR = '#f0f0f0';
    const CANDLE_UP = '#26a69a';
    const CANDLE_DOWN = '#ef5350';

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

    function chartLayoutOptions(height) {
        return {
            height: height,
            layout: { background: { color: CHART_BG }, textColor: '#666' },
            grid: {
                vertLines: { color: GRID_COLOR },
                horzLines: { color: GRID_COLOR },
            },
            crosshair: { mode: 0 },
            rightPriceScale: { borderColor: '#e0e0e0' },
            timeScale: {
                borderColor: '#e0e0e0',
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
            rsiChart.timeScale().fitContent();

            // Sync crosshair between charts
            syncCharts(candlestickChart, rsiChart);

            updateActiveStates(coin, days);
        } catch (err) {
            console.error('Error loading OHLC:', err);
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
        if (el) el.innerHTML = `<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#999;font-style:italic;">${msg}</div>`;
    }

    function updateActiveStates(coin, days) {
        document.querySelectorAll('.coin-selector-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.coin === coin);
        });
        document.querySelectorAll('.tf-btn').forEach(btn => {
            btn.classList.toggle('active', parseInt(btn.dataset.days) === days);
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
        loadEquity,
        getCurrentCoin() { return currentCoin; },
        getCurrentDays() { return currentDays; },
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
        },    };
})();
