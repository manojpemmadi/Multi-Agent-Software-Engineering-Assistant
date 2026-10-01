"""CodePilot Main Entry Point: CLI or Web Server."""

import argparse
import sys
import uvicorn
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from codepilot.config import settings
from codepilot.models.schemas import InputMode, UserRequest, WorkflowProgressEvent
from codepilot.orchestrator.orchestrator import MultiAgentOrchestrator

console = Console()


def run_cli():
    """Interactive command-line interface for CodePilot."""
    console.print(
        Panel.fit(
            "[bold cyan]CodePilot[/bold cyan] — Production Multi-Agent Software Engineering Assistant\n"
            f"[dim]Provider: {settings.LLM_PROVIDER} | Gemini Model: {settings.GEMINI_MODEL}[/dim]",
            border_style="cyan",
        )
    )

    orchestrator = MultiAgentOrchestrator()

    while True:
        try:
            console.print("\n[bold green]Choose Mode:[/bold green] [1] Paste Code / Fix Bug  [2] GitHub Repository  [3] Exit")
            choice = input("Select [1-3]: ").strip()

            if choice == "3" or choice.lower() in ("exit", "quit"):
                console.print("[yellow]Exiting CodePilot...[/yellow]")
                break

            if choice == "2":
                repo_url = input("Enter public GitHub repository URL: ").strip()
                task_msg = input("Describe the task / issue: ").strip()
                req = UserRequest(
                    message=task_msg,
                    input_mode=InputMode.GITHUB_REPO,
                    github_url=repo_url,
                )
            else:
                console.print("Paste your source code (press Enter twice or type END on a new line to finish):")
                lines = []
                while True:
                    line = input()
                    if line == "END" or (not line and lines and not lines[-1]):
                        break
                    lines.append(line)
                code_snippet = "\n".join(lines)
                task_msg = input("Describe the defect, error, or requested change: ").strip()
                err_msg = input("Error message (optional): ").strip()

                req = UserRequest(
                    message=task_msg,
                    input_mode=InputMode.PASTE_CODE,
                    code_snippet=code_snippet,
                    error_message=err_msg or None,
                )

            console.print("\n[bold cyan]Starting Multi-Agent Workflow...[/bold cyan]")

            def _cli_event_callback(ev: WorkflowProgressEvent):
                status_color = "green" if ev.status == "success" else ("yellow" if ev.status == "warning" else "cyan")
                prefix = f"[{status_color}]{ev.status.upper()}[/{status_color}]"
                agent_tag = f"[bold magenta][{ev.agent}][/bold magenta] " if ev.agent else ""
                console.print(f"  • {prefix} {agent_tag}{ev.message}")

            result = orchestrator.run(req, event_callback=_cli_event_callback)

            console.print("\n" + "=" * 65)
            console.print(f"[bold {'green' if result.success else 'red'}]FINAL RESULT: {'SUCCESS' if result.success else 'WARNING'}[/bold {'green' if result.success else 'red'}]")
            console.print("=" * 65)
            console.print(f"\n[bold]Summary:[/bold] {result.summary}")

            if result.solution_code:
                console.print(f"\n[bold cyan]Solution Code ({result.solution_language}):[/bold cyan]")
                console.print(Panel(result.solution_code, border_style="green"))

            if result.files_modified:
                console.print(f"\n[bold yellow]Modified Files ({len(result.files_modified)}):[/bold yellow]")
                for f in result.files_modified:
                    console.print(f" - {f['file_path']} ({f.get('summary', '')})")

            if result.test_evidence:
                console.print(f"\n[bold magenta]Test Evidence:[/bold magenta]")
                console.print(f"  Framework: {result.test_evidence.test_framework}")
                console.print(f"  Outcome: {'[green]PASSED[/green]' if result.test_evidence.passed else '[red]FAILED[/red]'}")
                console.print(f"  Passed: {result.test_evidence.passed_tests}, Failed: {result.test_evidence.failed_tests}")

        except (KeyboardInterrupt, EOFError):
            console.print("\n[yellow]Session ended.[/yellow]")
            break
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")


def run_web():
    """Start the FastAPI backend with uvicorn and serve the chatbot UI."""
    console.print(
        f"[bold cyan]Starting CodePilot Web Assistant on http://{settings.HOST}:{settings.PORT}[/bold cyan]"
    )
    uvicorn.run(
        "codepilot.api.app:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )


def main():
    parser = argparse.ArgumentParser(description="CodePilot Multi-Agent Assistant")
    parser.add_argument("--web", action="store_true", help="Launch the web chatbot interface (default)")
    parser.add_argument("--cli", action="store_true", help="Launch interactive command-line interface")
    parser.add_argument("--host", type=str, default=settings.HOST, help="Web server host")
    parser.add_argument("--port", type=int, default=settings.PORT, help="Web server port")

    args = parser.parse_args()

    if args.cli:
        run_cli()
    else:
        run_web()


if __name__ == "__main__":
    main()
