
function serializeHashState() {
  const params = new URLSearchParams();
  params.set("view", state.currentView || "skills");
  if (state.currentView === "skills") {
    params.set("skill_mode", state.skillManagerMode || "matrix");
    Object.entries(state.matrixQuery).forEach(([key, value]) => {
      if (value === null || value === undefined || value === "") {
        return;
      }
      params.set(`matrix_${key}`, String(value));
    });
    if (state.selectedMatrixFamily) {
      params.set("matrix_family", state.selectedMatrixFamily);
    }
    if (state.selectedMatrixClient) {
      params.set("matrix_client_focus", state.selectedMatrixClient);
    }
    if (state.selectedMatrixFamilies.length) {
      params.set("matrix_selected", state.selectedMatrixFamilies.join(","));
    }
  }
  if (state.currentView === "skills") {
    Object.entries(state.skillQuery).forEach(([key, value]) => {
      const defaultValue = DEFAULT_SKILL_QUERY[key];
      if (value === null || value === undefined || value === "" || value === defaultValue) {
        return;
      }
      params.set(key, String(value));
    });
    if (state.selectedSkillId) {
      params.set("skill_id", state.selectedSkillId);
    }
  }
  if (state.currentView === "conflicts" && state.conflictFamilyFilter) {
    params.set("conflict_family", state.conflictFamilyFilter);
  }
  if (state.currentView === "sync") {
    if (state.syncCenter.sourceClient) {
      params.set("sync_source", state.syncCenter.sourceClient);
    }
    if (state.syncCenter.targetClients.length) {
      params.set("sync_targets", state.syncCenter.targetClients.join(","));
    }
    if (!state.syncCenter.includeSkills) {
      params.set("sync_skills", "0");
    }
    if (!state.syncCenter.includeMcp) {
      params.set("sync_mcp", "0");
    }
    if (state.syncCenter.scope && state.syncCenter.scope !== "all_published") {
      params.set("sync_scope", state.syncCenter.scope);
    }
  }
  return params.toString();
}

function syncHash() {
  const nextHash = serializeHashState() || "view=dashboard";
  if (window.location.hash.slice(1) === nextHash) {
    return;
  }
  hashSyncing = true;
  window.location.hash = nextHash;
  window.setTimeout(() => {
    hashSyncing = false;
  }, 0);
}

function applyHashState() {
  const params = new URLSearchParams(window.location.hash.replace(/^#/, ""));
  const view = params.get("view");
  state.currentView = view || "skills";
  state.skillManagerMode = params.get("skill_mode") || "matrix";
  state.matrixQuery = {
    ...DEFAULT_MATRIX_QUERY,
    q: params.get("matrix_q") || "",
    client: params.get("matrix_client") || "",
    anomaly: params.get("matrix_anomaly") || "",
    source_scope: params.get("matrix_source_scope") || "",
    only_anomalies: params.get("matrix_only_anomalies") || "",
    only_duplicates: params.get("matrix_only_duplicates") || "",
  };
  state.skillQuery = {
    ...DEFAULT_SKILL_QUERY,
    page: Math.max(parseIntSafe(params.get("page"), DEFAULT_SKILL_QUERY.page), 1),
    page_size: Math.max(parseIntSafe(params.get("page_size"), DEFAULT_SKILL_QUERY.page_size), 1),
    sort_by: params.get("sort_by") || DEFAULT_SKILL_QUERY.sort_by,
    sort_dir: params.get("sort_dir") || DEFAULT_SKILL_QUERY.sort_dir,
    client: params.get("client") || "",
    family: params.get("family") || "",
    status: params.get("status") || "",
    enabled_global: params.get("enabled_global") || "",
    source_scope: params.get("source_scope") || "",
    q: params.get("q") || "",
  };
  state.selectedSkillId = params.get("skill_id") || null;
  state.selectedMatrixFamily = params.get("matrix_family") || null;
  state.selectedMatrixClient = params.get("matrix_client_focus") || null;
  state.selectedMatrixFamilies = (params.get("matrix_selected") || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  state.conflictFamilyFilter = params.get("conflict_family") || "";
  state.syncCenter.sourceClient = params.get("sync_source") || state.syncCenter.sourceClient || "";
  state.syncCenter.targetClients = (params.get("sync_targets") || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  state.syncCenter.includeSkills = params.get("sync_skills") !== "0";
  state.syncCenter.includeMcp = params.get("sync_mcp") !== "0";
  state.syncCenter.scope = params.get("sync_scope") || "all_published";
}

function switchView(view, { sync = true } = {}) {
  state.currentView = view;
  $$(".nav-link").forEach((button) => button.classList.toggle("active", button.dataset.view === view));
  $$(".view").forEach((section) => section.classList.toggle("active", section.id === `view-${view}`));
  if (sync) {
    syncHash();
  }
}

async function refreshAll() {
  const [status, reports, skills, conflicts, systemStatus, toolActions] = await Promise.all([
    api("/api/status"),
    api("/api/reports"),
    api(buildSkillsPath()),
    api(buildConflictsPath()),
    api("/api/system"),
    api("/api/tools/actions"),
  ]);
  state.status = status;
  state.reports = reports;
  state.skills = skills;
  state.conflicts = conflicts;
  state.systemStatus = systemStatus;
  state.toolActions = toolActions;
  if (!state.selectedQuickActionId || !(toolActions.actions || []).some((item) => item.id === state.selectedQuickActionId)) {
    state.selectedQuickActionId = toolActions.actions?.[0]?.id || null;
  }
  ensureCurrentClient();
  renderAll();
  if (state.currentView === "inventory" || state.inventorySummary) {
    state.inventorySummary = await api("/api/inventory");
    if (state.currentClient) {
      state.inventoryDetails[state.currentClient] = await api(`/api/inventory/${encodeURIComponent(state.currentClient)}`);
    }
  }
  if (state.currentView === "mcp" || state.mcpSummary) {
    state.mcpSummary = await api("/api/mcp/clients");
    if (state.currentClient) {
      state.mcpDetails[state.currentClient] = await api(`/api/mcp/clients/${encodeURIComponent(state.currentClient)}`);
    }
  }
  if (state.currentView === "cleanup" || state.cleanup) {
    state.cleanup = await api("/api/cleanup");
  }
  if (state.currentView === "skills" || state.currentView === "sync" || state.skillMatrix?.rows?.length || state.scanSources?.sources?.length || state.discoverySummary) {
    state.skillManagerLoading = true;
    renderSkillManager();
    const matrix = await api(buildSkillMatrixPath());
    state.skillMatrix = matrix;
    if (state.selectedMatrixFamily && !matrix.rows.some((row) => row.conflict_family === state.selectedMatrixFamily)) {
      state.selectedMatrixFamily = null;
      state.selectedMatrixClient = null;
    }
    if (state.selectedMatrixFamily) {
      await loadMatrixFamilyInstances(state.selectedMatrixFamily);
    }
    state.skillManagerLoading = false;
    renderSkillManager();

    state.scanSourcesLoading = true;
    state.discoveryLoading = true;
    renderSkillManager();
    const [scanSources, discoverySummary] = await Promise.all([api("/api/scan-sources"), api("/api/discovery/summary")]);
    state.scanSources = scanSources;
    state.discoverySummary = discoverySummary;
    state.discoveryDetails = {};
    await loadDiscoveryGroup(state.selectedDiscoveryGroup || "untracked_discovered", true);
    state.scanSourcesLoading = false;
    state.discoveryLoading = false;
  }
  if (state.selectedSkillId) {
    try {
      state.skillDetail = await api(`/api/skills/${encodeURIComponent(state.selectedSkillId)}`);
    } catch (error) {
      if (error.code === "not_found") {
        state.selectedSkillId = null;
        state.skillDetail = null;
      } else {
        throw error;
      }
    }
  }
  renderAll();
}

async function refreshStatusOnly() {
  const [status, systemStatus] = await Promise.all([api("/api/status"), api("/api/system")]);
  state.status = status;
  state.systemStatus = systemStatus;
  ensureCurrentClient();
  renderDashboard();
  renderClientOptions();
  renderClientDetail();
  renderInventory();
  renderMcp();
  renderCleanup();
  renderSkillManager();
  renderSyncCenter();
  renderConflicts();
  renderSkills();
}

function renderAll() {
  renderServiceStatus();
  renderClientOptions();
  renderDashboard();
  renderClientDetail();
  renderInventory();
  renderMcp();
  renderCleanup();
  renderBackups();
  renderSkillManager();
  renderSyncCenter();
  renderSkillsFilters();
  renderSkills();
  renderSkillDetail();
  renderConflicts();
  renderReports();
  switchView(state.currentView || "skills", { sync: false });
}

