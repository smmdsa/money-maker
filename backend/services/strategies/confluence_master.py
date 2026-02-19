"""
Confluence Master Strategy — Institutional multi-factor approach.

Only trades when 5+ indicators align. Higher leverage for
overwhelming confluence. Fewest trades, highest win rate.
"""
from typing import Dict

from backend.services.strategies.base import BaseStrategy
from backend.services.strategies.models import STRATEGIES, Signal


class ConfluenceMasterStrategy(BaseStrategy):

    def evaluate(self, ind: Dict, price: float,
                 has_long: bool = False, has_short: bool = False,
                 entry_price: float = 0.0) -> Signal:

        reasons = []
        long_signals = 0
        short_signals = 0
        total_checks = 0
        cfg = STRATEGIES["confluence_master"]

        # 1. RSI
        rsi = ind.get("rsi")
        if rsi is not None:
            total_checks += 1
            if rsi < 35:
                long_signals += 1
                reasons.append(f"\u2713 RSI bullish ({rsi:.0f})")
            elif rsi > 65:
                short_signals += 1
                reasons.append(f"\u2713 RSI bearish ({rsi:.0f})")
            else:
                reasons.append(f"\u25cb RSI neutral ({rsi:.0f})")

        # 2. MACD
        macd = ind.get("macd")
        if macd:
            total_checks += 1
            if macd["histogram"] > 0:
                long_signals += 1
                reasons.append("\u2713 MACD bullish")
            else:
                short_signals += 1
                reasons.append("\u2713 MACD bearish")
            if macd["crossover"] == "bullish":
                long_signals += 1
                reasons.append("\u2713 MACD bullish crossover")
            elif macd["crossover"] == "bearish":
                short_signals += 1
                reasons.append("\u2713 MACD bearish crossover")

        # 3. Bollinger Bands
        bb = ind.get("bb")
        if bb:
            total_checks += 1
            if bb["pct_b"] < 0.2:
                long_signals += 1
                reasons.append(f"\u2713 BB oversold (%B={bb['pct_b']:.2f})")
            elif bb["pct_b"] > 0.8:
                short_signals += 1
                reasons.append(f"\u2713 BB overbought (%B={bb['pct_b']:.2f})")
            else:
                reasons.append(f"\u25cb BB neutral (%B={bb['pct_b']:.2f})")

        # 4. EMA alignment
        ema9 = ind.get("ema_9")
        ema21 = ind.get("ema_21")
        if ema9 and ema21:
            total_checks += 1
            if ema9 > ema21:
                long_signals += 1
                reasons.append("\u2713 EMA bullish alignment")
            else:
                short_signals += 1
                reasons.append("\u2713 EMA bearish alignment")

        # 5. ADX trend strength
        adx = ind.get("adx")
        if adx:
            total_checks += 1
            if adx["trending"]:
                if adx["plus_di"] > adx["minus_di"]:
                    long_signals += 1
                    reasons.append(f"\u2713 ADX uptrend ({adx['adx']:.0f})")
                else:
                    short_signals += 1
                    reasons.append(f"\u2713 ADX downtrend ({adx['adx']:.0f})")
            else:
                reasons.append(f"\u25cb ADX no trend ({adx['adx']:.0f})")

        # 6. Stochastic RSI
        stoch = ind.get("stoch_rsi")
        if stoch:
            total_checks += 1
            if stoch["oversold"]:
                long_signals += 1
                reasons.append(f"\u2713 StochRSI oversold ({stoch['k']:.0f})")
            elif stoch["overbought"]:
                short_signals += 1
                reasons.append(f"\u2713 StochRSI overbought ({stoch['k']:.0f})")
            else:
                reasons.append(f"\u25cb StochRSI neutral ({stoch['k']:.0f})")

        # 7. Volume
        vol = ind.get("volume")
        if vol:
            total_checks += 1
            if vol["spike"] or vol["increasing"]:
                reasons.append("\u2713 Volume confirms")
                if long_signals > short_signals:
                    long_signals += 1
                elif short_signals > long_signals:
                    short_signals += 1

        # 8. Momentum
        mom = ind.get("momentum", 0)
        total_checks += 1
        if mom > 2:
            long_signals += 1
            reasons.append(f"\u2713 Momentum bullish (+{mom:.1f}%)")
        elif mom < -2:
            short_signals += 1
            reasons.append(f"\u2713 Momentum bearish ({mom:.1f}%)")
        else:
            reasons.append(f"\u25cb Momentum neutral ({mom:.1f}%)")

        # Confluence requires at least 5 signals aligned
        max_signals = max(long_signals, short_signals)
        dominant = "long" if long_signals > short_signals else "short"
        confidence = max_signals / max(total_checks, 1)

        if max_signals < 5:
            return Signal(
                "neutral", confidence, cfg.default_leverage,
                3.0, 8.0,
                f"HOLD \u2014 Insufficient confluence: {long_signals}L/{short_signals}S "
                f"out of {total_checks} checks. Need 5+. | " + "; ".join(reasons),
                {"long": long_signals, "short": short_signals, "checks": total_checks},
                trail_pct=0.0,
            )

        # Higher leverage for stronger confluence
        leverage = cfg.default_leverage
        if max_signals >= 7:
            leverage = min(cfg.max_leverage, 10)
        elif max_signals >= 6:
            leverage = min(cfg.max_leverage, 7)

        atr_pct = ind.get("atr_pct") or 3.0
        sl = max(atr_pct * 2, 3.0)
        tp = max(atr_pct * 5, 10.0)
        trail = max(atr_pct * cfg.trail_atr_mult, sl)

        direction = dominant
        reasoning = (
            f"{'LONG' if direction == 'long' else 'SHORT'} \u2014 "
            f"Confluence {max_signals}/{total_checks} | " + "; ".join(reasons)
        )

        if has_long and direction == "short":
            direction = "close_long"
            reasoning = (f"CLOSE LONG \u2014 Confluence shifted bearish "
                         f"({short_signals}/{total_checks}) | " + "; ".join(reasons))
        elif has_short and direction == "long":
            direction = "close_short"
            reasoning = (f"CLOSE SHORT \u2014 Confluence shifted bullish "
                         f"({long_signals}/{total_checks}) | " + "; ".join(reasons))

        return Signal(
            direction, confidence, leverage, sl, tp, reasoning,
            {"long": long_signals, "short": short_signals, "checks": total_checks},
            trail_pct=trail,
        )
