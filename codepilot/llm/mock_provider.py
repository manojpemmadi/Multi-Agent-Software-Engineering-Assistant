"""Deterministic mock LLM provider for unit and integration testing."""

from typing import Any, Dict, List, Optional, Type, TypeVar
from pydantic import BaseModel

from codepilot.llm.base import BaseLLMService
from codepilot.models.schemas import (
    AgentRole,
    AgentResult,
    EvaluationCriteria,
    EvaluationResult,
    ExecutionPlan,
    PlanStep,
    TaskStatus,
    ValidationResult,
)

T = TypeVar("T", bound=BaseModel)


class MockLLMService(BaseLLMService):
    """Deterministic LLM service for testing orchestration, planning, and evaluation."""

    def __init__(self, default_response: str = "Mock LLM output"):
        self.default_response = default_response
        self.preset_structured_responses: Dict[Type[BaseModel], BaseModel] = {}
        self.history: List[Dict[str, Any]] = []

    def is_available(self) -> bool:
        return True

    def get_provider_name(self) -> str:
        return "mock"

    def get_model_name(self) -> str:
        return "mock-model-v1"

    def set_preset_structured(self, response_model_instance: BaseModel) -> None:
        """Register a specific mock object to return for its model type."""
        self.preset_structured_responses[type(response_model_instance)] = response_model_instance

    def generate_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.2,
    ) -> str:
        self.history.append({"prompt": prompt, "system_prompt": system_prompt})
        return self.default_response

    def generate_structured(
        self,
        prompt: str,
        response_model: Type[T],
        system_prompt: Optional[str] = None,
        temperature: float = 0.1,
    ) -> T:
        self.history.append({"prompt": prompt, "system_prompt": system_prompt, "schema": response_model.__name__})

        if response_model in self.preset_structured_responses:
            return self.preset_structured_responses[response_model]  # type: ignore

        # Provide sensible default instances for key models
        if response_model == ExecutionPlan:
            return ExecutionPlan(
                user_intent="Analyze, fix, and validate code based on the task description.",
                steps=[
                    PlanStep(
                        step_id=1,
                        agent=AgentRole.CODE_ANALYSIS,
                        objective="Inspect workspace files and identify the defect or architecture.",
                        expected_output="Detailed analysis of files and potential failure causes.",
                        dependencies=[],
                        allowed_tools=["read_file", "search_code", "list_files"],
                    ),
                    PlanStep(
                        step_id=2,
                        agent=AgentRole.DEBUGGING,
                        objective="Correct the identified defect and write modified code to file.",
                        expected_output="Patch applied and syntax verified.",
                        dependencies=[1],
                        allowed_tools=["read_file", "edit_file", "write_file", "run_command"],
                    ),
                    PlanStep(
                        step_id=3,
                        agent=AgentRole.TESTING,
                        objective="Execute automated tests to validate the proposed fix.",
                        expected_output="Test execution report with pass/fail evidence.",
                        dependencies=[2],
                        allowed_tools=["read_file", "edit_file", "run_tests", "run_command"],
                    ),
                ],
                estimated_complexity="medium",
                rationale="Dynamic plan covering complete analysis, patching, and regression testing.",
            )  # type: ignore

        elif response_model == EvaluationResult:
            return EvaluationResult(
                is_objective_completed=True,
                quality_score=0.95,
                criteria=EvaluationCriteria(
                    relevant_code_inspected=True,
                    proposed_modification_addresses_problem=True,
                    tests_executed=True,
                    tests_passed=True,
                    no_unresolved_errors=True,
                    claims_supported_by_evidence=True,
                ),
                reasoning="All tests passed and code changes match the requested specification.",
                requires_retry=False,
            )  # type: ignore

        elif response_model.__name__ == "ProposedFix":
            return response_model(
                target_file="main.py",
                root_cause_analysis="Syntax error due to missing colon in function definition.",
                complete_fixed_code="def calculate_discount(price, rate):\n    if rate < 0 or rate > 1:\n        raise ValueError('Invalid rate')\n    return price * (1 - rate)\n",
                summary_of_changes="Added missing colon and rate validation.",
            )  # type: ignore

        elif response_model.__name__ == "TestSuiteProposal":
            return response_model(
                test_file_path="test_main.py",
                test_code="from main import calculate_discount\nimport pytest\n\ndef test_calculate():\n    assert calculate_discount(100, 0.2) == 80.0\n\ndef test_invalid_rate():\n    with pytest.raises(ValueError):\n        calculate_discount(100, -1)\n",
                coverage_explanation="Normal and edge case testing.",
            )  # type: ignore

        # Default fallback
        try:
            return response_model()  # type: ignore
        except Exception:
            raise ValueError(f"MockLLMService cannot construct default instance for {response_model}")
