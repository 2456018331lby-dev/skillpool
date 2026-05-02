async function submitGithubImport(event) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const payload = Object.fromEntries(form.entries());
  const result = await runAction("导入 GitHub", () => postJson("/api/import/github", payload));
  $("#importOutput").textContent = asJson(result);
  await refreshAll();
}

async function submitZipImport(event) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const result = await runAction("导入 ZIP", () => api("/api/import/zip", { method: "POST", body: form }));
  $("#importOutput").textContent = asJson(result);
  await refreshAll();
}

async function refreshSkillManagerView(force = true) {
  if (force) {
    state.matrixFamilyInstances = {};
  }
  state.skillManagerLoading = true;
  renderSkillManager();
  const matrix = await loadSkillMatrix(force);
  state.skillMatrix = matrix;
  if (state.selectedMatrixFamily) {
    await loadMatrixFamilyInstances(state.selectedMatrixFamily, force);
  }
  state.skillManagerLoading = false;

  state.scanSourcesLoading = true;
  state.discoveryLoading = true;
  renderSkillManager();
  const [scanSources, discoverySummary] = await Promise.all([loadScanSources(force), loadDiscoverySummary(force)]);
  state.scanSources = scanSources;
  state.discoverySummary = discoverySummary;
  if (force) {
    state.discoveryDetails = {};
  }
  await loadDiscoveryGroup(state.selectedDiscoveryGroup || "untracked_discovered", force);
  state.scanSourcesLoading = false;
  state.discoveryLoading = false;
  renderSkillManager();
}

function syncRequestBody() {
  return {
    source_client: syncSourceClient(),
    target_clients: normalizedTargetClients(),
    include_skills: Boolean(state.syncCenter.includeSkills),
    include_mcp: Boolean(state.syncCenter.includeMcp),
    families: selectedFamiliesForSync(),
  };
}

function syncSelectionMissing() {
  return state.syncCenter.scope === "selected" && !selectedFamiliesForSync().length;
}

async function previewSyncCenterAction() {
  if (syncSelectionMissing()) {
    toast("当前选择了“当前已选 family”，但矩阵里还没有勾选任何 family。");
    return null;
  }
  const payload = syncRequestBody();
  if (!payload.target_clients.length) {
    toast("请至少选择一个目标客户端。");
    return null;
  }
  state.syncCenter.applyResult = null;
  state.syncCenter.preview = await runAction("同步预览", () => postJson("/api/sync/preview", payload));
  renderSyncCenter();
  return state.syncCenter.preview;
}

async function applySyncCenterAction() {
  if (syncSelectionMissing()) {
    toast("当前选择了“当前已选 family”，但矩阵里还没有勾选任何 family。");
    return null;
  }
  const payload = syncRequestBody();
  if (!payload.target_clients.length) {
    toast("请至少选择一个目标客户端。");
    return null;
  }
  const preview = state.syncCenter.preview || (await previewSyncCenterAction());
  if (!preview) {
    return null;
  }
  if ((preview.blocked_targets || []).length) {
    toast(`有阻断目标：${preview.blocked_targets.join(", ")}`);
    return null;
  }
  state.syncCenter.applyResult = await runAction("应用同步", () => postJson("/api/sync/apply", payload));
  await refreshAll();
  switchView("sync");
  renderSyncCenter();
  return state.syncCenter.applyResult;
}

async function runMatrixBatchAction(action) {
  const families = [...(state.selectedMatrixFamilies || [])];
  const clients = normalizedBatchClients();
  if (!families.length) {
    toast("请先勾选至少一个 family。");
    return null;
  }
  if (!clients.length) {
    toast("请至少勾选一个目标客户端。");
    return null;
  }
  const label = action === "disable" ? "批量禁用 family" : "批量恢复继承";
  const result = await runAction(label, () => postJson(`/api/batch/${action}`, { clients, families }));
  await refreshAll();
  return result;
}

function useSelectedFamiliesForSync() {
  state.syncCenter.scope = "selected";
  if (state.currentClient && !state.syncCenter.sourceClient) {
    state.syncCenter.sourceClient = state.currentClient;
  }
  state.syncCenter.preview = null;
  state.syncCenter.applyResult = null;
  switchView("sync");
  renderSyncCenter();
}

function clearMatrixDetail() {
  state.selectedMatrixFamily = null;
  state.selectedMatrixClient = null;
  syncHash();
  renderMatrixDrawer();
  renderSkillMatrix();
}

async function submitScanSourceForm(event) {
  event.preventDefault();
  const payload = {
    path: $("#scanSourcePath").value.trim(),
    role: $("#scanSourceRole").value,
    client: $("#scanSourceClient").value || null,
    path_kind: $("#scanSourceKind").value,
    enabled: true,
  };
  const result = await runAction("添加扫描源", () => postJson("/api/scan-sources/add", payload));
  $("#scanSourcePath").value = "";
  $("#scanSourceClient").value = "";
  $("#scanSourceRole").value = "global_source";
  $("#scanSourceKind").value = "stable";
  await refreshSkillManagerView(true);
  return result;
}

async function checkHealth(silent = true, autoRefreshOnReconnect = true) {
  const wasOnline = state.serviceOnline;
  try {
    const response = await fetch("/api/health", { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const payload = await response.json();
    if (!payload.ok) {
      throw new Error(payload.error?.message || "health check failed");
    }
    setServiceOnline(true);
    if (autoRefreshOnReconnect && wasOnline === false && !reconnectRefreshInFlight) {
      reconnectRefreshInFlight = true;
      refreshAll()
        .catch((error) => {
          toast(`恢复连接后刷新失败：${error.message}`);
          logEvent(`恢复连接后刷新失败：${error.message}`);
        })
        .finally(() => {
          reconnectRefreshInFlight = false;
        });
    }
    return true;
  } catch (error) {
    setServiceOnline(false);
    if (!silent) {
      const normalized = normalizeFetchError(error);
      toast(normalized.message);
      logEvent(normalized.message);
    }
    return false;
  }
}

