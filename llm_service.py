"""CodePilot LLM Service (Root compatibility wrapper)."""

from typing import List, Optional
from codepilot.config import settings
from codepilot.llm.base import BaseLLMService
from codepilot.llm.factory import get_llm_provider


class LLMService:
    """Production LLM Service wrapping the modular provider interface."""

    def __init__(self, provider_name: Optional[str] = None):
        self.provider: BaseLLMService = get_llm_provider(provider_name=provider_name)

    def generate_answer(
        self,
        question: str,
        retrieved_chunks: List[dict],
    ) -> str:
        if not question.strip():
            raise ValueError("Question cannot be empty.")

        context_parts = []
        for chunk in retrieved_chunks:
            file_path = chunk.get("file_path", "unknown")
            text = chunk.get("text", "")
            context_parts.append(f"FILE: {file_path}\nCODE:\n{text}\n")

        context = "\n---\n".join(context_parts)

        prompt = f"""
You are CodePilot AI, an autonomous software engineering assistant.

The user is asking a question about a software repository or codebase.

USER QUESTION:
{question}

RETRIEVED CODE CONTEXT:
{context}

Provide a comprehensive, accurate technical answer based on the retrieved code context.
"""
        return self.provider.generate_text(prompt=prompt)


if __name__ == "__main__":
    llm = LLMService()
    print(f"Provider: {llm.provider.get_provider_name()} ({llm.provider.get_model_name()})")
    print(f"Available: {llm.provider.is_available()}")