"""FastAPI API routes for CodePilot chatbot and workspace inspections."""

import asyncio
import json
import logging
import uuid
from typing import Any, Dict
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from codepilot.api.events import event_bus
from codepilot.config import settings
from codepilot.llm.factory import get_llm_provider
from codepilot.mcp.client import MCPClient
from codepilot.models.schemas import FinalResult, UserRequest, WorkflowProgressEvent
from codepilot.orchestrator.orchestrator import MultiAgentOrchestrator
from codepilot.workspace.manager import WorkspaceManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

# Shared singletons
workspace_manager = WorkspaceManager()
mcp_client = MCPClient()


@router.get("/health")
async def health_check():
    """System health and LLM provider status check."""
    llm = get_llm_provider()
    all_tools = mcp_client.server.list_tools()
    return {
        "status": "online",
        "app_name": settings.APP_NAME,
        "version": settings.VERSION,
        "provider": llm.get_provider_name(),
        "model": llm.get_model_name(),
        "is_available": llm.is_available(),
        "total_mcp_tools": len(all_tools),
        "tools": [t["name"] for t in all_tools],
        "workspaces_count": len(workspace_manager._workspaces),
    }


@router.post("/chat", response_model=FinalResult)
async def process_chat(request: UserRequest):
    """Process a software engineering request synchronously."""
    session_id = request.session_id or f"session_{uuid.uuid4().hex[:6]}"

    def _on_event(ev: WorkflowProgressEvent):
        event_bus.publish(session_id, ev)

    orchestrator = MultiAgentOrchestrator(
        mcp_client=mcp_client,
        workspace_manager=workspace_manager,
    )

    try:
        # Run in thread pool to prevent blocking the async event loop
        loop = asyncio.get_running_loop()
        final_result = await loop.run_in_executor(
            None,
            lambda: orchestrator.run(request, event_callback=_on_event),
        )
        return final_result
    except Exception as e:
        logger.error("Orchestrator error: %s", e, exc_info=True)
        return FinalResult(
            success=False,
            summary=f"An error occurred during multi-agent execution: {str(e)}",
            raw_error=str(e),
        )


@router.get("/events/{session_id}")
async def sse_events(session_id: str):
    """Server-Sent Events endpoint to stream real-time agent execution progress."""
    queue = event_bus.subscribe(session_id)

    async def event_generator():
        try:
            # Send initial connected ping
            yield f"data: {json.dumps({'step': 'connected', 'status': 'online', 'message': 'Connected to agent event stream'})}\n\n"
            while True:
                ev: WorkflowProgressEvent = await queue.get()
                yield f"data: {json.dumps(ev.model_dump())}\n\n"
        except asyncio.CancelledError:
            event_bus.unsubscribe(session_id, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/workspace/{workspace_id}")
async def get_workspace_info(workspace_id: str):
    """Inspect files and modifications inside a workspace."""
    ws = workspace_manager.get_workspace(workspace_id)
    if not ws:
        raise HTTPException(status_code=404, detail=f"Workspace '{workspace_id}' not found.")

    tree = mcp_client.server.execute_tool("view_tree", {"max_depth": 3}, ws)
    diff = mcp_client.server.execute_tool("git_diff", {}, ws)
    modifications = ws.get_modified_files()

    return {
        "workspace_id": workspace_id,
        "tree": tree.output,
        "diff": diff.output,
        "modified_files": modifications,
    }


@router.post("/config")
async def update_config(payload: Dict[str, Any]):
    """Update active LLM credentials or provider configuration at runtime."""
    if "gemini_api_key" in payload and payload["gemini_api_key"]:
        settings.GEMINI_API_KEY = payload["gemini_api_key"]
    if "openai_api_key" in payload and payload["openai_api_key"]:
        settings.OPENAI_API_KEY = payload["openai_api_key"]
    if "llm_provider" in payload and payload["llm_provider"]:
        settings.LLM_PROVIDER = payload["llm_provider"].lower()

    # Re-test active provider
    llm = get_llm_provider()
    return {
        "success": True,
        "provider": llm.get_provider_name(),
        "model": llm.get_model_name(),
        "is_available": llm.is_available(),
    }
