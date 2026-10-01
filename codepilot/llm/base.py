"""Base interface for LLM providers in CodePilot."""

from abc import ABC, abstractmethod
from typing import Optional, Type, TypeVar
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class BaseLLMService(ABC):
    """Abstract interface isolating LLM interactions from agents and orchestrator."""

    @abstractmethod
    def generate_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.2,
    ) -> str:
        """Generate unstructured text response from the model."""
        pass

    @abstractmethod
    def generate_structured(
        self,
        prompt: str,
        response_model: Type[T],
        system_prompt: Optional[str] = None,
        temperature: float = 0.1,
    ) -> T:
        """Generate structured output validated against a Pydantic model."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if the provider has credentials and is operational."""
        pass

    @abstractmethod
    def get_provider_name(self) -> str:
        """Return the name of the LLM provider."""
        pass

    @abstractmethod
    def get_model_name(self) -> str:
        """Return the model identifier."""
        pass
