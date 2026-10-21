/**
 * Autonomous AI Research Assistant - Frontend Application
 * Handles multi-screen switching, SSE stream subscriptions, REST interactions,
 * real-time agent monitors, source discovery tables, verification matrix, and benchmark comparisons.
 */

const AppState = {
  activeScreen: "setup",
  currentProjectId: null,
  currentRunId: null,
  activeRunData: null,
  eventSource: null,
  systemStatus: null,
};

// Initialize application on DOM ready
document.addEventListener("DOMContentLoaded", async () => {
  setupNavigation();
  await loadSystemStatus();
  await loadProjects();
  setupForms();

  // Periodic health polling every 10 seconds to update badge dynamically without page reload
  setInterval(loadSystemStatus, 10000);
});

// Navigation handlers
function setupNavigation() {
  const navItems = document.querySelectorAll(".nav-item");
  navItems.forEach((item) => {
    item.addEventListener("click", (e) => {
      e.preventDefault();
      const targetScreen = item.getAttribute("data-screen");
      switchScreen(targetScreen);
    });
  });
}

function switchScreen(screenName) {
  AppState.activeScreen = screenName;

  // Update navigation items
  document.querySelectorAll(".nav-item").forEach((item) => {
    item.classList.toggle("active", item.getAttribute("data-screen") === screenName);
  });

  // Update view panels
  document.querySelectorAll(".view-panel").forEach((panel) => {
    panel.classList.toggle("active", panel.id === `view-${screenName}`);
  });

  // Load screen-specific data
  if (screenName === "sources") loadSources();
  if (screenName === "verification") loadVerificationResults();
  if (screenName === "report") loadReport();
  if (screenName === "history") loadHistoryAndBenchmarks();
  if (screenName === "monitor" && AppState.currentRunId) refreshRunStatus();
}

// System Status
async function loadSystemStatus() {
  try {
    const res = await fetch("/api/status");
    const data = await res.json();
    AppState.systemStatus = data;

    const badge = document.getElementById("provider-status-badge");
    const dot = document.getElementById("status-dot-indicator");
    const label = document.getElementById("provider-status-label");
    const ollamaBadge = document.getElementById("ollama-status-badge");

    const oHealth = data.ollama || data.ollama_health;

    // 1. Update Top Bar Ollama Connectivity Badge
    if (ollamaBadge) {
      if (data.llm.provider !== "ollama") {
        ollamaBadge.textContent = `Provider: ${data.llm.provider.toUpperCase()}`;
        ollamaBadge.style.color = "var(--text-secondary)";
        ollamaBadge.style.borderColor = "var(--border-subtle)";
      } else if (!oHealth) {
        ollamaBadge.textContent = "Ollama: Checking...";
        ollamaBadge.style.color = "var(--accent-cyan)";
        ollamaBadge.style.borderColor = "rgba(6, 182, 212, 0.4)";
      } else if (oHealth.reachable && oHealth.model_installed) {
        ollamaBadge.textContent = `Ollama: Online (${oHealth.configured_model})`;
        ollamaBadge.style.color = "var(--status-success)";
        ollamaBadge.style.borderColor = "rgba(16, 185, 129, 0.4)";
      } else if (oHealth.reachable && !oHealth.model_installed) {
        ollamaBadge.textContent = `Ollama: Model Missing (${oHealth.configured_model})`;
        ollamaBadge.style.color = "var(--status-warning)";
        ollamaBadge.style.borderColor = "rgba(245, 158, 11, 0.4)";
      } else if (!oHealth.reachable && oHealth.status === "timeout") {
        ollamaBadge.textContent = "Ollama: Timeout";
        ollamaBadge.style.color = "var(--status-error)";
        ollamaBadge.style.borderColor = "rgba(239, 68, 68, 0.4)";
      } else {
        ollamaBadge.textContent = "Ollama: Offline";
        ollamaBadge.style.color = "var(--status-error)";
        ollamaBadge.style.borderColor = "rgba(239, 68, 68, 0.4)";
      }
    }

    // 2. Update Sidebar Provider Mode Card
    if (data.llm.is_demo_mode) {
      badge.textContent = "DEMO MODE (OFFLINE ENGINE)";
      badge.className = "badge badge-info";
      label.textContent = "Demonstration Provider (Offline)";
      dot.className = "status-dot demo";
    } else if (data.llm.provider === "ollama") {
      if (oHealth && oHealth.reachable && oHealth.model_installed) {
        badge.textContent = `OLLAMA: ${data.llm.model}`;
        badge.className = "badge badge-success";
        label.textContent = `Local LLM Active @ ${oHealth.base_url || data.llm.base_url || 'http://localhost:11434'}`;
        dot.className = "status-dot";
      } else if (oHealth && oHealth.reachable && !oHealth.model_installed) {
        badge.textContent = `MODEL MISSING (${data.llm.model})`;
        badge.className = "badge badge-warning";
        label.textContent = `Run 'ollama pull ${data.llm.model}'`;
        dot.className = "status-dot warning";
      } else if (oHealth && oHealth.status === "timeout") {
        badge.textContent = "OLLAMA TIMEOUT";
        badge.className = "badge badge-error";
        label.textContent = `Timed out @ ${oHealth.base_url || 'http://localhost:11434'}`;
        dot.className = "status-dot offline";
      } else if (oHealth && oHealth.status === "error") {
        badge.textContent = "OLLAMA ERROR";
        badge.className = "badge badge-error";
        label.textContent = oHealth.message || "Health check failed";
        dot.className = "status-dot offline";
      } else {
        badge.textContent = "OLLAMA OFFLINE";
        badge.className = "badge badge-error";
        label.textContent = `Unreachable @ ${data.llm.base_url || 'http://localhost:11434'}`;
        dot.className = "status-dot offline";
      }
    } else {
      badge.textContent = `LIVE AI (${data.llm.model})`;
      badge.className = "badge badge-success";
      label.textContent = `${data.llm.provider} - ${data.llm.masked_key}`;
      dot.className = "status-dot";
    }
  } catch (e) {
    console.error("Failed to load system status", e);
  }
}

// Projects & Active Run Selection
async function loadProjects() {
  try {
    const res = await fetch("/api/projects");
    const projects = await res.json();
    const select = document.getElementById("project-select");
    select.innerHTML = '<option value="">-- Create New Project --</option>';

    projects.forEach((p) => {
      const opt = document.createElement("option");
      opt.value = p.id;
      opt.textContent = `${p.title} (${new Date(p.created_at).toLocaleDateString()})`;
      select.appendChild(opt);
    });

    if (projects.length > 0 && !AppState.currentProjectId) {
      AppState.currentProjectId = projects[0].id;
      select.value = projects[0].id;
      await selectProjectAndLatestRun(projects[0].id);
    }
  } catch (e) {
    console.error("Failed loading projects", e);
  }
}

async function selectProjectAndLatestRun(projectId) {
  try {
    const res = await fetch(`/api/projects/${projectId}`);
    if (!res.ok) return;
    const project = await res.json();
    AppState.currentProjectId = project.id;
    updateActiveProjectBadge(project.title);

    if (project.runs && project.runs.length > 0) {
      const latestRun = project.runs[0];
      AppState.currentRunId = latestRun.id;
      AppState.activeRunData = latestRun;
      updateActiveRunBadge(latestRun);
    } else {
      AppState.currentRunId = null;
      AppState.activeRunData = null;
      updateActiveRunBadge(null);
    }
  } catch (e) {
    console.error("Failed selecting project run", e);
  }
}

function updateActiveProjectBadge(title) {
  const badge = document.getElementById("active-project-badge");
  if (badge) badge.textContent = `Project: ${title}`;
}

function updateActiveRunBadge(run) {
  const badge = document.getElementById("active-run-badge");
  if (!badge) return;
  if (run && run.id) {
    badge.style.display = "inline-flex";
    const statusText = run.status ? ` (${run.status})` : "";
    badge.textContent = `Run: #${run.id.slice(0, 8)}${statusText}`;
  } else {
    badge.style.display = "none";
  }
}

// Form Handlers
function setupForms() {
  // Project selection change listener
  const projectSelect = document.getElementById("project-select");
  if (projectSelect) {
    projectSelect.addEventListener("change", async (e) => {
      const selectedId = e.target.value;
      if (selectedId) {
        await selectProjectAndLatestRun(selectedId);
      } else {
        AppState.currentProjectId = null;
        updateActiveProjectBadge("New Project");
        updateActiveRunBadge(null);
      }
    });
  }

  // Example prompt filler
  const exampleBtn = document.getElementById("btn-load-example");
  if (exampleBtn) {
    exampleBtn.addEventListener("click", () => {
      document.getElementById("research-question").value =
        "Compare Retrieval-Augmented Generation (RAG) and fine-tuning for domain-specific question answering. Evaluate accuracy, latency, cost, limitations, and research gaps using scholarly sources.";
      document.getElementById("research-topic").value = "Artificial Intelligence & LLMs";
    });
  }

  // Start Research Submission
  const startForm = document.getElementById("research-setup-form");
  if (startForm) {
    startForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      await handleStartResearch();
    });
  }

  // Cancel Button in Monitor
  const cancelBtn = document.getElementById("btn-cancel-run");
  if (cancelBtn) {
    cancelBtn.addEventListener("click", async () => {
      if (!AppState.currentRunId) return;
      if (confirm("Are you sure you want to cancel the active research execution?")) {
        await fetch(`/api/runs/${AppState.currentRunId}/cancel`, { method: "POST" });
        appendLogEntry("User requested run cancellation.");
      }
    });
  }
}

async function handleStartResearch() {
  const question = document.getElementById("research-question").value.trim();
  const topic = document.getElementById("research-topic").value.trim();
  const maxSources = parseInt(document.getElementById("max-sources").value, 10) || 8;
  const projectSelect = document.getElementById("project-select").value;

  if (question.length < 10) {
    alert("Please provide a sufficiently detailed research question (minimum 10 characters).");
    return;
  }

  // Search providers checkboxes
  const providers = [];
  if (document.getElementById("source-openalex").checked) providers.push("openalex");
  if (document.getElementById("source-arxiv").checked) providers.push("arxiv");

  let projectId = projectSelect;
  if (!projectId) {
    // Create new project
    const pTitle = topic || question.slice(0, 45) + "...";
    const pRes = await fetch("/api/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: pTitle, description: question }),
    });
    const newProj = await pRes.json();
    projectId = newProj.id;
    AppState.currentProjectId = projectId;
    await loadProjects();
  }

  const modeElem = document.getElementById("research-mode");
  const providerMode = modeElem ? modeElem.value : "ollama";

  // Start Run
  const submitBtn = document.getElementById("btn-start-research");
  submitBtn.disabled = true;
  submitBtn.textContent = "Initiating Run...";

  try {
    const runRes = await fetch(`/api/projects/${projectId}/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question: question,
        max_sources: maxSources,
        search_providers: providers,
        provider_mode: providerMode,
      }),
    });
    const run = await runRes.json();
    AppState.currentRunId = run.id;
    AppState.activeRunData = run;
    updateActiveRunBadge(run);

    // Reset monitor UI and connect SSE
    resetMonitorUI(run);
    subscribeToRunEvents(run.id);

    // Switch to monitor screen
    switchScreen("monitor");
  } catch (err) {
    alert("Failed to initiate research run: " + err.message);
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = "Start Research Run";
  }
}

// Server-Sent Events (SSE) Monitor
function subscribeToRunEvents(runId) {
  if (AppState.eventSource) {
    AppState.eventSource.close();
  }

  const sseUrl = `/api/runs/${runId}/events`;
  const es = new EventSource(sseUrl);
  AppState.eventSource = es;

  appendLogEntry(`Connected to live event stream for run #${runId.slice(0, 8)}`);

  es.addEventListener("STATE_CHANGED", (e) => {
    const payload = JSON.parse(e.data);
    handleStateChangedEvent(payload.data);
  });

  es.addEventListener("RUN_COMPLETED", (e) => {
    const payload = JSON.parse(e.data);
    appendLogEntry("Workflow successfully finished. Quality gates passed.");
    updateWorkflowStateBadge("COMPLETED");
    if (AppState.activeRunData) AppState.activeRunData.status = "COMPLETED";
    updateActiveRunBadge({ id: runId, status: "COMPLETED" });
    markAllAgentsFinished();
    es.close();
  });

  es.addEventListener("RUN_FAILED", (e) => {
    const payload = JSON.parse(e.data);
    appendLogEntry(`Workflow failed: ${payload.data.error}`);
    updateWorkflowStateBadge("FAILED");
    if (AppState.activeRunData) AppState.activeRunData.status = "FAILED";
    updateActiveRunBadge({ id: runId, status: "FAILED" });
    es.close();
  });

  es.addEventListener("RUN_CANCELLED", (e) => {
    appendLogEntry("Workflow cancelled by user action.");
    updateWorkflowStateBadge("CANCELLED");
    if (AppState.activeRunData) AppState.activeRunData.status = "CANCELLED";
    updateActiveRunBadge({ id: runId, status: "CANCELLED" });
    es.close();
  });

  es.onerror = () => {
    console.warn("SSE stream closed or error, polling status fallback...");
    refreshRunStatus();
  };
}

function handleStateChangedEvent(data) {
  const state = data.state;
  updateWorkflowStateBadge(state);
  if (AppState.currentRunId) {
    updateActiveRunBadge({ id: AppState.currentRunId, status: state });
  }

  if (data.message) {
    appendLogEntry(data.message);
  }

  // Update agent card highlight
  const agentMap = {
    PLANNING: "planner",
    RESEARCHING: "researcher",
    ANALYZING: "analyst",
    VERIFYING: "fact_checker",
    GENERATING_REPORT: "report_writer",
  };

  const activeAgent = agentMap[state];
  if (activeAgent) {
    setAgentCardStatus(activeAgent, "running", data.message || "Active execution...");
  }
}

function resetMonitorUI(run) {
  document.getElementById("monitor-question-display").textContent = run.question;
  updateWorkflowStateBadge(run.status || "PLANNING");
  document.getElementById("terminal-logs").innerHTML = "";

  const agents = ["planner", "researcher", "analyst", "fact_checker", "report_writer"];
  agents.forEach((a) => {
    setAgentCardStatus(a, "idle", "Awaiting execution trigger...");
  });
}

function updateWorkflowStateBadge(state) {
  const badge = document.getElementById("run-state-badge");
  if (!badge) return;
  badge.textContent = `State: ${state}`;

  badge.className = "badge";
  if (state === "COMPLETED") badge.classList.add("badge-success");
  else if (state === "FAILED" || state === "CANCELLED") badge.classList.add("badge-error");
  else badge.classList.add("badge-info");
}

function setAgentCardStatus(agentKey, status, taskText) {
  const card = document.getElementById(`agent-card-${agentKey}`);
  if (!card) return;

  card.className = "agent-card";
  if (status === "running") card.classList.add("running");
  if (status === "completed") card.classList.add("completed");

  const taskElem = card.querySelector(".agent-task");
  if (taskElem && taskText) taskElem.textContent = taskText;

  const badgeElem = card.querySelector(".agent-badge");
  if (badgeElem) badgeElem.textContent = status.toUpperCase();
}

function markAllAgentsFinished() {
  const agents = ["planner", "researcher", "analyst", "fact_checker", "report_writer"];
  agents.forEach((a) => setAgentCardStatus(a, "completed", "Completed successfully"));
}

function appendLogEntry(text) {
  const box = document.getElementById("terminal-logs");
  if (!box) return;
  const timeStr = new Date().toLocaleTimeString();
  const line = document.createElement("div");
  line.className = "log-entry";
  line.innerHTML = `<span class="log-time">[${timeStr}]</span> <span>${escapeHtml(text)}</span>`;
  box.appendChild(line);
  box.scrollTop = box.scrollHeight;
}

async function refreshRunStatus() {
  if (!AppState.currentRunId) return;
  try {
    const res = await fetch(`/api/runs/${AppState.currentRunId}`);
    const data = await res.json();
    AppState.activeRunData = data;
    updateWorkflowStateBadge(data.status);
    updateActiveRunBadge(data);
    if (data.tasks) {
      data.tasks.forEach((t) => {
        setAgentCardStatus(t.agent_name, t.status.toLowerCase(), t.task_name);
      });
    }
  } catch (e) {
    console.error("Failed refreshing run status", e);
  }
}

// Source Explorer Screen
async function loadSources() {
  const tbody = document.getElementById("sources-table-body");
  if (!tbody) return;

  if (!AppState.currentRunId) {
    tbody.innerHTML = '<tr><td colspan="7" class="empty-state">No research run active. Select or start a run in Setup first.</td></tr>';
    return;
  }

  tbody.innerHTML = '<tr><td colspan="7" style="text-align:center; padding:20px;">Loading harvested sources for active run...</td></tr>';

  try {
    const res = await fetch(`/api/runs/${AppState.currentRunId}/sources`);
    const sources = await res.json();

    if (sources.length === 0) {
      tbody.innerHTML = '<tr><td colspan="7" class="empty-state">No sources retrieved yet for this run.</td></tr>';
      return;
    }

    tbody.innerHTML = "";
    sources.forEach((s, idx) => {
      const tr = document.createElement("tr");

      const isDemo = s.provider === "demo" || (s.title && s.title.startsWith("[DEMO"));
      let repoBadge;
      if (isDemo) {
        repoBadge = '<span class="badge badge-warning" style="font-size:0.72rem;">DEMO</span>';
      } else {
        repoBadge = `<span class="badge badge-info" style="font-size:0.72rem;">${escapeHtml((s.provider || 'openalex').toUpperCase())}</span>`;
      }

      // Relevance Evaluation Badge and Details
      const rel = s.relevance;
      let relevanceHtml = '<span style="color:#94a3b8; font-size:0.8rem;">Unassessed</span>';
      if (rel) {
        let decBadgeClass = "badge-neutral";
        if (rel.decision === "INCLUDE") decBadgeClass = "badge-success";
        else if (rel.decision === "REVIEW") decBadgeClass = "badge-warning";
        else if (rel.decision === "EXCLUDE") decBadgeClass = "badge-error";

        relevanceHtml = `
          <div style="display:flex; align-items:center; gap:6px; margin-bottom:3px;">
            <span class="badge ${decBadgeClass}" style="font-size:0.72rem; font-weight:700;">${rel.decision}</span>
            <span style="font-weight:700; color:#fff; font-size:0.85rem;">${rel.relevance_score}/100</span>
          </div>
          <div style="font-size:0.72rem; color:#94a3b8;" title="Component Breakdown: Direct 40%, Methodology 25%, Findings 25%, Domain 10%">
            Dir: ${rel.direct_relevance} | Met: ${rel.methodology_relevance} | Fin: ${rel.findings_relevance} | Dom: ${rel.domain_relevance}
          </div>
          <div style="font-size:0.72rem; color:#cbd5e1; margin-top:3px; max-width:240px; line-height:1.3;" title="${escapeHtml(rel.direct_explanation || '')}">
            ${escapeHtml((rel.direct_explanation || '').slice(0, 75))}${rel.direct_explanation && rel.direct_explanation.length > 75 ? '...' : ''}
          </div>
        `;
      }

      // Peer-Review & Publication Classification
      const pub = s.publication_classification;
      let peerHtml = '<span class="badge" style="background:#334155; color:#94a3b8; font-size:0.72rem;">UNKNOWN</span>';
      let venueName = s.venue || "Unspecified Venue";
      if (pub) {
        const prStatus = pub.peer_review_status || "UNKNOWN";
        venueName = pub.venue_name || venueName;
        let pBadgeClass = "badge-neutral";
        let pBadgeStyle = "";

        if (prStatus === "PEER_REVIEWED_JOURNAL") {
          pBadgeClass = "badge-success";
        } else if (prStatus === "PEER_REVIEWED_CONFERENCE") {
          pBadgeClass = "badge-info";
        } else if (prStatus === "PREPRINT") {
          pBadgeStyle = "background:#f59e0b; color:#0f172a; font-weight:700;"; // Prominent amber preprint badge
        } else if (prStatus === "UNKNOWN") {
          pBadgeStyle = "background:#475569; color:#e2e8f0; font-weight:700;"; // Visible unknown status badge
        } else if (prStatus === "TECHNICAL_REPORT") {
          pBadgeClass = "badge-info";
        }

        peerHtml = `
          <div style="margin-bottom:3px;">
            <span class="badge ${pBadgeClass}" style="font-size:0.72rem; ${pBadgeStyle}">${escapeHtml(prStatus.replace(/_/g, ' '))}</span>
          </div>
          <div style="font-size:0.72rem; color:#94a3b8; max-width:200px; line-height:1.2;" title="${escapeHtml(pub.classification_evidence || '')}">
            ${escapeHtml((pub.classification_evidence || '').slice(0, 65))}${pub.classification_evidence && pub.classification_evidence.length > 65 ? '...' : ''}
          </div>
        `;
      }

      // Inspection Level
      let inspectionBadge;
      if (s.access_status === "full_text_inspected" || s.inspected_full_text === 1) {
        inspectionBadge = '<span class="badge badge-success" style="font-size:0.72rem;">Full-Text PDF</span>';
      } else if (s.access_status === "abstract_only" || (s.abstract && s.abstract.length > 0)) {
        inspectionBadge = '<span class="badge badge-neutral" style="font-size:0.72rem;">Abstract Only</span>';
      } else {
        inspectionBadge = '<span class="badge" style="background:#334155; color:#94a3b8; font-size:0.72rem;">Metadata Only</span>';
      }

      const displayTitle = isDemo
        ? `<span style="display:inline-block; background:#f59e0b20; color:#fbbf24; border:1px solid #f59e0b40; font-size:0.7rem; font-weight:700; padding:1px 6px; border-radius:4px; margin-right:6px;">DEMO</span>${escapeHtml(s.title.replace(/^\[DEMO BENCHMARK\]\s*/i, ''))}`
        : escapeHtml(s.title);

      const urlLink = s.canonical_url
        ? `<a href="${escapeHtml(s.canonical_url)}" target="_blank" rel="noopener noreferrer" style="color:#38bdf8; text-decoration:underline;">Link ↗</a>`
        : "N/A";

      tr.innerHTML = `
        <td><strong>[${idx + 1}]</strong></td>
        <td style="max-width:280px;">
          <div style="font-weight:600; color:#fff; line-height:1.35;">${displayTitle}</div>
          <div style="font-size:0.75rem; color:#94a3b8; margin-top:3px;">${escapeHtml(s.authors || 'Unknown')}</div>
        </td>
        <td>
          <div style="font-size:0.8rem; font-weight:600; color:#cbd5e1;">${escapeHtml(venueName)}</div>
          <div style="font-size:0.75rem; color:#94a3b8;">${s.publication_year || 'n.d.'}</div>
        </td>
        <td>${relevanceHtml}</td>
        <td>${peerHtml}</td>
        <td>${inspectionBadge}</td>
        <td>${urlLink}</td>
      `;
      tbody.appendChild(tr);
    });
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="7" class="badge-error">Error loading sources: ${e.message}</td></tr>`;
  }
}

// Verification Results Screen
async function loadVerificationResults() {
  const container = document.getElementById("claims-container");
  if (!container) return;

  if (!AppState.currentRunId) {
    container.innerHTML = '<div class="empty-state">No research run active. Select or start a run in Setup first.</div>';
    return;
  }

  container.innerHTML = '<div style="text-align:center; padding:30px; color:var(--text-secondary);">Auditing claim verification matrix...</div>';

  try {
    const res = await fetch(`/api/runs/${AppState.currentRunId}/claims`);
    const claims = await res.json();

    if (claims.length === 0) {
      container.innerHTML = '<div class="empty-state">No claims extracted yet for this run.</div>';
      return;
    }

    container.innerHTML = "";
    claims.forEach((c) => {
      const verif = c.verification || {};
      const verdict = verif.verdict || "UNVERIFIED";

      let badgeClass = "badge-neutral";
      let customBadgeStyle = "";
      if (verdict === "SUPPORTED") {
        badgeClass = "badge-success";
      } else if (verdict === "PARTIALLY_SUPPORTED") {
        badgeClass = "badge-warning";
      } else if (verdict === "CONTRADICTED") {
        badgeClass = "badge-error";
        customBadgeStyle = "background:#ef4444; color:#fff; font-weight:700;";
      } else if (verdict === "INVALID_CITATION") {
        customBadgeStyle = "background:#831843; color:#fbcfe8; border:1px solid #db2777; font-weight:700;";
      } else if (verdict === "INSUFFICIENT_EVIDENCE") {
        customBadgeStyle = "background:#334155; color:#cbd5e1;";
      }

      const quoteBadge = verif.is_direct_quote
        ? '<span class="badge" style="background:#0284c7; color:#fff; font-size:0.7rem; margin-left:8px;">Direct Quote</span>'
        : '<span class="badge" style="background:#334155; color:#94a3b8; font-size:0.7rem; margin-left:8px;">Paraphrase</span>';

      // Passages & Evidence info
      const evList = c.evidence || [];
      const evInfoList = evList.map((e) => {
        const titleStr = e.source_title ? `Source: "${e.source_title.slice(0, 40)}..."` : `Source ID: ${e.source_id.slice(0, 8)}`;
        return `
          <div style="margin-bottom:6px; font-size:0.78rem; background:var(--bg-card); padding:6px 10px; border-radius:4px; border-left:2px solid var(--accent-blue);">
            <div style="font-weight:600; color:#38bdf8; display:flex; justify-content:space-between;">
              <span>${escapeHtml(titleStr)}</span>
              <span style="color:#94a3b8;">EvID: ${e.id ? e.id.slice(0, 8) : 'N/A'}</span>
            </div>
            <div style="color:#cbd5e1; margin-top:2px; font-style:italic;">"${escapeHtml(e.passage_text || '')}"</div>
          </div>
        `;
      }).join("");

      // Contradiction callout
      let contraHtml = "";
      if (verif.contradiction_found || verif.contradicting_evidence) {
        contraHtml = `
          <div style="margin-top:8px; background:#450a0a; border:1px solid #b91c1c; padding:8px 12px; border-radius:6px; font-size:0.8rem; color:#fca5a5;">
            <strong>⚠️ Contradicting Evidence Detected:</strong> ${escapeHtml(verif.contradicting_evidence || "Passage contradicts asserted factual claim.")}
          </div>
        `;
      }

      // Supporting excerpts callout
      let excerptsHtml = "";
      if (verif.supporting_excerpts && verif.supporting_excerpts.length > 0) {
        excerptsHtml = `
          <div style="margin-top:8px; font-size:0.8rem; color:#86efac;">
            <strong>Corroborating Excerpt:</strong> ${escapeHtml(verif.supporting_excerpts.join("; "))}
          </div>
        `;
      }

      const card = document.createElement("div");
      card.className = "card";
      card.style.marginBottom = "16px";

      card.innerHTML = `
        <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:8px;">
          <div style="display:flex; align-items:center;">
            <span class="badge ${badgeClass}" style="font-size:0.8rem; padding:4px 10px; ${customBadgeStyle}">${verdict}</span>
            ${quoteBadge}
          </div>
          <span style="font-size:0.75rem; color:#94a3b8;">Type: ${escapeHtml(c.claim_type)} | Conf: ${verif.confidence !== undefined ? ((verif.confidence) * 100).toFixed(0) + '%' : 'N/A'}</span>
        </div>
        <div style="font-size:0.95rem; font-weight:600; color:#fff; margin-bottom:10px; line-height:1.4;">
          "${escapeHtml(c.claim_text)}"
        </div>
        <div style="margin-bottom:8px;">
          ${evInfoList || '<div style="font-size:0.78rem; color:#94a3b8;">No linked passages.</div>'}
        </div>
        <div style="background:var(--bg-surface); padding:10px 14px; border-radius:6px; font-size:0.82rem; color:#cbd5e1; border-left:3px solid var(--accent-blue);">
          <strong>Auditor Rationale:</strong> ${escapeHtml(verif.rationale || verif.explanation || "Direct textual corroboration checked against passage.")}
          ${excerptsHtml}
          ${contraHtml}
        </div>
      `;
      container.appendChild(card);
    });
  } catch (e) {
    container.innerHTML = `<div class="badge-error">Error loading claims: ${e.message}</div>`;
  }
}


// Helper to extract clean inner HTML body without double document tags
function extractReportBody(htmlContent) {
  if (!htmlContent) return "";
  const bodyMatch = htmlContent.match(/<body[^>]*>([\s\S]*?)<\/body>/i);
  let inner = bodyMatch ? bodyMatch[1] : htmlContent;
  const cardMatch = inner.match(/^\s*<div class="report-card"[^>]*>([\s\S]*?)<\/div>\s*$/i);
  if (cardMatch) {
    inner = cardMatch[1];
  }
  return inner;
}

// Final Report Screen
async function loadReport() {
  const container = document.getElementById("report-view-container");
  const metaBox = document.getElementById("report-meta-box");
  if (!container) return;

  if (!AppState.currentRunId) {
    if (metaBox) metaBox.style.display = "none";
    container.innerHTML = '<div class="empty-state">No research run active. Select or start a research run to view its report.</div>';
    return;
  }

  container.innerHTML = '<div style="text-align:center; padding:30px; color:var(--text-secondary);">Retrieving canonical research report...</div>';

  try {
    const [reportRes, runRes] = await Promise.all([
      fetch(`/api/runs/${AppState.currentRunId}/report`),
      fetch(`/api/runs/${AppState.currentRunId}`),
    ]);

    const run = runRes.ok ? await runRes.json() : null;

    if (reportRes.status === 404) {
      if (metaBox) metaBox.style.display = "none";
      const runStatus = run ? run.status : "IN PROGRESS";
      container.innerHTML = `
        <div class="empty-state">
          <div style="font-size:1.1rem; font-weight:600; color:var(--text-primary); margin-bottom:8px;">Report Not Ready</div>
          <p>The report for active run <code>#${AppState.currentRunId.slice(0, 8)}</code> is currently in status: <strong>${runStatus}</strong>.</p>
          <div style="margin-top:16px;">
            <button class="btn btn-primary btn-sm" onclick="switchScreen('monitor')">View Agent Monitor</button>
          </div>
        </div>
      `;
      return;
    }

    const report = await reportRes.json();

    // Update export buttons
    const mdBtn = document.getElementById("btn-export-md");
    const htmlBtn = document.getElementById("btn-export-html");
    if (mdBtn) mdBtn.href = `/api/runs/${AppState.currentRunId}/export/markdown`;
    if (htmlBtn) htmlBtn.href = `/api/runs/${AppState.currentRunId}/export/html`;

    // Render Run Association Metadata Banner
    if (metaBox && run) {
      metaBox.style.display = "block";
      const qGate = report.quality_summary || {};
      const gateBadge = qGate.passed
        ? '<span class="badge badge-success">Quality Gate Passed</span>'
        : '<span class="badge badge-warning">Quality Audit Active</span>';

      let providerBadge = '<span class="badge badge-info">Demonstration Mode</span>';
      if (run.provider_mode === "ollama") {
        providerBadge = `<span class="badge badge-success">Ollama Inference: ${escapeHtml(run.model_name || 'qwen2.5:3b')}</span>`;
      } else if (run.provider_mode !== "demo") {
        providerBadge = `<span class="badge badge-success">Live Model: ${escapeHtml(run.model_name || 'AI Model')}</span>`;
      }

      metaBox.innerHTML = `
        <div class="report-meta-header">
          <div class="report-meta-badges">
            <span class="badge badge-neutral">Active Run: <strong>#${run.id.slice(0, 8)}</strong></span>
            ${providerBadge}
            <span class="badge badge-neutral">${report.citation_count || run.source_count || 0} Citations Linked</span>
            ${gateBadge}
          </div>
          <span style="font-size:0.75rem; color:var(--text-muted);">
            Generated: ${new Date(report.created_at || run.updated_at).toLocaleString()}
          </span>
        </div>
        <div class="report-question-title">
          <strong>Research Question:</strong> ${escapeHtml(run.question)}
        </div>
      `;
    }

    // Render clean, safely formatted report inside centered .report-paper
    const cleanBodyHtml = extractReportBody(report.html_content);
    container.innerHTML = `
      <div class="report-paper">
        ${cleanBodyHtml}
      </div>
    `;
  } catch (e) {
    if (metaBox) metaBox.style.display = "none";
    container.innerHTML = `<div class="badge-error">Error loading report: ${e.message}</div>`;
  }
}

async function loadRunQualityMetrics(runId) {
  const badge = document.getElementById("metrics-run-badge");
  const relCoverage = document.getElementById("metric-relevance-coverage");
  const relDetails = document.getElementById("metric-relevance-details");
  const citValidity = document.getElementById("metric-citation-validity");
  const citDetails = document.getElementById("metric-citation-details");
  const claimCoverage = document.getElementById("metric-claim-coverage");
  const claimDetails = document.getElementById("metric-claim-details");
  const pubCoverage = document.getElementById("metric-pub-coverage");
  const pubDetails = document.getElementById("metric-pub-details");

  if (!runId) {
    if (badge) badge.textContent = "No active run selected. Select a run in History or Setup.";
    return;
  }

  try {
    const res = await fetch(`/api/runs/${runId}/metrics`);
    if (!res.ok) return;
    const data = await res.json();
    if (badge) badge.textContent = `Run #${runId.slice(0, 8)}`;

    // Relevance
    const r = data.relevance || {};
    if (relCoverage) relCoverage.textContent = `${((r.coverage || 0) * 100).toFixed(0)}%`;
    if (relDetails) {
      relDetails.innerHTML = `
        <strong>${r.total_evaluated || 0}/${r.total_sources || 0}</strong> evaluated<br>
        Inc: ${r.included_count || 0} (${r.pct_included || 0}%) | Rev: ${r.reviewed_count || 0} | Exc: ${r.excluded_count || 0}<br>
        Avg Score: <strong>${r.avg_relevance_score || 0}/100</strong>
      `;
    }

    // Citation & Provenance
    const cp = data.citation_provenance || {};
    if (citValidity) citValidity.textContent = `${((cp.citation_id_validity_rate || 0) * 100).toFixed(0)}%`;
    if (citDetails) {
      citDetails.innerHTML = `
        <strong>${cp.valid_citations_in_report || 0}/${cp.total_citations_in_report || 0}</strong> valid citations<br>
        Provenance Validity: <strong>${((cp.provenance_validity_rate || 0) * 100).toFixed(0)}%</strong> (${cp.valid_provenance_links || 0}/${cp.total_provenance_links || 0})
      `;
    }

    // Claims
    const cl = data.claims || {};
    if (claimCoverage) claimCoverage.textContent = `${((cl.verification_coverage || 0) * 100).toFixed(0)}%`;
    if (claimDetails) {
      claimDetails.innerHTML = `
        <strong>${cl.audited_claims || 0}/${cl.total_claims || 0}</strong> claims audited<br>
        Support Rate: <strong>${((cl.support_rate || 0) * 100).toFixed(0)}%</strong><br>
        Partial: ${((cl.partial_support_rate || 0) * 100).toFixed(0)}% | Contra: ${((cl.contradiction_rate || 0) * 100).toFixed(0)}%
      `;
    }

    // Publication
    const pb = data.publication || {};
    if (pubCoverage) pubCoverage.textContent = `${((pb.coverage || 0) * 100).toFixed(0)}%`;
    if (pubDetails) {
      pubDetails.innerHTML = `
        <strong>${pb.total_classified || 0}/${pb.total_sources || 0}</strong> classified<br>
        Peer-Rev: ${((pb.peer_reviewed_rate || 0) * 100).toFixed(0)}% | Preprint: ${((pb.preprint_rate || 0) * 100).toFixed(0)}%<br>
        Unknown Status: <strong>${((pb.unknown_rate || 0) * 100).toFixed(0)}%</strong>
      `;
    }
  } catch (e) {
    console.error("Failed loading quality metrics", e);
  }
}

// History & Benchmarks Screen
async function loadHistoryAndBenchmarks() {
  const runsTableBody = document.getElementById("history-runs-body");
  const benchTableBody = document.getElementById("benchmarks-body");

  // Load Active Run Validation Metrics
  await loadRunQualityMetrics(AppState.currentRunId);

  // Load Past Runs
  try {
    const pRes = await fetch("/api/projects");
    const projects = await pRes.json();
    if (runsTableBody) {
      runsTableBody.innerHTML = "";
      let foundRuns = 0;
      for (const p of projects) {
        const detRes = await fetch(`/api/projects/${p.id}`);
        const pDet = await detRes.json();
        (pDet.runs || []).forEach((r) => {
          foundRuns++;
          const tr = document.createElement("tr");
          let modeBadge;
          if (r.provider_mode === 'demo') {
            modeBadge = '<span class="badge badge-info">DEMO</span>';
          } else if (r.provider_mode === 'ollama') {
            modeBadge = `<span class="badge badge-success">OLLAMA (${escapeHtml(r.model_name || 'qwen2.5:3b')})</span>`;
          } else {
            modeBadge = `<span class="badge badge-success">LIVE (${escapeHtml(r.model_name || 'AI')})</span>`;
          }

          const isActiveRun = AppState.currentRunId === r.id;

          tr.innerHTML = `
            <td>
              <strong>${escapeHtml(p.title)}</strong>
              ${isActiveRun ? ' <span class="badge badge-info" style="font-size:0.65rem;">ACTIVE</span>' : ''}
            </td>
            <td title="${escapeHtml(r.question)}">${escapeHtml(r.question.slice(0, 65))}...</td>
            <td><span class="badge ${r.status === 'COMPLETED' ? 'badge-success' : 'badge-neutral'}">${r.status}</span></td>
            <td>${modeBadge}</td>
            <td>${r.retry_count}</td>
            <td>${new Date(r.created_at).toLocaleString()}</td>
            <td>
              <div style="display:flex; gap:6px; flex-wrap:wrap;">
                <button class="btn btn-primary btn-sm" onclick="viewRunReport('${r.id}')">Report</button>
                <button class="btn btn-secondary btn-sm" onclick="inspectRun('${r.id}')">Monitor</button>
              </div>
            </td>
          `;
          runsTableBody.appendChild(tr);
        });
      }
      if (foundRuns === 0) {
        runsTableBody.innerHTML = '<tr><td colspan="7" class="empty-state">No prior research runs found.</td></tr>';
      }
    }
  } catch (e) {
    console.error("Failed loading history", e);
  }

  // Load Benchmark Questions
  try {
    const bRes = await fetch("/api/benchmarks/questions");
    const questions = await bRes.json();
    const benchSelect = document.getElementById("benchmark-question-select");
    if (benchSelect && benchSelect.options.length <= 1) {
      questions.forEach((q) => {
        const opt = document.createElement("option");
        opt.value = q.id;
        opt.textContent = `[${q.id}] ${q.category}: ${q.question.slice(0, 75)}...`;
        benchSelect.appendChild(opt);
      });
    }

    // Load Benchmark Results Table
    const resResp = await fetch("/api/benchmarks/results");
    const results = await resResp.json();
    if (benchTableBody) {
      benchTableBody.innerHTML = "";
      if (results.length === 0) {
        benchTableBody.innerHTML = '<tr><td colspan="8" class="empty-state">No benchmark evaluations recorded yet. Run a benchmark test above!</td></tr>';
      } else {
        results.forEach((br) => {
          const tr = document.createElement("tr");
          const variantBadge = br.system_variant === "five_agent_collaborative"
            ? '<span class="badge badge-success">5-Agent Collab</span>'
            : '<span class="badge badge-warning">Single Baseline</span>';

          const executionModeBadge = '<span class="badge badge-info">DEMO BENCHMARK</span>';

          tr.innerHTML = `
            <td><strong>${br.benchmark_question_id}</strong></td>
            <td>${variantBadge}</td>
            <td>${executionModeBadge}</td>
            <td>${((br.retrieval_relevance || 0) * 100).toFixed(1)}%</td>
            <td>${((br.research_coverage || 0) * 100).toFixed(1)}%</td>
            <td><strong>${((br.claim_support_rate || 0) * 100).toFixed(1)}%</strong></td>
            <td>${((br.citation_correctness || 0) * 100).toFixed(1)}%</td>
            <td>${(br.runtime_seconds || 0).toFixed(1)}s</td>
          `;
          benchTableBody.appendChild(tr);
        });
      }
    }
  } catch (e) {
    console.error("Failed loading benchmarks", e);
  }
}

// Global window actions
window.viewRunReport = async function (runId) {
  AppState.currentRunId = runId;
  updateActiveRunBadge({ id: runId, status: "SELECTED" });
  switchScreen("report");
};

window.inspectRun = async function (runId) {
  AppState.currentRunId = runId;
  updateActiveRunBadge({ id: runId, status: "SELECTED" });
  switchScreen("monitor");
};

window.openPreviousRun = function (runId) {
  AppState.currentRunId = runId;
  updateActiveRunBadge({ id: runId, status: "SELECTED" });
  switchScreen("monitor");
};

window.runBenchmarkTest = async function () {
  const select = document.getElementById("benchmark-question-select");
  const qId = select.value;
  if (!qId) {
    alert("Please select a benchmark question first.");
    return;
  }

  const btn = document.getElementById("btn-run-benchmark");
  btn.disabled = true;
  btn.textContent = "Running Benchmark & Baseline...";

  try {
    // 1. Run Baseline
    await fetch("/api/benchmarks/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question_id: qId, system_variant: "single_agent_baseline" }),
    });

    // 2. Run Proposed 5-Agent Collaborative
    await fetch("/api/benchmarks/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question_id: qId, system_variant: "five_agent_collaborative" }),
    });

    await loadHistoryAndBenchmarks();
    alert("Benchmark evaluation complete! Both Five-Agent and Baseline runs recorded.");
  } catch (e) {
    alert("Benchmark execution failed: " + e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "Run Benchmark Comparison";
  }
};

function escapeHtml(text) {
  if (!text) return "";
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
