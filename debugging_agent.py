"""Debugging Agent (Root compatibility wrapper)."""

from codepilot.config import settings
from codepilot.llm.factory import get_llm_provider
from codepilot.mcp.client import MCPClient
from codepilot.agents.debugging_agent import DebuggingAgent as CoreDebuggingAgent
from codepilot.models.schemas import AgentTask, AgentRole
from codepilot.workspace.manager import WorkspaceManager


class DebuggingAgent:
    """Wrapper around codepilot.agents.DebuggingAgent."""

    def __init__(self):
        self.llm = get_llm_provider()
        self.mcp = MCPClient()
        self.core_agent = CoreDebuggingAgent(self.llm, self.mcp)
        self.ws_mgr = WorkspaceManager()

    def run(self, task: str) -> dict:
        ws = self.ws_mgr.create_paste_workspace("# Code workspace\n")
        agent_task = AgentTask(
            task_id="debugging_root_task",
            role=AgentRole.DEBUGGING,
            objective=task,
            workspace_path=str(ws.root_path),
        )
        res = self.core_agent.run(agent_task, ws)
        return {
            "agent": "debugging",
            "task": task,
            "status": res.status.value,
            "summary": res.summary,
            "changes_made": res.changes_made,
            "evidence": res.evidence,
            "confidence": res.confidence,
        }


if __name__ == "__main__":
    agent = DebuggingAgent()
    task = input("\nDescribe the bug or error: ").strip()
    result = agent.run(task)
    print("\n" + "=" * 60)
    print("DEBUGGING AGENT RESULT")
    print("=" * 60)
    print(f"Summary: {result['summary']}")
    print(f"\nEvidence:\n{result['evidence']}")