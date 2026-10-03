"""Unit tests for the Gemini Interactions API provider."""

from types import SimpleNamespace
from unittest.mock import Mock

from codepilot.llm.gemini_provider import GeminiLLMService
from codepilot.models.schemas import ExecutionPlan


def _service_with_mock_interactions(output_text: str) -> tuple[GeminiLLMService, Mock]:
    service = GeminiLLMService(api_key="test-key", model_name="gemini-3.8-flash")
    interactions = Mock()
    interactions.create.return_value = SimpleNamespace(output_text=output_text)
    service._client = SimpleNamespace(interactions=interactions)
    return service, interactions


def test_generate_text_uses_interactions_api():
    service, interactions = _service_with_mock_interactions("Generated answer")

    result = service.generate_text(
        "Explain the change",
        system_prompt="You are a coding assistant.",
        temperature=0.4,
    )

    assert result == "Generated answer"
    interactions.create.assert_called_once_with(
        model="gemini-3.8-flash",
        input="Explain the change",
        system_instruction="You are a coding assistant.",
        generation_config={"temperature": 0.4},
        store=False,
    )


def test_generate_structured_uses_json_schema_and_validates_response():
    output = (
        '{"user_intent":"Inspect repository",'
        '"steps":[],"estimated_complexity":"low","rationale":"No changes needed."}'
    )
    service, interactions = _service_with_mock_interactions(output)

    plan = service.generate_structured(
        "Create an execution plan",
        response_model=ExecutionPlan,
        system_prompt="Plan using the registered agents.",
    )

    assert isinstance(plan, ExecutionPlan)
    assert plan.user_intent == "Inspect repository"
    call = interactions.create.call_args.kwargs
    assert call["model"] == "gemini-3.8-flash"
    assert call["input"] == "Create an execution plan"
    assert call["system_instruction"] == "Plan using the registered agents."
    assert call["generation_config"] == {"temperature": 0.1}
    assert call["response_format"] == {
        "type": "text",
        "mime_type": "application/json",
        "schema": ExecutionPlan.model_json_schema(),
    }
    assert call["store"] is False
