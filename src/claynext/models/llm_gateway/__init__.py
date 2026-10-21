"""Provider gateway: one chat interface over OpenAI and other OpenAI-compatible platforms."""
from __future__ import annotations

from claynext.models.llm_gateway.base import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    LlmProvider,
    Pricing,
    ProviderError,
    TraceLog,
    Usage,
)
from claynext.models.llm_gateway.openai_provider import OpenAICompatibleProvider


def get_provider(provider_id: str = "openai", **kwargs) -> LlmProvider:
    """Chat provider by id from ``llm_providers.CHAT_PROVIDERS`` (all speak the OpenAI chat API)."""
    return OpenAICompatibleProvider(provider_id, **kwargs)


__all__ = [
    "ChatMessage",
    "ChatRequest",
    "ChatResponse",
    "LlmProvider",
    "OpenAICompatibleProvider",
    "Pricing",
    "ProviderError",
    "TraceLog",
    "Usage",
    "get_provider",
]
