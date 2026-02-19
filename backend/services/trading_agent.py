"""
AI Trading Agent — Futures-capable with configurable strategies
===============================================================
Supports LONG and SHORT positions with leverage.
Uses the StrategyEngine for signal generation and professional
risk-based position sizing.
"""
import logging
from typing import Dict, List, Optional
import random
from datetime import datetime
from sqlalchemy.orm import Session

from backend.models.database import TradingAgent, Portfolio, Trade, Decision, NewsEvent
from backend.services.market_data import MarketDataService
from backend.services.llm_service import LLMService
from backend.services.strategies import (
    StrategyEngine, Indicators, STRATEGIES,
    calculate_position_size, calculate_liquidation_price, Signal
)

logger = logging.getLogger(__name__)


class TradingAgentService:
    """AI Trading Agent with futures support and configurable strategies."""

    def __init__(self, market_service: MarketDataService, llm_service: LLMService = None):
        self.market_service = market_service
        self.strategy_engine = StrategyEngine()
        self.llm_service = llm_service

    # ── Main decision loop ────────────────────────────────────────────────

    def make_trading_decision(self, agent: TradingAgent, db: Session) -> Optional[Dict]:
        """
        Full decision cycle:
        1. Check existing positions (liquidation, stop-loss, take-profit)
        2. Scan all coins for the best new signal
        3. Execute if signal is strong enough
        """
        try:
            strategy_key = agent.strategy or "confluence_master"
            strategy_cfg = STRATEGIES.get(strategy_key)
            if not strategy_cfg:
                logger.warning(f"Unknown strategy {strategy_key}, using confluence_master")
                strategy_key = "confluence_master"
                strategy_cfg = STRATEGIES["confluence_master"]

            # Step 1: Check existing positions for stop-loss / take-profit / liquidation
            existing_positions = db.query(Portfolio).filter(
                Portfolio.agent_id == agent.id,
                Portfolio.amount > 0
            ).all()

            for pos in existing_positions:
                close_decision = self._check_position(agent, pos, strategy_key, db)
                if close_decision:
                    return close_decision

            # Step 2: If we haven't hit max positions, look for new signals
            open_count = len(existing_positions)
            if open_count >= strategy_cfg.max_positions:
                return {
                    "action": "hold",
                    "coin": "—",
                    "confidence": 0.0,
                    "reasoning": f"Max positions reached ({open_count}/{strategy_cfg.max_positions})",
                    "strategy": strategy_key,
                }

            # Step 3: Scan coins and pick the best signal
            best_signal, best_coin = self._scan_for_best_signal(
                agent, strategy_key, existing_positions, db
            )

            if best_signal and best_coin and best_signal.direction in ("long", "short"):
                if best_signal.confidence >= strategy_cfg.min_confidence:
                    # Enrich with LLM analysis before opening
                    llm_analysis = self._get_llm_analysis(
                        best_coin, best_signal, strategy_key, db
                    )
                    decision = self._open_position(
                        agent, best_coin, best_signal, strategy_key, db,
                        llm_analysis=llm_analysis,
                    )
                    return decision

            # No actionable signal
            coin_label = best_coin or "market"
            reasoning = best_signal.reasoning if best_signal else "No clear signals detected"
            self._log_decision(db, agent.id, coin_label, {
                "action": "hold",
                "reasoning": reasoning,
                "confidence": best_signal.confidence if best_signal else 0.0,
            }, {}, [], strategy_key)
            db.commit()

            return {
                "action": "hold",
                "coin": coin_label,
                "confidence": best_signal.confidence if best_signal else 0.0,
                "reasoning": reasoning,
                "strategy": strategy_key,
            }

        except Exception as e:
            logger.error(f"Error in trading decision for agent {agent.id}: {e}")
            return None

    # ── Position Checks (SL / TP / Liquidation) ───────────────────────────

    def _check_position(self, agent: TradingAgent, pos: Portfolio,
                        strategy_key: str, db: Session) -> Optional[Dict]:
        """Check an existing position for liquidation, stop-loss, or take-profit."""
        current_price = self.market_service.get_coin_price(pos.cryptocurrency)
        if not current_price or current_price <= 0:
            return None

        pos.current_price = current_price

        # 1. Liquidation check
        if pos.leverage > 1 and pos.liquidation_price > 0:
            liquidated = (
                (pos.position_type == "long" and current_price <= pos.liquidation_price) or
                (pos.position_type == "short" and current_price >= pos.liquidation_price)
            )
            if liquidated:
                return self._close_position(
                    agent, pos, current_price, db,
                    reason=f"LIQUIDATED at ${current_price:.2f} (liq price: ${pos.liquidation_price:.2f})",
                    force_loss=-pos.margin,
                    strategy_key=strategy_key,
                )

        # 2. Stop-loss check
        if pos.stop_loss_price > 0:
            sl_hit = (
                (pos.position_type == "long" and current_price <= pos.stop_loss_price) or
                (pos.position_type == "short" and current_price >= pos.stop_loss_price)
            )
            if sl_hit:
                return self._close_position(
                    agent, pos, current_price, db,
                    reason=f"Stop-loss hit at ${current_price:.2f} (SL: ${pos.stop_loss_price:.2f})",
                    strategy_key=strategy_key,
                )

        # 3. Take-profit check
        if pos.take_profit_price > 0:
            tp_hit = (
                (pos.position_type == "long" and current_price >= pos.take_profit_price) or
                (pos.position_type == "short" and current_price <= pos.take_profit_price)
            )
            if tp_hit:
                return self._close_position(
                    agent, pos, current_price, db,
                    reason=f"Take-profit hit at ${current_price:.2f} (TP: ${pos.take_profit_price:.2f})",
                    strategy_key=strategy_key,
                )

        # 4. Strategy-based close signal
        indicators = self._compute_indicators(pos.cryptocurrency)
        if indicators:
            signal = self.strategy_engine.evaluate(
                strategy_key, indicators, current_price,
                has_long=(pos.position_type == "long"),
                has_short=(pos.position_type == "short"),
                entry_price=pos.avg_buy_price,
            )
            if signal.direction in ("close_long", "close_short"):
                return self._close_position(
                    agent, pos, current_price, db,
                    reason=signal.reasoning,
                    strategy_key=strategy_key,
                )

        return None

    # ── Scan for Best Signal ──────────────────────────────────────────────

    def _scan_for_best_signal(
        self, agent: TradingAgent, strategy_key: str,
        existing_positions: List[Portfolio], db: Session
    ) -> tuple:
        """Scan all coins and return the best signal + coin."""
        existing_coins = {p.cryptocurrency for p in existing_positions}
        best_signal: Optional[Signal] = None
        best_coin: Optional[str] = None

        # Get market activity for prioritization
        all_market = self.market_service.get_all_market_data()
        coins_to_scan = []

        if all_market:
            scored = []
            for coin in all_market:
                coin_id = coin.get("id", "")
                if coin_id in existing_coins:
                    continue
                change = abs(coin.get("price_change_24h") or 0)
                scored.append((coin_id, change))
            scored.sort(key=lambda x: x[1], reverse=True)
            coins_to_scan = [c[0] for c in scored]
        else:
            coins_to_scan = [c for c in self.market_service.supported_coins
                           if c not in existing_coins]

        # Evaluate top coins
        for coin in coins_to_scan[:6]:
            indicators = self._compute_indicators(coin)
            if not indicators:
                continue

            current_price = indicators.get("current_price", 0)
            if current_price <= 0:
                continue

            signal = self.strategy_engine.evaluate(
                strategy_key, indicators, current_price,
                has_long=False, has_short=False, entry_price=0.0
            )

            # Factor in news sentiment
            sentiment = self._get_news_sentiment(coin, db)
            if sentiment != 0:
                self._adjust_signal_for_sentiment(signal, sentiment)

            if signal.direction in ("long", "short"):
                if best_signal is None or signal.confidence > best_signal.confidence:
                    best_signal = signal
                    best_coin = coin

        return best_signal, best_coin

    # ── Indicator Computation ─────────────────────────────────────────────

    def _compute_indicators(self, coin: str) -> Optional[Dict]:
        """Compute all technical indicators for a coin."""
        market_data = self.market_service.get_market_data(coin)
        if not market_data:
            return None

        current_price = market_data.get("current_price")
        if not current_price:
            return None

        # Get OHLC data (need at least 55+ bars for EMA-55)
        ohlc = self.market_service.get_ohlc(coin, days=90)
        if not ohlc or len(ohlc) < 15:
            ohlc = self.market_service.get_ohlc(coin, days=30)

        close_prices = [c["close"] for c in ohlc] if ohlc else []

        if len(close_prices) < 15:
            historical = self.market_service.get_historical_prices(coin, days=30)
            if historical:
                close_prices = [h["price"] for h in historical]

        if len(close_prices) < 15:
            return None

        # Compute all indicators
        indicators = Indicators.compute_all(close_prices, ohlc or [], current_price)

        # Add market context
        indicators["price_change_24h"] = market_data.get("price_change_24h", 0) or 0
        indicators["price_change_7d"] = market_data.get("price_change_7d", 0) or 0
        indicators["volume_24h"] = market_data.get("volume_24h", 0) or 0
        indicators["market_cap"] = market_data.get("market_cap", 0) or 0

        return indicators

    # ── LLM Analysis ────────────────────────────────────────────────────

    def _get_llm_analysis(self, coin: str, signal: Signal,
                          strategy_key: str, db: Session):
        """Get LLM-enriched analysis for a trade signal. Returns None if unavailable."""
        if not self.llm_service or not self.llm_service.is_available:
            return None

        try:
            # Gather news for LLM context
            recent_news = db.query(NewsEvent).filter(
                (NewsEvent.cryptocurrency == coin) |
                (NewsEvent.cryptocurrency.is_(None))
            ).order_by(NewsEvent.timestamp.desc()).limit(8).all()

            news_items = [{
                "title": n.title,
                "sentiment": n.sentiment,
                "impact_score": n.impact_score,
                "source": n.source,
            } for n in recent_news]

            # Gather indicators
            indicators = self._compute_indicators(coin) or {}

            strategy_cfg = STRATEGIES.get(strategy_key)
            strategy_name = strategy_cfg.name if strategy_cfg else strategy_key

            current_price = indicators.get("current_price", 0)

            return self.llm_service.analyze_trade(
                coin=coin,
                direction=signal.direction,
                confidence=signal.confidence,
                strategy_name=strategy_name,
                indicators=indicators,
                news_items=news_items,
                current_price=current_price,
                reasoning_technical=signal.reasoning,
            )
        except Exception as e:
            logger.warning(f"LLM analysis failed for {coin}: {e}")
            return None

    # ── News Sentiment ────────────────────────────────────────────────────

    def _get_news_sentiment(self, coin: str, db: Session) -> float:
        recent_news = db.query(NewsEvent).filter(
            NewsEvent.cryptocurrency == coin
        ).order_by(NewsEvent.timestamp.desc()).limit(5).all()

        if not recent_news:
            return 0.0

        return sum(n.impact_score for n in recent_news) / len(recent_news)

    def _adjust_signal_for_sentiment(self, signal: Signal, sentiment: float):
        if signal.direction == "long" and sentiment > 0.1:
            signal.confidence = min(signal.confidence + 0.05, 0.95)
            signal.reasoning += f"; Positive news (+{sentiment:.2f})"
        elif signal.direction == "long" and sentiment < -0.1:
            signal.confidence = max(signal.confidence - 0.05, 0.0)
            signal.reasoning += f"; ⚠ Negative news ({sentiment:.2f})"
        elif signal.direction == "short" and sentiment < -0.1:
            signal.confidence = min(signal.confidence + 0.05, 0.95)
            signal.reasoning += f"; Negative news confirms ({sentiment:.2f})"
        elif signal.direction == "short" and sentiment > 0.1:
            signal.confidence = max(signal.confidence - 0.05, 0.0)
            signal.reasoning += f"; ⚠ Positive news conflicts (+{sentiment:.2f})"

    # ── Open Position ─────────────────────────────────────────────────────

    def _open_position(
        self, agent: TradingAgent, coin: str,
        signal: Signal, strategy_key: str, db: Session,
        llm_analysis=None,
    ) -> Dict:
        """Open a LONG or SHORT futures position."""
        current_price = self.market_service.get_coin_price(coin) or 0
        if current_price <= 0:
            return {"action": "hold", "coin": coin, "confidence": 0,
                    "reasoning": "Price unavailable", "strategy": strategy_key}

        leverage = min(signal.leverage, agent.max_leverage)

        margin = calculate_position_size(
            agent.current_balance, strategy_key, leverage,
            signal.stop_loss_pct, current_price
        )

        if margin <= 0 or margin > agent.current_balance:
            return {"action": "hold", "coin": coin, "confidence": signal.confidence,
                    "reasoning": f"Insufficient margin (need ${margin:.2f}, have ${agent.current_balance:.2f})",
                    "strategy": strategy_key}

        position_value = margin * leverage
        amount_coins = position_value / current_price
        direction = signal.direction

        liq_price = calculate_liquidation_price(current_price, leverage, direction)

        if direction == "long":
            sl_price = current_price * (1 - signal.stop_loss_pct / 100)
            tp_price = current_price * (1 + signal.take_profit_pct / 100)
        else:
            sl_price = current_price * (1 + signal.stop_loss_pct / 100)
            tp_price = current_price * (1 - signal.take_profit_pct / 100)

        market_data = self.market_service.get_market_data(coin)
        symbol = (market_data.get("symbol", coin[:3]).upper()
                  if market_data else coin[:3].upper())

        agent.current_balance -= margin

        portfolio_item = Portfolio(
            agent_id=agent.id,
            cryptocurrency=coin,
            symbol=symbol,
            amount=amount_coins,
            avg_buy_price=current_price,
            current_price=current_price,
            position_type=direction,
            leverage=leverage,
            margin=margin,
            liquidation_price=liq_price,
            stop_loss_price=sl_price,
            take_profit_price=tp_price,
        )
        db.add(portfolio_item)

        trade = Trade(
            agent_id=agent.id,
            cryptocurrency=coin,
            symbol=symbol,
            trade_type=f"open_{direction}",
            amount=amount_coins,
            price=current_price,
            total_value=position_value,
            profit_loss=0,
            leverage=leverage,
            margin=margin,
        )
        db.add(trade)

        # Apply LLM confidence adjustment if available
        effective_confidence = signal.confidence
        llm_reasoning = None
        if llm_analysis:
            effective_confidence = max(0, min(0.95,
                signal.confidence + llm_analysis.sentiment_adjustment
            ))
            llm_reasoning = llm_analysis.reasoning
            if llm_analysis.risk_notes:
                llm_reasoning += f" ⚠ {llm_analysis.risk_notes}"
            if llm_analysis.news_summary:
                llm_reasoning += f" | News: {llm_analysis.news_summary}"
            if llm_analysis.market_context:
                llm_reasoning += f" | Market: {llm_analysis.market_context}"
            logger.info(
                f"Agent {agent.name}: LLM adj {signal.confidence:.2f} → "
                f"{effective_confidence:.2f} ({llm_analysis.sentiment_adjustment:+.2f})"
            )

        decision_id = self._log_decision(db, agent.id, coin, {
            "action": direction,
            "reasoning": signal.reasoning,
            "confidence": effective_confidence,
        }, {}, [], strategy_key,
            llm_reasoning=llm_reasoning,
            llm_sentiment_adj=llm_analysis.sentiment_adjustment if llm_analysis else 0.0,
        )

        trade.decision_id = decision_id
        db.commit()

        tag = "LONG" if direction == "long" else "SHORT"
        logger.info(
            f"Agent {agent.name}: {tag} {coin} — margin ${margin:.2f} "
            f"× {leverage}x = ${position_value:.2f} @ ${current_price:.2f} "
            f"(SL: ${sl_price:.2f} | TP: ${tp_price:.2f})"
        )

        return {
            "action": direction,
            "coin": coin,
            "confidence": effective_confidence,
            "reasoning": signal.reasoning,
            "llm_reasoning": llm_reasoning,
            "strategy": strategy_key,
            "leverage": leverage,
            "margin": margin,
            "position_value": position_value,
        }

    # ── Close Position ────────────────────────────────────────────────────

    def _close_position(
        self, agent: TradingAgent, pos: Portfolio,
        current_price: float, db: Session,
        reason: str = "", force_loss: Optional[float] = None,
        strategy_key: str = ""
    ) -> Dict:
        """Close an existing LONG or SHORT position."""
        if force_loss is not None:
            pnl = force_loss
        elif pos.position_type == "long":
            pnl = pos.amount * (current_price - pos.avg_buy_price)
        else:
            pnl = pos.amount * (pos.avg_buy_price - current_price)

        cash_return = max(pos.margin + pnl, 0)
        agent.current_balance += cash_return

        trade_type = f"close_{pos.position_type}"

        trade = Trade(
            agent_id=agent.id,
            cryptocurrency=pos.cryptocurrency,
            symbol=pos.symbol,
            trade_type=trade_type,
            amount=pos.amount,
            price=current_price,
            total_value=pos.amount * current_price,
            profit_loss=pnl,
            leverage=pos.leverage,
            margin=pos.margin,
        )
        db.add(trade)

        decision_id = self._log_decision(db, agent.id, pos.cryptocurrency, {
            "action": trade_type,
            "reasoning": reason,
            "confidence": 0.9,
        }, {}, [], strategy_key)

        trade.decision_id = decision_id
        db.delete(pos)
        db.commit()

        tag = pos.position_type.upper()
        logger.info(
            f"Agent {agent.name}: CLOSE {tag} {pos.cryptocurrency} — "
            f"PnL: ${pnl:.2f} (margin: ${pos.margin:.2f} → returned ${cash_return:.2f}) "
            f"| {reason}"
        )

        return {
            "action": trade_type,
            "coin": pos.cryptocurrency,
            "confidence": 0.9,
            "reasoning": reason,
            "strategy": strategy_key,
            "profit_loss": pnl,
            "leverage": pos.leverage,
        }

    # ── Decision Logging ──────────────────────────────────────────────────

    def _log_decision(
        self, db: Session, agent_id: int, coin: str,
        decision: Dict, indicators: Dict,
        news: List, strategy_key: str = "",
        llm_reasoning: str = None,
        llm_sentiment_adj: float = 0.0,
    ):
        """Log AI decision to database."""
        news_data = ([{"title": n.title, "sentiment": n.sentiment}
                      for n in news[:3]] if news and hasattr(news[0] if news else None, 'title') else None)

        safe_indicators = {}
        for k, v in indicators.items():
            if isinstance(v, (int, float, str, bool, type(None))):
                safe_indicators[k] = v
            elif isinstance(v, dict):
                safe_indicators[k] = {
                    sk: sv for sk, sv in v.items()
                    if isinstance(sv, (int, float, str, bool, type(None)))
                }

        log = Decision(
            agent_id=agent_id,
            decision_type="analysis",
            cryptocurrency=coin,
            reasoning=decision.get("reasoning", ""),
            llm_reasoning=llm_reasoning,
            llm_sentiment_adj=llm_sentiment_adj,
            indicators=safe_indicators,
            news_considered=news_data,
            action_taken=decision.get("action", "hold"),
            confidence=decision.get("confidence", 0.0),
            strategy=strategy_key,
        )
        db.add(log)
        db.flush()  # get the ID before commit
        return log.id
