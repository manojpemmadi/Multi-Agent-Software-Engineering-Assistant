"""Code Analysis Agent (Root compatibility wrapper)."""

from codepilot.config import settings
from codepilot.llm.factory import get_llm_provider
from codepilot.mcp.client import MCPClient
from codepilot.agents.code_analysis_agent import CodeAnalysisAgent as CoreCodeAnalysisAgent
from codepilot.models.schemas import AgentTask, AgentRole
from codepilot.workspace.manager import WorkspaceManager


class CodeAnalysisAgent:
    """Wrapper around codepilot.agents.CodeAnalysisAgent."""

    def __init__(self):
        self.llm = get_llm_provider()
        self.mcp = MCPClient()
        self.core_agent = CoreCodeAnalysisAgent(self.llm, self.mcp)
        self.ws_mgr = WorkspaceManager()

    def run(self, task: str) -> dict:
        ws = self.ws_mgr.create_paste_workspace("# Temporary analysis workspace\n")
        agent_task = AgentTask(
            task_id="analysis_root_task",
            role=AgentRole.CODE_ANALYSIS,
            objective=task,
            workspace_path=str(ws.root_path),
        )
        res = self.core_agent.run(agent_task, ws)
        return {
            "agent": "code_analysis",
            "task": task,
            "status": res.status.value,
            "summary": res.summary,
            "evidence": res.evidence,
            "files_inspected": res.files_inspected,
            "confidence": res.confidence,
        }


if __name__ == "__main__":
    agent = CodeAnalysisAgent()
    task = input("\nAsk something about the codebase: ").strip()
    result = agent.run(task)
    print("\n" + "=" * 60)
    print("CODE ANALYSIS RESULT")
    print("=" * 60)
    print(f"Summary: {result['summary']}")
    print(f"\nEvidence:\n{result['evidence']}")