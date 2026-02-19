"""
LLM Service — AI-powered trade analysis using Google Gemini
=============================================================
Enriches trading decisions with deep news analysis and
natural-language reasoning. Falls back gracefully when
the LLM is unavailable or rate-limited.

Provider: Gemini 2.0 Flash (free tier: 15 RPM, 1M tokens/min)
"""
import logging
import os
import json
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ── Configuration ───────────────────────────────────────────────────────

GEMINI_MODEL = "gemini-2.0-flash"
MAX_RETRIES = 2
REQUEST_TIMEOUT = 15  # seconds
MIN_INTERVAL = 4.5    # seconds between calls (stay under 15 RPM)


@dataclass
class LLMAnalysis:
    """Structured output from the LLM analysis."""
    reasoning: str               # Natural-language explanation
    sentiment_adjustment: float  # -0.15 to +0.15 confidence adjustment
    risk_notes: str              # Risk warnings if any
    news_summary: str            # Short summary of relevant news
    market_context: str          # Market regime description


class LLMService:
    """Service for AI-powered trade analysis using Google Gemini."""

    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY", "")
        self._model = None
        self._available = False
        self._last_call_time = 0.0
        self._consecutive_failures = 0
        self._disabled_until = 0.0

        if self.api_key:
            try:
                import google.generativeai as genai
                genai.configure(api_key=self.api_key)
                self._model = genai.GenerativeModel(GEMINI_MODEL)
                self._available = True
                logger.info(f"✅ LLM Service initialized (model: {GEMINI_MODEL})")
            except ImportError:
                logger.warning("⚠ google-generativeai not installed — LLM disabled")
            except Exception as e:
                logger.warning(f"⚠ Failed to initialize Gemini: {e}")
        else:
            logger.info("ℹ No GEMINI_API_KEY set — LLM analysis disabled (technical-only mode)")

    @property
    def is_available(self) -> bool:
        """Check if LLM is usable right now."""
        if not self._available or not self._model:
            return False
        if time.time() < self._disabled_until:
            return False
        return True

    def _rate_limit_wait(self):
        """Ensure we don't exceed Gemini's rate limit (15 RPM)."""
        elapsed = time.time() - self._last_call_time
        if elapsed < MIN_INTERVAL:
            time.sleep(MIN_INTERVAL - elapsed)

    # ── Main Analysis Method ────────────────────────────────────────────

    def analyze_trade(
        self,
        coin: str,
        direction: str,
        confidence: float,
        strategy_name: str,
        indicators: Dict,
        news_items: List[Dict],
        current_price: float,
        reasoning_technical: str,
    ) -> Optional[LLMAnalysis]:
        """
        Analyze a potential trade using LLM.

        Takes the raw technical signal + news and produces:
        - Rich natural-language reasoning
        - Sentiment adjustment (±0.15 max)
        - Risk notes and market context

        Returns None if LLM is unavailable (graceful fallback).
        """
        if not self.is_available:
            return None

        try:
            self._rate_limit_wait()

            prompt = self._build_prompt(
                coin, direction, confidence, strategy_name,
                indicators, news_items, current_price, reasoning_technical
            )

            self._last_call_time = time.time()

            response = self._model.generate_content(
                prompt,
                generation_config={
                    "temperature": 0.3,
                    "max_output_tokens": 600,
                    "response_mime_type": "application/json",
                }
            )

            result = self._parse_response(response.text)
            self._consecutive_failures = 0
            return result

        except Exception as e:
            self._consecutive_failures += 1
            logger.warning(
                f"LLM analysis failed ({self._consecutive_failures}x): {e}"
            )
            # After 3 consecutive failures, disable for 5 minutes
            if self._consecutive_failures >= 3:
                self._disabled_until = time.time() + 300
                logger.warning("LLM disabled for 5 minutes after repeated failures")
            return None

    # ── Prompt Engineering ──────────────────────────────────────────────

    def _build_prompt(
        self,
        coin: str,
        direction: str,
        confidence: float,
        strategy_name: str,
        indicators: Dict,
        news_items: List[Dict],
        current_price: float,
        reasoning_technical: str,
    ) -> str:
        """Build a focused prompt for trade analysis."""

        # Format indicators concisely
        ind_summary = self._format_indicators(indicators)

        # Format news
        if news_items:
            news_text = "\n".join(
                f"- [{n.get('sentiment', '?')}] {n.get('title', 'N/A')} "
                f"(source: {n.get('source', '?')}, "
                f"impact: {n.get('impact_score', 0):.2f})"
                for n in news_items[:8]
            )
        else:
            news_text = "No recent news available."

        return f"""You are a senior crypto trading analyst. Analyze this potential trade and provide your assessment.

TRADE SIGNAL:
- Coin: {coin.upper()} (current price: ${current_price:,.2f})
- Direction: {direction.upper()}
- Strategy: {strategy_name}
- Technical confidence: {confidence:.0%}
- Technical reasoning: {reasoning_technical}

INDICATORS:
{ind_summary}

RECENT NEWS:
{news_text}

Respond in JSON with exactly these fields:
{{
  "reasoning": "2-3 sentence analysis combining technical + fundamental factors. Be specific about WHY this trade makes sense or doesn't. Reference specific indicators and news.",
  "sentiment_adjustment": <float between -0.15 and 0.15. Positive = news supports the trade, negative = news contradicts it. 0 if neutral or no relevant news.>,
  "risk_notes": "Brief risk warning if any (empty string if none)",
  "news_summary": "One-sentence summary of how news affects this coin right now",
  "market_context": "One sentence describing the current market regime (trending/ranging/volatile/etc)"
}}

IMPORTANT: Keep reasoning concise but insightful. Focus on actionable analysis, not generic commentary. If news is unrelated to the coin, sentiment_adjustment should be 0."""

    def _format_indicators(self, indicators: Dict) -> str:
        """Format indicators dict into readable text."""
        parts = []

        rsi = indicators.get("rsi")
        if rsi is not None:
            label = "oversold" if rsi < 30 else "overbought" if rsi > 70 else "neutral"
            parts.append(f"RSI: {rsi:.1f} ({label})")

        macd = indicators.get("macd")
        if isinstance(macd, dict):
            parts.append(
                f"MACD: {macd.get('histogram', 0):.4f} "
                f"({macd.get('crossover', 'none')} crossover)"
            )

        bb = indicators.get("bb")
        if isinstance(bb, dict):
            parts.append(
                f"BB: %B={bb.get('pct_b', 0.5):.2f}, "
                f"width={bb.get('width_pct', 0):.1f}%"
                f"{' [SQUEEZE]' if bb.get('squeeze') else ''}"
            )

        adx_data = indicators.get("adx")
        if isinstance(adx_data, dict):
            parts.append(
                f"ADX: {adx_data.get('adx', 0):.1f} "
                f"(+DI={adx_data.get('plus_di', 0):.1f} "
                f"-DI={adx_data.get('minus_di', 0):.1f})"
            )

        stoch = indicators.get("stoch_rsi")
        if isinstance(stoch, dict):
            parts.append(f"StochRSI: K={stoch.get('k', 50):.0f} D={stoch.get('d', 50):.0f}")

        vol = indicators.get("volume")
        if isinstance(vol, dict):
            parts.append(
                f"Volume: ratio={vol.get('ratio', 1.0):.2f}"
                f"{' [SPIKE]' if vol.get('spike') else ''}"
            )

        mom = indicators.get("momentum", 0)
        parts.append(f"Momentum: {mom:+.2f}%")

        change_24h = indicators.get("price_change_24h", 0)
        change_7d = indicators.get("price_change_7d", 0)
        parts.append(f"24h: {change_24h:+.2f}% | 7d: {change_7d:+.2f}%")

        ema9 = indicators.get("ema_9")
        ema21 = indicators.get("ema_21")
        ema55 = indicators.get("ema_55")
        if ema9 and ema21:
            alignment = "bullish" if ema9 > ema21 else "bearish"
            if ema55:
                if ema9 > ema21 > ema55:
                    alignment = "strong bullish (9>21>55)"
                elif ema9 < ema21 < ema55:
                    alignment = "strong bearish (9<21<55)"
            parts.append(f"EMA alignment: {alignment}")

        return "\n".join(f"  • {p}" for p in parts)

    # ── Response Parsing ────────────────────────────────────────────────

    def _parse_response(self, text: str) -> LLMAnalysis:
        """Parse JSON response from Gemini into LLMAnalysis."""
        try:
            # Clean potential markdown code fences
            cleaned = text.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1]
                if cleaned.endswith("```"):
                    cleaned = cleaned[:-3]
                cleaned = cleaned.strip()

            data = json.loads(cleaned)

            # Clamp sentiment adjustment to safe range
            adj = float(data.get("sentiment_adjustment", 0))
            adj = max(-0.15, min(0.15, adj))

            return LLMAnalysis(
                reasoning=str(data.get("reasoning", "No analysis available")),
                sentiment_adjustment=adj,
                risk_notes=str(data.get("risk_notes", "")),
                news_summary=str(data.get("news_summary", "")),
                market_context=str(data.get("market_context", "")),
            )
        except (json.JSONDecodeError, TypeError, KeyError) as e:
            logger.warning(f"Failed to parse LLM response: {e}")
            # Return a minimal analysis from the raw text
            return LLMAnalysis(
                reasoning=text[:500] if text else "LLM response unparseable",
                sentiment_adjustment=0.0,
                risk_notes="",
                news_summary="",
                market_context="",
            )

    # ── Health Check ────────────────────────────────────────────────────

    def health_check(self) -> Dict:
        """Return LLM service status."""
        if not self.api_key:
            return {"status": "disabled", "reason": "No API key configured"}
        if not self._available:
            return {"status": "error", "reason": "Failed to initialize"}
        if time.time() < self._disabled_until:
            remaining = int(self._disabled_until - time.time())
            return {"status": "cooldown", "reason": f"Disabled for {remaining}s after failures"}
        return {
            "status": "ok",
            "model": GEMINI_MODEL,
            "consecutive_failures": self._consecutive_failures,
        }
