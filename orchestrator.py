"""CodePilot Multi-Agent Orchestrator (Root compatibility wrapper)."""

import sys
from codepilot.config import settings
from codepilot.models.schemas import InputMode, UserRequest
from codepilot.orchestrator.orchestrator import MultiAgentOrchestrator


class Orchestrator:
    """Production orchestrator delegating to codepilot.orchestrator."""

    def __init__(self):
        print(f"[Orchestrator] Initializing CodePilot Multi-Agent System ({settings.LLM_PROVIDER})...")
        self._orchestrator = MultiAgentOrchestrator()
        print("[Orchestrator] Agents initialized and registered: Code Analysis, Debugging, Testing.")

    def run(self, task: str) -> dict:
        if not task.strip():
            raise ValueError("Task cannot be empty.")

        print(f"\n[Orchestrator] Received task: {task}")
        req = UserRequest(
            message=task,
            input_mode=InputMode.GENERAL_QUERY,
        )

        final_res = self._orchestrator.run(req)

        return {
            "status": "success" if final_res.success else "warning",
            "task": task,
            "summary": final_res.summary,
            "solution_code": final_res.solution_code,
            "modified_files": final_res.files_modified,
            "validation": final_res.test_evidence.model_dump() if final_res.test_evidence else None,
            "timeline": final_res.execution_timeline,
        }


def main():
    orchestrator = Orchestrator()

    print("\n" + "=" * 60)
    print("CODEPILOT — Multi-Agent Software Engineering Assistant")
    print(f"Provider: {settings.LLM_PROVIDER} | Model: {settings.GEMINI_MODEL}")
    print("=" * 60)

    while True:
        try:
            task = input("\nCodePilot > ").strip()
            if task.lower() in {"exit", "quit"}:
                print("\nExiting CodePilot...")
                break

            response = orchestrator.run(task)

            print("\n" + "=" * 60)
            print("ORCHESTRATOR RESULT")
            print("=" * 60)
            print(f"Status: {response['status']}")
            print(f"Summary: {response['summary']}")

            if response.get("solution_code"):
                print("\n--- SOLUTION CODE ---")
                print(response["solution_code"])

            if response.get("validation"):
                print("\n--- VALIDATION EVIDENCE ---")
                v = response["validation"]
                print(f"Passed: {v.get('passed')} ({v.get('passed_tests')}/{v.get('total_tests')} tests)")
                print(f"Command: {v.get('test_command')}")

        except (KeyboardInterrupt, EOFError):
            print("\nSession ended.")
            break
        except Exception as error:
            print(f"\n[Orchestrator Error]: {error}")


if __name__ == "__main__":
    main()