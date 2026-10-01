"""Final Evaluation Stage: Verifies objective completion against tool execution evidence."""

import logging
from typing import List, Optional

from codepilot.llm.base import BaseLLMService
from codepilot.models.schemas import (
    AgentResult,
    AgentRole,
    EvaluationCriteria,
    EvaluationResult,
    TaskStatus,
    UserRequest,
)

logger = logging.getLogger(__name__)


class FinalEvaluator:
    """Verifies that the requested objective was actually completed using tool execution evidence."""

    def __init__(self, llm_service: Optional[BaseLLMService] = None):
        self.llm_service = llm_service

    def evaluate(
        self,
        request: UserRequest,
        agent_results: List[AgentResult],
        current_retry_count: int = 0,
        max_retries: int = 3,
    ) -> EvaluationResult:
        """Evaluate workflow results against strict evidence criteria."""
        logger.info("[FinalEvaluator] Running evidence-based evaluation stage...")

        criteria = EvaluationCriteria()

        # 1. Check if files were inspected
        inspected_files = set()
        for r in agent_results:
            inspected_files.update(r.files_inspected)
        criteria.relevant_code_inspected = len(inspected_files) > 0

        # 2. Check if modifications were made
        has_modifications = any(len(r.changes_made) > 0 for r in agent_results)
        criteria.proposed_modification_addresses_problem = has_modifications or (
            request.input_mode.value == "general_query" and not request.error_message
        )

        # 3. Check test execution
        validation_results = [r.validation for r in agent_results if r.validation is not None]
        if validation_results:
            latest_val = validation_results[-1]
            criteria.tests_executed = latest_val.total_tests > 0
            criteria.tests_passed = latest_val.passed
        else:
            # If no testing step was run (e.g. read-only query)
            criteria.tests_executed = False
            criteria.tests_passed = (request.input_mode.value == "general_query")

        # 4. Check for unresolved errors
        has_errors = any(len(r.errors) > 0 for r in agent_results)
        any_failed_step = any(r.status in (TaskStatus.FAILURE, TaskStatus.NEEDS_RETRY) for r in agent_results)
        criteria.no_unresolved_errors = (not has_errors) and (not any_failed_step or criteria.tests_passed)

        # 5. Check if claims are supported by tool evidence
        tool_calls_count = sum(len(r.tool_calls_made) for r in agent_results)
        criteria.claims_supported_by_evidence = tool_calls_count > 0

        # Compute Quality Score
        weights = [
            (criteria.relevant_code_inspected, 0.20),
            (criteria.proposed_modification_addresses_problem, 0.25),
            (criteria.tests_executed, 0.15),
            (criteria.tests_passed, 0.25),
            (criteria.no_unresolved_errors, 0.10),
            (criteria.claims_supported_by_evidence, 0.05),
        ]
        quality_score = sum(w for passed, w in weights if passed)

        is_completed = (quality_score >= 0.70) and (criteria.tests_passed or not validation_results)
        requires_retry = (not is_completed) and (current_retry_count < max_retries)

        retry_agent = None
        retry_guidance = None

        if requires_retry:
            if not criteria.tests_passed:
                retry_agent = AgentRole.DEBUGGING
                failed_msg = validation_results[-1].raw_output if validation_results else "Tests failed."
                retry_guidance = (
                    f"Automated test validation failed. Test Output:\n{failed_msg[:400]}\n"
                    f"Please inspect the failure trace, diagnose the bug, and revise the code fix."
                )
            elif not criteria.proposed_modification_addresses_problem:
                retry_agent = AgentRole.DEBUGGING
                retry_guidance = "No code modifications were applied to address the problem. Please modify the target file."
            elif not criteria.tests_executed:
                retry_agent = AgentRole.TESTING
                retry_guidance = "No tests were executed. Please construct and execute validation test cases."

        reasoning = (
            f"Evaluation Score: {quality_score:.2f}/1.00. "
            f"Code Inspected: {criteria.relevant_code_inspected}, "
            f"Modifications Made: {criteria.proposed_modification_addresses_problem}, "
            f"Tests Executed: {criteria.tests_executed}, "
            f"Tests Passed: {criteria.tests_passed}, "
            f"Evidence Backed: {criteria.claims_supported_by_evidence}."
        )

        return EvaluationResult(
            is_objective_completed=is_completed,
            quality_score=round(quality_score, 2),
            criteria=criteria,
            reasoning=reasoning,
            requires_retry=requires_retry,
            retry_target_agent=retry_agent,
            retry_guidance=retry_guidance,
        )
