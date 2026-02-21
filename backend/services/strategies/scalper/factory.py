"""
ScalperFactory — Factory pattern for scalper strategy instantiation.

Maps strategy keys to concrete scalper subclasses and provides
type-safe creation with validation.
"""
from __future__ import annotations

from typing import Dict, List, Type

from backend.services.strategies.scalper.base_scalper import BaseScalperStrategy
from backend.services.strategies.scalper.scalper_1m import Scalper1M
from backend.services.strategies.scalper.scalper_3m import Scalper3M
from backend.services.strategies.scalper.scalper_5m import Scalper5M
from backend.services.strategies.scalper.scalper_15m import Scalper15M
from backend.services.strategies.scalper.scalper_1h import Scalper1H


# ── Registry ────────────────────────────────────────────────────────────────

_REGISTRY: Dict[str, Type[BaseScalperStrategy]] = {
    "scalper_1m": Scalper1M,
    "scalper_3m": Scalper3M,
    "scalper_5m": Scalper5M,
    "scalper_15m": Scalper15M,
    "scalper": Scalper1H,
}


class ScalperFactory:
    """Factory for creating scalper strategy instances.

    Usage::

        strategy = ScalperFactory.create("scalper_15m")
        signal = strategy.evaluate(indicators, price)

    The factory maintains a singleton cache so repeated ``create()`` calls
    for the same key return the same instance (scalper strategies are
    stateless — safe to share).
    """

    _cache: Dict[str, BaseScalperStrategy] = {}

    @classmethod
    def create(cls, key: str) -> BaseScalperStrategy:
        """Create (or retrieve cached) a scalper strategy by key.

        Args:
            key: Strategy registry key (e.g. ``'scalper_15m'``).

        Returns:
            Concrete ``BaseScalperStrategy`` subclass instance.

        Raises:
            ValueError: If ``key`` is not in the registry.
        """
        if key in cls._cache:
            return cls._cache[key]

        klass = _REGISTRY.get(key)
        if klass is None:
            valid = ", ".join(sorted(_REGISTRY))
            raise ValueError(
                f"Unknown scalper key '{key}'. Valid keys: {valid}"
            )

        instance = klass()
        cls._cache[key] = instance
        return instance

    @classmethod
    def keys(cls) -> List[str]:
        """Return all registered scalper strategy keys."""
        return list(_REGISTRY.keys())

    @classmethod
    def is_scalper(cls, key: str) -> bool:
        """Check if a strategy key belongs to a scalper variant."""
        return key in _REGISTRY

    @classmethod
    def reset_cache(cls) -> None:
        """Clear singleton cache (useful for testing)."""
        cls._cache.clear()
