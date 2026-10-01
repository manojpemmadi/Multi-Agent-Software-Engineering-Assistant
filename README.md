
# CodePilot — Production Multi-Agent Software Engineering Assistant

CodePilot is a production-level, LLM-based autonomous software engineering assistant. It provides an intuitive chatbot web interface where developers can paste broken source code, submit error traces, or supply a public GitHub repository URL. The system understands the request, inspects the codebase using a RAG knowledge retrieval subsystem, reasons about the problem, utilizes real external tools via the **Model Context Protocol (MCP)**, makes surgical and controlled modifications, runs automated test suites, and verifies the solution with an evidence-based final evaluation loop before presenting the answer to the user.

---

## 🏛️ System Architecture

CodePilot contains **exactly three specialized worker agents**, an **LLM-powered orchestrator & planner**, an **independent MCP tool server/client**, an **isolated workspace manager**, and a **RAG subsystem**.

```
                         ┌─────────────────────────────┐
                         │   CodePilot Web Interface   │
                         │ (Chatbot / Paste / Repo URL)│
                         └──────────────┬──────────────┘
                                        │ REST / SSE
                                        ▼
                         ┌─────────────────────────────┐
                         │       FastAPI Backend       │
                         └──────────────┬──────────────┘
                                        │
                                        ▼
                         ┌─────────────────────────────┐
                         │  Multi-Agent Orchestrator   │
                         │    + Dynamic LLM Planner    │
                         └──────────────┬──────────────┘
                                        │
                         Google Gemini Structured Plan
                                        │
             ┌──────────────────────────┼──────────────────────────┐
             ▼                          ▼                          ▼
    ┌─────────────────┐       ┌──────────────────┐       ┌──────────────────┐
    │  Code Analysis  │       │ Debugging/Fixing │       │Testing/Validation│
    │      Agent      │       │      Agent       │       │      Agent       │
    │(Structure & AST)│       │(Root-Cause/Patch)│       │(Pytest / Evidence│
    └────────┬────────┘       └─────────┬────────┘       └─────────┬────────┘
             │                          │                          │
             └──────────────────────────┼──────────────────────────┘
                                        │
                                        ▼
                         ┌─────────────────────────────┐
                         │          MCP Layer          │
                         │   (Model Context Protocol)  │
                         │  - Independent Permissions  │
                         │  - JSON Schema Validation   │
                         └──────────────┬──────────────┘
                                        │
             ┌──────────────────────────┼──────────────────────────┐
             ▼                          ▼                          ▼
      File & Search Tools        Controlled Edit Tools     Safe Terminal & Tests
      - list_files               - write_file              - run_command (sandbox)
      - view_tree                - replace_file_content    - run_tests (pytest)
      - read_file                                          - git_status / git_diff
      - search_code (grep)
                                        │
                                        ▼
                         ┌─────────────────────────────┐
                         │     Isolated Workspace      │
                         │ (Path Traversal & Sandbox)  │
                         └──────────────┬──────────────┘
                                        │
                                        ▼
                         ┌─────────────────────────────┐
                         │        RAG Subsystem        │
                         │  - AST & Semantic Chunker   │
                         │  - MiniLM / ChromaDB Store  │
                         │  - Context Retriever        │
                         └──────────────┬──────────────┘
                                        │
                                        ▼
                         ┌─────────────────────────────┐
                         │    Final Evaluation Loop    │
                         │ (Evidence-Based Validation) │
                         └──────────────┬──────────────┘
                                        │
                          ┌─────────────┴─────────────┐
                          ▼                           ▼
                        PASS                        FAIL
                          │                           │
                          ▼                           ▼
                  User Solution Card          Bounded Retries
```

---

## 🌟 Key Capabilities

### 1. Dynamic LLM Planning (Zero Keyword Routing)
The orchestrator never relies on hardcoded `if "debug" in task` rules. Instead, it prompts Google Gemini with the task description, workspace context, and the **Agent Registry** (which defines each agent's domain and allowed tools) to generate a structured, dependency-ordered DAG (`ExecutionPlan`). The plan is strictly validated against the registry before execution.

### 2. Specialized Worker Agents
- **🔍 Code Analysis Agent**: Inspects unfamiliar repositories, traces execution flows, searches functions/classes via RAG and MCP tools, and provides structured architecture/defect findings.
- **🛠️ Debugging/Fixing Agent**: Investigates root causes rather than guessing, produces controlled surgical patches, modifies files using MCP tools, and validates syntax. Never claims a bug is fixed without validation.
- **🧪 Testing/Validation Agent**: Determines test requirements, creates comprehensive test cases (normal, edge, and failure scenarios), executes test suites via MCP test runners, and categorizes failures (`fix_failure`, `syntax_error`, `environment_failure`, `unrelated_failure`).

### 3. Genuine Model Context Protocol (MCP) Layer
Agents interact with the outside world exclusively through standard Model Context Protocol (MCP) tools:
- **Independent Permissions**: Enforced in Python code, preventing the LLM from executing unauthorized tools (e.g. Code Analysis Agent cannot call `write_file` or `run_command`).
- **Sandboxed Execution**: Subprocess commands run inside the isolated workspace root with timeouts and dangerous command blocking (`rm -rf /`, `format`, network exfiltration).
- **Environment Sanitization**: Sensitive environment variables (`GEMINI_API_KEY`, etc.) are stripped from sub-shells.

### 4. Codebase RAG Subsystem
- Clones public GitHub repositories or loads multi-file workspaces into isolated directory sandboxes.
- Ignores `.git`, `.venv`, `node_modules`, build artifacts, and caches.
- AST-aware chunking detects function and class boundaries, extracting rich metadata (line numbers, symbols, file paths).
- Persists dense vector embeddings into ChromaDB for semantic similarity retrieval.

### 5. Final Evaluation & Bounded Retries Loop
Before displaying results, the **FinalEvaluator** examines tangible tool evidence (test results, diffs, syntax checks). If tests fail or modifications are absent, the orchestrator triggers a targeted retry cycle, feeding the failure trace back to the Debugging Agent to revise the fix, bounded to a maximum of 3 attempts to prevent infinite loops.

### 6. Clean, Swappable LLM Service Interface
All LLM operations are isolated behind the `BaseLLMService` abstract class. Google Gemini (`gemini-2.5-flash`) is the primary provider using the official `google-genai` SDK, with built-in swappable providers for OpenAI and an offline deterministic mock provider for testing.

---

## 🚀 Getting Started

### Prerequisites
- Python 3.10+
- Git installed on your system
- A Google Gemini API key from [Google AI Studio](https://aistudio.google.com/)

### 1. Installation
Clone the repository and install dependencies in a virtual environment:

```bash
# Clone the repository
git clone https://github.com/your-username/codepilot.git
cd codepilot

# Activate virtual environment
# Windows:
.\venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Environment Configuration
Copy the template configuration file:

```bash
cp .env.example .env
```

Edit `.env` to supply your API credentials:

```env
# LLM Provider: 'gemini', 'openai', or 'mock'
LLM_PROVIDER=gemini

# Google Gemini API Key
GEMINI_API_KEY=AIzaSyYourGeminiApiKeyHere
GEMINI_MODEL=gemini-2.5-flash

# Optional alternative provider
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini

# Server & Storage
HOST=127.0.0.1
PORT=8000
CHROMA_DIR=chroma_db
WORKSPACES_DIR=.workspaces
```

### 3. Launching the Web Interface
Start the FastAPI server and chatbot UI:

```bash
python run.py --web
```

Open your browser to: **`http://127.0.0.1:8000`**

### 4. Launching the Interactive CLI
Alternatively, run the assistant directly in your terminal:

```bash
python run.py --cli
```

---

## 🧪 Running Automated Tests

Run the complete test suite (22 unit & integration tests covering MCP permissions, sandboxing, RAG, planning, and end-to-end workflows):

```bash
pytest tests/ -v
```

---

## 💻 Example End-to-End Walkthrough

### Scenario: Broken Code Snippet
1. User enters:
   > *"This code is throwing a syntax error; correct it and make sure it works."*
2. User pastes:
   ```python
   def calculate_discount(price, discount_rate)
       if discount_rate < 0 or discount_rate > 1:
           raise ValueError("Invalid discount rate")
       return price * (1 - discount_rate)
   ```
3. **Orchestrator** creates an isolated workspace `paste_a1b2c3d4/main.py`.
4. **LLM Planner** formulates a structured execution plan:
   - Step 1: `CodeAnalysisAgent` -> Inspect workspace and defect.
   - Step 2: `DebuggingAgent` -> Fix syntax error and write updated `main.py`.
   - Step 3: `TestingAgent` -> Generate test cases and run `pytest`.
5. **Debugging Agent** uses MCP `read_file` to diagnose the missing colon, applies surgical fix via MCP `write_file`, and validates syntax with `python -m py_compile`.
6. **Testing Agent** constructs a unit test file `test_main.py` and executes `pytest -v` via MCP `run_tests`.
7. **Final Evaluator** confirms:
   - Code inspected: ✅
   - Modifications applied: ✅
   - Tests executed: ✅ (2 passed, 0 failed)
   - Quality Score: 0.95/1.00
8. Chatbot displays the corrected code block, unified diff, and pytest execution output to the user.

---

## 🛡️ Security & Sandboxing

CodePilot enforces defense-in-depth when dealing with untrusted user code or external GitHub repositories:
- **Path Traversal Guards**: All file access is validated with `Workspace.resolve_safe_path()`, preventing access outside `.workspaces/<session_id>`.
- **Blocked Dangerous Commands**: Prohibits shell commands matching dangerous patterns (`rm -rf /`, `mkfs`, fork bombs, system alteration).
- **Process Timeouts**: Subprocess execution times out after 45 seconds to prevent infinite loops.
- **Secret Redaction**: Child processes run in sanitized environments where API keys and tokens are stripped from environment variables.
- **Independent MCP Tool Authorization**: Agent roles cannot grant themselves capabilities beyond their registry boundaries.

---

## 📁 Repository Structure

```
├── codepilot/
│   ├── api/             # FastAPI backend, routes, SSE streaming
│   ├── agents/          # BaseAgent, CodeAnalysisAgent, DebuggingAgent, TestingAgent
│   ├── orchestrator/    # MultiAgentOrchestrator, LLMPlanner, AgentRegistry, FinalEvaluator
│   ├── mcp/             # Model Context Protocol server, client, role permissions & tools
│   ├── rag/             # Scanner, AST code chunker, SentenceTransformers, ChromaDB retriever
│   ├── workspace/       # Isolated sandbox workspace manager & ecosystem detector
│   ├── llm/             # Swappable LLM providers (Gemini, OpenAI, Mock) & factory
│   ├── models/          # Pydantic schemas for tasks, plans, results, validation, events
│   └── frontend/        # Modern single-page web interface (HTML/CSS/JS)
├── tests/               # 22 Unit and integration tests
├── .env.example         # Environment template
├── run.py               # Application entry point (--web or --cli)
└── README.md            # Comprehensive documentation
```
>>>>>>> bac0a9f (Initial commit: Production-level CodePilot multi-agent SE assistant)
