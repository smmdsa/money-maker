"""
Base strategy class with the shared _build_signal method.
All concrete strategies inherit from this.
"""
from typing import Dict, List

from backend.services.strategies.models import Signal, StrategyConfig


class BaseStrategy:
    """Abstract base for all trading strategies."""

    def evaluate(self, indicators: Dict, current_price: float,
                 has_long: bool = False, has_short: bool = False,
                 entry_price: float = 0.0) -> Signal:
        raise NotImplementedError

    # ── Shared signal builder ───────────────────────────────────────────

    def _build_signal(
        self,
        long_score: int,
        short_score: int,
        reasons: List[str],
        cfg: StrategyConfig,
        has_long: bool,
        has_short: bool,
        stop_loss_pct: float,
        take_profit_pct: float,
        entry_price: float,
        current_price: float,
        trail_pct: float = 0.0,
    ) -> Signal:
        """Convert raw scores into a Signal object."""
        max_score = max(long_score, short_score)
        min_score_to_act = 3
        confidence = min(max_score / 10.0, 0.95)
        reasoning_str = "; ".join(reasons) if reasons else "No clear signals"

        # Scale leverage with confidence
        leverage = cfg.default_leverage
        if confidence > 0.7:
            leverage = min(cfg.max_leverage, cfg.default_leverage + 2)
        elif confidence < 0.5:
            leverage = max(1, cfg.default_leverage - 1)

        def _sig(direction, conf, lev, reason, scores):
            return Signal(direction, conf, lev, stop_loss_pct, take_profit_pct,
                          reason, scores, trail_pct=trail_pct)

        # Check for position close signals first
        if has_long:
            if short_score >= min_score_to_act and short_score > long_score:
                return _sig(
                    "close_long", confidence, leverage,
                    f"CLOSE LONG \u2014 Bearish reversal: {reasoning_str}",
                    {"long": long_score, "short": short_score}
                )
            if entry_price > 0:
                pnl_pct = (current_price - entry_price) / entry_price * 100
                if pnl_pct <= -stop_loss_pct:
                    return _sig(
                        "close_long", 0.95, leverage,
                        f"CLOSE LONG \u2014 Stop-loss hit ({pnl_pct:.1f}%)",
                        {"pnl_pct": pnl_pct}
                    )
                if pnl_pct >= take_profit_pct:
                    return _sig(
                        "close_long", 0.90, leverage,
                        f"CLOSE LONG \u2014 Take-profit hit (+{pnl_pct:.1f}%)",
                        {"pnl_pct": pnl_pct}
                    )

        if has_short:
            if long_score >= min_score_to_act and long_score > short_score:
                return _sig(
                    "close_short", confidence, leverage,
                    f"CLOSE SHORT \u2014 Bullish reversal: {reasoning_str}",
                    {"long": long_score, "short": short_score}
                )
            if entry_price > 0:
                pnl_pct = (entry_price - current_price) / entry_price * 100
                if pnl_pct <= -stop_loss_pct:
                    return _sig(
                        "close_short", 0.95, leverage,
                        f"CLOSE SHORT \u2014 Stop-loss hit ({pnl_pct:.1f}%)",
                        {"pnl_pct": pnl_pct}
                    )
                if pnl_pct >= take_profit_pct:
                    return _sig(
                        "close_short", 0.90, leverage,
                        f"CLOSE SHORT \u2014 Take-profit hit (+{pnl_pct:.1f}%)",
                        {"pnl_pct": pnl_pct}
                    )

        # New position signals
        if long_score >= min_score_to_act and long_score > short_score and not has_long:
            if confidence >= cfg.min_confidence:
                return _sig(
                    "long", confidence, leverage,
                    f"LONG \u2014 {reasoning_str}",
                    {"long": long_score, "short": short_score}
                )

        if short_score >= min_score_to_act and short_score > long_score and not has_short:
            if confidence >= cfg.min_confidence:
                return _sig(
                    "short", confidence, leverage,
                    f"SHORT \u2014 {reasoning_str}",
                    {"long": long_score, "short": short_score}
                )

        return _sig(
            "neutral", confidence, leverage,
            f"HOLD \u2014 {reasoning_str} (L={long_score}/S={short_score})",
            {"long": long_score, "short": short_score}
        )
