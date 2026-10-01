"""Multi-Agent Orchestrator: Coordinates planning, execution, feedback loops, and evaluation."""

import logging
import uuid
from typing import Any, Callable, Dict, List, Optional

from codepilot.agents.code_analysis_agent import CodeAnalysisAgent
from codepilot.agents.debugging_agent import DebuggingAgent
from codepilot.agents.testing_agent import TestingAgent
from codepilot.config import settings
from codepilot.llm.base import BaseLLMService
from codepilot.llm.factory import get_llm_provider
from codepilot.mcp.client import MCPClient
from codepilot.models.schemas import (
    AgentResult,
    AgentRole,
    AgentTask,
    ExecutionPlan,
    FinalResult,
    InputMode,
    TaskStatus,
    UserRequest,
    WorkflowProgressEvent,
)
from codepilot.orchestrator.agent_registry import AgentRegistry
from codepilot.orchestrator.evaluator import FinalEvaluator
from codepilot.orchestrator.planner import LLMPlanner
from codepilot.rag.retriever import CodeRetriever
from codepilot.workspace.detector import ProjectDetector
from codepilot.workspace.manager import Workspace, WorkspaceManager

logger = logging.getLogger(__name__)


class MultiAgentOrchestrator:
    """Master orchestrator driving the iterative multi-agent engineering workflow."""

    def __init__(
        self,
        llm_service: Optional[BaseLLMService] = None,
        mcp_client: Optional[MCPClient] = None,
        workspace_manager: Optional[WorkspaceManager] = None,
        retriever: Optional[CodeRetriever] = None,
        max_retries: int = settings.MAX_RETRIES,
    ):
        self.llm_service = llm_service or get_llm_provider()
        self.mcp_client = mcp_client or MCPClient()
        self.workspace_manager = workspace_manager or WorkspaceManager()
        self.retriever = retriever or CodeRetriever()
        self.registry = AgentRegistry()
        self.planner = LLMPlanner(self.llm_service, self.registry)
        self.evaluator = FinalEvaluator(self.llm_service)
        self.max_retries = max_retries

        # Initialize the three specialized worker agents
        self.worker_agents = {
            AgentRole.CODE_ANALYSIS: CodeAnalysisAgent(self.llm_service, self.mcp_client),
            AgentRole.DEBUGGING: DebuggingAgent(self.llm_service, self.mcp_client),
            AgentRole.TESTING: TestingAgent(self.llm_service, self.mcp_client),
        }

    def run(
        self,
        request: UserRequest,
        event_callback: Optional[Callable[[WorkflowProgressEvent], None]] = None,
    ) -> FinalResult:
        """Execute end-to-end multi-agent workflow."""
        timeline: List[Dict[str, Any]] = []

        def emit(step: str, status: str, message: str, agent: Optional[str] = None, details: Optional[Dict] = None):
            ev = WorkflowProgressEvent(step=step, status=status, message=message, agent=agent, details=details)
            timeline.append(ev.model_dump())
            if event_callback:
                try:
                    event_callback(ev)
                except Exception as e:
                    logger.debug("Event callback error: %s", e)

        emit("init", "running", "Setting up isolated workspace environment...")

        # 1. Setup Isolated Workspace
        workspace = self._setup_workspace(request)
        emit(
            "workspace",
            "success",
            f"Workspace '{workspace.workspace_id}' created at: {workspace.root_path.name}",
            details={"workspace_id": workspace.workspace_id},
        )

        # 2. Ecosystem Detection
        eco = ProjectDetector.detect(str(workspace.root_path))
        emit(
            "detection",
            "success",
            f"Detected project ecosystem: {eco.get('language', 'generic')} ({eco.get('files_count', 0)} files)",
            details=eco,
        )

        # 3. RAG Codebase Indexing (if multiple files or repo)
        if request.github_url or eco.get("files_count", 0) > 1:
            emit("rag_indexing", "running", "Scanning and indexing codebase into ChromaDB vector store...")
            idx_res = self.retriever.index_workspace(str(workspace.root_path), workspace.workspace_id)
            emit(
                "rag_indexing",
                "success",
                f"RAG indexing complete: {idx_res.get('indexed_chunks', 0)} semantic code chunks stored.",
                details=idx_res,
            )

        # 4. LLM Planning (NO hardcoded keywords!)
        emit("planning", "running", "Asking Gemini to formulate a structured execution plan...")
        plan = self.planner.create_plan(request, eco)
        emit(
            "planning",
            "success",
            f"Execution plan formulated: {len(plan.steps)} steps (Complexity: {plan.estimated_complexity})",
            details=plan.model_dump(),
        )

        # 5. Execute Plan Steps iteratively
        agent_results: List[AgentResult] = []
        prior_context: Dict[str, Any] = {
            "user_intent": plan.user_intent,
            "project_metadata": eco,
        }

        for step in plan.steps:
            agent = self.worker_agents.get(step.agent)
            if not agent:
                logger.error("Unknown agent in plan: %s", step.agent)
                continue

            emit(
                f"step_{step.step_id}",
                "running",
                f"Running {step.agent.value.replace('_', ' ').title()}: {step.objective}",
                agent=step.agent.value,
            )

            # Retrieve RAG context relevant to this specific step's objective
            rag_chunks = self.retriever.retrieve(
                query=f"{step.objective} {request.error_message or ''}",
                workspace_id=workspace.workspace_id,
                top_k=settings.RAG_TOP_K,
            )

            task_payload = AgentTask(
                task_id=f"step_{step.step_id}_{uuid.uuid4().hex[:4]}",
                role=step.agent,
                objective=step.objective,
                workspace_path=str(workspace.root_path),
                context=prior_context,
                retrieved_code_chunks=rag_chunks,
                allowed_tools=step.allowed_tools,
            )

            result = agent.run(task_payload, workspace)
            agent_results.append(result)

            # Update prior context for downstream agents
            prior_context[f"step_{step.step_id}_{step.agent.value}"] = {
                "summary": result.summary,
                "evidence": result.evidence[:300],
                "changes_made": result.changes_made,
                "files_inspected": result.files_inspected,
            }

            emit(
                f"step_{step.step_id}",
                "success" if result.status == TaskStatus.SUCCESS else "warning",
                f"{step.agent.value.replace('_', ' ').title()}: {result.summary}",
                agent=step.agent.value,
                details={
                    "status": result.status.value,
                    "changes": len(result.changes_made),
                    "confidence": result.confidence,
                },
            )

        # 6. Evaluation & Bounded Retries Loop
        current_retry = 0
        eval_result = None

        while current_retry <= self.max_retries:
            emit("evaluation", "running", "Evaluating objective completion against tool execution evidence...")
            eval_result = self.evaluator.evaluate(
                request=request,
                agent_results=agent_results,
                current_retry_count=current_retry,
                max_retries=self.max_retries,
            )

            if eval_result.is_objective_completed or not eval_result.requires_retry:
                emit(
                    "evaluation",
                    "success" if eval_result.is_objective_completed else "failure",
                    f"Final Evaluation (Score {eval_result.quality_score:.2f}): {eval_result.reasoning}",
                    details=eval_result.model_dump(),
                )
                break

            # Need to coordinate retry
            current_retry += 1
            retry_agent_role = eval_result.retry_target_agent or AgentRole.DEBUGGING
            emit(
                "retry",
                "running",
                f"Retry {current_retry}/{self.max_retries}: Invoking {retry_agent_role.value} with failure feedback...",
                agent=retry_agent_role.value,
                details={"guidance": eval_result.retry_guidance},
            )

            retry_agent = self.worker_agents[retry_agent_role]
            retry_task = AgentTask(
                task_id=f"retry_{current_retry}_{uuid.uuid4().hex[:4]}",
                role=retry_agent_role,
                objective=f"Revise and resolve failures for: {request.message}",
                workspace_path=str(workspace.root_path),
                context=prior_context,
                retry_attempt=current_retry,
                feedback=eval_result.retry_guidance,
                allowed_tools=list(self.registry.get_agent_capability(retry_agent_role).allowed_tools),
            )

            retry_result = retry_agent.run(retry_task, workspace)
            agent_results.append(retry_result)

            # If debugging fixed code, immediately run testing agent to re-validate
            if retry_agent_role == AgentRole.DEBUGGING:
                emit("retry_test", "running", "Re-running test suite to validate revised patch...", agent="testing")
                test_agent = self.worker_agents[AgentRole.TESTING]
                retest_task = AgentTask(
                    task_id=f"retest_{current_retry}_{uuid.uuid4().hex[:4]}",
                    role=AgentRole.TESTING,
                    objective="Re-run tests on the newly modified code.",
                    workspace_path=str(workspace.root_path),
                    context=prior_context,
                    allowed_tools=list(self.registry.get_agent_capability(AgentRole.TESTING).allowed_tools),
                )
                retest_result = test_agent.run(retest_task, workspace)
                agent_results.append(retest_result)

        # 7. Synthesize Final User Deliverable
        all_modified_files = workspace.get_modified_files()
        primary_modified_content = None
        primary_lang = eco.get("language", "python")

        if all_modified_files:
            try:
                target_f = workspace.resolve_safe_path(all_modified_files[0]["file_path"])
                if target_f.exists() and target_f.is_file():
                    primary_modified_content = target_f.read_text(encoding="utf-8", errors="replace")
            except Exception:
                pass
        elif request.code_snippet and (workspace.root_path / "main.py").exists():
            primary_modified_content = (workspace.root_path / "main.py").read_text(encoding="utf-8", errors="replace")

        # Collect latest validation evidence
        latest_val = None
        for r in reversed(agent_results):
            if r.validation:
                latest_val = r.validation
                break

        summary_parts = []
        for r in agent_results:
            if r.agent == AgentRole.DEBUGGING and r.changes_made:
                summary_parts.append(r.summary)
        if not summary_parts:
            summary_parts.append(agent_results[-1].summary if agent_results else "Workflow completed.")

        final_summary = " ".join(summary_parts)

        return FinalResult(
            success=eval_result.is_objective_completed if eval_result else True,
            summary=final_summary,
            solution_code=primary_modified_content,
            solution_language=primary_lang,
            files_modified=all_modified_files,
            test_evidence=latest_val,
            execution_timeline=timeline,
            evaluation=eval_result,
        )

    def _setup_workspace(self, request: UserRequest) -> Workspace:
        """Create or clone the appropriate workspace based on user request."""
        if request.github_url:
            return self.workspace_manager.clone_github_repo(request.github_url)

        snippet = request.code_snippet or ""
        lang = request.code_language or "python"

        # If user pasted code inside message
        if not snippet and ("def " in request.message or "class " in request.message or "import " in request.message):
            snippet = request.message
            lang = "python"

        if not snippet:
            snippet = f"# CodePilot workspace placeholder for task: {request.message}\n"

        return self.workspace_manager.create_paste_workspace(
            code_snippet=snippet,
            language=lang,
        )
