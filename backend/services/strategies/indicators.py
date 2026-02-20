"""
Technical Indicator Library.
Stateless computations used by all strategies.

SCALP_PROFILES provides timeframe-specific indicator periods
for scalper variants (1m, 3m, 5m, 15m, 1h).
"""
import math
from typing import Dict, List, Optional


# ── Scalper indicator profiles (timeframe-optimized periods) ─────────────

SCALP_PROFILES: Dict[str, Dict] = {
    "scalper_1m": {
        "rsi_period": 7,
        "macd_fast": 5, "macd_slow": 13, "macd_signal": 4,
        "bb_period": 10, "bb_std": 1.8,
        "atr_period": 10, "adx_period": 10,
        "stoch_rsi_period": 7, "stoch_k_smooth": 3,
        "ema_short": 5, "ema_mid": 13, "ema_long": 21,
        "sma_fast": 5, "sma_mid": 13, "sma_slow": 21,
        "vol_recent": 3, "vol_older": 8,
    },
    "scalper_3m": {
        "rsi_period": 9,
        "macd_fast": 8, "macd_slow": 17, "macd_signal": 6,
        "bb_period": 14, "bb_std": 2.0,
        "atr_period": 10, "adx_period": 10,
        "stoch_rsi_period": 9, "stoch_k_smooth": 3,
        "ema_short": 7, "ema_mid": 17, "ema_long": 34,
        "sma_fast": 5, "sma_mid": 14, "sma_slow": 30,
        "vol_recent": 4, "vol_older": 10,
    },
    "scalper_5m": {
        "rsi_period": 10,
        "macd_fast": 8, "macd_slow": 21, "macd_signal": 7,
        "bb_period": 16, "bb_std": 2.0,
        "atr_period": 12, "adx_period": 12,
        "stoch_rsi_period": 10, "stoch_k_smooth": 3,
        "ema_short": 8, "ema_mid": 21, "ema_long": 50,
        "sma_fast": 7, "sma_mid": 21, "sma_slow": 50,
        "vol_recent": 5, "vol_older": 12,
    },
    "scalper_15m": {
        "rsi_period": 12,
        "macd_fast": 10, "macd_slow": 22, "macd_signal": 8,
        "bb_period": 18, "bb_std": 2.0,
        "atr_period": 14, "adx_period": 14,
        "stoch_rsi_period": 12, "stoch_k_smooth": 3,
        "ema_short": 9, "ema_mid": 21, "ema_long": 50,
        "sma_fast": 7, "sma_mid": 21, "sma_slow": 50,
        "vol_recent": 5, "vol_older": 15,
    },
    "scalper": {  # 1h
        "rsi_period": 14,
        "macd_fast": 12, "macd_slow": 26, "macd_signal": 9,
        "bb_period": 20, "bb_std": 2.0,
        "atr_period": 14, "adx_period": 14,
        "stoch_rsi_period": 14, "stoch_k_smooth": 3,
        "ema_short": 9, "ema_mid": 21, "ema_long": 55,
        "sma_fast": 7, "sma_mid": 21, "sma_slow": 50,
        "vol_recent": 5, "vol_older": 15,
    },
}


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

        # DI crossover detection
        cur_plus, cur_minus = dx_values[-1][1], dx_values[-1][2]
        prev_plus, prev_minus = dx_values[-2][1], dx_values[-2][2] if len(dx_values) >= 2 else (cur_plus, cur_minus)

        di_crossover = "none"
        if prev_plus <= prev_minus and cur_plus > cur_minus:
            di_crossover = "bullish"
        elif prev_plus >= prev_minus and cur_plus < cur_minus:
            di_crossover = "bearish"

        return {
            "adx": adx_val,
            "plus_di": cur_plus,
            "minus_di": cur_minus,
            "trending": adx_val > 25,
            "strong_trend": adx_val > 40,
            "di_crossover": di_crossover,
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
    def volume_analysis(ohlc: List[Dict], recent_n: int = 5,
                        older_n: int = 10) -> Optional[Dict]:
        """Analyze volume trend and detect surges."""
        volumes = [bar.get("volume", 0) for bar in ohlc]
        if not any(v > 0 for v in volumes):
            return None

        recent = volumes[-recent_n:] if len(volumes) >= recent_n else volumes
        if len(volumes) >= recent_n + older_n:
            older = volumes[-(recent_n + older_n):-recent_n]
        elif len(volumes) > recent_n:
            older = volumes[:-recent_n]
        else:
            older = volumes[:max(1, len(volumes) // 2)]

        avg_recent = sum(recent) / len(recent) if recent else 1
        avg_older = sum(older) / len(older) if older else 1

        ratio = avg_recent / avg_older if avg_older > 0 else 1.0
        last_vol = volumes[-1] if volumes else 0
        spike = last_vol > avg_older * 2.0 if avg_older > 0 else False

        return {
            "ratio": ratio,
            "increasing": ratio > 1.3,
            "spike": spike,
            "avg_volume": avg_recent,
        }

    # ── EMA Slope (rate of change) ──────────────────────────────────────

    @staticmethod
    def ema_slope(prices: List[float], period: int = 21,
                  lookback: int = 5) -> Optional[float]:
        """Slope of EMA as pct change over last `lookback` values.
        Positive = accelerating up, negative = accelerating down.
        """
        series = Indicators.ema_series(prices, period)
        if len(series) < lookback + 1:
            return None
        old = series[-lookback - 1]
        cur = series[-1]
        return ((cur - old) / old * 100) if old > 0 else 0.0

    # ── Composite indicator set ─────────────────────────────────────────

    @staticmethod
    def compute_all(close_prices: List[float], ohlc: List[Dict],
                    current_price: float,
                    profile: Optional[Dict] = None) -> Dict:
        """Compute all indicators at once and return a flat dict.

        If *profile* is given (e.g. from SCALP_PROFILES), its values
        override the default indicator periods.  Backward-compatible:
        when called without a profile, behaviour is identical to before.
        """
        p = profile or {}
        result: Dict = {"current_price": current_price}

        # ── Core oscillators ────────────────────────
        rsi_period = p.get("rsi_period", 14)
        result["rsi"] = Indicators.rsi(close_prices, rsi_period)

        result["macd"] = Indicators.macd(
            close_prices,
            p.get("macd_fast", 12),
            p.get("macd_slow", 26),
            p.get("macd_signal", 9),
        )

        result["bb"] = Indicators.bollinger_bands(
            close_prices,
            p.get("bb_period", 20),
            p.get("bb_std", 2.0),
        )

        atr_period = p.get("atr_period", 14)
        result["atr"] = Indicators.atr(ohlc, atr_period)
        result["atr_pct"] = Indicators.atr_pct(ohlc, atr_period)

        adx_period = p.get("adx_period", 14)
        result["adx"] = Indicators.adx(ohlc, adx_period)

        stoch_period = p.get("stoch_rsi_period", 14)
        stoch_k = p.get("stoch_k_smooth", 3)
        result["stoch_rsi"] = Indicators.stochastic_rsi(
            close_prices, stoch_period, stoch_period, stoch_k,
        )

        result["volume"] = Indicators.volume_analysis(
            ohlc,
            p.get("vol_recent", 5),
            p.get("vol_older", 10),
        )

        # ── Moving averages ─────────────────────────
        ema_short = p.get("ema_short", 9)
        ema_mid = p.get("ema_mid", 21)
        ema_long = p.get("ema_long", 55)

        result["ema_9"] = Indicators.ema(close_prices, ema_short)
        result["ema_21"] = Indicators.ema(close_prices, ema_mid)
        result["ema_55"] = Indicators.ema(close_prices, ema_long)

        sma_fast = p.get("sma_fast", 7)
        sma_mid_p = p.get("sma_mid", 21)
        sma_slow = p.get("sma_slow", 50)

        result["sma_7"] = Indicators.sma(close_prices, sma_fast)
        result["sma_21"] = Indicators.sma(close_prices, sma_mid_p)
        result["sma_50"] = Indicators.sma(close_prices, sma_slow)

        # EMA slopes (trend velocity)
        result["ema21_slope"] = Indicators.ema_slope(close_prices, ema_mid, 5)
        result["ema55_slope"] = Indicators.ema_slope(close_prices, ema_long, 5)

        avg_fast = result["sma_7"]
        if avg_fast and avg_fast > 0:
            result["momentum"] = (current_price - avg_fast) / avg_fast * 100
        else:
            result["momentum"] = 0.0

        return result
