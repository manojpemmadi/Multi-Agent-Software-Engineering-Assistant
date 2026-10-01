"""OpenAI LLM provider implementation for swappable multi-provider support."""

import json
import logging
from typing import Optional, Type, TypeVar
from pydantic import BaseModel

from codepilot.config import settings
from codepilot.llm.base import BaseLLMService

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


class OpenAILLMService(BaseLLMService):
    """OpenAI implementation of the BaseLLMService."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
    ):
        self.api_key = api_key or settings.OPENAI_API_KEY
        self.model_name = model_name or settings.OPENAI_MODEL
        self._client = None

        if self.api_key:
            try:
                from openai import OpenAI
                self._client = OpenAI(api_key=self.api_key)
                logger.info("OpenAI client initialized with model: %s", self.model_name)
            except Exception as e:
                logger.error("Failed to initialize OpenAI client: %s", e)
                self._client = None
        else:
            logger.warning("OPENAI_API_KEY is not set.")

    def is_available(self) -> bool:
        return bool(self._client and self.api_key)

    def get_provider_name(self) -> str:
        return "openai"

    def get_model_name(self) -> str:
        return self.model_name

    def generate_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.2,
    ) -> str:
        if not self.is_available():
            raise RuntimeError("OpenAI API key is not configured.")

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            response = self._client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=temperature,
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            logger.error("OpenAI text generation failed: %s", e)
            raise RuntimeError(f"OpenAI API error: {str(e)}") from e

    def generate_structured(
        self,
        prompt: str,
        response_model: Type[T],
        system_prompt: Optional[str] = None,
        temperature: float = 0.1,
    ) -> T:
        if not self.is_available():
            raise RuntimeError("OpenAI API key is not configured.")

        messages = []
        schema_json = json.dumps(response_model.model_json_schema())
        system_instruction = (
            (system_prompt + "\n\n" if system_prompt else "")
            + f"Output strictly valid JSON matching this JSON Schema:\n{schema_json}"
        )
        messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})

        try:
            try:
                # Try beta structured parse if supported
                completion = self._client.beta.chat.completions.parse(
                    model=self.model_name,
                    messages=messages,
                    response_format=response_model,
                    temperature=temperature,
                )
                if completion.choices[0].message.parsed:
                    return completion.choices[0].message.parsed
            except Exception:
                pass

            # Fall back to json_object response format
            response = self._client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=temperature,
            )
            raw_text = response.choices[0].message.content or "{}"
            return response_model.model_validate_json(raw_text)

        except Exception as e:
            logger.error("OpenAI structured generation failed: %s", e)
            raise RuntimeError(f"OpenAI structured output error: {str(e)}") from e
