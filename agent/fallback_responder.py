"""Backward-compatible name for Nova's multi-provider reasoning pool."""

from __future__ import annotations

from .provider_pool import ReasoningProviderPool


class FallbackResponder(ReasoningProviderPool):
    """Compatibility wrapper around the health-aware provider pool."""

    pass
