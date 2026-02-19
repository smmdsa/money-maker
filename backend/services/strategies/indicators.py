"""
Technical Indicator Library.
Stateless computations used by all strategies.
"""
import math
from typing import Dict, List, Optional


class Indicators:
    """Stateless library of technical indicator computations."""

    # ── Series helpers ──────────────────────────────────────────────────

    @staticmethod
    def ema_series(prices: List[float], period: int) -> List[float]:
        """Full EMA series. First value is SMA seed."""
        if len(prices) < period:
            return []
        k = 2.0 / (period + 1)
        emas = [sum(prices[:period]) / period]
        for price in prices[period:]:
            emas.append(price * k + emas[-1] * (1 - k))
        return emas

    @staticmethod
    def sma_series(prices: List[float], period: int) -> List[float]:
        if len(prices) < period:
            return []
        return [sum(prices[i - period + 1:i + 1]) / period
                for i in range(period - 1, len(prices))]

    @staticmethod
    def rsi_series(prices: List[float], period: int = 14) -> List[float]:
        """Wilder-smoothed RSI series."""
        if len(prices) < period + 1:
            return []
        deltas = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
        gains = [max(d, 0) for d in deltas]
        losses = [max(-d, 0) for d in deltas]

        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period

        rsis = []
        if avg_loss == 0:
            rsis.append(100.0)
        else:
            rsis.append(100 - 100 / (1 + avg_gain / avg_loss))

        for i in range(period, len(deltas)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period
            if avg_loss == 0:
                rsis.append(100.0)
            else:
                rsis.append(100 - 100 / (1 + avg_gain / avg_loss))
        return rsis

    # ── Point-value indicators ──────────────────────────────────────────

    @staticmethod
    def rsi(prices: List[float], period: int = 14) -> Optional[float]:
        series = Indicators.rsi_series(prices, period)
        return series[-1] if series else None

    @staticmethod
    def ema(prices: List[float], period: int) -> Optional[float]:
        series = Indicators.ema_series(prices, period)
        return series[-1] if series else None

    @staticmethod
    def sma(prices: List[float], period: int) -> Optional[float]:
        if len(prices) < period:
            return None
        return sum(prices[-period:]) / period

    # ── MACD ────────────────────────────────────────────────────────────

    @staticmethod
    def macd(prices: List[float], fast: int = 12, slow: int = 26,
             signal_period: int = 9) -> Optional[Dict]:
        """MACD with proper signal line (EMA-9 of MACD series)."""
        if len(prices) < slow + signal_period:
            return None

        ema_fast = Indicators.ema_series(prices, fast)
        ema_slow = Indicators.ema_series(prices, slow)

        offset = slow - fast
        if offset > len(ema_fast):
            return None

        macd_series = [ema_fast[i + offset] - ema_slow[i]
                       for i in range(len(ema_slow))]

        if len(macd_series) < signal_period:
            return None

        signal_series = Indicators.ema_series(macd_series, signal_period)
        if not signal_series:
            return None

        macd_val = macd_series[-1]
        signal_val = signal_series[-1]
        histogram = macd_val - signal_val

        prev_macd = macd_series[-2] if len(macd_series) >= 2 else macd_val
        prev_signal = signal_series[-2] if len(signal_series) >= 2 else signal_val
        prev_histogram = prev_macd - prev_signal

        return {
            "macd": macd_val,
            "signal": signal_val,
            "histogram": histogram,
            "crossover": ("bullish" if prev_macd <= prev_signal and macd_val > signal_val
                          else "bearish" if prev_macd >= prev_signal and macd_val < signal_val
                          else "none"),
            "prev_histogram": prev_histogram,
        }

    # ── Bollinger Bands ─────────────────────────────────────────────────

    @staticmethod
    def bollinger_bands(prices: List[float], period: int = 20,
                        std_mult: float = 2.0) -> Optional[Dict]:
        if len(prices) < period:
            return None
        recent = prices[-period:]
        sma = sum(recent) / period
        std = math.sqrt(sum((p - sma) ** 2 for p in recent) / period)
        upper = sma + std_mult * std
        lower = sma - std_mult * std
        width_pct = ((upper - lower) / sma * 100) if sma > 0 else 0

        current = prices[-1]
        pct_b = (current - lower) / (upper - lower) if (upper - lower) > 0 else 0.5

        return {
            "upper": upper,
            "middle": sma,
            "lower": lower,
            "width_pct": width_pct,
            "pct_b": pct_b,
            "squeeze": width_pct < 5,
        }

    # ── ATR ─────────────────────────────────────────────────────────────

    @staticmethod
    def atr(ohlc: List[Dict], period: int = 14) -> Optional[float]:
        """Average True Range — Wilder smoothing."""
        if len(ohlc) < period + 1:
            return None
        trs = []
        for i in range(1, len(ohlc)):
            h = ohlc[i]["high"]
            l = ohlc[i]["low"]
            pc = ohlc[i - 1]["close"]
            trs.append(max(h - l, abs(h - pc), abs(l - pc)))

        atr_val = sum(trs[:period]) / period
        for tr in trs[period:]:
            atr_val = (atr_val * (period - 1) + tr) / period
        return atr_val

    @staticmethod
    def atr_pct(ohlc: List[Dict], period: int = 14) -> Optional[float]:
        """ATR as percentage of current price."""
        a = Indicators.atr(ohlc, period)
        if a is None or not ohlc:
            return None
        current = ohlc[-1]["close"]
        return (a / current * 100) if current > 0 else None

    # ── ADX ─────────────────────────────────────────────────────────────

    @staticmethod
    def adx(ohlc: List[Dict], period: int = 14) -> Optional[Dict]:
        """ADX with +DI / -DI. Requires 2*period + 1 bars minimum."""
        if len(ohlc) < 2 * period + 1:
            return None

        plus_dms, minus_dms, trs = [], [], []

        for i in range(1, len(ohlc)):
            h, l = ohlc[i]["high"], ohlc[i]["low"]
            ph, pl = ohlc[i - 1]["high"], ohlc[i - 1]["low"]
            pc = ohlc[i - 1]["close"]

            up = h - ph
            down = pl - l
            plus_dms.append(up if up > down and up > 0 else 0)
            minus_dms.append(down if down > up and down > 0 else 0)
            trs.append(max(h - l, abs(h - pc), abs(l - pc)))

        sm_plus = sum(plus_dms[:period])
        sm_minus = sum(minus_dms[:period])
        sm_tr = sum(trs[:period])

        dx_values = []
        for i in range(period, len(trs)):
            sm_plus = sm_plus - sm_plus / period + plus_dms[i]
            sm_minus = sm_minus - sm_minus / period + minus_dms[i]
            sm_tr = sm_tr - sm_tr / period + trs[i]

            plus_di = (100 * sm_plus / sm_tr) if sm_tr > 0 else 0
            minus_di = (100 * sm_minus / sm_tr) if sm_tr > 0 else 0
            di_sum = plus_di + minus_di
            dx = (abs(plus_di - minus_di) / di_sum * 100) if di_sum > 0 else 0
            dx_values.append((dx, plus_di, minus_di))

        if len(dx_values) < period:
            return None

        adx_val = sum(d[0] for d in dx_values[:period]) / period
        for dx, _, _ in dx_values[period:]:
            adx_val = (adx_val * (period - 1) + dx) / period

        return {
            "adx": adx_val,
            "plus_di": dx_values[-1][1],
            "minus_di": dx_values[-1][2],
            "trending": adx_val > 25,
            "strong_trend": adx_val > 40,
        }

    # ── Stochastic RSI ──────────────────────────────────────────────────

    @staticmethod
    def stochastic_rsi(prices: List[float], rsi_period: int = 14,
                       stoch_period: int = 14, k_smooth: int = 3) -> Optional[Dict]:
        rsi_vals = Indicators.rsi_series(prices, rsi_period)
        if len(rsi_vals) < stoch_period:
            return None

        stoch_rsi_vals = []
        for i in range(stoch_period - 1, len(rsi_vals)):
            window = rsi_vals[i - stoch_period + 1:i + 1]
            min_r, max_r = min(window), max(window)
            stoch_rsi_vals.append(
                ((rsi_vals[i] - min_r) / (max_r - min_r) * 100)
                if max_r != min_r else 50.0
            )

        k = (sum(stoch_rsi_vals[-k_smooth:]) / k_smooth
             if len(stoch_rsi_vals) >= k_smooth else stoch_rsi_vals[-1])
        prev_k = (sum(stoch_rsi_vals[-k_smooth - 1:-1]) / k_smooth
                  if len(stoch_rsi_vals) >= k_smooth + 1 else k)

        return {"k": k, "d": prev_k, "oversold": k < 20, "overbought": k > 80}

    # ── Volume Analysis ─────────────────────────────────────────────────

    @staticmethod
    def volume_analysis(ohlc: List[Dict]) -> Optional[Dict]:
        """Analyze volume trend and detect surges."""
        volumes = [bar.get("volume", 0) for bar in ohlc]
        if not any(v > 0 for v in volumes):
            return None

        recent_5 = volumes[-5:] if len(volumes) >= 5 else volumes
        older_10 = (volumes[-15:-5] if len(volumes) >= 15
                    else volumes[:max(len(volumes) - 5, 1)])

        avg_recent = sum(recent_5) / len(recent_5) if recent_5 else 1
        avg_older = sum(older_10) / len(older_10) if older_10 else 1

        ratio = avg_recent / avg_older if avg_older > 0 else 1.0
        last_vol = volumes[-1] if volumes else 0
        spike = last_vol > avg_older * 2.0 if avg_older > 0 else False

        return {
            "ratio": ratio,
            "increasing": ratio > 1.3,
            "spike": spike,
            "avg_volume": avg_recent,
        }

    # ── Composite indicator set ─────────────────────────────────────────

    @staticmethod
    def compute_all(close_prices: List[float], ohlc: List[Dict],
                    current_price: float) -> Dict:
        """Compute all indicators at once and return a flat dict."""
        result: Dict = {"current_price": current_price}

        result["rsi"] = Indicators.rsi(close_prices)
        result["macd"] = Indicators.macd(close_prices)
        result["bb"] = Indicators.bollinger_bands(close_prices)
        result["atr"] = Indicators.atr(ohlc)
        result["atr_pct"] = Indicators.atr_pct(ohlc)
        result["adx"] = Indicators.adx(ohlc)
        result["stoch_rsi"] = Indicators.stochastic_rsi(close_prices)
        result["volume"] = Indicators.volume_analysis(ohlc)

        result["ema_9"] = Indicators.ema(close_prices, 9)
        result["ema_21"] = Indicators.ema(close_prices, 21)
        result["ema_55"] = Indicators.ema(close_prices, 55)

        result["sma_7"] = Indicators.sma(close_prices, 7)
        result["sma_21"] = Indicators.sma(close_prices, 21)
        result["sma_50"] = Indicators.sma(close_prices, 50)

        avg_7 = result["sma_7"]
        if avg_7 and avg_7 > 0:
            result["momentum"] = (current_price - avg_7) / avg_7 * 100
        else:
            result["momentum"] = 0.0

        return result
