"""Testing Agent (Root compatibility wrapper)."""

from codepilot.config import settings
from codepilot.llm.factory import get_llm_provider
from codepilot.mcp.client import MCPClient
from codepilot.agents.testing_agent import TestingAgent as CoreTestingAgent
from codepilot.models.schemas import AgentTask, AgentRole
from codepilot.workspace.manager import WorkspaceManager


class TestingAgent:
    """Wrapper around codepilot.agents.TestingAgent."""

    def __init__(self):
        self.llm = get_llm_provider()
        self.mcp = MCPClient()
        self.core_agent = CoreTestingAgent(self.llm, self.mcp)
        self.ws_mgr = WorkspaceManager()

    def run(self, task: str) -> dict:
        ws = self.ws_mgr.create_paste_workspace("# Code workspace\n")
        agent_task = AgentTask(
            task_id="testing_root_task",
            role=AgentRole.TESTING,
            objective=task,
            workspace_path=str(ws.root_path),
        )
        res = self.core_agent.run(agent_task, ws)
        return {
            "agent": "testing",
            "task": task,
            "status": res.status.value,
            "summary": res.summary,
            "validation": res.validation.model_dump() if res.validation else None,
            "evidence": res.evidence,
            "confidence": res.confidence,
        }


if __name__ == "__main__":
    agent = TestingAgent()
    task = input("\nDescribe what you want to test: ").strip()
    result = agent.run(task)
    print("\n" + "=" * 60)
    print("TESTING AGENT RESULT")
    print("=" * 60)
    print(f"Summary: {result['summary']}")
    print(f"\nEvidence:\n{result['evidence']}")