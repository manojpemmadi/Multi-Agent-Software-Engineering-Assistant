"""Google Gemini LLM provider implementation using google-genai SDK."""

import json
import logging
from typing import Optional, Type, TypeVar
from pydantic import BaseModel

from codepilot.config import settings
from codepilot.llm.base import BaseLLMService

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


class GeminiLLMService(BaseLLMService):
    """Production Gemini integration using official google-genai client."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
    ):
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.model_name = model_name or settings.GEMINI_MODEL
        self._client = None

        if self.api_key:
            try:
                from google import genai
                self._client = genai.Client(api_key=self.api_key)
                logger.info("Gemini client initialized with model: %s", self.model_name)
            except Exception as e:
                logger.error("Failed to initialize Gemini client: %s", e)
                self._client = None
        else:
            logger.warning("GEMINI_API_KEY is not set. GeminiLLMService is unauthenticated.")

    def is_available(self) -> bool:
        return bool(self._client and self.api_key)

    def get_provider_name(self) -> str:
        return "gemini"

    def get_model_name(self) -> str:
        return self.model_name

    def generate_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.2,
    ) -> str:
        if not self.is_available():
            raise RuntimeError(
                "Gemini API key is not configured. Please set GEMINI_API_KEY in your .env file."
            )

        from google.genai import types

        config = types.GenerateContentConfig(
            temperature=temperature,
            system_instruction=system_prompt if system_prompt else None,
        )

        try:
            response = self._client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=config,
            )
            return response.text or ""
        except Exception as e:
            logger.error("Gemini text generation failed: %s", e)
            raise RuntimeError(f"Gemini API error: {str(e)}") from e

    def generate_structured(
        self,
        prompt: str,
        response_model: Type[T],
        system_prompt: Optional[str] = None,
        temperature: float = 0.1,
    ) -> T:
        if not self.is_available():
            raise RuntimeError(
                "Gemini API key is not configured. Please set GEMINI_API_KEY in your .env file."
            )

        from google.genai import types

        config = types.GenerateContentConfig(
            temperature=temperature,
            system_instruction=system_prompt if system_prompt else None,
            response_mime_type="application/json",
            response_schema=response_model,
        )

        try:
            response = self._client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=config,
            )

            # Check if response.parsed already holds the instantiated model
            if hasattr(response, "parsed") and isinstance(response.parsed, response_model):
                return response.parsed

            # Fall back to parsing the json text
            raw_text = response.text or "{}"
            # Clean markdown code blocks if present
            raw_text = raw_text.strip()
            if raw_text.startswith("```json"):
                raw_text = raw_text[7:]
            elif raw_text.startswith("```"):
                raw_text = raw_text[3:]
            if raw_text.endswith("```"):
                raw_text = raw_text[:-3]
            raw_text = raw_text.strip()

            return response_model.model_validate_json(raw_text)

        except Exception as e:
            logger.error("Gemini structured generation failed: %s", e)
            raise RuntimeError(f"Gemini structured output error: {str(e)}") from e
