// CodePilot Frontend Application Logic

let currentMode = "paste_code";
let eventSource = null;

document.addEventListener("DOMContentLoaded", () => {
  initHealthCheck();
  initTabs();
  initScenarios();
  initSettingsModal();
  initRunAction();
});

// 1. Health check & provider status
async function initHealthCheck() {
  try {
    const res = await fetch("/api/health");
    if (!res.ok) return;
    const data = await res.json();
    
    const nameEl = document.getElementById("providerName");
    const dotEl = document.getElementById("providerDot");
    const toolsEl = document.getElementById("toolsBadge");

    nameEl.textContent = `${data.provider.toUpperCase()} (${data.model})`;
    toolsEl.textContent = `MCP Tools: ${data.total_mcp_tools} Active`;

    if (data.is_available) {
      dotEl.style.backgroundColor = "var(--success)";
    } else {
      dotEl.style.backgroundColor = "var(--danger)";
      nameEl.textContent += " (Unconfigured)";
    }
  } catch (err) {
    console.warn("Health check failed:", err);
  }
}

// 2. Tab Navigation
function initTabs() {
  const tabs = document.querySelectorAll(".mode-tab");
  tabs.forEach(tab => {
    tab.addEventListener("click", () => {
      tabs.forEach(t => t.classList.remove("active"));
      tab.classList.add("active");
      currentMode = tab.dataset.mode;

      document.getElementById("pasteInputs").style.display = (currentMode === "paste_code") ? "block" : "none";
      document.getElementById("repoInputs").style.display = (currentMode === "github_repo") ? "block" : "none";
      document.getElementById("scenariosInputs").style.display = (currentMode === "scenarios") ? "block" : "none";
    });
  });
}

// 3. Pre-configured scenarios
function initScenarios() {
  document.getElementById("demoSyntax").addEventListener("click", () => {
    document.getElementById("tabPaste").click();
    document.getElementById("taskMessage").value = "This code throws a syntax error on execution; fix it and verify with tests.";
    document.getElementById("codeLanguage").value = "python";
    document.getElementById("codeSnippet").value = `def calculate_discount(price, discount_rate)
    if discount_rate < 0 or discount_rate > 1:
        raise ValueError("Invalid discount rate")
    return price * (1 - discount_rate)

def main():
    final_price = calculate_discount(100, 0.2)
    print(f"Final price: {final_price}")

if __name__ == "__main__":
    main()`;
    document.getElementById("errorMessage").value = "SyntaxError: expected ':' at line 1";
  });

  document.getElementById("demoApi").addEventListener("click", () => {
    document.getElementById("tabPaste").click();
    document.getElementById("taskMessage").value = "My login authentication API returns 500 when username is valid. Fix the defect and validate.";
    document.getElementById("codeLanguage").value = "python";
    document.getElementById("codeSnippet").value = `users_db = {
    "alice": {"password_hash": "hash_123", "role": "admin"}
}

def authenticate(username, password_attempt):
    user = users_db.get(username)
    if not user:
        return False
    # Bug: looking up 'hashed_password' instead of 'password_hash'
    return user["hashed_password"] == f"hash_{password_attempt}"

def test_login():
    assert authenticate("alice", "123") is True
    assert authenticate("bob", "123") is False`;
    document.getElementById("errorMessage").value = "KeyError: 'hashed_password' in authenticate";
  });

  document.getElementById("demoTests").addEventListener("click", () => {
    document.getElementById("tabPaste").click();
    document.getElementById("taskMessage").value = "Generate comprehensive test coverage including normal, edge, and boundary cases.";
    document.getElementById("codeLanguage").value = "python";
    document.getElementById("codeSnippet").value = `def parse_version(version_str: str) -> tuple:
    '''Parse a semver string like '1.2.3' into (1, 2, 3).'''
    parts = version_str.strip().split('.')
    if len(parts) != 3:
        raise ValueError(f"Invalid semver: {version_str}")
    return tuple(int(p) for p in parts)`;
    document.getElementById("errorMessage").value = "";
  });
}

// 4. Run Action & SSE Pipeline
function initRunAction() {
  const runBtn = document.getElementById("runBtn");
  const welcomeState = document.getElementById("welcomeState");
  const timelineCard = document.getElementById("timelineCard");
  const timelineSteps = document.getElementById("timelineSteps");
  const resultsCard = document.getElementById("resultsCard");

  runBtn.addEventListener("click", async () => {
    runBtn.disabled = true;
    welcomeState.style.display = "none";
    timelineCard.style.display = "block";
    timelineSteps.innerHTML = "";
    resultsCard.style.display = "none";

    const sessionId = "session_" + Math.random().toString(36).substring(2, 9);

    // Prepare Request Payload
    let payload = {
      session_id: sessionId,
      input_mode: currentMode === "github_repo" ? "github_repo" : "paste_code",
    };

    if (currentMode === "github_repo") {
      payload.github_url = document.getElementById("githubUrl").value.trim();
      payload.message = document.getElementById("repoTaskMessage").value.trim();
    } else {
      payload.message = document.getElementById("taskMessage").value.trim();
      payload.code_snippet = document.getElementById("codeSnippet").value;
      payload.code_language = document.getElementById("codeLanguage").value;
      payload.error_message = document.getElementById("errorMessage").value.trim();
    }

    // Connect SSE for live streaming updates
    if (eventSource) eventSource.close();
    eventSource = new EventSource(`/api/events/${sessionId}`);

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.step === "connected") return;
        renderTimelineStep(data);
      } catch (e) {
        console.error("SSE parse error:", e);
      }
    };

    try {
      const resp = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      const finalResult = await resp.json();
      renderFinalResult(finalResult);
    } catch (err) {
      alert("Execution error: " + err.message);
    } finally {
      runBtn.disabled = false;
      if (eventSource) eventSource.close();
    }
  });

  // Copy code handler
  document.getElementById("copyCodeBtn").addEventListener("click", () => {
    const code = document.getElementById("solutionCode").textContent;
    navigator.clipboard.writeText(code);
    const btn = document.getElementById("copyCodeBtn");
    btn.textContent = "✓ Copied!";
    setTimeout(() => { btn.textContent = "📋 Copy"; }, 2000);
  });
}

function renderTimelineStep(step) {
  const stepsContainer = document.getElementById("timelineSteps");
  const existing = document.getElementById(`step-${step.step}`);

  const statusIcons = {
    running: "🔄",
    success: "✅",
    warning: "⚠️",
    failure: "❌",
  };
  const icon = statusIcons[step.status] || "ℹ️";

  if (existing) {
    existing.className = `step-item ${step.status}`;
    existing.querySelector(".step-icon").textContent = icon;
    existing.querySelector(".step-detail").textContent = step.message;
  } else {
    const item = document.createElement("div");
    item.id = `step-${step.step}`;
    item.className = `step-item ${step.status}`;
    item.innerHTML = `
      <span class="step-icon">${icon}</span>
      <div class="step-content">
        <div class="step-name">${(step.agent ? `[${step.agent.toUpperCase()}] ` : "") + step.step.replace(/_/g, ' ').toUpperCase()}</div>
        <div class="step-detail">${step.message}</div>
      </div>
    `;
    stepsContainer.appendChild(item);
  }
}

function renderFinalResult(res) {
  const card = document.getElementById("resultsCard");
  card.style.display = "block";

  const successIcon = document.getElementById("resultSuccessIcon");
  const heading = document.getElementById("resultHeading");
  const scoreBadge = document.getElementById("evalScoreBadge");
  const summaryBox = document.getElementById("resultSummary");
  const codeSection = document.getElementById("codeSection");
  const solutionCode = document.getElementById("solutionCode");
  const diffSection = document.getElementById("diffSection");
  const diffContent = document.getElementById("diffContent");
  const testBox = document.getElementById("testBox");
  const testOutcome = document.getElementById("testOutcomePill");
  const testCommandLabel = document.getElementById("testCommandLabel");
  const testRawOutput = document.getElementById("testRawOutput");

  if (res.success) {
    successIcon.textContent = "✅";
    heading.textContent = "Solution Validated & Verified";
    scoreBadge.style.backgroundColor = "var(--success-bg)";
    scoreBadge.style.color = "var(--success)";
  } else {
    successIcon.textContent = "⚠️";
    heading.textContent = "Execution Complete with Warnings";
    scoreBadge.style.backgroundColor = "var(--warning-bg)";
    scoreBadge.style.color = "var(--warning)";
  }

  const score = res.evaluation ? res.evaluation.quality_score : 1.0;
  scoreBadge.textContent = `Quality Score: ${score.toFixed(2)}`;
  summaryBox.textContent = res.summary || "All agent objectives executed.";

  // Solution Code
  if (res.solution_code) {
    codeSection.style.display = "block";
    solutionCode.textContent = res.solution_code;
    document.getElementById("codeLangLabel").textContent = (res.solution_language || "python").toUpperCase();
  } else {
    codeSection.style.display = "none";
  }

  // Modified Files Diffs
  if (res.files_modified && res.files_modified.length > 0) {
    diffSection.style.display = "block";
    let diffLines = [];
    res.files_modified.forEach(f => {
      diffLines.push(`--- FILE: ${f.file_path} ---`);
      diffLines.push(f.diff || "(No textual diff)");
    });
    diffContent.textContent = diffLines.join("\n\n");
  } else {
    diffSection.style.display = "none";
  }

  // Test Evidence
  if (res.test_evidence) {
    testBox.style.display = "block";
    const passed = res.test_evidence.passed;
    testOutcome.textContent = passed ? "PASSED" : "FAILED";
    testOutcome.className = passed ? "test-pass" : "test-fail";
    testCommandLabel.textContent = `Test Command: ${res.test_evidence.test_command || "pytest -v"}`;
    testRawOutput.textContent = res.test_evidence.raw_output || "Tests executed cleanly.";
  } else {
    testBox.style.display = "none";
  }
}

// 5. Settings Modal Handlers
function initSettingsModal() {
  const modal = document.getElementById("settingsModal");
  document.getElementById("openSettingsBtn").addEventListener("click", () => {
    modal.classList.add("active");
  });
  document.getElementById("closeSettingsBtn").addEventListener("click", () => {
    modal.classList.remove("active");
  });
  document.getElementById("saveSettingsBtn").addEventListener("click", async () => {
    const provider = document.getElementById("settingProvider").value;
    const geminiKey = document.getElementById("settingGeminiKey").value.trim();
    const openaiKey = document.getElementById("settingOpenaiKey").value.trim();

    const res = await fetch("/api/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        llm_provider: provider,
        gemini_api_key: geminiKey || undefined,
        openai_api_key: openaiKey || undefined,
      }),
    });

    if (res.ok) {
      modal.classList.remove("active");
      initHealthCheck();
    }
  });
}
