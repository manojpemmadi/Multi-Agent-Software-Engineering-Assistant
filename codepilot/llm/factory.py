"""LLM provider factory."""

import logging
from typing import Optional

from codepilot.config import settings
from codepilot.llm.base import BaseLLMService
from codepilot.llm.gemini_provider import GeminiLLMService
from codepilot.llm.openai_provider import OpenAILLMService
from codepilot.llm.mock_provider import MockLLMService

logger = logging.getLogger(__name__)


def get_llm_provider(
    provider_name: Optional[str] = None,
    api_key: Optional[str] = None,
    model_name: Optional[str] = None,
) -> BaseLLMService:
    """Factory to retrieve configured LLM service instance."""
    name = (provider_name or settings.LLM_PROVIDER).lower()

    if name == "mock":
        return MockLLMService()

    elif name == "gemini":
        gemini_key = api_key or settings.GEMINI_API_KEY
        if not gemini_key and settings.OPENAI_API_KEY:
            logger.info("GEMINI_API_KEY not found, falling back to OPENAI_API_KEY.")
            return OpenAILLMService(api_key=settings.OPENAI_API_KEY, model_name=model_name)
        return GeminiLLMService(api_key=gemini_key, model_name=model_name)

    elif name == "openai":
        return OpenAILLMService(api_key=api_key or settings.OPENAI_API_KEY, model_name=model_name)

    else:
        raise ValueError(
            f"Unsupported LLM provider '{name}'. Valid options: 'gemini', 'openai', 'mock'."
        )
