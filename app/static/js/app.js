/**
 * Autonomous AI Research Assistant - Redesigned Workspace Application
 * Project-centered information architecture, multi-run isolation,
 * research library aggregation, multi-run synthesis, and URL hash navigation.
 */

const AppState = {
  activeScreen: "projects",
  currentProjectId: null,
  currentRunId: null,
  currentSynthesisId: null,
  currentProjectData: null,
  currentRunData: null,
  projectsList: [],
  projectFilter: "ALL",
  runFilter: "ALL",
  projectSearchTerm: "",
  runSearchTerm: "",
  activeWorkspaceTab: "runs",
  activeRunSubtab: "overview",
  eventSource: null,
  systemStatus: null,
  eligibleSynthesisRuns: [],
};

// ==========================================================================
// INITIALIZATION & ROUTING
// ==========================================================================

document.addEventListener("DOMContentLoaded", async () => {
  setupSidebarNavigation();
  await loadSystemStatus();
  setInterval(loadSystemStatus, 10000);

  // Handle URL hash changes
  window.addEventListener("hashchange", handleRoute);

  // Initial routing
  await handleRoute();
});

async function handleRoute() {
  const hash = window.location.hash.slice(1).trim();
  const parts = hash.split("/").filter(Boolean);

  if (parts.length === 0 || parts[0] === "projects") {
    await navigateTo("projects", false);
  } else if (parts[0] === "project" && parts[1]) {
    await openProjectWorkspace(parts[1], false);
    if (parts[2] === "library") {
      switchWorkspaceTab("library");
    } else if (parts[2] === "syntheses") {
      switchWorkspaceTab("syntheses");
    }
  } else if (parts[0] === "run" && parts[1]) {
    await openRunResults(parts[1], false);
    if (parts[2]) {
      switchRunSubtab(parts[2]);
    }
  } else if (parts[0] === "synthesis" && parts[1]) {
    await openSynthesisView(parts[1], false);
  } else if (parts[0] === "benchmarks") {
    await navigateTo("benchmarks", false);
  } else {
    await navigateTo("projects", false);
  }
}

function updateHash(newHash) {
  if (window.location.hash.slice(1) !== newHash) {
    history.pushState(null, "", `#${newHash}`);
  }
}

// ==========================================================================
// NAVIGATION & SCREEN SWITCHING
// ==========================================================================

function setupSidebarNavigation() {
  document.querySelectorAll(".sidebar-nav .nav-link").forEach((link) => {
    link.addEventListener("click", (e) => {
      e.preventDefault();
      const targetScreen = link.getAttribute("data-screen");
      if (targetScreen === "projects") {
        navigateTo("projects");
      } else if (targetScreen === "workspace") {
        if (AppState.currentProjectId) {
          openProjectWorkspace(AppState.currentProjectId);
        } else {
          navigateTo("projects");
        }
      } else if (targetScreen === "library") {
        if (AppState.currentProjectId) {
          openProjectWorkspace(AppState.currentProjectId);
          switchWorkspaceTab("library");
        } else {
          alert("Please select or create a project workspace first.");
          navigateTo("projects");
        }
      } else if (targetScreen === "run") {
        if (AppState.currentRunId) {
          openRunResults(AppState.currentRunId);
        }
      } else if (targetScreen === "synthesis") {
        if (AppState.currentSynthesisId) {
          openSynthesisView(AppState.currentSynthesisId);
        }
      } else if (targetScreen === "benchmarks") {
        navigateTo("benchmarks");
      }
    });
  });
}

async function navigateTo(screenName, updateUrl = true) {
  AppState.activeScreen = screenName;

  // Update navigation link highlights
  document.querySelectorAll(".sidebar-nav .nav-link").forEach((link) => {
    link.classList.toggle("active", link.getAttribute("data-screen") === screenName);
  });

  // Update view visibility
  document.querySelectorAll(".view-panel").forEach((panel) => {
    panel.classList.toggle("active", panel.id === `view-${screenName}`);
  });

  // Update top actions visibility
  const btnTopRun = document.getElementById("btn-top-new-run");
  if (btnTopRun) {
    btnTopRun.style.display = AppState.currentProjectId ? "inline-flex" : "none";
  }

  // Update Breadcrumbs
  updateBreadcrumbs(screenName);

  if (screenName === "projects") {
    if (updateUrl) updateHash("projects");
    await loadProjectsHub();
  } else if (screenName === "benchmarks") {
    if (updateUrl) updateHash("benchmarks");
    await loadBenchmarksSuite();
  }
}

function updateBreadcrumbs(screenName) {
  const bcProject = document.getElementById("bc-project");
  const bcRun = document.getElementById("bc-run");
  const bcSep1 = document.getElementById("bc-sep-1");
  const bcSep2 = document.getElementById("bc-sep-2");

  if (screenName === "projects") {
    if (bcSep1) bcSep1.style.display = "none";
    if (bcProject) bcProject.style.display = "none";
    if (bcSep2) bcSep2.style.display = "none";
    if (bcRun) bcRun.style.display = "none";
  } else if (screenName === "workspace" || screenName === "library") {
    if (bcSep1) bcSep1.style.display = "inline";
    if (bcProject) {
      bcProject.style.display = "inline";
      bcProject.innerHTML = `<a href="#project/${AppState.currentProjectId}" onclick="openProjectWorkspace('${AppState.currentProjectId}'); return false;">${escapeHtml(AppState.currentProjectData?.title || "Project")}</a>`;
    }
    if (bcSep2) bcSep2.style.display = "none";
    if (bcRun) bcRun.style.display = "none";
  } else if (screenName === "run") {
    if (bcSep1) bcSep1.style.display = "inline";
    if (bcProject) {
      bcProject.style.display = "inline";
      bcProject.innerHTML = `<a href="#project/${AppState.currentProjectId}" onclick="openProjectWorkspace('${AppState.currentProjectId}'); return false;">${escapeHtml(AppState.currentProjectData?.title || "Project")}</a>`;
    }
    if (bcSep2) bcSep2.style.display = "inline";
    if (bcRun) {
      bcRun.style.display = "inline";
      bcRun.textContent = `Inquiry #${(AppState.currentRunId || "").slice(0, 8)}`;
    }
  } else if (screenName === "synthesis") {
    if (bcSep1) bcSep1.style.display = "inline";
    if (bcProject) {
      bcProject.style.display = "inline";
      bcProject.innerHTML = `<a href="#project/${AppState.currentProjectId}" onclick="openProjectWorkspace('${AppState.currentProjectId}'); return false;">${escapeHtml(AppState.currentProjectData?.title || "Project")}</a>`;
    }
    if (bcSep2) bcSep2.style.display = "inline";
    if (bcRun) {
      bcRun.style.display = "inline";
      bcRun.textContent = "Synthesis Meta-Review";
    }
  } else if (screenName === "benchmarks") {
    if (bcSep1) bcSep1.style.display = "inline";
    if (bcProject) {
      bcProject.style.display = "inline";
      bcProject.textContent = "Evaluation & Benchmarks";
    }
    if (bcSep2) bcSep2.style.display = "none";
    if (bcRun) bcRun.style.display = "none";
  }
}

// ==========================================================================
// SYSTEM STATUS & HEALTH POLLING
// ==========================================================================

async function loadSystemStatus() {
  try {
    const res = await fetch("/api/status");
    if (!res.ok) return;
    const data = await res.json();
    AppState.systemStatus = data;

    const dot = document.getElementById("sidebar-ollama-dot");
    const badge = document.getElementById("sidebar-ollama-badge");
    const caption = document.getElementById("sidebar-ollama-caption");
    const headerPill = document.getElementById("header-ollama-pill");

    const oHealth = data.ollama || data.ollama_health;

    if (data.llm.is_demo_mode) {
      if (dot) dot.className = "status-pulse-dot";
      if (badge) badge.textContent = "DEMO BENCHMARK";
      if (caption) caption.textContent = "Deterministic offline engine";
      if (headerPill) {
        headerPill.textContent = "Mode: Demo Benchmark";
        headerPill.style.color = "var(--status-info)";
        headerPill.style.borderColor = "var(--border-subtle)";
      }
    } else if (data.llm.provider === "ollama") {
      if (oHealth && oHealth.reachable && oHealth.model_installed) {
        if (dot) dot.className = "status-pulse-dot online";
        if (badge) badge.textContent = "OLLAMA ACTIVE";
        if (caption) caption.textContent = `Local inference: ${oHealth.configured_model}`;
        if (headerPill) {
          headerPill.textContent = `Ollama: Online (${oHealth.configured_model})`;
          headerPill.style.color = "var(--status-success)";
          headerPill.style.borderColor = "rgba(52, 211, 153, 0.4)";
        }
      } else if (oHealth && oHealth.reachable && !oHealth.model_installed) {
        if (dot) dot.className = "status-pulse-dot";
        if (badge) badge.textContent = "MODEL MISSING";
        if (caption) caption.textContent = `Pull model: ${oHealth.configured_model}`;
        if (headerPill) {
          headerPill.textContent = `Ollama: Model Missing (${oHealth.configured_model})`;
          headerPill.style.color = "var(--status-warning)";
          headerPill.style.borderColor = "rgba(251, 191, 36, 0.4)";
        }
      } else {
        if (dot) dot.className = "status-pulse-dot offline";
        if (badge) badge.textContent = "OLLAMA OFFLINE";
        if (caption) caption.textContent = "Service unreachable @ port 11434";
        if (headerPill) {
          headerPill.textContent = "Ollama: Offline";
          headerPill.style.color = "var(--status-error)";
          headerPill.style.borderColor = "rgba(248, 113, 113, 0.4)";
        }
      }
    } else {
      if (dot) dot.className = "status-pulse-dot online";
      if (badge) badge.textContent = `AI: ${data.llm.provider.toUpperCase()}`;
      if (caption) caption.textContent = `Model: ${data.llm.model}`;
      if (headerPill) {
        headerPill.textContent = `Model: ${data.llm.model}`;
        headerPill.style.color = "var(--accent-secondary)";
      }
    }
  } catch (err) {
    console.warn("Failed checking system status:", err);
  }
}

// ==========================================================================
// VIEW 1: PROJECTS HUB LOGIC
// ==========================================================================

async function loadProjectsHub() {
  const container = document.getElementById("projects-grid");
  if (!container) return;

  try {
    const res = await fetch("/api/projects");
    if (!res.ok) throw new Error("Could not load projects");
    AppState.projectsList = await res.json();
    renderProjectsGrid();
  } catch (e) {
    container.innerHTML = `<div class="empty-state" style="color:var(--status-error);">Failed loading projects: ${e.message}</div>`;
  }
}

function handleProjectSearch() {
  const input = document.getElementById("project-search-input");
  AppState.projectSearchTerm = (input ? input.value : "").trim().toLowerCase();
  renderProjectsGrid();
}

function setProjectFilter(filter, btn) {
  AppState.projectFilter = filter;
  document.querySelectorAll(".filter-btn[data-filter]").forEach((b) => b.classList.remove("active"));
  if (btn) btn.classList.add("active");
  renderProjectsGrid();
}

function renderProjectsGrid() {
  const container = document.getElementById("projects-grid");
  if (!container) return;

  let filtered = AppState.projectsList.filter((p) => {
    // Status filter
    if (AppState.projectFilter === "ACTIVE" && p.status === "ARCHIVED") return false;
    if (AppState.projectFilter === "ARCHIVED" && p.status !== "ARCHIVED") return false;

    // Search filter
    if (AppState.projectSearchTerm) {
      const matchTitle = (p.title || "").toLowerCase().includes(AppState.projectSearchTerm);
      const matchDesc = (p.description || "").toLowerCase().includes(AppState.projectSearchTerm);
      const matchRunQ = (p.latest_run_question || "").toLowerCase().includes(AppState.projectSearchTerm);
      if (!matchTitle && !matchDesc && !matchRunQ) return false;
    }
    return true;
  });

  if (filtered.length === 0) {
    if (AppState.projectsList.length === 0) {
      container.innerHTML = `
        <div class="empty-state" style="grid-column: 1 / -1;">
          <div style="font-size:2rem; margin-bottom:12px;">🗂️</div>
          <h3 style="font-size:1.15rem; color:var(--text-primary); margin-bottom:8px;">No Research Workspaces Yet</h3>
          <p style="max-width:480px; margin:0 auto 18px; color:var(--text-secondary);">
            Create your first research project to organize multi-agent literature queries, evidence passages, and synthesized reports.
          </p>
          <button class="btn btn-primary" onclick="openCreateProjectModal()">
            <span class="btn-icon">+</span> Create First Workspace
          </button>
        </div>
      `;
    } else {
      container.innerHTML = `
        <div class="empty-state" style="grid-column: 1 / -1;">
          No projects match your search criteria. Try a different search term or filter.
        </div>
      `;
    }
    return;
  }

  container.innerHTML = "";
  filtered.forEach((p) => {
    const isArchived = p.status === "ARCHIVED";
    const statusPill = isArchived
      ? '<span class="project-status-pill archived">ARCHIVED</span>'
      : '<span class="project-status-pill active">ACTIVE</span>';

    const lastAct = p.latest_run_time || p.updated_at || p.created_at;
    const dateFormatted = lastAct ? new Date(lastAct).toLocaleDateString() : "n.d.";

    const card = document.createElement("div");
    card.className = "project-card";
    card.innerHTML = `
      <div class="project-card-header">
        <h3 class="project-card-title" onclick="openProjectWorkspace('${p.id}')">${escapeHtml(p.title)}</h3>
        ${statusPill}
      </div>
      <p class="project-card-desc">${escapeHtml(p.description || "No description provided.")}</p>

      <div class="project-card-stats">
        <div class="card-stat-item">
          <div class="card-stat-val">${p.runs_count || 0}</div>
          <div class="card-stat-lbl">Inquiries</div>
        </div>
        <div class="card-stat-item">
          <div class="card-stat-val">${p.completed_runs_count || 0}</div>
          <div class="card-stat-lbl">Completed</div>
        </div>
        <div class="card-stat-item">
          <div class="card-stat-val">${p.syntheses_count || 0}</div>
          <div class="card-stat-lbl">Syntheses</div>
        </div>
      </div>

      <div class="project-card-footer">
        <span>Activity: ${dateFormatted}</span>
        <div class="project-card-actions">
          <button class="btn btn-secondary btn-sm" onclick="openProjectWorkspace('${p.id}')">Open Workspace</button>
        </div>
      </div>
    `;
    container.appendChild(card);
  });
}

// ==========================================================================
// VIEW 2: PROJECT WORKSPACE LOGIC
// ==========================================================================

async function openProjectWorkspace(projectId, updateUrl = true) {
  AppState.currentProjectId = projectId;
  if (updateUrl) updateHash(`project/${projectId}`);

  // Switch to workspace view
  AppState.activeScreen = "workspace";
  document.querySelectorAll(".sidebar-nav .nav-link").forEach((link) => {
    link.classList.toggle("active", link.getAttribute("data-screen") === "workspace");
  });
  document.querySelectorAll(".view-panel").forEach((panel) => {
    panel.classList.toggle("active", panel.id === "view-workspace");
  });

  const btnTopRun = document.getElementById("btn-top-new-run");
  if (btnTopRun) btnTopRun.style.display = "inline-flex";

  try {
    const res = await fetch(`/api/projects/${projectId}`);
    if (!res.ok) throw new Error("Workspace not found");
    const p = await res.json();
    AppState.currentProjectData = p;

    // Update sidebar context pill
    const sbCtx = document.getElementById("sidebar-project-context");
    const sbTitle = document.getElementById("sidebar-project-title");
    const sbMeta = document.getElementById("sidebar-project-meta");
    const navRunsBadge = document.getElementById("nav-runs-count");
    if (sbCtx) sbCtx.style.display = "block";
    if (sbTitle) sbTitle.textContent = p.title;
    if (sbMeta) sbMeta.textContent = `${p.runs?.length || 0} Inquiries • ${p.status || "ACTIVE"}`;
    if (navRunsBadge) {
      navRunsBadge.textContent = p.runs?.length || 0;
      navRunsBadge.style.display = "inline-block";
    }

    // Update Header breadcrumbs
    updateBreadcrumbs("workspace");

    // Populate Workspace Header
    document.getElementById("workspace-title").textContent = p.title;
    document.getElementById("workspace-desc").textContent = p.description || "No description provided for this research workspace.";

    const pill = document.getElementById("workspace-status-pill");
    const archiveBtn = document.getElementById("btn-workspace-archive");
    if (p.status === "ARCHIVED") {
      pill.className = "project-status-pill archived";
      pill.textContent = "ARCHIVED";
      if (archiveBtn) archiveBtn.innerHTML = "<span>📦</span> Restore";
    } else {
      pill.className = "project-status-pill active";
      pill.textContent = "ACTIVE";
      if (archiveBtn) archiveBtn.innerHTML = "<span>📦</span> Archive";
    }

    // Populate Stats Ribbon
    const stats = p.stats || {};
    document.getElementById("workspace-stat-runs").textContent = stats.runs_count || (p.runs?.length || 0);
    document.getElementById("workspace-stat-completed").textContent = stats.completed_runs_count || 0;
    document.getElementById("workspace-stat-sources").textContent = stats.sources_count || 0;
    document.getElementById("workspace-stat-syntheses").textContent = stats.syntheses_count || (p.syntheses?.length || 0);

    // Tab counts
    document.getElementById("tab-runs-count").textContent = p.runs?.length || 0;
    document.getElementById("tab-sources-count").textContent = stats.sources_count || 0;
    document.getElementById("tab-syntheses-count").textContent = stats.syntheses_count || (p.syntheses?.length || 0);

    // Render Tab Content
    renderWorkspaceRuns(p.runs || []);
    if (AppState.activeWorkspaceTab === "library") {
      loadProjectLibrary(projectId);
    } else if (AppState.activeWorkspaceTab === "syntheses") {
      renderProjectSyntheses(p.syntheses || []);
    }
  } catch (err) {
    alert("Error loading project workspace: " + err.message);
    navigateTo("projects");
  }
}

function switchWorkspaceTab(tabName, btn) {
  AppState.activeWorkspaceTab = tabName;
  document.querySelectorAll(".workspace-tabs-bar .tab-btn").forEach((b) => b.classList.remove("active"));
  if (btn) {
    btn.classList.add("active");
  } else {
    const matchingBtn = document.querySelector(`.workspace-tabs-bar .tab-btn[data-tab="${tabName}"]`);
    if (matchingBtn) matchingBtn.classList.add("active");
  }

  document.querySelectorAll(".wtab-content").forEach((c) => c.classList.remove("active"));
  const activeContent = document.getElementById(`wtab-${tabName}`);
  if (activeContent) activeContent.classList.add("active");

  if (tabName === "library" && AppState.currentProjectId) {
    loadProjectLibrary(AppState.currentProjectId);
  } else if (tabName === "syntheses" && AppState.currentProjectData) {
    renderProjectSyntheses(AppState.currentProjectData.syntheses || []);
  }
}

function handleRunSearch() {
  const input = document.getElementById("run-search-input");
  AppState.runSearchTerm = (input ? input.value : "").trim().toLowerCase();
  if (AppState.currentProjectData) {
    renderWorkspaceRuns(AppState.currentProjectData.runs || []);
  }
}

function setRunFilter(filter, btn) {
  AppState.runFilter = filter;
  document.querySelectorAll(".filter-btn[data-run-filter]").forEach((b) => b.classList.remove("active"));
  if (btn) btn.classList.add("active");
  if (AppState.currentProjectData) {
    renderWorkspaceRuns(AppState.currentProjectData.runs || []);
  }
}

function renderWorkspaceRuns(runs) {
  const container = document.getElementById("workspace-runs-list");
  if (!container) return;

  let filtered = runs.filter((r) => {
    if (AppState.runFilter === "COMPLETED" && r.status !== "COMPLETED") return false;
    if (AppState.runFilter === "RUNNING" && !["RUNNING", "PLANNING", "RESEARCHING", "ANALYZING", "VERIFYING", "GENERATING_REPORT", "EVALUATING"].includes(r.status)) return false;
    if (AppState.runSearchTerm) {
      if (!r.question.toLowerCase().includes(AppState.runSearchTerm)) return false;
    }
    return true;
  });

  if (filtered.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        ${runs.length === 0 ? "No research runs in this workspace yet. Click 'New Research Run' to initiate an inquiry." : "No runs match your search/filter criteria."}
      </div>
    `;
    return;
  }

  container.innerHTML = "";
  filtered.forEach((r) => {
    let statusClass = "badge-neutral";
    if (r.status === "COMPLETED") statusClass = "badge-success";
    else if (["RUNNING", "PLANNING", "RESEARCHING", "ANALYZING", "VERIFYING", "GENERATING_REPORT"].includes(r.status)) statusClass = "badge-warning";
    else if (r.status === "FAILED") statusClass = "badge-error";

    const item = document.createElement("div");
    item.className = "run-card-item";
    item.innerHTML = `
      <div class="run-card-left">
        <div class="run-card-tags">
          <span class="domain-pill">${escapeHtml(r.domain || "Computer Science")}</span>
          <span class="badge ${statusClass}">${r.status}</span>
          <span style="font-size:0.75rem; color:var(--text-muted); font-family:var(--font-mono);">#${r.id.slice(0, 8)}</span>
        </div>
        <div class="run-card-question" onclick="openRunResults('${r.id}')">${escapeHtml(r.question)}</div>
        <div class="run-card-meta">
          <span>📚 Sources: <strong>${r.source_count || 0}</strong></span>
          <span>🔍 Verified Claims: <strong>${r.verified_count || 0}</strong></span>
          <span>🤖 Model: ${escapeHtml(r.model_name || "default")}</span>
          <span>📅 ${new Date(r.created_at).toLocaleDateString()}</span>
        </div>
      </div>
      <div class="run-card-right">
        <button class="btn btn-secondary btn-sm" onclick="openRunResults('${r.id}')">Open Results</button>
        <button class="btn btn-secondary btn-sm" onclick="openRunActivity('${r.id}')">Activity Stream</button>
        <button class="btn btn-danger btn-sm" onclick="openDeleteRunModal('${r.id}', event)"><span>🗑️</span> Delete</button>
      </div>
    `;
    container.appendChild(item);
  });
}

async function loadProjectLibrary(projectId) {
  const tbody = document.getElementById("project-library-table-body");
  if (!tbody) return;

  tbody.innerHTML = '<tr><td colspan="7" class="empty-state">Aggregating unique scholarly literature across project runs...</td></tr>';

  try {
    const res = await fetch(`/api/projects/${projectId}/sources`);
    if (!res.ok) throw new Error("Could not load sources");
    const sources = await res.json();

    if (sources.length === 0) {
      tbody.innerHTML = '<tr><td colspan="7" class="empty-state">No sources retrieved in this project yet. Start a research run to populate.</td></tr>';
      return;
    }

    tbody.innerHTML = "";
    sources.forEach((s, idx) => {
      const row = document.createElement("tr");

      // Peer review badge
      const prStatus = s.peer_review_status || "UNKNOWN";
      let prBadge = `<span class="badge badge-neutral">${prStatus.replace(/_/g, " ")}</span>`;
      if (prStatus.includes("PEER_REVIEWED")) {
        prBadge = `<span class="badge badge-success">${prStatus.replace(/_/g, " ")}</span>`;
      } else if (prStatus === "PREPRINT") {
        prBadge = `<span class="badge badge-warning">PREPRINT</span>`;
      }

      // Relevance badge
      const relDec = s.relevance_decision || "INCLUDE";
      let relBadge = `<span class="badge badge-success">INCLUDE</span>`;
      if (relDec === "REVIEW") relBadge = `<span class="badge badge-warning">REVIEW</span>`;
      if (relDec === "EXCLUDE") relBadge = `<span class="badge badge-error">EXCLUDE</span>`;

      // Contributing runs pills
      const contributingHtml = (s.contributing_runs || [])
        .map((cr) => `<a href="#run/${cr.run_id}" onclick="openRunResults('${cr.run_id}'); return false;" class="domain-pill" title="${escapeHtml(cr.question)}">Run #${cr.run_id.slice(0, 8)}</a>`)
        .join(" ");

      // Identifiers
      let idLink = "-";
      if (s.doi) {
        idLink = `<a href="https://doi.org/${escapeHtml(s.doi)}" target="_blank" rel="noopener" class="citation-ref">DOI</a>`;
      } else if (s.arxiv_id) {
        idLink = `<a href="https://arxiv.org/abs/${escapeHtml(s.arxiv_id)}" target="_blank" rel="noopener" class="citation-ref">arXiv</a>`;
      } else if (s.canonical_url) {
        idLink = `<a href="${escapeHtml(s.canonical_url)}" target="_blank" rel="noopener" class="citation-ref">Link</a>`;
      }

      row.innerHTML = `
        <td style="color:var(--text-muted); font-family:var(--font-mono);">${idx + 1}</td>
        <td>
          <div style="font-weight:600; color:var(--text-primary); margin-bottom:2px;">${escapeHtml(s.title)}</div>
          <div style="font-size:0.75rem; color:var(--text-secondary);">${escapeHtml(s.authors || "Unknown Authors")}</div>
        </td>
        <td>${s.publication_year || "n.d."}<br><span style="font-size:0.75rem; color:var(--text-muted);">${escapeHtml(s.venue_name || s.doc_type || "")}</span></td>
        <td>${prBadge}</td>
        <td>${relBadge}</td>
        <td>${contributingHtml || "-"}</td>
        <td>${idLink}</td>
      `;
      tbody.appendChild(row);
    });
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="7" class="badge-error">Error loading library: ${e.message}</td></tr>`;
  }
}

function renderProjectSyntheses(syntheses) {
  const container = document.getElementById("project-syntheses-grid");
  if (!container) return;

  if (syntheses.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        No multi-run syntheses generated yet. When you have 2 or more completed inquiries, click "Create Research Synthesis".
      </div>
    `;
    return;
  }

  container.innerHTML = "";
  syntheses.forEach((synth) => {
    const card = document.createElement("div");
    card.className = "project-card";
    const dateFormatted = new Date(synth.created_at).toLocaleDateString();

    card.innerHTML = `
      <div class="project-card-header">
        <h3 class="project-card-title" onclick="openSynthesisView('${synth.id}')">${escapeHtml(synth.title)}</h3>
        <span class="badge badge-info">SYNTHESIS</span>
      </div>
      <p class="project-card-desc">
        Integrated synthesis combining <strong>${synth.contributing_run_ids?.length || 0} inquiries</strong> with <strong>${synth.citation_count || 0} citations</strong> and <strong>${synth.conflict_count || 0} divergence points</strong> analyzed.
      </p>
      <div class="project-card-footer">
        <span>Created: ${dateFormatted}</span>
        <div class="project-card-actions">
          <button class="btn btn-secondary btn-sm" onclick="openSynthesisView('${synth.id}')">Read Synthesis</button>
          <a class="btn btn-secondary btn-sm" href="/api/syntheses/${synth.id}/export/html" target="_blank">Export HTML</a>
        </div>
      </div>
    `;
    container.appendChild(card);
  });
}

// ==========================================================================
// VIEW 3: RUN DETAIL & RESULTS VIEW LOGIC
// ==========================================================================

function updateRunHeaderCounts(sourceCount, claimCount) {
  if (sourceCount !== undefined && sourceCount !== null) {
    const srcEl = document.getElementById("run-source-count");
    if (srcEl) srcEl.textContent = sourceCount;
    if (AppState.currentRunData) AppState.currentRunData.source_count = sourceCount;
  }
  if (claimCount !== undefined && claimCount !== null) {
    const claimEl = document.getElementById("run-claim-count");
    if (claimEl) claimEl.textContent = claimCount;
    if (AppState.currentRunData) AppState.currentRunData.claim_count = claimCount;
  }
}

async function refreshActiveRunMetadata(runId) {
  if (!runId) return;
  try {
    const res = await fetch(`/api/runs/${runId}`);
    if (!res.ok) return;
    const run = await res.json();
    AppState.currentRunData = run;

    updateRunHeaderCounts(run.source_count, run.claim_count);

    const statusBadge = document.getElementById("run-status-badge");
    const navStatus = document.getElementById("nav-run-status");
    if (statusBadge) {
      statusBadge.textContent = run.status;
      statusBadge.className = `badge ${run.status === "COMPLETED" ? "badge-success" : run.status === "FAILED" ? "badge-error" : "badge-warning"}`;
    }
    if (navStatus) {
      navStatus.textContent = run.status;
    }

    const dur = run.duration_seconds ? `${run.duration_seconds.toFixed(1)}s` : "--";
    const durEl = document.getElementById("run-duration-display");
    if (durEl) durEl.textContent = dur;

    const cancelBtn = document.getElementById("btn-cancel-run");
    if (cancelBtn) {
      cancelBtn.style.display = ["RUNNING", "PLANNING", "RESEARCHING", "ANALYZING", "VERIFYING", "GENERATING_REPORT"].includes(run.status) ? "inline-flex" : "none";
    }
  } catch (e) {
    console.warn("Could not refresh run metadata:", e);
  }
}

async function openRunResults(runId, updateUrl = true) {
  AppState.currentRunId = runId;
  if (updateUrl) updateHash(`run/${runId}`);

  // Switch to run view
  AppState.activeScreen = "run";
  document.querySelectorAll(".sidebar-nav .nav-link").forEach((link) => {
    link.classList.toggle("active", link.getAttribute("data-screen") === "run");
  });
  document.querySelectorAll(".view-panel").forEach((panel) => {
    panel.classList.toggle("active", panel.id === "view-run");
  });

  const navRun = document.getElementById("nav-run");
  if (navRun) navRun.style.display = "flex";

  try {
    const res = await fetch(`/api/runs/${runId}`);
    if (!res.ok) throw new Error("Run not found");
    const run = await res.json();
    AppState.currentRunData = run;

    // Ensure project is registered
    if (run.project_id) {
      AppState.currentProjectId = run.project_id;
    }

    // Update Header breadcrumbs
    updateBreadcrumbs("run");

    // Populate Run Header Card
    document.getElementById("run-question-heading").textContent = run.question;
    document.getElementById("run-domain-tag").textContent = run.domain || "Computer Science";
    document.getElementById("run-id-display").textContent = `#${run.id.slice(0, 8)}`;
    document.getElementById("run-model-display").textContent = run.model_name || run.provider_mode || "default";
    document.getElementById("run-date-display").textContent = new Date(run.created_at).toLocaleString();

    const dur = run.duration_seconds ? `${run.duration_seconds.toFixed(1)}s` : "--";
    document.getElementById("run-duration-display").textContent = dur;

    const statusBadge = document.getElementById("run-status-badge");
    const navStatus = document.getElementById("nav-run-status");
    if (statusBadge) {
      statusBadge.textContent = run.status;
      statusBadge.className = `badge ${run.status === "COMPLETED" ? "badge-success" : run.status === "FAILED" ? "badge-error" : "badge-warning"}`;
    }
    if (navStatus) {
      navStatus.textContent = run.status;
    }

    // Cancel Button visibility
    const cancelBtn = document.getElementById("btn-cancel-run");
    if (cancelBtn) {
      cancelBtn.style.display = ["RUNNING", "PLANNING", "RESEARCHING", "ANALYZING", "VERIFYING", "GENERATING_REPORT"].includes(run.status) ? "inline-flex" : "none";
    }

    // Export buttons
    document.getElementById("btn-run-export-md").href = `/api/runs/${runId}/export/markdown`;
    document.getElementById("btn-run-export-html").href = `/api/runs/${runId}/export/html`;

    // Counts in tabs
    updateRunHeaderCounts(run.source_count !== undefined ? run.source_count : 0, run.claim_count !== undefined ? run.claim_count : 0);

    // Connect SSE if still in progress
    if (["RUNNING", "PLANNING", "RESEARCHING", "ANALYZING", "VERIFYING", "GENERATING_REPORT", "CREATED"].includes(run.status)) {
      subscribeToRunEvents(runId);
    }

    // Load active subtab content
    switchRunSubtab(AppState.activeRunSubtab);
  } catch (err) {
    alert("Error loading research run: " + err.message);
    if (AppState.currentProjectId) {
      openProjectWorkspace(AppState.currentProjectId);
    } else {
      navigateTo("projects");
    }
  }
}

function openRunActivity(runId) {
  AppState.activeRunSubtab = "monitor";
  openRunResults(runId);
}

function backToWorkspace() {
  if (AppState.currentProjectId) {
    openProjectWorkspace(AppState.currentProjectId);
  } else {
    navigateTo("projects");
  }
}

function switchRunSubtab(subtabName, btn) {
  AppState.activeRunSubtab = subtabName;
  document.querySelectorAll(".run-subtabs-bar .run-subtab-btn").forEach((b) => b.classList.remove("active"));
  if (btn) {
    btn.classList.add("active");
  } else {
    const matchingBtn = document.querySelector(`.run-subtabs-bar .run-subtab-btn[data-subtab="${subtabName}"]`);
    if (matchingBtn) matchingBtn.classList.add("active");
  }

  document.querySelectorAll(".rsubtab-content").forEach((c) => c.classList.remove("active"));
  const activeContent = document.getElementById(`rsubtab-${subtabName}`);
  if (activeContent) activeContent.classList.add("active");

  if (!AppState.currentRunId) return;

  if (subtabName === "overview") loadRunOverview(AppState.currentRunId);
  else if (subtabName === "monitor") loadRunTasks(AppState.currentRunId);
  else if (subtabName === "sources") loadRunSources(AppState.currentRunId);
  else if (subtabName === "verification") loadRunClaims(AppState.currentRunId);
  else if (subtabName === "report") loadRunReport(AppState.currentRunId);
}

async function loadRunOverview(runId) {
  try {
    await refreshActiveRunMetadata(runId);
    const res = await fetch(`/api/runs/${runId}/metrics`);
    if (!res.ok) return;
    const m = await res.json();

    const rScore = m.relevance?.coverage !== undefined ? `${Math.round(m.relevance.coverage * 100)}%` : "--%";
    const cScore = m.citation_provenance?.validity_rate !== undefined ? `${Math.round(m.citation_provenance.validity_rate * 100)}%` : "--%";
    const clScore = m.claims?.support_rate !== undefined ? `${Math.round(m.claims.support_rate * 100)}%` : "--%";
    const pScore = m.publication?.classified_rate !== undefined ? `${Math.round(m.publication.classified_rate * 100)}%` : "--%";

    document.getElementById("rmetric-relevance").textContent = rScore;
    document.getElementById("rmetric-citations").textContent = cScore;
    document.getElementById("rmetric-claims").textContent = clScore;
    document.getElementById("rmetric-peer-review").textContent = pScore;

    // Populate Run Configuration & Parameters Card
    const run = AppState.currentRunData || {};
    const domainEl = document.getElementById("run-cfg-domain");
    if (domainEl) domainEl.textContent = run.domain || "Computer Science & AI";

    const sourcesEl = document.getElementById("run-cfg-max-sources");
    if (sourcesEl) sourcesEl.textContent = `${run.max_sources || 8} papers`;

    const repoEl = document.getElementById("run-cfg-repositories");
    if (repoEl) {
      const rawRepo = run.search_providers || "openalex,arxiv";
      const formattedRepos = rawRepo.split(",").map((p) => {
        const clean = p.trim().toLowerCase();
        if (clean === "openalex") return "OpenAlex";
        if (clean === "arxiv") return "arXiv";
        return p.trim();
      }).join(", ");
      repoEl.textContent = formattedRepos || "OpenAlex, arXiv";
    }

    const modelEl = document.getElementById("run-cfg-model");
    if (modelEl) {
      const mode = run.provider_mode || "ollama";
      const mName = run.model_name || "qwen2.5:3b";
      modelEl.textContent = mode === "demo" ? "Deterministic Demo Engine" : `Local Ollama (${mName})`;
    }

    const pubPrefEl = document.getElementById("run-cfg-pub-pref");
    if (pubPrefEl) {
      const pp = run.publication_preference || "all";
      if (pp === "peer_reviewed_only") pubPrefEl.textContent = "Peer-Reviewed Only";
      else if (pp === "preprints_preferred") pubPrefEl.textContent = "Preprints Preferred";
      else pubPrefEl.textContent = "Peer-Reviewed & Preprints";
    }

    const evPrefEl = document.getElementById("run-cfg-evidence-pref");
    if (evPrefEl) {
      const ep = run.evidence_preference || "full_text_preferred";
      if (ep === "abstract_only") evPrefEl.textContent = "Abstract-Only Extraction";
      else if (ep === "full_text_required") evPrefEl.textContent = "Strict Full-Text Required";
      else evPrefEl.textContent = "Full-Text PDF (Abstract Fallback)";
    }

    const relEl = document.getElementById("run-cfg-relevance-cutoff");
    if (relEl) {
      relEl.textContent = `≥ ${run.relevance_threshold !== undefined ? run.relevance_threshold : 50}% Topicality`;
    }

    const retriesEl = document.getElementById("run-cfg-retries");
    if (retriesEl) {
      retriesEl.textContent = `${run.max_retries !== undefined ? run.max_retries : 2} targeted cycle(s)`;
    }

    // Fetch report summary
    const repRes = await fetch(`/api/runs/${runId}/report`);
    const sumBox = document.getElementById("run-executive-summary");
    if (repRes.ok) {
      const rep = await repRes.json();
      // Extract Executive Summary section if present
      const match = rep.markdown_content.match(/## Executive Summary\s+([\s\S]*?)(?=##|\Z)/i);
      if (match && match[1]) {
        sumBox.textContent = match[1].trim();
      } else {
        sumBox.textContent = `A comprehensive scientific report with ${rep.citation_count || 0} citations has been generated and validated.`;
      }
    } else {
      sumBox.innerHTML = '<span style="color:var(--text-muted);">Report not ready yet. View the Agent Monitor to track progress.</span>';
    }
  } catch (err) {
    console.warn("Metrics error:", err);
  }
}

// Current selected agent for inspector telemetry
AppState.selectedAgentInspector = "planner";
AppState.currentRunTasks = [];

async function loadRunTasks(runId) {
  try {
    const res = await fetch(`/api/runs/${runId}/tasks`);
    if (!res.ok) return;
    const tasks = await res.json();
    AppState.currentRunTasks = tasks;

    // Update overall pipeline bar status
    const run = AppState.currentRunData || {};
    const pipelineStatusPill = document.getElementById("agent-pipeline-pill");
    const pipelineTimePill = document.getElementById("agent-pipeline-time");
    const liveIndicator = document.getElementById("terminal-live-indicator");

    if (pipelineStatusPill) {
      const isCompleted = run.status === "COMPLETED";
      const isRunning = ["RUNNING", "PLANNING", "RESEARCHING", "ANALYZING", "VERIFYING", "GENERATING_REPORT"].includes(run.status);
      pipelineStatusPill.textContent = run.status || "IDLE";
      pipelineStatusPill.className = `badge ${isCompleted ? "badge-success" : isRunning ? "badge-warning" : "badge-neutral"}`;
    }

    if (pipelineTimePill) {
      const dur = run.duration_seconds ? `${run.duration_seconds.toFixed(1)}s total` : "In Progress";
      pipelineTimePill.textContent = `⏱️ Execution: ${dur}`;
    }

    if (liveIndicator) {
      if (run.status === "COMPLETED" || run.status === "FAILED") {
        liveIndicator.textContent = `● Execution Log (${tasks.length} Checkpoints)`;
        liveIndicator.className = "stream-live-indicator static";
      } else {
        liveIndicator.textContent = "● Live Stream Active";
        liveIndicator.className = "stream-live-indicator";
      }
    }

    // Map tasks to 5 agent cards
    const agentMap = {
      planner: { name: "1. Planner", icon: "🧭", role: "Decomposition & Strategy", defaultTask: "Formulate research sub-queries" },
      researcher: { name: "2. Researcher", icon: "🔬", role: "Literature Retrieval & PDFs", defaultTask: "Query OpenAlex & arXiv repositories" },
      analyst: { name: "3. Analyst", icon: "🧠", role: "Passage Synthesis & Claims", defaultTask: "Extract atomic verifiable claims" },
      fact_checker: { name: "4. Fact-Checker", icon: "⚖️", role: "Adversarial Ground Audit", defaultTask: "Audit claims & verify citations" },
      report_writer: { name: "5. Report Writer", icon: "📑", role: "Quality-Gated Synthesis", defaultTask: "Compile quality-gated report" },
    };

    Object.keys(agentMap).forEach((agentKey) => {
      const t = tasks.find((item) => item.agent_name === agentKey);
      const card = document.getElementById(`agent-card-${agentKey}`);
      const badge = document.getElementById(`badge-agent-${agentKey}`);
      const taskText = document.getElementById(`task-agent-${agentKey}`);
      const metaCapsule = document.getElementById(`meta-agent-${agentKey}`);

      if (!card) return;

      if (t) {
        if (t.status === "COMPLETED") {
          card.className = `agent-card completed ${AppState.selectedAgentInspector === agentKey ? "selected-inspector" : ""}`;
          if (badge) {
            const dur = t.duration_seconds ? `${t.duration_seconds.toFixed(1)}s` : "DONE";
            badge.textContent = dur !== "DONE" ? `✓ ${dur}` : "✓ DONE";
          }
        } else if (t.status === "RUNNING") {
          card.className = `agent-card running ${AppState.selectedAgentInspector === agentKey ? "selected-inspector" : ""}`;
          if (badge) badge.textContent = "⚡ ACTIVE";
        } else if (t.status === "FAILED") {
          card.className = `agent-card failed ${AppState.selectedAgentInspector === agentKey ? "selected-inspector" : ""}`;
          if (badge) badge.textContent = "✕ FAILED";
        }

        if (taskText && t.task_name) {
          taskText.textContent = t.task_name;
        }

        if (metaCapsule && t.output_data) {
          const out = t.output_data;
          let summary = "";
          if (agentKey === "planner") {
            const qCount = out.subquestions?.length || 0;
            summary = `${qCount} Sub-queries • 4 Research Facets`;
          } else if (agentKey === "researcher") {
            const sCount = out.total_sources || 0;
            const pdfCount = out.inspected_full_text_count || 0;
            summary = `${sCount} Sources Indexed • ${pdfCount} PDFs Parsed`;
          } else if (agentKey === "analyst") {
            const cCount = out.total_claims || (out.claims?.length) || 0;
            summary = `${cCount} Atomic Claims • Grounded`;
          } else if (agentKey === "fact_checker") {
            const supp = out.supported_count || 0;
            const tot = out.total_claims_audited || 0;
            summary = `${supp}/${tot} Supported • 0 Retries`;
          } else if (agentKey === "report_writer") {
            const cit = out.citation_count || 0;
            summary = `Report Compiled • ${cit} Citations`;
          }
          if (summary) {
            metaCapsule.innerHTML = `<span class="capsule-item">${escapeHtml(summary)}</span>`;
          }
        }
      } else {
        card.className = `agent-card ${AppState.selectedAgentInspector === agentKey ? "selected-inspector" : ""}`;
        if (badge) badge.textContent = "PENDING";
        if (taskText) taskText.textContent = agentMap[agentKey].defaultTask;
        if (metaCapsule) metaCapsule.innerHTML = '<span class="capsule-item">Awaiting trigger...</span>';
      }
    });

    // Populate terminal logs from tasks if terminal currently has 0 or only default 1 entry
    const terminal = document.getElementById("terminal-logs");
    if (terminal && (terminal.children.length <= 1) && tasks.length > 0) {
      terminal.innerHTML = "";
      tasks.forEach((t) => {
        const agentTag = t.agent_name.replace("_", " ").toUpperCase();
        const startStr = t.start_time ? new Date(t.start_time).toLocaleTimeString() : "--";
        const endStr = t.end_time ? new Date(t.end_time).toLocaleTimeString() : "--";
        const dur = t.duration_seconds ? `${t.duration_seconds.toFixed(1)}s` : "";

        // Start entry
        appendTerminalLogEntry(startStr, t.agent_name, `[${agentTag}] Initiated task: ${t.task_name}`);

        // Finish entry
        if (t.status === "COMPLETED") {
          let extra = "";
          if (t.output_data) {
            if (t.agent_name === "planner" && t.output_data.subquestions) {
              extra = ` — Formulated ${t.output_data.subquestions.length} research sub-questions`;
            } else if (t.agent_name === "researcher") {
              extra = ` — Harvested ${t.output_data.total_sources || 0} scholarly papers (${t.output_data.inspected_full_text_count || 0} full-text PDFs parsed)`;
            } else if (t.agent_name === "analyst") {
              extra = ` — Extracted ${t.output_data.total_claims || 0} verifiable claims linked to passages`;
            } else if (t.agent_name === "fact_checker") {
              extra = ` — Audited ${t.output_data.total_claims_audited || 0} claims: ${t.output_data.supported_count || 0} supported, ${t.output_data.contradicted_count || 0} contradicted`;
            } else if (t.agent_name === "report_writer") {
              extra = ` — Report finalized with ${t.output_data.citation_count || 0} citations and quality validation passed`;
            }
          }
          appendTerminalLogEntry(endStr, t.agent_name, `[${agentTag}] Completed in ${dur}${extra}`);
        } else if (t.status === "FAILED") {
          appendTerminalLogEntry(endStr, t.agent_name, `[${agentTag}] FAILED: ${t.error_message || "Unknown execution error"}`);
        }
      });

      if (run.status === "COMPLETED") {
        appendTerminalLogEntry(new Date(run.completed_time || Date.now()).toLocaleTimeString(), "system", "[SYSTEM] Multi-agent quality gates passed. Synthesized report published.");
      }
    }

    // Refresh telemetry view if active
    if (document.getElementById("inspector-view-telemetry")?.style.display !== "none") {
      showAgentPayload(AppState.selectedAgentInspector || "planner");
    }
  } catch (err) {
    console.warn("Tasks error:", err);
  }
}

async function loadRunSources(runId) {
  const tbody = document.getElementById("sources-table-body");
  if (!tbody) return;

  tbody.innerHTML = '<tr><td colspan="7" class="empty-state">Loading retrieved literature...</td></tr>';

  try {
    const res = await fetch(`/api/runs/${runId}/sources`);
    if (!res.ok) throw new Error("Could not load sources");
    const sources = await res.json();

    // Immediately update tab badge count
    updateRunHeaderCounts(sources.length, undefined);

    if (sources.length === 0) {
      tbody.innerHTML = '<tr><td colspan="7" class="empty-state">No sources retrieved yet for this inquiry.</td></tr>';
      return;
    }

    tbody.innerHTML = "";
    sources.forEach((s, idx) => {
      const row = document.createElement("tr");

      // Peer review badge
      const pubC = s.publication_classification || {};
      const prStatus = pubC.peer_review_status || s.doc_type || "UNKNOWN";
      let prBadge = `<span class="badge badge-neutral">${prStatus.replace(/_/g, " ")}</span>`;
      if (prStatus.includes("PEER_REVIEWED")) prBadge = `<span class="badge badge-success">${prStatus.replace(/_/g, " ")}</span>`;
      else if (prStatus === "PREPRINT") prBadge = `<span class="badge badge-warning">PREPRINT</span>`;

      // Relevance score
      const rel = s.relevance || {};
      let score = "--";
      if (rel.relevance_score !== undefined && rel.relevance_score !== null) {
        const num = Number(rel.relevance_score);
        score = num <= 1.0 ? `${Math.round(num * 100)}%` : `${Math.round(num)}%`;
      }

      // Access status
      const accessMode = s.inspected_full_text === 1 ? "Full-Text PDF" : "Abstract Only";

      // Link
      let linkHtml = "-";
      if (s.doi) linkHtml = `<a href="https://doi.org/${escapeHtml(s.doi)}" target="_blank" rel="noopener" class="citation-ref">DOI</a>`;
      else if (s.arxiv_id) linkHtml = `<a href="https://arxiv.org/abs/${escapeHtml(s.arxiv_id)}" target="_blank" rel="noopener" class="citation-ref">arXiv</a>`;
      else if (s.canonical_url) linkHtml = `<a href="${escapeHtml(s.canonical_url)}" target="_blank" rel="noopener" class="citation-ref">URL</a>`;

      row.innerHTML = `
        <td style="color:var(--text-muted); font-family:var(--font-mono);">${idx + 1}</td>
        <td>
          <div style="font-weight:600; color:var(--text-primary); margin-bottom:2px;">${escapeHtml(s.title)}</div>
          <div style="font-size:0.75rem; color:var(--text-secondary);">${escapeHtml(s.authors || "Unknown Authors")}</div>
        </td>
        <td>${s.publication_year || "n.d."}<br><span style="font-size:0.75rem; color:var(--text-muted);">${escapeHtml(pubC.venue_name || s.provider || "")}</span></td>
        <td>${score} (${rel.decision || "INCLUDE"})</td>
        <td>${prBadge}</td>
        <td><span class="badge badge-neutral">${accessMode}</span></td>
        <td>${linkHtml}</td>
      `;
      tbody.appendChild(row);
    });
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="7" class="badge-error">Error: ${err.message}</td></tr>`;
  }
}

async function loadRunClaims(runId) {
  const container = document.getElementById("claims-container");
  if (!container) return;

  container.innerHTML = '<div class="empty-state">Loading audited claims...</div>';

  try {
    const res = await fetch(`/api/runs/${runId}/claims`);
    if (!res.ok) throw new Error("Could not load claims");
    const claims = await res.json();

    // Immediately update tab badge count
    updateRunHeaderCounts(undefined, claims.length);

    if (claims.length === 0) {
      container.innerHTML = '<div class="empty-state">No claims verified for this inquiry.</div>';
      return;
    }

    container.innerHTML = "";
    claims.forEach((c) => {
      const v = c.verification || {};
      const verdict = v.verdict || "UNCHECKED";

      let verdictBadge = '<span class="badge badge-neutral">UNCHECKED</span>';
      if (verdict === "SUPPORTED") verdictBadge = '<span class="badge badge-success">SUPPORTED</span>';
      else if (verdict === "CONTRADICTED") verdictBadge = '<span class="badge badge-error">CONTRADICTED</span>';
      else if (verdict === "INSUFFICIENT_EVIDENCE") verdictBadge = '<span class="badge badge-warning">INSUFFICIENT EVIDENCE</span>';

      const card = document.createElement("div");
      card.className = "claim-card";

      const evPassages = (c.evidence || [])
        .map((ev) => `<div class="evidence-box"><strong>Passage:</strong> "${escapeHtml(ev.passage_text || "")}" <br><span style="font-size:0.72rem; color:var(--text-muted);">Source: ${escapeHtml(ev.source_title || ev.doi || "Indexed paper")}</span></div>`)
        .join("");

      card.innerHTML = `
        <div class="claim-header-row">
          <span style="font-size:0.75rem; font-weight:700; color:var(--text-muted); text-transform:uppercase;">Claim #${c.id.slice(0, 8)}</span>
          ${verdictBadge}
        </div>
        <div class="claim-text">"${escapeHtml(c.claim_text)}"</div>
        ${evPassages || '<div style="font-size:0.75rem; color:var(--text-muted); margin-bottom:8px;">No linked passage.</div>'}
        <div class="auditor-box">
          <strong>Auditor Rationale:</strong> ${escapeHtml(v.rationale || "Validated against literature passage.")}
        </div>
      `;
      container.appendChild(card);
    });
  } catch (err) {
    container.innerHTML = `<div class="badge-error">Error loading claims: ${err.message}</div>`;
  }
}

async function loadRunReport(runId) {
  const container = document.getElementById("report-view-container");
  const metaBox = document.getElementById("report-meta-box");
  if (!container) return;

  container.innerHTML = '<div class="loading-state"><div class="spinner"></div><span>Loading academic report...</span></div>';

  try {
    const res = await fetch(`/api/runs/${runId}/report`);
    if (res.status === 404) {
      if (metaBox) metaBox.style.display = "none";
      container.innerHTML = `
        <div class="empty-state">
          <h3>Report Not Ready</h3>
          <p>The research inquiry has not completed report generation yet.</p>
        </div>
      `;
      return;
    }

    const report = await res.json();
    if (metaBox) {
      metaBox.style.display = "block";
      metaBox.innerHTML = `
        <div style="display:flex; justify-content:space-between; align-items:center;">
          <span style="font-size:0.85rem; font-weight:700; color:var(--text-primary);">${escapeHtml(report.title)}</span>
          <span class="badge badge-success">${report.citation_count || 0} Citations Linked</span>
        </div>
      `;
    }

    // Render HTML body cleanly inside .report-paper
    const bodyMatch = report.html_content ? report.html_content.match(/<body[^>]*>([\s\S]*?)<\/body>/i) : null;
    const bodyHtml = bodyMatch ? bodyMatch[1] : report.html_content;

    container.innerHTML = `
      <div class="report-paper">
        ${bodyHtml}
      </div>
    `;
  } catch (err) {
    container.innerHTML = `<div class="badge-error">Error loading report: ${err.message}</div>`;
  }
}

// SSE Event Stream for Live Inquiries
function subscribeToRunEvents(runId) {
  if (AppState.eventSource) {
    AppState.eventSource.close();
  }

  const es = new EventSource(`/api/runs/${runId}/events`);
  AppState.eventSource = es;

  appendTerminalLog(`Connected to live event stream for Inquiry #${runId.slice(0, 8)}`);

  es.addEventListener("STATE_CHANGED", async (e) => {
    try {
      const payload = JSON.parse(e.data);
      appendTerminalLog(`State transition: ${payload.data?.new_state || "PROGRESS"}`);
    } catch (_) {}
    await refreshActiveRunMetadata(runId);
    if (AppState.activeRunSubtab === "monitor") {
      loadRunTasks(runId);
    } else if (AppState.activeRunSubtab === "sources") {
      loadRunSources(runId);
    } else if (AppState.activeRunSubtab === "verification") {
      loadRunClaims(runId);
    }
  });

  es.addEventListener("RUN_COMPLETED", async () => {
    appendTerminalLog("Workflow completed successfully. Quality gates passed.");
    await refreshActiveRunMetadata(runId);
    switchRunSubtab(AppState.activeRunSubtab);
    es.close();
  });

  es.addEventListener("RUN_FAILED", async (e) => {
    appendTerminalLog(`Workflow failed: ${e.data}`);
    await refreshActiveRunMetadata(runId);
    switchRunSubtab(AppState.activeRunSubtab);
    es.close();
  });
}

function appendTerminalLogEntry(timeStr, agentTagKey, messageText) {
  const terminal = document.getElementById("terminal-logs");
  if (!terminal) return;
  const entry = document.createElement("div");
  entry.className = "log-entry";
  const tagClass = `tag-${agentTagKey || "system"}`;
  entry.innerHTML = `
    <span class="log-time">[${timeStr}]</span>
    <span class="log-tag ${tagClass}">${escapeHtml((agentTagKey || "sys").toUpperCase().slice(0, 10))}</span>
    <span class="log-text">${escapeHtml(messageText)}</span>
  `;
  terminal.appendChild(entry);
  terminal.scrollTop = terminal.scrollHeight;
}

function appendTerminalLog(msg) {
  const now = new Date().toLocaleTimeString();
  let tagKey = "system";
  const lower = msg.toLowerCase();
  if (lower.includes("planner")) tagKey = "planner";
  else if (lower.includes("researcher")) tagKey = "researcher";
  else if (lower.includes("analyst")) tagKey = "analyst";
  else if (lower.includes("fact_checker") || lower.includes("fact-checker")) tagKey = "fact_checker";
  else if (lower.includes("report_writer") || lower.includes("report writer")) tagKey = "report_writer";

  appendTerminalLogEntry(now, tagKey, msg);
}

function switchInspectorTab(tabName) {
  const btnTerm = document.getElementById("tab-btn-terminal");
  const btnTelem = document.getElementById("tab-btn-telemetry");
  const viewTerm = document.getElementById("inspector-view-terminal");
  const viewTelem = document.getElementById("inspector-view-telemetry");

  if (tabName === "terminal") {
    if (btnTerm) btnTerm.classList.add("active");
    if (btnTelem) btnTelem.classList.remove("active");
    if (viewTerm) { viewTerm.style.display = "block"; viewTerm.classList.add("active"); }
    if (viewTelem) { viewTelem.style.display = "none"; viewTelem.classList.remove("active"); }
  } else {
    if (btnTerm) btnTerm.classList.remove("active");
    if (btnTelem) btnTelem.classList.add("active");
    if (viewTerm) { viewTerm.style.display = "none"; viewTerm.classList.remove("active"); }
    if (viewTelem) { viewTelem.style.display = "block"; viewTelem.classList.add("active"); }
    showAgentPayload(AppState.selectedAgentInspector || "planner");
  }
}

function selectAgentInspector(agentName) {
  AppState.selectedAgentInspector = agentName;
  document.querySelectorAll(".agent-card").forEach((c) => c.classList.remove("selected-inspector"));
  const card = document.getElementById(`agent-card-${agentName}`);
  if (card) card.classList.add("selected-inspector");

  switchInspectorTab("telemetry");
  showAgentPayload(agentName);
}

function showAgentPayload(agentName) {
  AppState.selectedAgentInspector = agentName;

  // Highlight pill
  document.querySelectorAll(".telemetry-pill").forEach((p) => p.classList.remove("active"));
  const activePill = document.getElementById(`pill-agent-${agentName}`);
  if (activePill) activePill.classList.add("active");

  const box = document.getElementById("telemetry-content-box");
  if (!box) return;

  const task = (AppState.currentRunTasks || []).find((t) => t.agent_name === agentName);

  if (!task || !task.output_data) {
    box.innerHTML = `
      <div class="empty-state" style="padding:28px 20px;">
        <div style="font-size:1.4rem; margin-bottom:8px;">⏳</div>
        <div style="font-weight:600; color:var(--text-primary); margin-bottom:4px;">No Output Telemetry Yet</div>
        <div style="font-size:0.8rem; color:var(--text-muted);">This agent has not completed its assigned execution stage for this inquiry.</div>
      </div>
    `;
    return;
  }

  const out = task.output_data;
  let detailHtml = "";

  if (agentName === "planner") {
    const subqs = out.subquestions || [];
    const objectives = out.objectives || [];
    detailHtml = `
      <div class="telemetry-card">
        <div class="telemetry-card-title">
          <span>🎯 Formulated Research Sub-Queries (${subqs.length})</span>
          <span class="badge badge-success">Strategy Ready</span>
        </div>
        <ul class="telemetry-item-list">
          ${subqs.map((q, idx) => `<li><strong>Q${idx + 1}:</strong> ${escapeHtml(typeof q === "string" ? q : q.query || JSON.stringify(q))}</li>`).join("")}
        </ul>
      </div>
      ${objectives.length ? `
      <div class="telemetry-card">
        <div class="telemetry-card-title">
          <span>📋 Research Objectives</span>
        </div>
        <ul class="telemetry-item-list">
          ${objectives.map((o) => `<li>&bull; ${escapeHtml(o)}</li>`).join("")}
        </ul>
      </div>` : ""}
    `;
  } else if (agentName === "researcher") {
    detailHtml = `
      <div class="telemetry-card">
        <div class="telemetry-card-title">
          <span>📚 Retrieval & Ingestion Breakdown</span>
          <span class="badge badge-success">${out.total_sources || 0} Sources Retrieved</span>
        </div>
        <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(180px, 1fr)); gap:10px; margin-top:8px;">
          <div style="background:var(--bg-surface); padding:10px; border-radius:4px; font-size:0.8rem;">
            <div style="color:var(--text-muted); font-size:0.72rem;">FULL-TEXT PDFS</div>
            <div style="font-size:1.2rem; font-weight:700; color:var(--text-primary);">${out.inspected_full_text_count || 0}</div>
          </div>
          <div style="background:var(--bg-surface); padding:10px; border-radius:4px; font-size:0.8rem;">
            <div style="color:var(--text-muted); font-size:0.72rem;">EXTRACTED PASSAGES</div>
            <div style="font-size:1.2rem; font-weight:700; color:var(--text-primary);">${out.total_passages || 0}</div>
          </div>
          <div style="background:var(--bg-surface); padding:10px; border-radius:4px; font-size:0.8rem;">
            <div style="color:var(--text-muted); font-size:0.72rem;">RELEVANCE INCLUDED</div>
            <div style="font-size:1.2rem; font-weight:700; color:var(--status-success);">${out.included_count || 0}</div>
          </div>
          <div style="background:var(--bg-surface); padding:10px; border-radius:4px; font-size:0.8rem;">
            <div style="color:var(--text-muted); font-size:0.72rem;">OPEN-ACCESS RATIO</div>
            <div style="font-size:1.2rem; font-weight:700; color:var(--accent-secondary);">${out.open_access_count || out.total_sources || 0}/${out.total_sources || 0}</div>
          </div>
        </div>
      </div>
    `;
  } else if (agentName === "analyst") {
    const claims = out.claims || [];
    detailHtml = `
      <div class="telemetry-card">
        <div class="telemetry-card-title">
          <span>🧠 Extracted Atomic Claims (${out.total_claims || claims.length})</span>
          <span class="badge badge-success">Attribution Linked</span>
        </div>
        <ul class="telemetry-item-list">
          ${claims.slice(0, 10).map((c, idx) => `
            <li>
              <strong>Claim #${idx + 1}:</strong> "${escapeHtml(typeof c === "string" ? c : c.claim_text || JSON.stringify(c))}"
            </li>
          `).join("")}
        </ul>
      </div>
      ${out.synthesis_summary ? `
      <div class="telemetry-card">
        <div class="telemetry-card-title"><span>Synthesis Abstract</span></div>
        <div style="font-size:0.82rem; color:var(--text-secondary); line-height:1.5;">${escapeHtml(out.synthesis_summary)}</div>
      </div>` : ""}
    `;
  } else if (agentName === "fact_checker") {
    detailHtml = `
      <div class="telemetry-card">
        <div class="telemetry-card-title">
          <span>⚖️ Verification Audit Matrix Results</span>
          <span class="badge ${out.supported_count === out.total_claims_audited ? "badge-success" : "badge-warning"}">
            ${out.supported_count || 0}/${out.total_claims_audited || 0} Verified
          </span>
        </div>
        <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(160px, 1fr)); gap:10px; margin-top:8px;">
          <div style="background:var(--bg-surface); padding:10px; border-radius:4px; font-size:0.8rem;">
            <div style="color:var(--text-muted); font-size:0.72rem;">SUPPORTED</div>
            <div style="font-size:1.2rem; font-weight:700; color:var(--status-success);">${out.supported_count || 0}</div>
          </div>
          <div style="background:var(--bg-surface); padding:10px; border-radius:4px; font-size:0.8rem;">
            <div style="color:var(--text-muted); font-size:0.72rem;">CONTRADICTED</div>
            <div style="font-size:1.2rem; font-weight:700; color:var(--status-error);">${out.contradicted_count || 0}</div>
          </div>
          <div style="background:var(--bg-surface); padding:10px; border-radius:4px; font-size:0.8rem;">
            <div style="color:var(--text-muted); font-size:0.72rem;">INSUFFICIENT EVIDENCE</div>
            <div style="font-size:1.2rem; font-weight:700; color:var(--status-warning);">${out.insufficient_evidence_count || 0}</div>
          </div>
          <div style="background:var(--bg-surface); padding:10px; border-radius:4px; font-size:0.8rem;">
            <div style="color:var(--text-muted); font-size:0.72rem;">RETRIES REQUIRED</div>
            <div style="font-size:1.2rem; font-weight:700; color:var(--text-primary);">${out.needs_retry ? "Yes" : "0 (Passed Gate)"}</div>
          </div>
        </div>
      </div>
    `;
  } else if (agentName === "report_writer") {
    detailHtml = `
      <div class="telemetry-card">
        <div class="telemetry-card-title">
          <span>📑 Academic Report Generation Telemetry</span>
          <span class="badge badge-success">Quality Gated</span>
        </div>
        <div style="font-size:0.85rem; color:var(--text-primary); margin-bottom:10px;">
          <strong>Title:</strong> ${escapeHtml(out.title || "Academic Report")}
        </div>
        <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(180px, 1fr)); gap:10px;">
          <div style="background:var(--bg-surface); padding:10px; border-radius:4px;">
            <div style="color:var(--text-muted); font-size:0.72rem;">LINKED CITATIONS</div>
            <div style="font-size:1.2rem; font-weight:700; color:var(--accent-secondary);">${out.citation_count || 0}</div>
          </div>
          <div style="background:var(--bg-surface); padding:10px; border-radius:4px;">
            <div style="color:var(--text-muted); font-size:0.72rem;">VERIFIED CLAIMS</div>
            <div style="font-size:1.2rem; font-weight:700; color:var(--status-success);">${out.verified_claim_count || 0}</div>
          </div>
          <div style="background:var(--bg-surface); padding:10px; border-radius:4px;">
            <div style="color:var(--text-muted); font-size:0.72rem;">QUALITY STATUS</div>
            <div style="font-size:1.2rem; font-weight:700; color:var(--status-success);">PASSED</div>
          </div>
        </div>
      </div>
    `;
  }

  // Raw JSON toggle accordion
  const rawJson = JSON.stringify(out, null, 2);
  const rawAccordion = `
    <details style="margin-top:14px; background:var(--bg-base); border:1px solid var(--border-subtle); border-radius:4px; padding:8px 12px;">
      <summary style="cursor:pointer; font-size:0.78rem; font-weight:600; color:var(--text-muted);">
        { } View Raw Task Output JSON (${(rawJson.length / 1024).toFixed(1)} KB)
      </summary>
      <pre style="margin-top:8px; font-family:var(--font-mono); font-size:0.74rem; color:var(--accent-secondary); max-height:240px; overflow-y:auto; white-space:pre-wrap; word-break:break-all;">${escapeHtml(rawJson)}</pre>
    </details>
  `;

  box.innerHTML = `
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:14px;">
      <div style="font-size:0.92rem; font-weight:700; color:var(--text-primary);">
        Task Payload: <span style="color:var(--accent-secondary);">${escapeHtml(task.task_name)}</span>
      </div>
      <div style="font-size:0.76rem; color:var(--text-muted); font-family:var(--font-mono);">
        Duration: ${task.duration_seconds ? task.duration_seconds.toFixed(2) + "s" : "--"} &bull; Attempt #${(task.retry_attempt || 0) + 1}
      </div>
    </div>
    ${detailHtml}
    ${rawAccordion}
  `;
}

function copyTerminalLogs() {
  const terminal = document.getElementById("terminal-logs");
  if (!terminal) return;
  const text = terminal.innerText;
  navigator.clipboard.writeText(text).then(() => {
    alert("Event stream logs copied to clipboard!");
  }).catch(() => {
    alert("Could not copy logs to clipboard.");
  });
}

function clearTerminalLogs() {
  const terminal = document.getElementById("terminal-logs");
  if (terminal) {
    terminal.innerHTML = '<div class="log-entry"><span class="log-time">[System]</span><span>Event stream buffer cleared.</span></div>';
  }
}

async function cancelActiveRun() {
  if (!AppState.currentRunId) return;
  if (!confirm("Are you sure you want to cancel this active research run?")) return;
  try {
    await fetch(`/api/runs/${AppState.currentRunId}/cancel`, { method: "POST" });
    appendTerminalLog("Cancellation requested.");
  } catch (err) {
    alert("Cancellation error: " + err.message);
  }
}

// ==========================================================================
// VIEW 4: SYNTHESIS VIEWER LOGIC
// ==========================================================================

async function openSynthesisView(synthesisId, updateUrl = true) {
  AppState.currentSynthesisId = synthesisId;
  if (updateUrl) updateHash(`synthesis/${synthesisId}`);

  AppState.activeScreen = "synthesis";
  document.querySelectorAll(".sidebar-nav .nav-link").forEach((link) => {
    link.classList.toggle("active", link.getAttribute("data-screen") === "synthesis");
  });
  document.querySelectorAll(".view-panel").forEach((panel) => {
    panel.classList.toggle("active", panel.id === "view-synthesis");
  });

  const navSynth = document.getElementById("nav-synthesis");
  if (navSynth) navSynth.style.display = "flex";

  const container = document.getElementById("synthesis-content-container");
  container.innerHTML = '<div class="loading-state"><div class="spinner"></div><span>Loading synthesis document...</span></div>';

  try {
    const res = await fetch(`/api/syntheses/${synthesisId}`);
    if (!res.ok) throw new Error("Synthesis not found");
    const s = await res.json();

    if (s.project_id) AppState.currentProjectId = s.project_id;
    updateBreadcrumbs("synthesis");

    document.getElementById("synthesis-title-heading").textContent = s.title;
    document.getElementById("synthesis-meta-display").textContent = `Created: ${new Date(s.created_at).toLocaleString()} • ${s.contributing_run_ids?.length || 0} Inquiries Synthesized • ${s.citation_count || 0} Unique Citations • ${s.conflict_count || 0} Divergences Analyzed`;

    document.getElementById("btn-synth-export-md").href = `/api/syntheses/${synthesisId}/export/markdown`;
    document.getElementById("btn-synth-export-html").href = `/api/syntheses/${synthesisId}/export/html`;

    const bodyMatch = s.html_content ? s.html_content.match(/<body[^>]*>([\s\S]*?)<\/body>/i) : null;
    const bodyHtml = bodyMatch ? bodyMatch[1] : s.html_content;

    container.innerHTML = bodyHtml;
  } catch (err) {
    container.innerHTML = `<div class="badge-error">Error loading synthesis: ${err.message}</div>`;
  }
}

async function deleteActiveSynthesis() {
  if (!AppState.currentSynthesisId) return;
  if (!confirm("Are you sure you want to delete this synthesis document? This will not affect the original inquiry reports.")) return;

  try {
    const res = await fetch(`/api/syntheses/${AppState.currentSynthesisId}`, { method: "DELETE" });
    if (!res.ok) throw new Error("Could not delete synthesis");
    alert("Synthesis deleted.");
    if (AppState.currentProjectId) {
      openProjectWorkspace(AppState.currentProjectId);
      switchWorkspaceTab("syntheses");
    } else {
      navigateTo("projects");
    }
  } catch (err) {
    alert("Error: " + err.message);
  }
}

// ==========================================================================
// VIEW 5: EVALUATION & BENCHMARKS LOGIC
// ==========================================================================

async function loadBenchmarksSuite() {
  const select = document.getElementById("benchmark-question-select");
  const tbody = document.getElementById("benchmarks-body");

  try {
    const [qRes, rRes] = await Promise.all([
      fetch("/api/benchmarks/questions"),
      fetch("/api/benchmarks/results"),
    ]);

    if (qRes.ok && select) {
      const questions = await qRes.json();
      select.innerHTML = '<option value="">-- Choose Benchmark Question --</option>';
      questions.forEach((q) => {
        const opt = document.createElement("option");
        opt.value = q.id;
        opt.textContent = `[${q.category}] ${q.question.slice(0, 70)}...`;
        select.appendChild(opt);
      });
    }

    if (rRes.ok && tbody) {
      const results = await rRes.json();
      if (results.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" class="empty-state">No benchmark evaluations recorded yet. Run a test above.</td></tr>';
        return;
      }

      tbody.innerHTML = "";
      results.forEach((r) => {
        const row = document.createElement("tr");
        const rel = r.retrieval_relevance !== null ? `${(r.retrieval_relevance * 100).toFixed(0)}%` : "--";
        const cov = r.research_coverage !== null ? `${(r.research_coverage * 100).toFixed(0)}%` : "--";
        const csr = r.claim_support_rate !== null ? `${(r.claim_support_rate * 100).toFixed(0)}%` : "--";
        const cor = r.citation_correctness !== null ? `${(r.citation_correctness * 100).toFixed(0)}%` : "--";

        row.innerHTML = `
          <td><code>${escapeHtml(r.benchmark_question_id)}</code></td>
          <td><span class="domain-pill">${escapeHtml(r.system_variant)}</span></td>
          <td>${rel}</td>
          <td>${cov}</td>
          <td>${csr}</td>
          <td>${cor}</td>
          <td>${r.runtime_seconds ? r.runtime_seconds.toFixed(1) + 's' : '--'}</td>
        `;
        tbody.appendChild(row);
      });
    }
  } catch (err) {
    console.warn("Benchmarks error:", err);
  }
}

async function runBenchmarkTest() {
  const select = document.getElementById("benchmark-question-select");
  const qId = select.value;
  if (!qId) {
    alert("Please select a benchmark evaluation question.");
    return;
  }

  const btn = document.getElementById("btn-run-benchmark");
  btn.disabled = true;
  btn.textContent = "Executing Benchmark...";

  try {
    const res = await fetch("/api/benchmarks/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question_id: qId, system_variant: "five_agent_collaborative" }),
    });
    if (!res.ok) throw new Error("Benchmark execution failed");
    alert("Benchmark test completed successfully!");
    await loadBenchmarksSuite();
  } catch (err) {
    alert("Error: " + err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "Run Benchmark Test";
  }
}

// ==========================================================================
// MODAL CONTROLLERS & ACTIONS
// ==========================================================================

function openModal(id) {
  const m = document.getElementById(id);
  if (m) m.style.display = "flex";
}

function closeModal(id) {
  const m = document.getElementById(id);
  if (m) m.style.display = "none";
}

// Create Project Modal
function openCreateProjectModal() {
  document.getElementById("new-project-title").value = "";
  document.getElementById("new-project-desc").value = "";
  openModal("modal-create-project");
  document.getElementById("new-project-title").focus();
}

function fillProjectTemplate(title, desc) {
  document.getElementById("new-project-title").value = title;
  document.getElementById("new-project-desc").value = desc;
}

async function handleCreateProjectSubmit(e) {
  e.preventDefault();
  const title = document.getElementById("new-project-title").value.trim();
  const desc = document.getElementById("new-project-desc").value.trim();

  if (title.length < 3) {
    alert("Project name must be at least 3 characters.");
    return;
  }

  const btn = document.getElementById("btn-submit-create-project");
  btn.disabled = true;
  btn.textContent = "Creating...";

  try {
    const res = await fetch("/api/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title, description: desc }),
    });
    if (!res.ok) throw new Error("Failed to create project");
    const newProj = await res.json();
    closeModal("modal-create-project");
    await openProjectWorkspace(newProj.id);
  } catch (err) {
    alert("Error creating project: " + err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "Create Workspace";
  }
}

// Edit Project Modal
function openEditProjectModal() {
  if (!AppState.currentProjectData) return;
  document.getElementById("edit-project-title").value = AppState.currentProjectData.title || "";
  document.getElementById("edit-project-desc").value = AppState.currentProjectData.description || "";
  openModal("modal-edit-project");
}

async function handleEditProjectSubmit(e) {
  e.preventDefault();
  if (!AppState.currentProjectId) return;
  const title = document.getElementById("edit-project-title").value.trim();
  const desc = document.getElementById("edit-project-desc").value.trim();

  try {
    const res = await fetch(`/api/projects/${AppState.currentProjectId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title, description: desc }),
    });
    if (!res.ok) throw new Error("Failed to update project");
    closeModal("modal-edit-project");
    await openProjectWorkspace(AppState.currentProjectId);
  } catch (err) {
    alert("Error: " + err.message);
  }
}

// Archive / Restore
async function toggleArchiveProject() {
  if (!AppState.currentProjectId || !AppState.currentProjectData) return;
  const isArchived = AppState.currentProjectData.status === "ARCHIVED";
  const actionEndpoint = isArchived ? "restore" : "archive";

  try {
    const res = await fetch(`/api/projects/${AppState.currentProjectId}/${actionEndpoint}`, {
      method: "POST",
    });
    if (!res.ok) throw new Error(`Failed to ${actionEndpoint} project`);
    await openProjectWorkspace(AppState.currentProjectId);
  } catch (err) {
    alert("Error: " + err.message);
  }
}

// Delete Project Modal
async function openDeleteProjectModal() {
  if (!AppState.currentProjectId || !AppState.currentProjectData) return;
  document.getElementById("delete-project-name").textContent = AppState.currentProjectData.title;
  const discBox = document.getElementById("delete-disclosure-box");
  discBox.textContent = "Analyzing dependent research runs...";
  openModal("modal-delete-project");

  try {
    const res = await fetch(`/api/projects/${AppState.currentProjectId}`);
    const data = await res.json();
    const stats = data.stats || {};
    discBox.innerHTML = `
      <strong>Dependent Records to be Deleted:</strong>
      <ul style="margin:6px 0 0 20px; font-size:0.82rem;">
        <li><strong>${stats.runs_count || 0}</strong> Research inquiries and execution history</li>
        <li><strong>${stats.sources_count || 0}</strong> Indexed scientific papers and passages</li>
        <li><strong>${stats.reports_count || 0}</strong> Final scholarly reports</li>
        <li><strong>${stats.syntheses_count || 0}</strong> Multi-run synthesis documents</li>
      </ul>
    `;
  } catch (_) {
    discBox.textContent = "All dependent runs, sources, and reports will be deleted.";
  }
}

async function executeDeleteProject() {
  if (!AppState.currentProjectId) return;
  const btn = document.getElementById("btn-confirm-delete-project");
  btn.disabled = true;
  btn.textContent = "Deleting...";

  try {
    const res = await fetch(`/api/projects/${AppState.currentProjectId}`, {
      method: "DELETE",
    });
    if (!res.ok) throw new Error("Delete failed");
    closeModal("modal-delete-project");
    AppState.currentProjectId = null;
    AppState.currentProjectData = null;
    const sbCtx = document.getElementById("sidebar-project-context");
    if (sbCtx) sbCtx.style.display = "none";
    await navigateTo("projects");
  } catch (err) {
    alert("Delete error: " + err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "Permanently Delete Project";
  }
}

// Delete Research Run Modal Logic
function openDeleteRunModal(runId, event) {
  if (event) event.stopPropagation();
  AppState.deletingRunId = runId;

  let question = "Research Inquiry";
  if (AppState.currentProjectData && AppState.currentProjectData.runs) {
    const found = AppState.currentProjectData.runs.find((r) => r.id === runId);
    if (found) question = found.question;
  } else if (AppState.currentRunData && AppState.currentRunData.id === runId) {
    question = AppState.currentRunData.question;
  }

  const qEl = document.getElementById("delete-run-question-display");
  if (qEl) qEl.textContent = question;

  const idEl = document.getElementById("delete-run-id-display");
  if (idEl) idEl.textContent = `Run ID: #${runId}`;

  openModal("modal-delete-run");
}

async function executeDeleteRun() {
  const runId = AppState.deletingRunId;
  if (!runId) return;

  const btn = document.getElementById("btn-confirm-delete-run");
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner" style="width:14px; height:14px; border-width:2px; display:inline-block; vertical-align:middle; margin-right:6px;"></span> Deleting Run...';
  }

  try {
    const res = await fetch(`/api/runs/${runId}`, { method: "DELETE" });
    if (!res.ok) throw new Error("Server failed to delete run");

    closeModal("modal-delete-run");
    AppState.deletingRunId = null;

    // If currently viewing the deleted run, navigate back to workspace
    if (AppState.activeScreen === "run" && AppState.currentRunId === runId) {
      if (AppState.currentProjectId) {
        await openProjectWorkspace(AppState.currentProjectId);
      } else {
        await navigateTo("projects");
      }
    } else if (AppState.currentProjectId) {
      // Refresh project workspace to remove card and update stats ribbon
      await openProjectWorkspace(AppState.currentProjectId);
    }
  } catch (err) {
    alert("Error deleting research run: " + err.message);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = "Permanently Delete Run";
    }
  }
}

// New Research Run Modal
function openNewRunModal() {
  if (!AppState.currentProjectId) {
    alert("Please select or create a project workspace first.");
    return;
  }
  
  // Update target workspace display
  const disp = document.getElementById("modal-run-project-display");
  if (disp && AppState.currentProjectData) {
    disp.textContent = `${AppState.currentProjectData.title} (#${AppState.currentProjectId.slice(0, 8)})`;
  }
  
  // Clear any existing inline error
  clearRunFormError();
  
  // Set defaults while preserving question if already typed
  const questionEl = document.getElementById("run-form-question");
  if (questionEl && !questionEl.value) {
    questionEl.value = "";
  }
  
  const domainEl = document.getElementById("run-form-domain");
  if (domainEl) domainEl.value = "Computer Science & AI";
  
  const customDomainEl = document.getElementById("run-form-custom-domain");
  if (customDomainEl) {
    customDomainEl.value = "";
    customDomainEl.style.display = "none";
  }
  
  const maxSourcesEl = document.getElementById("run-form-max-sources");
  if (maxSourcesEl) maxSourcesEl.value = "8";
  
  const oaCheck = document.getElementById("run-source-openalex");
  if (oaCheck) oaCheck.checked = true;
  
  const arxivCheck = document.getElementById("run-source-arxiv");
  if (arxivCheck) arxivCheck.checked = true;
  
  const pubPrefEl = document.getElementById("run-form-pub-pref");
  if (pubPrefEl) pubPrefEl.value = "all";
  
  const modeEl = document.getElementById("run-form-mode");
  if (modeEl) modeEl.value = "ollama";
  
  const evPrefEl = document.getElementById("run-adv-evidence-pref");
  if (evPrefEl) evPrefEl.value = "full_text_preferred";
  
  const relCutoffEl = document.getElementById("run-adv-relevance-cutoff");
  if (relCutoffEl) relCutoffEl.value = "50";
  
  const retriesEl = document.getElementById("run-adv-retries");
  if (retriesEl) retriesEl.value = "2";
  
  openModal("modal-new-run");
  if (questionEl) questionEl.focus();
}

function handleDomainChange() {
  const domainSelect = document.getElementById("run-form-domain");
  const customDomainInput = document.getElementById("run-form-custom-domain");
  if (!domainSelect || !customDomainInput) return;
  
  if (domainSelect.value === "CUSTOM") {
    customDomainInput.style.display = "block";
    customDomainInput.focus();
  } else {
    customDomainInput.style.display = "none";
  }
}

function showRunFormError(msg) {
  const errBox = document.getElementById("run-form-error");
  const errMsg = document.getElementById("run-form-error-msg");
  if (errBox && errMsg) {
    errMsg.textContent = msg;
    errBox.style.display = "flex";
  }
}

function clearRunFormError() {
  const errBox = document.getElementById("run-form-error");
  if (errBox) errBox.style.display = "none";
}

function fillQuestion(q) {
  const questionEl = document.getElementById("run-form-question");
  if (questionEl) {
    questionEl.value = q;
    clearRunFormError();
    questionEl.focus();
  }
}

function toggleAdvancedSettings() {
  const box = document.getElementById("adv-settings-box");
  const arrow = document.getElementById("adv-arrow");
  if (!box || !arrow) return;
  if (box.style.display === "none") {
    box.style.display = "block";
    arrow.textContent = "▼";
  } else {
    box.style.display = "none";
    arrow.textContent = "▶";
  }
}

async function handleNewRunSubmit(e) {
  e.preventDefault();
  if (!AppState.currentProjectId) {
    showRunFormError("No active target workspace found. Please select a project first.");
    return;
  }

  clearRunFormError();

  const question = (document.getElementById("run-form-question")?.value || "").trim();
  const domainSelect = document.getElementById("run-form-domain")?.value || "Computer Science & AI";
  let domain = domainSelect;
  if (domainSelect === "CUSTOM") {
    domain = (document.getElementById("run-form-custom-domain")?.value || "").trim();
    if (!domain) {
      showRunFormError("Please enter your custom academic domain / subject area.");
      document.getElementById("run-form-custom-domain")?.focus();
      return;
    }
  }

  const maxSourcesRaw = document.getElementById("run-form-max-sources")?.value;
  const maxSources = parseInt(maxSourcesRaw, 10);
  if (isNaN(maxSources) || maxSources < 2 || maxSources > 30) {
    showRunFormError("Maximum source retrieval cap must be an integer between 2 and 30.");
    document.getElementById("run-form-max-sources")?.focus();
    return;
  }

  const providers = [];
  if (document.getElementById("run-source-openalex")?.checked) providers.push("openalex");
  if (document.getElementById("run-source-arxiv")?.checked) providers.push("arxiv");

  if (providers.length === 0) {
    showRunFormError("Please select at least one scholarly repository (OpenAlex or arXiv).");
    return;
  }

  if (question.length < 5) {
    showRunFormError("Please enter a research query of at least 5 characters (recommended 15+ characters).");
    document.getElementById("run-form-question")?.focus();
    return;
  }

  const mode = document.getElementById("run-form-mode")?.value || "ollama";
  const pubPref = document.getElementById("run-form-pub-pref")?.value || "all";
  const evidencePref = document.getElementById("run-adv-evidence-pref")?.value || "full_text_preferred";
  const relevanceThreshold = parseFloat(document.getElementById("run-adv-relevance-cutoff")?.value || "50");
  const maxRetries = parseInt(document.getElementById("run-adv-retries")?.value || "2", 10);

  const btn = document.getElementById("btn-submit-new-run");
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner" style="width:14px; height:14px; border-width:2px; display:inline-block; vertical-align:middle; margin-right:6px;"></span> Initiating Research Run...';

  try {
    const res = await fetch(`/api/projects/${AppState.currentProjectId}/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question: question,
        domain: domain,
        max_sources: maxSources,
        search_providers: providers,
        provider_mode: mode,
        publication_preference: pubPref,
        evidence_preference: evidencePref,
        relevance_threshold: isNaN(relevanceThreshold) ? 50.0 : relevanceThreshold,
        max_retries: isNaN(maxRetries) ? 2 : maxRetries,
      }),
    });

    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      throw new Error(errData.detail || "Server rejected run submission");
    }

    const run = await res.json();
    closeModal("modal-new-run");

    // Open newly launched run and jump to Agent Activity Monitor
    AppState.activeRunSubtab = "monitor";
    await openRunResults(run.id);
  } catch (err) {
    showRunFormError("Failed to initiate research run: " + err.message);
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<span class="btn-icon">⚡</span> Start Research Run';
  }
}

// Create Synthesis Modal
async function openCreateSynthesisModal() {
  if (!AppState.currentProjectId) return;
  const list = document.getElementById("synthesis-runs-checklist");
  list.innerHTML = '<div class="loading-state"><div class="spinner"></div><span>Loading completed runs...</span></div>';
  document.getElementById("synth-title").value = "";
  openModal("modal-create-synthesis");

  try {
    const res = await fetch(`/api/projects/${AppState.currentProjectId}`);
    const data = await res.json();
    const runs = data.runs || [];
    const completedRuns = runs.filter((r) => r.has_report || r.status === "COMPLETED");

    if (completedRuns.length < 2) {
      list.innerHTML = `
        <div class="empty-state" style="padding:20px; font-size:0.85rem;">
          ⚠️ Research synthesis requires at least <strong>2 completed inquiries</strong> with generated reports. Currently, this project has <strong>${completedRuns.length}</strong> eligible run(s). Complete another inquiry to enable synthesis.
        </div>
      `;
      document.getElementById("btn-submit-synthesis").disabled = true;
      return;
    }

    document.getElementById("btn-submit-synthesis").disabled = false;
    list.innerHTML = "";
    completedRuns.forEach((r, idx) => {
      const item = document.createElement("label");
      item.className = "run-checkbox-item";
      item.innerHTML = `
        <input type="checkbox" name="synth-run" value="${r.id}" ${idx < 4 ? "checked" : ""}>
        <div>
          <div style="font-weight:600; color:var(--text-primary); font-size:0.85rem;">${escapeHtml(r.question)}</div>
          <div style="font-size:0.75rem; color:var(--text-muted);">${r.domain || "Computer Science"} &bull; #${r.id.slice(0, 8)} &bull; ${new Date(r.created_at).toLocaleDateString()}</div>
        </div>
      `;
      list.appendChild(item);
    });
  } catch (err) {
    list.innerHTML = `<div class="badge-error">Error loading runs: ${err.message}</div>`;
  }
}

async function handleCreateSynthesisSubmit(e) {
  e.preventDefault();
  if (!AppState.currentProjectId) return;

  const checkboxes = document.querySelectorAll('input[name="synth-run"]:checked');
  const runIds = Array.from(checkboxes).map((cb) => cb.value);

  if (runIds.length < 2) {
    alert("Please select at least 2 research inquiries to synthesize.");
    return;
  }

  const title = document.getElementById("synth-title").value.trim() || null;
  const btn = document.getElementById("btn-submit-synthesis");
  btn.disabled = true;
  btn.textContent = "Synthesizing Findings...";

  try {
    const res = await fetch(`/api/projects/${AppState.currentProjectId}/synthesis`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ run_ids: runIds, title: title }),
    });
    if (!res.ok) {
      const errData = await res.json();
      throw new Error(errData.detail || "Synthesis creation failed");
    }
    const synthesis = await res.json();
    closeModal("modal-create-synthesis");
    await openSynthesisView(synthesis.id);
  } catch (err) {
    alert("Synthesis error: " + err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "Generate Synthesis";
  }
}

// Utility
function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
