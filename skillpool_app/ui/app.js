const DEFAULT_SKILL_QUERY = {
  page: 1,
  page_size: 25,
  sort_by: "name",
  sort_dir: "asc",
  client: "",
  family: "",
  status: "",
  enabled_global: "",
  source_scope: "",
  q: "",
};

const DEFAULT_MATRIX_QUERY = {
  q: "",
  client: "",
  anomaly: "",
  source_scope: "",
  only_anomalies: "",
  only_duplicates: "",
};

const state = {
  serviceOnline: null,
  status: null,
  systemStatus: null,
  toolActions: null,
  inventorySummary: null,
  inventoryDetails: {},
  inventoryFilters: { diffType: "", scope: "", sourceClient: "" },
  mcpSummary: null,
  mcpDetails: {},
  cleanup: null,
  cleanupLabelFilter: "",
  skillMatrix: { total: 0, rows: [], clients: [] },
  matrixFamilyInstances: {},
  skillManagerLoading: false,
  scanSourcesLoading: false,
  discoveryLoading: false,
  scanSources: { total: 0, sources: [] },
  scanSourceFilters: { enabled_only: false, suggested_only: false, transient_only: false },
  discoverySummary: null,
  discoveryDetails: {},
  skills: { total: 0, page: 1, page_size: 25, total_pages: 0, skills: [] },
  skillDetail: null,
  selectedSkillId: null,
  selectedMatrixFamily: null,
  selectedMatrixClient: null,
  selectedMatrixFamilies: [],
  matrixBatchClients: [],
  selectedDiscoveryGroup: "untracked_discovered",
  conflicts: { total: 0, conflicts: [] },
  conflictFamilyFilter: "",
  reports: null,
  currentClient: null,
  currentView: "skills",
  syncCenter: {
    sourceClient: "",
    targetClients: [],
    includeSkills: true,
    includeMcp: true,
    scope: "all_published",
    preview: null,
    applyResult: null,
  },
  clientPreview: {},
  backups: {},
  inspectedBackups: {},
  reportId: "skills_index",
  reportRaw: false,
  skillQuery: { ...DEFAULT_SKILL_QUERY },
  matrixQuery: { ...DEFAULT_MATRIX_QUERY },
  skillManagerMode: "matrix",
  selectedQuickActionId: null,
};

let hashSyncing = false;
let reconnectRefreshInFlight = false;
let matrixSearchTimer = null;

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

const LABELS = {
  active: "生效中",
  shadowed: "被遮蔽",
  disabled: "已禁用",
  enabled: "已启用",
  safe: "安全",
  pass: "通过",
  warning: "警告",
  blocked: "阻断",
  target_dir: "目标目录",
  extra_dir: "额外目录",
  client_live: "自定义 live",
  global_source: "全局源库",
  imported: "导入项",
  pool_only: "池内可见未生效",
  live_only: "live 存在未纳管",
  source_mismatch: "来源不一致",
  not_applicable: "不适用",
  duplicate_across_clients: "跨客户端重复",
  published: "已发布",
  both: "两者都是",
  global_source_role: "全局源库",
  client_live_role: "客户端 live",
  stable: "稳定",
  workspace: "工作区",
  transient: "临时/缓存",
  running: "在线",
  stopped: "离线",
  managed: "受管",
  unmanaged: "未受管",
  stale: "失效",
  ok: "可解析",
  unsupported_source: "不支持可靠统计",
  missing_config: "缺少配置",
  parse_error: "解析失败",
  candidate: "候选",
  keep: "保留",
  ignore: "忽略",
  ready: "已就绪",
  mismatch: "目标不匹配",
  missing: "缺失",
  prefer_exact: "精确装载",
  unresolved_family: "未解决 family",
  unavailable_family: "目标不可见",
  add: "新增",
  update: "更新",
  noop: "无需变更",
  success: "成功",
  rolled_back: "已回滚",
  unknown: "未知",
};

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function asJson(value) {
  return JSON.stringify(value, null, 2);
}

function zh(value, fallback = "未知") {
  if (value === null || value === undefined || value === "") {
    return fallback;
  }
  return LABELS[value] || String(value);
}

function parseIntSafe(value, fallback) {
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function formatList(values, empty = "全部") {
  return values && values.length ? values.join(", ") : empty;
}

function formatTime(value, empty = "-") {
  if (!value) {
    return empty;
  }
  return String(value).replace("T", " ").replace("Z", "");
}

function formatOverride(value) {
  if (!value) {
    return "继承";
  }
  if (value === "inherit") {
    return "继承";
  }
  if (value === "disabled") {
    return "禁用";
  }
  if (String(value).startsWith("prefer:")) {
    return `优先 ${String(value).slice("prefer:".length)}`;
  }
  return String(value);
}

function badge(value, fallback = "未知") {
  const text = value || fallback;
  const cls = String(text).toLowerCase();
  return `<span class="badge ${escapeHtml(cls)}">${escapeHtml(zh(text, fallback))}</span>`;
}

function normalizeFetchError(error) {
  if (error instanceof TypeError && /fetch/i.test(error.message || "")) {
    return new Error("无法连接本地 SkillPool 服务。请先运行 open-console.cmd，再刷新或回到页面。");
  }
  return error;
}

function setServiceOnline(online) {
  state.serviceOnline = online;
  const banner = $("#serviceBanner");
  if (banner) {
    banner.classList.toggle("hidden", online);
  }
  const strip = $("#serviceStrip");
  if (strip) {
    strip.classList.toggle("online", Boolean(online));
    strip.classList.toggle("offline", online === false);
  }
  const stateNode = $("#serviceState");
  if (stateNode) {
    stateNode.textContent = online === null ? "检测中" : (online ? "在线" : "离线");
  }
  const hintNode = $("#serviceHint");
  if (hintNode) {
    hintNode.textContent = online
      ? "本地 SkillPool 服务已连接，可以继续预览、发布、回滚和导入。"
      : "服务未连接。运行 open-console.cmd 启动，console-status.cmd 查看状态，stop-console.cmd 关闭服务。";
  }
  document.body.classList.toggle("service-offline", online === false);
  updateOnlineDependentControls();
}

function updateOnlineDependentControls() {
  const disabled = state.serviceOnline === false;
  $$("[data-online-required]").forEach((node) => {
    if ("disabled" in node) {
      node.disabled = disabled;
    }
  });
  updatePublishButton();
}

let csrfToken = null;

async function fetchCsrfToken() {
  try {
    const resp = await fetch("/api/csrf-token", { cache: "no-store" });
    const payload = await resp.json();
    if (payload.ok && payload.data?.token) {
      csrfToken = payload.data.token;
    }
  } catch (_e) {
    // CSRF endpoint may not exist yet; degrade gracefully
  }
  return csrfToken;
}

async function api(path, options = {}) {
  let response;
  try {
    response = await fetch(path, {
      cache: "no-store",
      ...options,
      headers:
        options.body instanceof FormData
          ? options.headers
          : { "Content-Type": "application/json", ...(options.headers || {}) },
    });
  } catch (error) {
    // Network error (fetch failed) — service is truly offline
    setServiceOnline(false);
    throw normalizeFetchError(error);
  }
  // We got a response from the server, so it IS online
  setServiceOnline(true);
  let payload;
  try {
    payload = await response.json();
  } catch (_e) {
    throw new Error(`无法解析服务器响应 (HTTP ${response.status})`);
  }
  if (!payload.ok) {
    const error = new Error(payload.error?.message || `HTTP ${response.status}`);
    error.code = payload.error?.code || "api_error";
    throw error;
  }
  return payload.data;
}

async function postJson(path, body = {}) {
  if (!csrfToken) {
    await fetchCsrfToken();
  }
  const headers = csrfToken ? { "X-CSRF-Token": csrfToken } : {};
  return api(path, { method: "POST", body: JSON.stringify(body), headers });
}

function toast(message) {
  const node = $("#toast");
  if (!node) {
    return;
  }
  node.textContent = message;
  node.classList.add("show");
  setTimeout(() => node.classList.remove("show"), 2600);
}

function logEvent(message, detail) {
  const log = $("#eventLog");
  if (!log) {
    return;
  }
  const entry = document.createElement("div");
  entry.className = "log-entry";
  const time = new Date().toLocaleTimeString();
  entry.innerHTML = `<strong>${escapeHtml(time)}</strong> ${escapeHtml(message)}`;
  if (detail) {
    entry.title = typeof detail === "string" ? detail : asJson(detail);
  }
  log.prepend(entry);
}

async function runAction(label, fn) {
  try {
    const result = await fn();
    toast(`${label} 已完成`);
    logEvent(label, result);
    return result;
  } catch (error) {
    const normalized = normalizeFetchError(error);
    toast(`${label} 失败：${normalized.message}`);
    logEvent(`${label} 失败：${normalized.message}`);
    throw normalized;
  }
}

function handleAsync(fn) {
  return async (...args) => {
    try {
      await fn(...args);
    } catch (_error) {
      // runAction/api already surface the error to the user.
    }
  };
}

function ensureCurrentClient() {
  const clients = Object.keys(state.status?.clients || {});
  if (!clients.length) {
    state.currentClient = null;
    return;
  }
  if (!state.currentClient || !clients.includes(state.currentClient)) {
    state.currentClient = clients[0];
  }
}

function buildSkillsPath() {
  const params = new URLSearchParams();
  Object.entries(state.skillQuery).forEach(([key, value]) => {
    if (value === null || value === undefined || value === "") {
      return;
    }
    params.set(key, String(value));
  });
  return `/api/skills?${params.toString()}`;
}

function buildConflictsPath() {
  const params = new URLSearchParams();
  if (state.conflictFamilyFilter) {
    params.set("family", state.conflictFamilyFilter);
  }
  return params.toString() ? `/api/conflicts?${params.toString()}` : "/api/conflicts";
}

function buildSkillMatrixPath() {
  const params = new URLSearchParams();
  Object.entries(state.matrixQuery).forEach(([key, value]) => {
    if (value === null || value === undefined || value === "") {
      return;
    }
    params.set(key, String(value));
  });
  params.set("include_instances", "0");
  return `/api/skills/matrix?${params.toString()}`;
}

async function loadInventorySummary(force = false) {
  if (!force && state.inventorySummary) {
    return state.inventorySummary;
  }
  state.inventorySummary = await api("/api/inventory");
  return state.inventorySummary;
}

async function loadInventoryDetail(client, force = false) {
  if (!client) {
    return null;
  }
  if (!force && state.inventoryDetails[client]) {
    return state.inventoryDetails[client];
  }
  state.inventoryDetails[client] = await api(`/api/inventory/${encodeURIComponent(client)}`);
  return state.inventoryDetails[client];
}

async function loadMcpSummary(force = false) {
  if (!force && state.mcpSummary) {
    return state.mcpSummary;
  }
  state.mcpSummary = await api("/api/mcp/clients");
  return state.mcpSummary;
}

async function loadMcpDetail(client, force = false) {
  if (!client) {
    return null;
  }
  if (!force && state.mcpDetails[client]) {
    return state.mcpDetails[client];
  }
  state.mcpDetails[client] = await api(`/api/mcp/clients/${encodeURIComponent(client)}`);
  return state.mcpDetails[client];
}

async function loadCleanup(force = false) {
  if (!force && state.cleanup) {
    return state.cleanup;
  }
  state.cleanup = await api("/api/cleanup");
  return state.cleanup;
}

async function loadSystemStatus(force = false) {
  if (!force && state.systemStatus) {
    return state.systemStatus;
  }
  state.systemStatus = await api("/api/system");
  return state.systemStatus;
}

async function loadToolActions(force = false) {
  if (!force && state.toolActions) {
    return state.toolActions;
  }
  state.toolActions = await api("/api/tools/actions");
  const actions = state.toolActions?.actions || [];
  if (!state.selectedQuickActionId || !actions.some((item) => item.id === state.selectedQuickActionId)) {
    state.selectedQuickActionId = actions[0]?.id || null;
  }
  return state.toolActions;
}

async function loadSkillMatrix(force = false) {
  if (!force && state.skillMatrix?.rows?.length) {
    return state.skillMatrix;
  }
  state.skillMatrix = await api(buildSkillMatrixPath());
  if (state.selectedMatrixFamily && !state.skillMatrix.rows.some((row) => row.conflict_family === state.selectedMatrixFamily)) {
    state.selectedMatrixFamily = null;
    state.selectedMatrixClient = null;
  }
  return state.skillMatrix;
}

async function loadMatrixFamilyInstances(family, force = false) {
  if (!family) {
    return [];
  }
  if (!force && state.matrixFamilyInstances[family]) {
    return state.matrixFamilyInstances[family];
  }
  const query = new URLSearchParams({
    family,
    page: "1",
    page_size: "200",
    sort_by: "name",
    sort_dir: "asc",
  });
  const response = await api(`/api/skills/instances?${query.toString()}`);
  const instances = response.skills || [];
  state.matrixFamilyInstances[family] = instances;
  return instances;
}

async function loadScanSources(force = false) {
  if (!force && state.scanSources?.sources?.length) {
    return state.scanSources;
  }
  state.scanSources = await api("/api/scan-sources");
  return state.scanSources;
}

async function loadDiscoverySummary(force = false) {
  if (!force && state.discoverySummary) {
    return state.discoverySummary;
  }
  state.discoverySummary = force ? await postJson("/api/discovery/refresh", { summary: true }) : await api("/api/discovery/summary");
  return state.discoverySummary;
}

async function loadDiscoveryGroup(group, force = false, limit = 20) {
  if (!group) {
    return null;
  }
  if (!force && state.discoveryDetails[group]) {
    return state.discoveryDetails[group];
  }
  const query = new URLSearchParams({ group });
  if (limit !== null && limit !== undefined) {
    query.set("limit", String(limit));
  }
  state.discoveryDetails[group] = await api(`/api/discovery/details?${query.toString()}`);
  return state.discoveryDetails[group];
}

async function refreshDiscoveryData(loadActiveGroup = true) {
  state.discoverySummary = await postJson("/api/discovery/refresh", { summary: true });
  state.discoveryDetails = {};
  if (loadActiveGroup && state.selectedDiscoveryGroup) {
    await loadDiscoveryGroup(state.selectedDiscoveryGroup, true);
  }
  return state.discoverySummary;
}

function downloadContent(filename, content, contentType) {
  const blob = new Blob([content], { type: contentType || "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

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

function renderServiceStatus() {
  const online = state.serviceOnline;
  const badgeNode = $("#serviceBadge");
  if (badgeNode) {
    const cls = online === null ? "warning" : (online ? "safe" : "danger");
    const label = online === null ? "检测中" : (online ? "在线" : "离线");
    badgeNode.innerHTML = `<span class="badge ${cls}">${escapeHtml(label)}</span>`;
  }
  updateOnlineDependentControls();
}

function renderClientOptions() {
  const clients = Object.keys(state.status?.clients || {});
  const options = clients.map((client) => `<option value="${escapeHtml(client)}">${escapeHtml(client)}</option>`).join("");

  const clientSelect = $("#clientSelect");
  clientSelect.innerHTML = options || `<option value="">暂无客户端</option>`;
  clientSelect.value = state.currentClient || "";

  const inventoryClientSelect = $("#inventoryClientSelect");
  if (inventoryClientSelect) {
    inventoryClientSelect.innerHTML = options || `<option value="">暂无客户端</option>`;
    inventoryClientSelect.value = state.currentClient || "";
  }

  const mcpClientSelect = $("#mcpClientSelect");
  if (mcpClientSelect) {
    mcpClientSelect.innerHTML = options || `<option value="">暂无客户端</option>`;
    mcpClientSelect.value = state.currentClient || "";
  }

  const skillClientFilter = $("#skillClientFilter");
  skillClientFilter.innerHTML = `<option value="">全部客户端</option>${options}`;
  skillClientFilter.value = state.skillQuery.client || "";
}

function selectedQuickAction() {
  const actions = state.toolActions?.actions || [];
  return actions.find((item) => item.id === state.selectedQuickActionId) || actions[0] || null;
}

function renderDashboard() {
  const status = state.status || {};
  $("#summaryStats").innerHTML = [
    ["技能总数", status.skill_count],
    ["已启用", status.enabled_count],
    ["冲突族", status.conflict_family_count],
    ["被遮蔽", status.shadowed_count],
  ]
    .map(([label, value]) => `<article class="stat"><span class="muted">${label}</span><strong>${escapeHtml(value ?? "-")}</strong></article>`)
    .join("");

  const system = state.systemStatus || {};
  const consoleStatus = system.console || {};
  const shortcutStatus = system.shortcut || {};
  $("#systemSummary").innerHTML = [
    {
      title: "服务状态",
      badges: `${badge(consoleStatus.status, "未知")} ${badge(consoleStatus.management, "未知")}`,
      detail: consoleStatus.message || "尚未读取服务状态。",
      meta: consoleStatus.url || "-",
    },
    {
      title: "桌面快捷方式",
      badges: `${badge(shortcutStatus.status, "未知")}`,
      detail: shortcutStatus.message || "尚未读取桌面快捷方式状态。",
      meta: shortcutStatus.path || "-",
    },
  ]
    .map(
      (item) => `
        <article class="system-card">
          <div class="panel-head slim">
            <h3>${escapeHtml(item.title)}</h3>
            <div class="badge-row">${item.badges}</div>
          </div>
          <div>${escapeHtml(item.detail)}</div>
          <div class="mono muted">${escapeHtml(item.meta)}</div>
        </article>
      `,
    )
    .join("");

  const manualCommands = system.manual_commands || [];
  $("#manualCommandList").innerHTML =
    manualCommands
      .map(
        (command) => `
          <article class="manual-command-card">
            <div class="panel-head slim">
              <h3>${escapeHtml(command.title)}</h3>
              ${command.status ? badge(command.status, "手动") : `<span class="badge">${escapeHtml("手动")}</span>`}
            </div>
            <div class="muted">${escapeHtml(command.description || "")}</div>
            <div class="command-row">
              <code>${escapeHtml(command.command_preview || "-")}</code>
              <button class="button small ghost" data-copy-text="${escapeHtml(command.copy_text || command.command_preview || "")}">复制</button>
            </div>
          </article>
        `,
      )
      .join("") || `<p class="muted">尚未读取快捷命令信息。</p>`;

  const actions = state.toolActions?.actions || [];
  const selectedAction = selectedQuickAction();
  $("#quickActionList").innerHTML =
    actions
      .map((action) => {
        const selected = action.id === state.selectedQuickActionId ? "selected-command" : "";
        const disabled = state.serviceOnline === false || action.online_required === false ? "" : "";
        return `
          <article class="command-card ${selected}" data-select-action="${escapeHtml(action.id)}">
            <div class="panel-head slim">
              <h3>${escapeHtml(action.title)}</h3>
              ${badge(action.risk_level, "未知")}
            </div>
            <div class="muted">${escapeHtml(action.description || "")}</div>
            <div class="badge-row">
              <span class="badge">${escapeHtml(action.category || "动作")}</span>
              ${action.online_required ? `<span class="badge">${escapeHtml("需在线")}</span>` : ""}
            </div>
            <div class="command-row">
              <code>${escapeHtml(action.command_preview || "-")}</code>
              <button class="button small" ${state.serviceOnline === false ? "disabled" : ""} data-run-action="${escapeHtml(action.id)}">执行</button>
            </div>
          </article>
        `;
      })
      .join("") || `<p class="muted">尚未读取快捷动作。</p>`;

  $("#quickActionTitle").textContent = selectedAction?.title || "请选择一个动作";
  $("#quickActionDescription").textContent = selectedAction?.description || "这里会显示当前动作的说明、命令预览和执行结果。";
  $("#quickActionCommand").textContent = selectedAction?.command_preview || "-";
  $("#quickActionBadges").innerHTML = selectedAction
    ? `${badge(selectedAction.risk_level, "未知")}<span class="badge">${escapeHtml(selectedAction.category || "动作")}</span>`
    : "";
  const runQuickActionButton = $("#runQuickAction");
  if (runQuickActionButton) {
    runQuickActionButton.disabled = !selectedAction || state.serviceOnline === false;
  }

  const clients = status.clients || {};
  $("#clientCards").innerHTML = Object.entries(clients)
    .map(([client, config]) => {
      const published = config.published_skill_ids?.length || 0;
      return `
        <article class="client-card">
          <div class="panel-head slim">
            <h3>${escapeHtml(client)}</h3>
            ${badge(config.last_deep_doctor_status, "未体检")}
          </div>
          <div class="badge-row">
            ${badge(config.last_preview_status, "未预览")}
            <span class="badge">${published} 个技能</span>
          </div>
          <div class="muted mono">${escapeHtml(config.target_dir || "-")}</div>
          <div class="table-actions">
            <button class="button small" data-open-client-view="clients" data-open-client="${escapeHtml(client)}">控制</button>
            <button class="button small ghost" data-open-client-view="inventory" data-open-client="${escapeHtml(client)}">盘点</button>
            <button class="button small ghost" data-open-client-view="mcp" data-open-client="${escapeHtml(client)}">MCP</button>
          </div>
        </article>
      `;
    })
    .join("") || `<p class="muted">还没有客户端状态。</p>`;
}

async function runQuickAction(actionId) {
  const action = (state.toolActions?.actions || []).find((item) => item.id === actionId);
  if (!action) {
    toast("当前动作不存在。");
    return;
  }
  state.selectedQuickActionId = actionId;
  renderDashboard();
  const result = await runAction(action.title, () => postJson("/api/tools/run", { action_id: actionId }));
  $("#quickActionOutput").textContent = asJson(result);
  if (actionId === "stop_console") {
    setServiceOnline(false);
    if (state.systemStatus?.console) {
      state.systemStatus.console.status = "stopped";
      state.systemStatus.console.management = "stopped";
      state.systemStatus.console.message = "已从页面触发停止当前 SkillPool 服务。";
    }
    renderDashboard();
    return;
  }
  await refreshAll();
}

function readMatrixFiltersFromDom() {
  state.matrixQuery.q = $("#matrixSearch")?.value?.trim() || "";
  state.matrixQuery.client = $("#matrixClientFilter")?.value || "";
  state.matrixQuery.anomaly = $("#matrixAnomalyFilter")?.value || "";
  state.matrixQuery.source_scope = $("#matrixSourceScopeFilter")?.value || "";
}

function updateScanSourceClientState() {
  const role = $("#scanSourceRole")?.value || "global_source";
  const clientSelect = $("#scanSourceClient");
  if (!clientSelect) {
    return;
  }
  const requiresClient = role === "client_live" || role === "both";
  if (!requiresClient) {
    clientSelect.value = "";
  }
  clientSelect.disabled = !requiresClient || state.serviceOnline === false;
}

function selectedMatrixRow() {
  return (state.skillMatrix?.rows || []).find((row) => row.conflict_family === state.selectedMatrixFamily) || null;
}

function selectedMatrixRows() {
  const selected = new Set(state.selectedMatrixFamilies || []);
  return (state.skillMatrix?.rows || []).filter((row) => selected.has(row.conflict_family));
}

function isMatrixFamilySelected(family) {
  return (state.selectedMatrixFamilies || []).includes(family);
}

function toggleMatrixFamilySelection(family) {
  if (!family) {
    return;
  }
  const next = new Set(state.selectedMatrixFamilies || []);
  if (next.has(family)) {
    next.delete(family);
  } else {
    next.add(family);
  }
  state.selectedMatrixFamilies = Array.from(next).sort();
}

function clearMatrixSelections() {
  state.selectedMatrixFamilies = [];
}

function filteredMatrixRows(response = state.skillMatrix || { rows: [] }) {
  return (response.rows || []).filter((row) => {
    if (state.matrixQuery.only_anomalies && !(row.anomalies || []).length) {
      return false;
    }
    if (
      state.matrixQuery.only_duplicates &&
      !((row.anomalies || []).some((item) => item.type === "duplicate_across_clients") || Number(row.member_count || 0) > 1)
    ) {
      return false;
    }
    return true;
  });
}

function matrixAnomalyTypes(row) {
  return Array.from(new Set((row?.anomalies || []).map((item) => item.type)));
}

function selectedFamiliesForSync() {
  return state.syncCenter.scope === "selected" ? [...(state.selectedMatrixFamilies || [])] : [];
}

function syncSourceClient() {
  const clients = Object.keys(state.status?.clients || {});
  if (state.syncCenter.sourceClient && clients.includes(state.syncCenter.sourceClient)) {
    return state.syncCenter.sourceClient;
  }
  if (state.currentClient && clients.includes(state.currentClient)) {
    state.syncCenter.sourceClient = state.currentClient;
    return state.syncCenter.sourceClient;
  }
  state.syncCenter.sourceClient = clients[0] || "";
  return state.syncCenter.sourceClient;
}

function normalizedTargetClients() {
  const clients = Object.keys(state.status?.clients || {});
  const source = syncSourceClient();
  state.syncCenter.targetClients = (state.syncCenter.targetClients || []).filter((client) => clients.includes(client) && client !== source);
  if (!state.syncCenter.targetClients.length) {
    state.syncCenter.targetClients = clients.filter((client) => client !== source);
  }
  return state.syncCenter.targetClients;
}

function normalizedBatchClients() {
  const clients = Object.keys(state.status?.clients || {});
  state.matrixBatchClients = (state.matrixBatchClients || []).filter((client) => clients.includes(client));
  if (!state.matrixBatchClients.length && state.currentClient && clients.includes(state.currentClient)) {
    state.matrixBatchClients = [state.currentClient];
  }
  return state.matrixBatchClients;
}

function matrixStatusClass(status) {
  return `status-${String(status || "unknown").toLowerCase()}`;
}

function matrixStatusExplanation(status, client, row, payload = {}) {
  const flags = payload.flags || [];
  const shadowNote = flags.includes("shadowed") ? " 当前还有同族候选被遮蔽。" : "";
  switch (status) {
    case "published":
      return `${client} 当前已经使用这个逻辑 skill 的受管发布版本。${shadowNote}`;
    case "live_only":
      return `${client} 的 live 源里发现了这个 family，但它还没有被当前发布结果接管。`;
    case "pool_only":
      return `${client} 对这个 family 可见，但当前只有池内候选，没有 live 生效结果。`;
    case "disabled":
      return `${client} 当前对这个 family 的可见候选都被全局状态或客户端覆盖规则禁用了。`;
    case "shadowed":
      return `${client} 当前能看到这个 family，但冲突裁决让别的同族实例优先生效。`;
    case "source_mismatch":
      return `${client} 当前检测到同族但不同内容的来源，需要先盘点确认再发布。`;
    case "not_applicable":
      return `${client} 当前不读取这个 family。`;
    default:
      return `${client} 当前状态为 ${zh(status, status)}。`;
  }
}

function matrixInstanceBySkillId(row, skillId) {
  const instances = state.matrixFamilyInstances[row?.conflict_family] || row?.instances || [];
  return instances.find((instance) => instance.skill_id === skillId) || null;
}

function matrixInstancesForRow(row) {
  return state.matrixFamilyInstances[row?.conflict_family] || row?.instances || [];
}

function renderMatrixClientMenu(row, client, payload) {
  const skillId = chooseMatrixSkillId(row, client);
  const selectedInstance = matrixInstanceBySkillId(row, skillId);
  const explanation = matrixStatusExplanation(payload.status, client, row, payload);
  const onlineDisabled = state.serviceOnline === false ? "disabled" : "";
  const flagBadges = (payload.flags || [])
    .map((flag) => `<span class="matrix-flag">${escapeHtml(zh(flag, flag))}</span>`)
    .join("");
  return `
    <div class="matrix-client-menu">
      <div class="matrix-client-menu-head">
        <strong>${escapeHtml(client)}</strong>
        ${badge(payload.status, payload.status)}
      </div>
      <p>${escapeHtml(explanation)}</p>
      ${flagBadges ? `<div class="matrix-status-flags">${flagBadges}</div>` : ""}
      ${
        skillId
          ? `<div class="matrix-menu-skill mono">当前候选：${escapeHtml(selectedInstance?.name || skillId)} · ${escapeHtml(skillId)}</div>`
          : ""
      }
      <div class="matrix-menu-actions">
        <button class="button small ghost" data-matrix-explain="${escapeHtml(client)}">查看解释</button>
        <button class="button small ghost" data-open-conflict="${escapeHtml(row.conflict_family)}">冲突裁决</button>
        ${skillId ? `<button class="button small primary" data-matrix-prefer="${escapeHtml(client)}" data-matrix-skill="${escapeHtml(skillId)}" ${onlineDisabled}>优先当前</button>` : ""}
        <button class="button small ghost" data-matrix-inherit="${escapeHtml(client)}" ${onlineDisabled}>继承</button>
        <button class="button small danger" data-matrix-disable="${escapeHtml(client)}" ${onlineDisabled}>禁用</button>
      </div>
      <div class="matrix-menu-links">
        <button class="link-button subtle" data-open-inventory-client="${escapeHtml(client)}" ${onlineDisabled}>盘点</button>
        <button class="link-button subtle" data-open-client="${escapeHtml(client)}" data-open-client-view="clients">客户端控制</button>
      </div>
    </div>
  `;
}

function renderMatrixClientCell(row, client) {
  const payload = row.clients?.[client] || { status: "not_applicable", flags: [] };
  if (payload.status === "not_applicable") {
    return `<div class="matrix-status-placeholder">-</div>`;
  }
  const menuOpen = state.selectedMatrixFamily === row.conflict_family && state.selectedMatrixClient === client;
  const flags = (payload.flags || []).map((flag) => `<span class="matrix-flag">${escapeHtml(zh(flag, flag))}</span>`).join("");
  return `
    <div class="matrix-cell ${escapeHtml(matrixStatusClass(payload.status))} ${menuOpen ? "menu-open" : ""}">
      <button
        class="matrix-status-button"
        data-open-matrix-family="${escapeHtml(row.conflict_family)}"
        data-open-matrix-client="${escapeHtml(client)}"
        aria-expanded="${menuOpen ? "true" : "false"}"
      >
        <span class="matrix-status-label">${escapeHtml(zh(payload.status, payload.status))}</span>
        ${flags ? `<span class="matrix-status-flags">${flags}</span>` : ""}
      </button>
      ${menuOpen ? renderMatrixClientMenu(row, client, payload) : ""}
    </div>
  `;
}

function renderMatrixInstances(row) {
  const instances = matrixInstancesForRow(row);
  if (!instances.length) {
    return `<div class="matrix-empty-state">正在加载实例层，或当前逻辑 skill 还没有可展示的实例数据。</div>`;
  }
  const cards = instances
    .map((instance) => {
      const overrideSummary = Object.entries(instance.client_overrides || {})
        .map(([client, override]) => `${client}: ${formatOverride(override)}`)
        .join(" · ");
      return `
        <article class="matrix-instance-card">
          <div class="matrix-instance-head">
            <div>
              <h4>${escapeHtml(instance.name || instance.skill_id)}</h4>
              <div class="mono">${escapeHtml(instance.skill_id)}</div>
            </div>
            <div class="badge-row">
              ${badge(instance.status, instance.status)}
              ${badge(instance.enabled_global, instance.enabled_global)}
            </div>
          </div>
          <div class="matrix-instance-grid-meta">
            <div class="matrix-kv">
              <small>来源路径</small>
              <strong class="mono">${escapeHtml(instance.source_root || "-")}</strong>
            </div>
            <div class="matrix-kv">
              <small>池内目录</small>
              <strong class="mono">${escapeHtml(instance.files_path || "-")}</strong>
            </div>
            <div class="matrix-kv">
              <small>来源范围</small>
              <strong>${escapeHtml(zh(instance.source_scope, instance.source_scope || "-"))}${instance.source_client ? ` · ${escapeHtml(instance.source_client)}` : ""}</strong>
            </div>
            <div class="matrix-kv">
              <small>Fingerprint</small>
              <strong class="mono">${escapeHtml(instance.fingerprint || "-")}</strong>
            </div>
            <div class="matrix-kv">
              <small>发布去向</small>
              <strong>${escapeHtml(formatList(instance.published_for, "未发布"))}</strong>
            </div>
            <div class="matrix-kv">
              <small>客户端覆盖</small>
              <strong>${escapeHtml(overrideSummary || "继承")}</strong>
            </div>
          </div>
          <div class="table-actions compact-actions">
            <button class="button small ghost" data-copy-text="${escapeHtml(instance.source_root || instance.files_path || "")}">复制来源</button>
            <button class="button small ghost" data-open-skill="${escapeHtml(instance.skill_id)}" data-open-skill-family="${escapeHtml(row.conflict_family)}">原始实例</button>
          </div>
        </article>
      `;
    })
    .join("");
  return cards;
}

function renderSkillManager() {
  const matrixMode = state.skillManagerMode !== "instances";
  $("#skillMatrixSection")?.classList.toggle("hidden", !matrixMode);
  $("#skillInstancesSection")?.classList.toggle("hidden", matrixMode);
  $("#showSkillMatrix")?.classList.toggle("active", matrixMode);
  $("#showSkillInstances")?.classList.toggle("active", !matrixMode);
  const clients = Object.keys(state.status?.clients || {});
  const matrixClientSelect = $("#matrixClientFilter");
  if (matrixClientSelect) {
    matrixClientSelect.innerHTML = `<option value="">全部客户端</option>${clients.map((item) => `<option value="${escapeHtml(item)}">${escapeHtml(item)}</option>`).join("")}`;
    matrixClientSelect.value = state.matrixQuery.client || "";
  }
  const scanClientSelect = $("#scanSourceClient");
  if (scanClientSelect) {
    scanClientSelect.innerHTML = `<option value="">无</option>${clients.map((item) => `<option value="${escapeHtml(item)}">${escapeHtml(item)}</option>`).join("")}`;
  }
  $("#matrixSearch").value = state.matrixQuery.q || "";
  $("#matrixAnomalyFilter").value = state.matrixQuery.anomaly || "";
  $("#matrixSourceScopeFilter").value = state.matrixQuery.source_scope || "";
  $("#matrixOnlyAnomalies")?.classList.toggle("active", Boolean(state.matrixQuery.only_anomalies));
  $("#matrixOnlyDuplicates")?.classList.toggle("active", Boolean(state.matrixQuery.only_duplicates));
  if (state.selectedMatrixFamily && !(state.skillMatrix?.rows || []).some((row) => row.conflict_family === state.selectedMatrixFamily)) {
    state.selectedMatrixFamily = null;
    state.selectedMatrixClient = null;
  }
  updateScanSourceClientState();
  renderSkillMatrix();
  renderMatrixDrawer();
  renderScanSources();
  renderDiscoverySummary();
}

function renderSkillMatrix() {
  const response = state.skillMatrix || { total: 0, rows: [], clients: [] };
  const clients = response.clients || [];
  if (state.skillManagerLoading && !(response.rows || []).length) {
    $("#skillMatrixMeta").innerHTML = "正在加载逻辑矩阵...";
    $("#skillsMatrixTable").innerHTML = `<div class="matrix-empty-state">正在读取逻辑 skill、客户端状态和基础摘要。</div>`;
    return;
  }
  const displayRows = filteredMatrixRows(response);
  const anomalyCount = (response.rows || []).filter((row) => (row.anomalies || []).length).length;
  const duplicateCount = (response.rows || []).filter((row) => (row.anomalies || []).some((item) => item.type === "duplicate_across_clients")).length;
  const batchClients = normalizedBatchClients();
  $("#skillMatrixMeta").innerHTML = `共 <strong>${escapeHtml(response.total ?? 0)}</strong> 个逻辑 skill，当前显示 <strong>${escapeHtml(displayRows.length)}</strong> 个；异常 <strong>${escapeHtml(anomalyCount)}</strong> 个，跨客户端重复 <strong>${escapeHtml(duplicateCount)}</strong> 个。点击左侧展开实例层，点击右侧客户端状态打开动作菜单。`;
  const selectedCount = selectedMatrixRows().length;
  const rows = displayRows
    .map((row) => {
      const anomalyBadges = matrixAnomalyTypes(row)
        .slice(0, 3)
        .map((type) => `<span class="badge small-badge">${escapeHtml(zh(type, type))}</span>`)
        .join("");
      const expanded = state.selectedMatrixFamily === row.conflict_family;
      const clientCells = clients.map((client) => renderMatrixClientCell(row, client)).join("");
      const publishedBadge = row.published_for?.length ? `<span class="badge">发布到 ${escapeHtml(formatList(row.published_for, "-"))}</span>` : `<span class="badge">未发布</span>`;
      const sourceSummary = row.source_scopes
        .slice(0, 3)
        .map((scope) => `<span class="badge">${escapeHtml(zh(scope, scope))}</span>`)
        .join("");
      return `
        <article class="matrix-row ${expanded ? "selected" : ""}">
          <div class="matrix-row-shell">
            <label class="matrix-select">
              <input type="checkbox" data-select-matrix-family="${escapeHtml(row.conflict_family)}" ${isMatrixFamilySelected(row.conflict_family) ? "checked" : ""} />
            </label>
            <button class="matrix-row-main" data-open-matrix-family="${escapeHtml(row.conflict_family)}">
              <div class="matrix-row-titleline">
                <h3 class="matrix-row-name">${escapeHtml(row.name || row.conflict_family)}</h3>
                <span class="matrix-row-family">${escapeHtml(row.conflict_family)}</span>
              </div>
              <p class="matrix-row-description">${escapeHtml(row.description || "无描述")}</p>
              <div class="matrix-row-meta">
                <span class="badge">${escapeHtml(row.member_count)} 个实例</span>
                ${publishedBadge}
                ${row.has_conflict ? `<span class="badge warning">冲突族</span>` : ""}
                ${anomalyBadges}
              </div>
              <div class="matrix-source-summary">
                ${sourceSummary}
                ${
                  row.source_clients?.length
                    ? `<span class="badge">${escapeHtml(formatList(row.source_clients, "无"))}</span>`
                    : ""
                }
              </div>
            </button>
            <div class="matrix-clients">${clientCells}</div>
          </div>
          ${
            expanded
              ? `
                <div class="matrix-row-expand">
                  <div class="matrix-expand-head">
                    <strong>实例层</strong>
                    <span class="muted">这里直接展示池内目录、来源路径、fingerprint 和发布去向。</span>
                  </div>
                  <div class="matrix-instance-grid">${renderMatrixInstances(row)}</div>
                </div>
              `
              : ""
          }
        </article>
      `;
    })
    .join("");
  $("#skillsMatrixTable").innerHTML = `
    <div class="matrix-board-shell">
      <div class="matrix-batch-bar">
        <div class="matrix-batch-main">
          <strong>已选 ${escapeHtml(selectedCount)} 个 family</strong>
          <span class="muted">${selectedCount ? "可以批量禁用、恢复继承，或把所选 family 送入同步中心。" : "先勾选左侧复选框，再执行批量动作。"}</span>
        </div>
        <div class="matrix-batch-controls">
          <div class="matrix-client-checks">
            ${clients
              .map(
                (client) => `
                  <label class="checkline compact-checkline">
                    <input type="checkbox" data-matrix-batch-client="${escapeHtml(client)}" ${batchClients.includes(client) ? "checked" : ""} />
                    ${escapeHtml(client)}
                  </label>
                `,
              )
              .join("")}
          </div>
          <div class="table-actions compact-actions">
            <button class="button small ghost" data-clear-matrix-selection>清空选择</button>
            <button class="button small ghost" data-open-sync-center ${selectedCount ? "" : "disabled"}>同步已选</button>
            <button class="button small danger" data-batch-disable ${selectedCount && batchClients.length ? "" : "disabled"}>批量禁用</button>
            <button class="button small" data-batch-inherit ${selectedCount && batchClients.length ? "" : "disabled"}>恢复继承</button>
          </div>
        </div>
      </div>
      <div class="matrix-legend-row">
        <div class="matrix-legend-text">
          <strong>逻辑 skill / family</strong>
          <span>左侧看名字、来源和异常，右侧直接看 6 个客户端当前状态。</span>
        </div>
        <div class="matrix-client-legend">
          ${clients.map((client) => `<span class="matrix-client-heading">${escapeHtml(client)}</span>`).join("")}
        </div>
      </div>
      <div class="matrix-list">${rows || `<div class="matrix-empty-state">当前筛选条件下没有逻辑 skill。</div>`}</div>
    </div>
  `;
}

function chooseMatrixSkillId(row, client) {
  const cell = row?.clients?.[client];
  if (!cell) {
    return null;
  }
  if (cell.skill_id) {
    return cell.skill_id;
  }
  return cell.visible_skill_ids?.[0] || row.instances?.[0]?.skill_id || null;
}

function renderMatrixDrawer() {
  const host = $("#matrixDrawerBody");
  const row = selectedMatrixRow();
  if (!row) {
    $("#matrixDrawerTitle").textContent = "请选择一个逻辑 skill";
    host.innerHTML = `<p class="muted">点击左侧名称展开实例层，点击某个客户端状态查看解释、冲突裁决和覆盖动作。这里会固定显示当前选中的逻辑 skill 详情。</p>`;
    return;
  }
  $("#matrixDrawerTitle").textContent = row.name || row.conflict_family;
  const clients = state.skillMatrix?.clients || [];
  const availableClients = clients.filter((client) => row.clients?.[client]?.status !== "not_applicable");
  const focusClient = availableClients.includes(state.selectedMatrixClient) ? state.selectedMatrixClient : availableClients[0] || null;
  const focusPayload = focusClient ? row.clients?.[focusClient] || { status: "not_applicable", flags: [] } : null;
  const focusSkillId = focusClient ? chooseMatrixSkillId(row, focusClient) : null;
  const focusExplanation = focusClient ? matrixStatusExplanation(focusPayload.status, focusClient, row, focusPayload) : "当前没有聚焦的客户端。";
  const onlineDisabled = state.serviceOnline === false ? "disabled" : "";
  const clientBlocks = clients
    .map((client) => {
      const payload = row.clients?.[client] || { status: "not_applicable", flags: [] };
      const skillId = chooseMatrixSkillId(row, client);
      return `
        <div class="matrix-mini-client ${client === focusClient ? "active" : ""}">
          <div class="matrix-mini-client-head">
            <strong>${escapeHtml(client)}</strong>
            ${badge(payload.status, payload.status)}
          </div>
          <p>${escapeHtml(matrixStatusExplanation(payload.status, client, row, payload))}</p>
          <div class="badge-row">${(payload.flags || []).map((flag) => `<span class="badge small-badge">${escapeHtml(zh(flag, flag))}</span>`).join("")}</div>
          <div class="table-actions compact-actions">
            <button class="button small ghost" data-open-matrix-family="${escapeHtml(row.conflict_family)}" data-open-matrix-client="${escapeHtml(client)}">聚焦</button>
            ${skillId ? `<button class="button small primary" data-matrix-prefer="${escapeHtml(client)}" data-matrix-skill="${escapeHtml(skillId)}" ${onlineDisabled}>优先</button>` : ""}
          </div>
        </div>
      `;
    })
    .join("");
  host.innerHTML = `
    <div class="detail-grid">
      ${detailItem("冲突族", row.conflict_family)}
      ${detailItem("主实例", row.primary_skill_id, { mono: true })}
      ${detailItem("实例数", row.member_count)}
      ${detailItem("已发布到", formatList(row.published_for, "未发布"))}
      ${detailItem("来源范围", formatList(row.source_scopes, "-"))}
      ${detailItem("来源客户端", formatList(row.source_clients, "无"))}
    </div>
    ${
      focusClient
        ? `
          <section class="drawer-section">
            <h4>${escapeHtml(focusClient)} 当前解释</h4>
            <div class="matrix-focus-card active">
              <div class="matrix-mini-client-head">
                <strong>${escapeHtml(focusClient)}</strong>
                ${badge(focusPayload.status, focusPayload.status)}
              </div>
              <p>${escapeHtml(focusExplanation)}</p>
              <div class="badge-row">${(focusPayload.flags || []).map((flag) => `<span class="badge small-badge">${escapeHtml(zh(flag, flag))}</span>`).join("")}</div>
              ${
                focusSkillId
                  ? `<div class="matrix-menu-skill mono">当前候选：${escapeHtml(matrixInstanceBySkillId(row, focusSkillId)?.name || focusSkillId)} · ${escapeHtml(focusSkillId)}</div>`
                  : ""
              }
              <div class="table-actions compact-actions">
                <button class="button small ghost" data-open-conflict="${escapeHtml(row.conflict_family)}">冲突裁决</button>
                <button class="button small ghost" data-open-inventory-client="${escapeHtml(focusClient)}" ${onlineDisabled}>盘点</button>
                <button class="button small ghost" data-open-client="${escapeHtml(focusClient)}" data-open-client-view="clients">客户端控制</button>
                ${focusSkillId ? `<button class="button small primary" data-matrix-prefer="${escapeHtml(focusClient)}" data-matrix-skill="${escapeHtml(focusSkillId)}" ${onlineDisabled}>优先当前</button>` : ""}
                <button class="button small ghost" data-matrix-inherit="${escapeHtml(focusClient)}" ${onlineDisabled}>继承</button>
                <button class="button small danger" data-matrix-disable="${escapeHtml(focusClient)}" ${onlineDisabled}>禁用</button>
              </div>
            </div>
          </section>
        `
        : ""
    }
    <section class="drawer-section">
      <h4>跨客户端状态</h4>
      <div class="matrix-mini-clients">${clientBlocks}</div>
    </section>
    <section class="drawer-section">
      <h4>来源实例</h4>
      <div class="skill-chip-list">
        ${
          matrixInstancesForRow(row).length
            ? matrixInstancesForRow(row)
                .map(
                  (instance) => `
                    <button class="skill-chip" data-open-skill="${escapeHtml(instance.skill_id)}" data-open-skill-family="${escapeHtml(row.conflict_family)}">
                      <strong>${escapeHtml(instance.name)}</strong>
                      <span>${escapeHtml(instance.skill_id)}</span>
                      <small>${escapeHtml(zh(instance.source_scope, instance.source_scope))}${instance.source_client ? ` · ${escapeHtml(instance.source_client)}` : ""}</small>
                    </button>
                  `,
                )
                .join("")
            : `<div class="matrix-empty-state">点击矩阵行后会按需加载这个 family 的实例层。</div>`
        }
      </div>
    </section>
  `;
}

function renderScanSources() {
  const response = state.scanSources || { total: 0, sources: [] };
  if (state.scanSourcesLoading && !(response.sources || []).length) {
    $("#scanSourcesTable").innerHTML = `<div class="matrix-empty-state">正在加载扫描源列表和发现计数。</div>`;
    return;
  }
  const allSources = response.sources || [];
  const enabledCount = allSources.filter((source) => source.enabled).length;
  const suggestedCount = allSources.filter((source) => source.suggested).length;
  const transientCount = allSources.filter((source) => source.path_kind === "transient").length;
  const sources = allSources.filter((source) => {
    if (state.scanSourceFilters.enabled_only && !source.enabled) {
      return false;
    }
    if (state.scanSourceFilters.suggested_only && !source.suggested) {
      return false;
    }
    if (state.scanSourceFilters.transient_only && source.path_kind !== "transient") {
      return false;
    }
    return true;
  });
  const disabledAttr = state.serviceOnline === false ? "disabled" : "";
  const rows = sources
    .map((source) => {
      const discovered = source.discovered_count ?? source.last_result_count ?? 0;
      return `
        <article class="scan-source-item ${source.enabled ? "is-enabled" : "is-disabled"} ${source.path_kind === "transient" ? "is-transient" : ""}">
          <div class="scan-source-main">
            <div class="scan-source-path mono">${escapeHtml(source.path || "-")}</div>
            <div class="scan-source-meta">
              ${badge(source.enabled ? "enabled" : "disabled")}
              <span class="badge">${escapeHtml(zh(source.path_kind, source.path_kind))}</span>
              <span class="badge">${escapeHtml(zh(source.role, source.role))}</span>
              ${source.client ? `<span class="badge">${escapeHtml(source.client)}</span>` : ""}
              ${source.suggested ? `<span class="badge warning">建议源</span>` : ""}
              ${source.default_entry ? `<span class="badge">默认</span>` : ""}
              ${source.exists ? "" : `<span class="badge danger">路径缺失</span>`}
            </div>
            <div class="scan-source-stats">
              <span>最近发现 ${escapeHtml(discovered)}</span>
              <span>上次扫描 ${escapeHtml(formatTime(source.last_scan_at, "未扫描"))}</span>
              ${
                source.last_result_count !== undefined && source.last_result_count !== null
                  ? `<span>上次结果 ${escapeHtml(source.last_result_count)}</span>`
                  : ""
              }
            </div>
            ${source.notes ? `<div class="scan-source-note">${escapeHtml(source.notes)}</div>` : ""}
          </div>
          <div class="scan-source-actions">
            <button class="button small" data-scan-source-run="${escapeHtml(source.id)}" ${disabledAttr}>仅扫描该源</button>
            <button class="button small ghost" data-scan-source-toggle="${escapeHtml(source.id)}" data-enabled="${escapeHtml(String(source.enabled))}" ${disabledAttr}>${source.enabled ? "停用" : "启用"}</button>
            <button class="button small ghost" data-copy-text="${escapeHtml(source.path || "")}">复制路径</button>
            ${source.default_entry ? "" : `<button class="button small danger" data-scan-source-remove="${escapeHtml(source.id)}" ${disabledAttr}>移除</button>`}
          </div>
        </article>
      `;
    })
    .join("");
  $("#scanSourcesTable").innerHTML = `
    <div class="scan-source-host">
      <div class="scan-source-summary">
        <span class="badge">${escapeHtml(response.total ?? 0)} 个扫描源</span>
        <span class="badge">${escapeHtml(enabledCount)} 个启用</span>
        <span class="badge">${escapeHtml(suggestedCount)} 个建议源</span>
        <span class="badge">${escapeHtml(transientCount)} 个临时源</span>
      </div>
      <div class="badge-row matrix-toggle-row">
        <button class="pill ${state.scanSourceFilters.enabled_only ? "active" : ""}" data-toggle-scan-filter="enabled_only">仅看启用源</button>
        <button class="pill ${state.scanSourceFilters.suggested_only ? "active" : ""}" data-toggle-scan-filter="suggested_only">仅看建议源</button>
        <button class="pill ${state.scanSourceFilters.transient_only ? "active" : ""}" data-toggle-scan-filter="transient_only">仅看临时源</button>
      </div>
      <div class="scan-source-list">${rows || `<div class="matrix-empty-state">当前没有扫描源。</div>`}</div>
    </div>
  `;
}

function discoveryGroups(summary = state.discoverySummary) {
  const counts = summary?.counts || {};
  const firstExamples = summary?.first_examples || {};
  return [
    { key: "untracked_discovered", label: "未纳管发现", count: counts.untracked_discovered || 0, first: firstExamples.untracked_discovered || null },
    { key: "source_mismatch", label: "来源不一致", count: counts.source_mismatch || 0, first: firstExamples.source_mismatch || null },
    { key: "transient_only", label: "临时源独有", count: counts.transient_only || 0, first: firstExamples.transient_only || null },
    { key: "duplicate_across_clients", label: "跨客户端重复", count: counts.duplicate_across_clients || 0, first: firstExamples.duplicate_across_clients || null },
  ];
}

function renderDiscoveryItem(groupKey, item) {
  if (groupKey === "duplicate_across_clients") {
    return `
      <article class="matrix-discovery-item">
        <strong>${escapeHtml(item.name || item.conflict_family || "-")}</strong>
        <div class="matrix-discovery-meta mono">${escapeHtml(item.conflict_family || "-")}</div>
        <div class="matrix-discovery-meta">可见客户端：${escapeHtml(formatList(item.clients, "-"))}</div>
        <div class="table-actions compact-actions">
          <button class="button small ghost" data-open-conflict="${escapeHtml(item.conflict_family || "")}">查看冲突裁决</button>
        </div>
      </article>
    `;
  }
  const poolMatchSummary =
    item.pool_matches && item.pool_matches.length
      ? `池内同族：${item.pool_matches.map((match) => `${match.skill_id} (${zh(match.source_scope, match.source_scope)})`).join(" · ")}`
      : "";
  return `
    <article class="matrix-discovery-item">
      <strong>${escapeHtml(item.name || item.normalized_name || item.path || "-")}</strong>
      <div class="matrix-discovery-meta mono">${escapeHtml(item.path || "-")}</div>
      <div class="matrix-discovery-meta">${escapeHtml(item.reason || "-")}</div>
      <div class="matrix-discovery-meta">${escapeHtml(poolMatchSummary || `${zh(item.path_kind, item.path_kind || "-")} · ${zh(item.role, item.role || "-")}${item.client ? ` · ${item.client}` : ""}`)}</div>
      <div class="table-actions compact-actions">
        <button class="button small ghost" data-copy-text="${escapeHtml(item.path || "")}">复制路径</button>
        ${item.normalized_name ? `<button class="button small ghost" data-open-conflict="${escapeHtml(item.normalized_name)}">查看冲突</button>` : ""}
      </div>
    </article>
  `;
}

function renderDiscoverySummary() {
  const summary = state.discoverySummary || { counts: {}, first_examples: {}, stale: false, generated_at: null };
  if (state.discoveryLoading && !state.discoverySummary) {
    $("#discoverySummary").innerHTML = `<div class="matrix-empty-state">正在加载 discovery 摘要和异常解释。</div>`;
    return;
  }
  const groups = discoveryGroups(summary);
  const activeGroup =
    groups.find((group) => group.key === state.selectedDiscoveryGroup && group.count) ||
    groups.find((group) => group.count) ||
    groups[0];
  state.selectedDiscoveryGroup = activeGroup.key;
  const detail = state.discoveryDetails[activeGroup.key] || { items: [], total: activeGroup.count || 0 };
  const buttons = groups
    .map(
      (group) => `
        <button class="matrix-discovery-button ${group.key === activeGroup.key ? "active" : ""}" data-discovery-group="${escapeHtml(group.key)}">
          <strong>${escapeHtml(group.count)}</strong>
          <span>${escapeHtml(group.label)}</span>
        </button>
      `,
    )
    .join("");
  const items = (detail.items || []).slice(0, 8).map((item) => renderDiscoveryItem(activeGroup.key, item)).join("");
  const note =
    activeGroup.key === "untracked_discovered"
      ? "这些路径里发现了 `SKILL.md`，但当前 registry 还没有纳入它们。"
      : activeGroup.key === "source_mismatch"
        ? "这些项和池内同族 skill 名字相同，但 fingerprint 或来源不同。"
        : activeGroup.key === "transient_only"
          ? "这些项只存在于临时或缓存源，不会自动进入稳定统计。"
          : "这些逻辑 skill 被多个客户端同时看见，适合优先做统一裁决。";
  $("#discoverySummary").innerHTML = `
    <div class="matrix-discovery-host">
      <div class="scan-source-summary">
        <span class="badge">${escapeHtml(summary.counts?.sources ?? 0)} 个扫描源</span>
        <span class="badge">${escapeHtml(summary.counts?.untracked_discovered ?? 0)} 个未纳管发现</span>
        <span class="badge">${escapeHtml(summary.counts?.source_mismatch ?? 0)} 个来源不一致</span>
        ${summary.stale ? `<span class="badge warning">缓存待刷新</span>` : `<span class="badge">${escapeHtml(formatTime(summary.generated_at, "未生成"))}</span>`}
      </div>
      <div class="matrix-discovery-strip">${buttons}</div>
      <div class="matrix-discovery-body">
        <div class="muted">${escapeHtml(note)}</div>
        <div class="table-actions compact-actions">
          <button class="button small ghost" data-export-discovery-group="${escapeHtml(activeGroup.key)}">导出当前分组</button>
          <button class="button small ghost" data-open-report-client="${escapeHtml(state.currentClient || "")}">跳库存报告</button>
        </div>
        <div class="matrix-discovery-list">${items || `<div class="matrix-empty-state">当前分组没有待看的项。</div>`}</div>
      </div>
    </div>
  `;
}

function renderSyncPreviewBlock(preview) {
  if (!preview) {
    return "先运行预览，查看每个目标客户端会新增什么、跳过什么，以及为什么跳过。";
  }
  const template = preview.skills_template || { families: [], published_family_count: 0, disabled_family_count: 0 };
  const targets = (preview.targets || [])
    .map((target) => {
      const skillCounts = target.skills?.counts || {};
      const mcpCounts = target.mcp?.counts || {};
      const notes = [...(target.issues || []), ...(target.mcp?.notes || [])]
        .filter(Boolean)
        .map((note) => `<li>${escapeHtml(note)}</li>`)
        .join("");
      return `
        <article class="sync-card ${escapeHtml(target.status || "ready")}">
          <div class="panel-head slim">
            <h4>${escapeHtml(target.client)}</h4>
            ${badge(target.status || "ready", target.status || "ready")}
          </div>
          <div class="sync-stats">
            <span>Skill 精确装载 <strong>${escapeHtml(skillCounts.prefer_exact ?? 0)}</strong></span>
            <span>禁用传播 <strong>${escapeHtml(skillCounts.disabled ?? 0)}</strong></span>
            <span>未解决 <strong>${escapeHtml(skillCounts.unresolved_family ?? 0)}</strong></span>
            <span>不可见 <strong>${escapeHtml(skillCounts.unavailable_family ?? 0)}</strong></span>
          </div>
          <div class="sync-stats">
            <span>MCP 新增 <strong>${escapeHtml(mcpCounts.add ?? 0)}</strong></span>
            <span>MCP 更新 <strong>${escapeHtml(mcpCounts.update ?? 0)}</strong></span>
            <span>MCP 无变化 <strong>${escapeHtml(mcpCounts.noop ?? 0)}</strong></span>
          </div>
          ${
            target.publish_preview
              ? `<div class="muted">发布预览：${escapeHtml(zh(target.publish_preview.status, target.publish_preview.status))} · ${escapeHtml(target.publish_preview.published_count ?? 0)} 个 skill</div>`
              : ""
          }
          ${notes ? `<ul class="sync-note-list">${notes}</ul>` : ""}
        </article>
      `;
    })
    .join("");
  return `
    <div class="sync-result">
      <div class="scan-source-summary">
        <span class="badge">模板 family ${escapeHtml(template.families?.length ?? 0)}</span>
        <span class="badge">已发布 ${escapeHtml(template.published_family_count ?? 0)}</span>
        <span class="badge">显式禁用 ${escapeHtml(template.disabled_family_count ?? 0)}</span>
        ${preview.blocked_targets?.length ? `<span class="badge danger">阻断 ${escapeHtml(preview.blocked_targets.join(", "))}</span>` : `<span class="badge safe">可应用</span>`}
      </div>
      <div class="sync-card-list">${targets || `<div class="matrix-empty-state">没有目标客户端。</div>`}</div>
    </div>
  `;
}

function renderSyncApplyBlock(result) {
  if (!result) {
    return "应用同步后，这里会显示逐客户端的成功、跳过、失败和已回滚结果。";
  }
  const cards = (result.results || [])
    .map(
      (item) => `
        <article class="sync-card ${escapeHtml(item.status || "ready")}">
          <div class="panel-head slim">
            <h4>${escapeHtml(item.client)}</h4>
            ${badge(item.status || "ready", item.status || "ready")}
          </div>
          <div class="sync-stats">
            <span>备份点 <strong class="mono">${escapeHtml(item.backup_id || "-")}</strong></span>
            <span>Skill 变更 <strong>${escapeHtml(item.skills?.changed_count ?? 0)}</strong></span>
            <span>Skill 跳过 <strong>${escapeHtml(item.skills?.skipped_count ?? 0)}</strong></span>
            <span>MCP 变更 <strong>${escapeHtml(item.mcp?.changed ? "1" : "0")}</strong></span>
          </div>
          ${item.mcp?.summary ? `<div class="muted">${escapeHtml(item.mcp.summary)}</div>` : ""}
          ${item.error ? `<div class="muted">${escapeHtml(item.error)}</div>` : ""}
        </article>
      `,
    )
    .join("");
  return `<div class="sync-card-list">${cards || `<div class="matrix-empty-state">本次没有目标客户端结果。</div>`}</div>`;
}

function renderSyncCenter() {
  const sourceSelect = $("#syncSourceClient");
  const targetHost = $("#syncTargetList");
  const familySummary = $("#syncFamilySummary");
  const previewHost = $("#syncPreviewOutput");
  const applyHost = $("#syncApplyOutput");
  if (!sourceSelect || !targetHost || !familySummary || !previewHost || !applyHost) {
    return;
  }
  const clients = Object.keys(state.status?.clients || {});
  const source = syncSourceClient();
  const targets = normalizedTargetClients();
  sourceSelect.innerHTML = clients.map((client) => `<option value="${escapeHtml(client)}">${escapeHtml(client)}</option>`).join("");
  sourceSelect.value = source;
  $("#syncIncludeSkills").checked = Boolean(state.syncCenter.includeSkills);
  $("#syncIncludeMcp").checked = Boolean(state.syncCenter.includeMcp);
  $("#syncScopeAll").classList.toggle("active", state.syncCenter.scope !== "selected");
  $("#syncScopeSelected").classList.toggle("active", state.syncCenter.scope === "selected");
  targetHost.innerHTML = clients
    .filter((client) => client !== source)
    .map(
      (client) => `
        <label class="sync-target ${targets.includes(client) ? "active" : ""}">
          <input type="checkbox" data-sync-target="${escapeHtml(client)}" ${targets.includes(client) ? "checked" : ""} />
          <span>${escapeHtml(client)}</span>
        </label>
      `,
    )
    .join("");
  const selectedRows = selectedMatrixRows();
  familySummary.innerHTML =
    state.syncCenter.scope === "selected"
      ? selectedRows.length
        ? `当前只同步 <strong>${escapeHtml(selectedRows.length)}</strong> 个已选 family：${escapeHtml(selectedRows.map((row) => row.name || row.conflict_family).slice(0, 6).join("、"))}${selectedRows.length > 6 ? " ..." : ""}`
        : "当前选择了“当前已选 family”，但矩阵里还没有勾选任何 family。"
      : `当前按 <strong>${escapeHtml(source || "-")}</strong> 的全部已发布 family 建立同步模板。`;
  previewHost.innerHTML = renderSyncPreviewBlock(state.syncCenter.preview);
  applyHost.innerHTML = renderSyncApplyBlock(state.syncCenter.applyResult);
}

function detailItem(label, value, options = {}) {
  const text = value === null || value === undefined || value === "" ? "-" : String(value);
  const className = options.mono ? "mono" : "";
  return `<div class="detail-item"><small>${escapeHtml(label)}</small><strong class="${className}">${escapeHtml(text)}</strong></div>`;
}

function renderClientDetail() {
  if (!state.currentClient || !state.status?.clients?.[state.currentClient]) {
    $("#clientDetail").innerHTML = "<p class=\"muted\">还没有选中客户端。</p>";
    $("#clientOutput").textContent = "先选择客户端，再运行预览或深度体检。";
    return;
  }
  const client = state.currentClient;
  const config = state.status.clients[client];
  const published = config.published_skill_ids?.length || 0;
  $("#clientDetail").innerHTML = `
    ${detailItem("目标目录", config.target_dir, { mono: true })}
    ${detailItem("配置文件", config.config_path || "无", { mono: true })}
    ${detailItem("已发布技能数", published)}
    ${detailItem("最近备份", config.last_backup_id || "无", { mono: true })}
    ${detailItem("最近预览", `${zh(config.last_preview_status, "无")} ${formatTime(config.last_preview_at, "")}`)}
    ${detailItem("最近深度体检", `${zh(config.last_deep_doctor_status, "无")} ${formatTime(config.last_deep_doctor_at, "")}`)}
  `;
  updatePublishButton();
}

function renderInventoryDiffTable(title, entries, emptyText) {
  const filteredEntries = (entries || []).filter((item) => {
    if (state.inventoryFilters.scope && item.scope !== state.inventoryFilters.scope) {
      return false;
    }
    if (state.inventoryFilters.sourceClient) {
      const haystack = String(item.source_client || item.source_root || "").toLowerCase();
      if (!haystack.includes(state.inventoryFilters.sourceClient.toLowerCase())) {
        return false;
      }
    }
    return true;
  });
  if (!entries || !entries.length) {
    return `
      <section class="inventory-section">
        <div class="panel-head slim">
          <h4>${escapeHtml(title)}</h4>
          <span class="badge">${escapeHtml("0")}</span>
        </div>
        <p class="muted">${escapeHtml(emptyText)}</p>
      </section>
    `;
  }
  const rows = filteredEntries
    .map(
      (item) => `
        <tr>
          <td>${escapeHtml(item.name || "-")}</td>
          <td class="mono">${escapeHtml(item.skill_id || "-")}</td>
          <td class="mono">
            ${escapeHtml(item.path || "-")}
            <div class="table-actions compact-actions">
              <button class="button small ghost" data-copy-text="${escapeHtml(item.path || "")}">复制路径</button>
              <button class="button small ghost" data-open-report-client="${escapeHtml(state.currentClient || "")}">跳报告</button>
            </div>
          </td>
          <td>${escapeHtml(zh(item.scope, item.scope || "-"))}</td>
          <td>${escapeHtml(item.reason || "-")}</td>
        </tr>
      `,
    )
    .join("");
  return `
      <section class="inventory-section">
      <div class="panel-head slim">
        <h4>${escapeHtml(title)}</h4>
        <span class="badge warning">${escapeHtml(String(filteredEntries.length))}</span>
      </div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>名称</th><th>skill_id</th><th>路径</th><th>范围</th><th>原因</th></tr></thead>
          <tbody>${rows || `<tr><td colspan="5">当前筛选下没有匹配条目。</td></tr>`}</tbody>
        </table>
      </div>
    </section>
  `;
}

function renderInventory() {
  const summaryHost = $("#inventorySummaryCards");
  const detailHost = $("#inventoryDetail");
  if (!summaryHost || !detailHost) {
    return;
  }
  const summary = state.inventorySummary?.clients || [];
  if (!summary.length) {
    summaryHost.innerHTML = `<p class="muted">进入盘点页后会从本地服务读取各客户端的真实盘点摘要。</p>`;
    detailHost.innerHTML = `<p class="muted">请选择一个客户端查看 live、pool、published 和 MCP 配置源详情。</p>`;
    return;
  }

  summaryHost.innerHTML = summary
    .map((entry) => {
      const skills = entry.skills || {};
      const mcp = entry.mcp || {};
      return `
        <article class="inventory-card" data-open-inventory-client="${escapeHtml(entry.client)}">
          <div class="panel-head slim">
            <h3>${escapeHtml(entry.client)}</h3>
            ${badge(mcp.source_status, "未知")}
          </div>
          <div class="inventory-card-stats">
            <span>live <strong>${escapeHtml(skills.live_total_count ?? "-")}</strong></span>
            <span>published <strong>${escapeHtml(skills.published_count ?? "-")}</strong></span>
            <span>pool visible <strong>${escapeHtml(skills.pool_visible_count ?? "-")}</strong></span>
          </div>
          <div class="muted">MCP：${
            mcp.server_count === null || mcp.server_count === undefined
              ? "当前无法可靠统计"
              : `${escapeHtml(mcp.server_count)} 个`
          }</div>
          <div class="muted">未纳管 live：${escapeHtml(skills.unmanaged_live_count ?? "-")}</div>
        </article>
      `;
    })
    .join("");

  const detail = state.inventoryDetails[state.currentClient];
  if (!detail) {
    detailHost.innerHTML = `<p class="muted">已加载摘要，点击上方客户端卡片或右上角选择框以查看盘点详情。</p>`;
    return;
  }

  const skills = detail.skills || {};
  const mcp = detail.mcp || {};
  const diffType = state.inventoryFilters.diffType || "";
  const sourceClientCounts = {};
  ["live_only", "pool_only", "published_only", "source_mismatch"].forEach((key) => {
    (skills[key] || []).forEach((item) => {
      const sourceKey = item.source_client || item.source_root || "未知来源";
      sourceClientCounts[sourceKey] = (sourceClientCounts[sourceKey] || 0) + 1;
    });
  });
  const sourceClientSummary = Object.entries(sourceClientCounts)
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .map(([name, count]) => `<span class="badge">${escapeHtml(name)} · ${escapeHtml(count)}</span>`)
    .join("");
  const sourceRows = (skills.source_directories || [])
    .map(
      (item) => `
        <tr>
          <td class="mono">
            ${escapeHtml(item.path || "-")}
            <div class="table-actions compact-actions">
              <button class="button small ghost" data-copy-text="${escapeHtml(item.path || "")}">复制路径</button>
              <button class="button small ghost" data-open-report-client="${escapeHtml(detail.client)}">跳报告</button>
            </div>
          </td>
          <td>${escapeHtml(formatList(item.roles || [], "-"))}</td>
        </tr>
      `,
    )
    .join("");
  const sourceFiles = (mcp.source_files || [])
    .map((sourceFile) => `<li class="mono">${escapeHtml(sourceFile)}</li>`)
    .join("");
  const serverRows = (mcp.servers || [])
    .map(
      (server) => `
        <tr>
          <td>${escapeHtml(server.name || "-")}</td>
          <td>${badge(server.enabled ? "enabled" : "disabled")}</td>
          <td class="mono">${escapeHtml(server.command || "-")}</td>
          <td class="mono">${escapeHtml(formatList(server.args || [], "-"))}</td>
          <td class="mono">${escapeHtml(server.source_file || "-")}</td>
        </tr>
      `,
    )
    .join("");
  const notes = (mcp.notes || []).map((note) => `<li>${escapeHtml(note)}</li>`).join("");

  detailHost.innerHTML = `
    <article class="inventory-focus">
      <div class="panel-head">
        <div>
          <p class="eyebrow">客户端详情</p>
          <h3>${escapeHtml(detail.client)}</h3>
        </div>
        <div class="hero-actions">
          ${badge(mcp.source_status, "未知")}
          <span class="badge">${escapeHtml(`live ${skills.live_total_count ?? "-"}`)}</span>
          <span class="badge">${escapeHtml(`published ${skills.published_count ?? "-"}`)}</span>
          <span class="badge">${escapeHtml(`pool ${skills.pool_visible_count ?? "-"}`)}</span>
        </div>
      </div>

      <div class="detail-grid">
        ${detailItem("live target", skills.live_target_count)}
        ${detailItem("live extraDirs", skills.live_extra_dir_count)}
        ${detailItem("live total", skills.live_total_count)}
        ${detailItem("published", skills.published_count)}
        ${detailItem("pool visible", skills.pool_visible_count)}
        ${detailItem("未纳管 live", skills.unmanaged_live_count)}
        ${detailItem("发布缺失", skills.published_missing_from_live_count)}
        ${detailItem("池内未发布", skills.pool_not_published_count)}
      </div>

      <section class="inventory-section">
        <div class="panel-head slim">
          <h4>技能来源目录</h4>
          <span class="badge">${escapeHtml(String((skills.source_directories || []).length))}</span>
        </div>
        ${
          sourceRows
            ? `<div class="table-wrap"><table><thead><tr><th>路径</th><th>角色</th></tr></thead><tbody>${sourceRows}</tbody></table></div>`
            : `<p class="muted">没有发现来源目录。</p>`
        }
      </section>

      <section class="inventory-section">
        <div class="panel-head slim">
          <h4>按来源客户端聚合</h4>
        </div>
        ${sourceClientSummary ? `<div class="badge-row">${sourceClientSummary}</div>` : `<p class="muted">当前没有可聚合的差异来源。</p>`}
      </section>

      ${!diffType || diffType === "live_only" ? renderInventoryDiffTable("live 独有", skills.live_only || [], "当前没有 live-only 项。") : ""}
      ${!diffType || diffType === "pool_only" ? renderInventoryDiffTable("仅池内", skills.pool_only || [], "当前没有 pool-only 项。") : ""}
      ${!diffType || diffType === "published_only" ? renderInventoryDiffTable("发布缺失", skills.published_only || [], "当前没有 published-only 项。") : ""}
      ${!diffType || diffType === "source_mismatch" ? renderInventoryDiffTable("来源不一致", skills.source_mismatch || [], "当前没有 source mismatch 项。") : ""}

      <section class="inventory-section">
        <div class="panel-head slim">
          <h4>MCP 配置盘点</h4>
          ${badge(mcp.source_status, "未知")}
        </div>
        <div class="detail-grid">
          ${detailItem("配置状态", zh(mcp.source_status, "未知"))}
          ${detailItem("MCP 数量", mcp.server_count === null || mcp.server_count === undefined ? "当前无法可靠统计" : mcp.server_count)}
        </div>
        <div class="inventory-mcp-grid">
          <div>
            <h5>配置源文件</h5>
            ${sourceFiles ? `<ul class="inventory-list">${sourceFiles}</ul>` : `<p class="muted">当前没有可用的配置源文件。</p>`}
          </div>
          <div>
            <h5>备注</h5>
            ${notes ? `<ul class="inventory-list">${notes}</ul>` : `<p class="muted">没有额外备注。</p>`}
          </div>
        </div>
        ${
          serverRows
            ? `<div class="table-wrap"><table><thead><tr><th>名称</th><th>启用</th><th>命令</th><th>参数</th><th>来源文件</th></tr></thead><tbody>${serverRows}</tbody></table></div>`
            : `<p class="muted">当前没有可列出的 MCP server 条目。</p>`
        }
      </section>
    </article>
  `;
}

async function openInventoryClient(client, { force = false } = {}) {
  state.currentClient = client;
  switchView("inventory", { sync: false });
  await loadInventorySummary(force);
  await loadInventoryDetail(client, force);
  renderClientOptions();
  renderInventory();
  syncHash();
}

async function refreshInventoryView() {
  const client = state.currentClient;
  if (!client) {
    toast("当前没有可刷新的客户端。");
    return;
  }
  await runAction(`${client} 盘点刷新`, async () => {
    await loadInventorySummary(true);
    return await loadInventoryDetail(client, true);
  });
  renderInventory();
}

async function exportInventory(format, client = state.currentClient) {
  const query = new URLSearchParams({ format });
  if (client) {
    query.set("client", client);
  }
  const result = await runAction(`导出盘点 ${format.toUpperCase()}`, () => api(`/api/inventory/export?${query.toString()}`));
  downloadContent(result.filename, result.content, result.content_type);
}

function resetMcpForm() {
  $("#mcpOriginalName").value = "";
  $("#mcpName").value = "";
  $("#mcpCommand").value = "";
  $("#mcpArgs").value = "";
  $("#mcpEnabled").checked = true;
  $("#mcpFormTitle").textContent = "新增或编辑 MCP server";
}

function renderMcp() {
  const summaryHost = $("#mcpSummary");
  const detailHost = $("#mcpDetail");
  if (!summaryHost || !detailHost) {
    return;
  }
  const summary = state.mcpSummary?.clients || [];
  if (!summary.length) {
    summaryHost.innerHTML = `<p class="muted">进入 MCP 页后会加载客户端支持状态与 server 摘要。</p>`;
    detailHost.innerHTML = `<p class="muted">请选择一个客户端查看或编辑 MCP 配置。</p>`;
    return;
  }
  summaryHost.innerHTML = summary
    .map(
      (item) => `
        <article class="inventory-card" data-open-mcp-client="${escapeHtml(item.client)}">
          <div class="panel-head slim">
            <h3>${escapeHtml(item.client)}</h3>
            ${badge(item.source_status, "未知")}
          </div>
          <div class="inventory-card-stats">
            <span>server <strong>${escapeHtml(item.server_count ?? "-")}</strong></span>
            <span>duplicates <strong>${escapeHtml(item.duplicate_count ?? 0)}</strong></span>
            <span>writable <strong>${escapeHtml(item.writable ? "yes" : "no")}</strong></span>
          </div>
          <div class="muted">${escapeHtml((item.notes || []).join(" "))}</div>
        </article>
      `,
    )
    .join("");

  const detail = state.mcpDetails[state.currentClient];
  if (!detail) {
    detailHost.innerHTML = `<p class="muted">点击上方客户端卡片或右上角选择框以查看 MCP 详情。</p>`;
    return;
  }
  const duplicateRows = (detail.duplicate_groups || [])
    .map(
      (group) => `
        <tr>
          <td>${escapeHtml(group.group_id)}</td>
          <td>${escapeHtml(formatList(group.names, "-"))}</td>
          <td class="mono">${escapeHtml(group.command || "-")}</td>
          <td class="mono">${escapeHtml(formatList(group.args || [], "-"))}</td>
        </tr>
      `,
    )
    .join("");
  const serverRows = (detail.servers || [])
    .map(
      (server) => `
        <tr>
          <td>${escapeHtml(server.name || "-")}</td>
          <td>${badge(server.enabled ? "enabled" : "disabled")}</td>
          <td><span class="badge ${server.managed ? "safe" : "warning"}">${server.managed ? "可管理" : "只读"}</span></td>
          <td class="mono">${escapeHtml(server.command || "-")}</td>
          <td class="mono">${escapeHtml(formatList(server.args || [], "-"))}</td>
          <td class="mono">${escapeHtml(server.source_kind || "-")}</td>
          <td class="table-actions">
            <button class="button small" data-edit-mcp-server="${escapeHtml(server.name)}">编辑</button>
            <button class="button small" ${!detail.writable || !server.managed ? "disabled" : ""} data-mcp-toggle="${escapeHtml(server.name)}" data-mcp-enabled="${escapeHtml(String(server.enabled))}">${server.enabled ? "禁用" : "启用"}</button>
            <button class="button small danger" ${!detail.writable || !server.managed ? "disabled" : ""} data-mcp-remove="${escapeHtml(server.name)}">删除</button>
          </td>
        </tr>
      `,
    )
    .join("");

  detailHost.innerHTML = `
    <article class="inventory-focus">
      <div class="panel-head">
        <div>
          <p class="eyebrow">客户端 MCP 详情</p>
          <h3>${escapeHtml(detail.client)}</h3>
        </div>
        <div class="hero-actions">
          ${badge(detail.source_status, "未知")}
          <span class="badge">${escapeHtml(`servers ${detail.server_count ?? "-"}`)}</span>
          <span class="badge">${escapeHtml(`duplicates ${detail.duplicate_groups?.length || 0}`)}</span>
        </div>
      </div>
      <div class="detail-grid">
        ${detailItem("配置状态", zh(detail.source_status, "未知"))}
        ${detailItem("可写", detail.writable ? "是" : "否")}
        ${detailItem("最近操作", detail.last_operation || "-")}
        ${detailItem("最近备份", detail.last_backup_id || "-")}
      </div>
      <section class="inventory-section">
        <h4>说明</h4>
        <ul class="inventory-list">${(detail.notes || []).map((note) => `<li>${escapeHtml(note)}</li>`).join("") || "<li>无</li>"}</ul>
      </section>
      <section class="inventory-section">
        <h4>重复项</h4>
        ${
          duplicateRows
            ? `<div class="table-wrap"><table><thead><tr><th>组</th><th>名称</th><th>命令</th><th>参数</th></tr></thead><tbody>${duplicateRows}</tbody></table></div>`
            : `<p class="muted">当前没有检测到重复项。</p>`
        }
      </section>
      <section class="inventory-section">
        <h4>Servers</h4>
        ${
          serverRows
            ? `<div class="table-wrap"><table><thead><tr><th>名称</th><th>启用</th><th>模式</th><th>命令</th><th>参数</th><th>来源</th><th>动作</th></tr></thead><tbody>${serverRows}</tbody></table></div>`
            : `<p class="muted">当前没有可列出的 MCP server。</p>`
        }
      </section>
    </article>
  `;

  const lastDiff = detail.last_diff?.text || "最近一次 MCP diff 会显示在这里。";
  $("#mcpDiffOutput").textContent = lastDiff;
}

async function openMcpClient(client, { force = false } = {}) {
  state.currentClient = client;
  switchView("mcp", { sync: false });
  await loadMcpSummary(force);
  await loadMcpDetail(client, force);
  renderClientOptions();
  renderMcp();
  syncHash();
}

async function refreshMcpView() {
  if (!state.currentClient) {
    toast("当前没有选中的客户端。");
    return;
  }
  await runAction(`${state.currentClient} MCP 刷新`, async () => {
    await loadMcpSummary(true);
    return await loadMcpDetail(state.currentClient, true);
  });
  renderMcp();
}

async function submitMcpForm(event) {
  event.preventDefault();
  if (!state.currentClient) {
    toast("当前没有选中的客户端。");
    return;
  }
  const originalName = $("#mcpOriginalName").value.trim();
  const serverName = $("#mcpName").value.trim();
  const command = $("#mcpCommand").value.trim();
  const args = $("#mcpArgs")
    .value.split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
  const enabled = $("#mcpEnabled").checked;
  const path = originalName ? `/api/mcp/clients/${encodeURIComponent(state.currentClient)}/update` : `/api/mcp/clients/${encodeURIComponent(state.currentClient)}/add`;
  const payload = originalName
    ? { server_name: originalName, new_name: serverName, command, args, enabled }
    : { server_name: serverName, command, args, enabled };
  const result = await runAction(`${state.currentClient} MCP 保存`, () => postJson(path, payload));
  state.mcpDetails[state.currentClient] = result.mcp;
  $("#mcpDiffOutput").textContent = result.diff?.text || asJson(result);
  resetMcpForm();
  await refreshAll();
}

async function cleanupScan() {
  const result = await runAction("扫描清理候选项", () => postJson("/api/cleanup/scan"));
  state.cleanup = result;
  $("#cleanupOutput").textContent = asJson(result);
  await refreshAll();
}

async function refreshCleanupView() {
  state.cleanup = await runAction("刷新清理候选项", () => api("/api/cleanup"));
  renderCleanup();
}

function renderCleanup() {
  const summaryNode = $("#cleanupSummary");
  const tableNode = $("#cleanupTable");
  if (!summaryNode || !tableNode) {
    return;
  }
  const cleanup = state.cleanup || { total: 0, candidates: [] };
  const candidates = (cleanup.candidates || []).filter((item) => !state.cleanupLabelFilter || item.label === state.cleanupLabelFilter);
  summaryNode.textContent = `共 ${cleanup.total || 0} 个候选项，当前筛选后 ${candidates.length} 个。`;
  const rows = candidates
    .map(
      (item) => `
        <tr>
          <td>
            <strong>${escapeHtml(item.name || "-")}</strong>
            <div class="mono">${escapeHtml(item.skill_id || "-")}</div>
          </td>
          <td>${badge(item.label || "candidate")}</td>
          <td>${badge(item.status || "-")}</td>
          <td>${escapeHtml(item.source_scope || "-")}</td>
          <td>${escapeHtml(item.source_client || "-")}</td>
          <td>${escapeHtml(formatList(item.published_for || [], "未发布"))}</td>
          <td>${escapeHtml((item.reasons || []).map((reason) => `${reason.type}: ${reason.message}`).join(" | ") || "-")}</td>
          <td class="table-actions">
            <button class="button small" data-cleanup-mark="${escapeHtml(item.skill_id)}" data-cleanup-label="candidate">候选</button>
            <button class="button small" data-cleanup-mark="${escapeHtml(item.skill_id)}" data-cleanup-label="keep">保留</button>
            <button class="button small danger" data-cleanup-mark="${escapeHtml(item.skill_id)}" data-cleanup-label="ignore">忽略</button>
          </td>
        </tr>
      `,
    )
    .join("");
  tableNode.innerHTML = `
    <table>
      <thead><tr><th>技能</th><th>标签</th><th>状态</th><th>来源范围</th><th>来源客户端</th><th>已发布到</th><th>原因</th><th>动作</th></tr></thead>
      <tbody>${rows || `<tr><td colspan="8">当前没有匹配的候选项。</td></tr>`}</tbody>
    </table>
  `;
}

function updatePublishButton() {
  const button = $("#runPublish");
  if (!button) {
    return;
  }
  const client = state.currentClient;
  const preview = state.clientPreview[client];
  const force = $("#forcePublish").checked;
  let enabled = state.serviceOnline !== false && Boolean(preview) && preview.status !== "blocked";
  if ((client === "openclaw" || client === "qclaw") && preview && preview.status !== "safe" && !force) {
    enabled = false;
  }
  button.disabled = !enabled;
}

async function loadPreview() {
  const client = state.currentClient;
  const preview = await runAction(`${client} 预览`, () => api(`/api/clients/${encodeURIComponent(client)}/preview?detailed=1`));
  state.clientPreview[client] = preview;
  $("#clientOutput").textContent = asJson(preview);
  updatePublishButton();
  await refreshStatusOnly();
}

async function loadDiff() {
  const client = state.currentClient;
  const diff = await runAction(`${client} 差异`, () => api(`/api/clients/${encodeURIComponent(client)}/diff`));
  $("#clientOutput").textContent = asJson(diff);
}

async function loadDoctor() {
  const client = state.currentClient;
  const doctor = await runAction(`${client} 深度体检`, () => api(`/api/clients/${encodeURIComponent(client)}/doctor?deep=1`));
  $("#clientOutput").textContent = asJson(doctor);
  await refreshStatusOnly();
}

async function publishClient() {
  const client = state.currentClient;
  const preview = state.clientPreview[client];
  if (!preview) {
    toast("发布前请先运行预览。");
    return;
  }
  if (preview.status === "blocked") {
    toast("当前预览是阻断状态，不能发布。");
    return;
  }
  const force = $("#forcePublish").checked;
  if (!window.confirm(`确认发布 ${client} 吗？发布前会自动创建备份。`)) {
    return;
  }
  const result = await runAction(`发布 ${client}`, () => postJson(`/api/clients/${encodeURIComponent(client)}/publish`, { force }));
  $("#clientOutput").textContent = asJson(result);
  await refreshAll();
}

async function loadBackups() {
  const client = state.currentClient;
  const backups = await runAction(`加载 ${client} 备份`, () => api(`/api/clients/${encodeURIComponent(client)}/backups`));
  state.backups[client] = backups.backups || [];
  renderBackups();
}

function renderBackups() {
  const client = state.currentClient;
  const backups = state.backups[client] || [];
  $("#backupList").innerHTML = backups.length
    ? backups
        .map(
          (backup) => `
            <div class="backup-item">
              <span class="mono">${escapeHtml(backup.backup_id)}</span>
              <button class="button small" ${state.serviceOnline === false ? "disabled" : ""} data-inspect-backup="${escapeHtml(backup.backup_id)}">检查</button>
              <button class="button small danger" ${state.serviceOnline === false ? "disabled" : "disabled"} data-rollback-backup="${escapeHtml(backup.backup_id)}">回滚</button>
            </div>
          `,
        )
        .join("")
    : `<p class="muted">还没有加载备份列表。</p>`;
}

async function inspectBackup(backupId) {
  const client = state.currentClient;
  const inspected = await runAction(`检查备份 ${backupId}`, () =>
    api(`/api/clients/${encodeURIComponent(client)}/backups/${encodeURIComponent(backupId)}`),
  );
  state.inspectedBackups[`${client}:${backupId}`] = inspected;
  $("#backupInspect").textContent = asJson(inspected);
  $$(`[data-rollback-backup="${backupId}"]`).forEach((button) => {
    button.disabled = state.serviceOnline === false;
  });
}

async function rollbackBackup(backupId) {
  const client = state.currentClient;
  if (!state.inspectedBackups[`${client}:${backupId}`]) {
    toast("回滚前请先检查这个备份。");
    return;
  }
  if (!window.confirm(`确认把 ${client} 回滚到 ${backupId} 吗？`)) {
    return;
  }
  const result = await runAction(`回滚 ${client}`, () =>
    postJson(`/api/clients/${encodeURIComponent(client)}/rollback`, { backup_id: backupId }),
  );
  $("#backupInspect").textContent = asJson(result);
  await refreshAll();
}

function readSkillFiltersFromDom() {
  state.skillQuery = {
    ...state.skillQuery,
    q: $("#skillSearch").value.trim(),
    client: $("#skillClientFilter").value,
    status: $("#skillStatusFilter").value,
    enabled_global: $("#skillEnabledFilter").value,
    source_scope: $("#skillScopeFilter").value,
    sort_by: $("#skillSortBy").value,
    page_size: parseIntSafe($("#skillPageSize").value, state.skillQuery.page_size),
  };
}

function renderSkillsFilters() {
  $("#skillSearch").value = state.skillQuery.q || "";
  $("#skillStatusFilter").value = state.skillQuery.status || "";
  $("#skillEnabledFilter").value = state.skillQuery.enabled_global || "";
  $("#skillScopeFilter").value = state.skillQuery.source_scope || "";
  $("#skillSortBy").value = state.skillQuery.sort_by || DEFAULT_SKILL_QUERY.sort_by;
  $("#skillPageSize").value = String(state.skillQuery.page_size || DEFAULT_SKILL_QUERY.page_size);
  $("#toggleSkillSortDir").textContent = state.skillQuery.sort_dir === "desc" ? "降序" : "升序";
  const familyNode = $("#skillFamilyFilter");
  familyNode.innerHTML = state.skillQuery.family
    ? `<button class="pill active" data-clear-family="1">冲突族：${escapeHtml(state.skillQuery.family)} · 点击清除</button>`
    : `<span class="muted">当前没有按冲突族锁定。</span>`;
}

async function loadSkillsFromFilters() {
  readSkillFiltersFromDom();
  state.skillQuery.page = 1;
  syncHash();
  state.skills = await runAction("筛选技能", () => api(buildSkillsPath()));
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
  renderSkills();
  renderSkillDetail();
}

function resetSkillFilters() {
  state.skillQuery = { ...DEFAULT_SKILL_QUERY };
  state.selectedSkillId = null;
  state.skillDetail = null;
  syncHash();
  renderSkillsFilters();
  return loadSkillsFromFilters();
}

function sortIndicator(sortBy) {
  if (state.skillQuery.sort_by !== sortBy) {
    return "";
  }
  return state.skillQuery.sort_dir === "desc" ? " ↓" : " ↑";
}

function renderSortHeader(label, sortBy) {
  const disabled = state.serviceOnline === false ? "disabled" : "";
  return `<button class="table-sort" ${disabled} data-sort-by="${escapeHtml(sortBy)}">${escapeHtml(label)}${escapeHtml(sortIndicator(sortBy))}</button>`;
}

function renderSkills() {
  const response = state.skills || { total: 0, page: 1, total_pages: 0, skills: [] };
  const skills = response.skills || [];
  $("#skillResultMeta").innerHTML = `
    <span>共 <strong>${escapeHtml(response.total ?? 0)}</strong> 个技能</span>
    <span>当前第 <strong>${escapeHtml(response.total ? response.page : 0)}</strong> / <strong>${escapeHtml(response.total_pages ?? 0)}</strong> 页</span>
  `;

  const rows = skills
    .map((skill) => {
      const nextAction = skill.enabled_global === "enabled" ? "disable" : "enable";
      const actionLabel = nextAction === "disable" ? "禁用" : "启用";
      const buttonClass = nextAction === "disable" ? "danger" : "primary";
      const selected = state.selectedSkillId === skill.skill_id ? "selected-row" : "";
      const disabled = state.serviceOnline === false ? "disabled" : "";
      return `
        <tr class="${selected}">
          <td>
            <button class="link-button" data-open-skill="${escapeHtml(skill.skill_id)}">${escapeHtml(skill.name)}</button>
            <div class="mono">${escapeHtml(skill.skill_id)}</div>
            <div class="muted">${escapeHtml(skill.description || "无描述")}</div>
          </td>
          <td>
            <button class="link-button subtle" data-filter-family="${escapeHtml(skill.conflict_family)}">${escapeHtml(skill.conflict_family)}</button>
          </td>
          <td>${badge(skill.status)}</td>
          <td>${badge(skill.enabled_global)}</td>
          <td>
            ${escapeHtml(zh(skill.source_scope, "-"))}
            <div class="muted">${escapeHtml(skill.source_client || skill.source_type || "-")}</div>
          </td>
          <td>${escapeHtml(formatList(skill.available_clients, "全部"))}</td>
          <td>${escapeHtml(formatList(skill.published_for, "未发布"))}</td>
          <td class="mono">${escapeHtml(formatTime(skill.imported_at))}</td>
          <td class="mono">${escapeHtml(formatTime(skill.last_seen_at))}</td>
          <td class="table-actions">
            <button class="button small" data-open-skill="${escapeHtml(skill.skill_id)}">详情</button>
            <button class="button small ${buttonClass}" ${disabled} data-skill-action="${nextAction}" data-skill-id="${escapeHtml(skill.skill_id)}">${actionLabel}</button>
          </td>
        </tr>
      `;
    })
    .join("");

  $("#skillsTable").innerHTML = `
    <table>
      <thead>
        <tr>
          <th>${renderSortHeader("技能", "name")}</th>
          <th>冲突族</th>
          <th>${renderSortHeader("状态", "status")}</th>
          <th>启用</th>
          <th>${renderSortHeader("来源范围", "source_scope")}</th>
          <th>可见客户端</th>
          <th>已发布到</th>
          <th>${renderSortHeader("导入时间", "imported_at")}</th>
          <th>${renderSortHeader("最近发现", "last_seen_at")}</th>
          <th>动作</th>
        </tr>
      </thead>
      <tbody>${rows || `<tr><td colspan="10">当前筛选条件下没有匹配技能。</td></tr>`}</tbody>
    </table>
  `;

  const totalPages = response.total_pages || 0;
  const previousPage = Math.max((response.page || 1) - 1, 1);
  const nextPage = Math.min((response.page || 1) + 1, totalPages || 1);
  const disabled = state.serviceOnline === false ? "disabled" : "";
  $("#skillPagination").innerHTML = `
    <div class="pagination-summary">第 ${escapeHtml(response.total ? response.page : 0)} / ${escapeHtml(totalPages)} 页，共 ${escapeHtml(response.total ?? 0)} 条</div>
    <div class="pagination-actions">
      <button class="button small ghost" ${disabled} ${response.page <= 1 ? "disabled" : ""} data-skill-page="1">首页</button>
      <button class="button small ghost" ${disabled} ${response.page <= 1 ? "disabled" : ""} data-skill-page="${escapeHtml(previousPage)}">上一页</button>
      <button class="button small ghost" ${disabled} ${!totalPages || response.page >= totalPages ? "disabled" : ""} data-skill-page="${escapeHtml(nextPage)}">下一页</button>
      <button class="button small ghost" ${disabled} ${!totalPages || response.page >= totalPages ? "disabled" : ""} data-skill-page="${escapeHtml(totalPages || 1)}">末页</button>
    </div>
  `;
}

function renderSkillDetail() {
  const host = $("#skillDrawerBody");
  if (!state.skillDetail) {
    $("#skillDrawerTitle").textContent = "请选择一个技能";
    host.innerHTML = `
      <p class="muted">可以从技能表或冲突页打开技能详情。详情里会展示来源记录、发布去向、客户端覆盖和同族技能。</p>
    `;
    return;
  }
  const skill = state.skillDetail;
  const nextAction = skill.enabled_global === "enabled" ? "disable" : "enable";
  const actionLabel = nextAction === "disable" ? "禁用技能" : "启用技能";
  const disabled = state.serviceOnline === false ? "disabled" : "";
  $("#skillDrawerTitle").textContent = skill.name;

  const sourceRows = (skill.source_records || [])
    .map(
      (record) => `
        <tr>
          <td>${escapeHtml(record.source_type || "-")}</td>
          <td>${escapeHtml(record.source_locator || "-")}</td>
          <td>${escapeHtml(record.source_version || "-")}</td>
          <td>${escapeHtml(record.source_client || "-")}</td>
          <td>${escapeHtml(zh(record.source_scope, "-"))}</td>
          <td class="mono">${escapeHtml(record.source_root || "-")}</td>
        </tr>
      `,
    )
    .join("");

  const overrideRows = Object.entries(skill.client_overrides || {})
    .map(
      ([client, override]) => `
        <div class="mini-row">
          <span>${escapeHtml(client)}</span>
          <strong>${escapeHtml(formatOverride(override))}</strong>
        </div>
      `,
    )
    .join("");

  const conflictRows = (skill.conflict_members || [])
    .map(
      (member) => `
        <button class="skill-chip" data-open-skill="${escapeHtml(member.skill_id)}">
          <strong>${escapeHtml(member.name)}</strong>
          <span>${escapeHtml(member.skill_id)}</span>
          <small>${escapeHtml(zh(member.status, member.status))}</small>
        </button>
      `,
    )
    .join("");
  const inventoryClients = Array.from(
    new Set([...(skill.published_for || []), ...(skill.available_clients || []), skill.source_client].filter(Boolean)),
  );
  const inventoryButtons = inventoryClients
    .map(
      (client) => `
        <button class="skill-chip" data-open-inventory-client="${escapeHtml(client)}">
          <strong>${escapeHtml(client)}</strong>
          <span>查看盘点</span>
        </button>
      `,
    )
    .join("");

  host.innerHTML = `
    <div class="detail-grid">
      ${detailItem("skill_id", skill.skill_id, { mono: true })}
      ${detailItem("冲突族", skill.conflict_family)}
      ${detailItem("全局启用", zh(skill.enabled_global))}
      ${detailItem("当前状态", zh(skill.status))}
      ${detailItem("来源范围", zh(skill.source_scope, "-"))}
      ${detailItem("来源客户端", skill.source_client || "-")}
      ${detailItem("导入时间", formatTime(skill.imported_at))}
      ${detailItem("最近发现", formatTime(skill.last_seen_at))}
      ${detailItem("可见客户端", formatList(skill.available_clients, "全部"))}
      ${detailItem("已发布到", formatList(skill.published_for, "未发布"))}
      ${detailItem("来源目录", skill.source_root || "-", { mono: true })}
      ${detailItem("池内路径", skill.files_path || "-", { mono: true })}
    </div>

    <div class="action-row compact">
      <button class="button small ${nextAction === "disable" ? "danger" : "primary"}" ${disabled} data-skill-action="${nextAction}" data-skill-id="${escapeHtml(skill.skill_id)}">${actionLabel}</button>
      <button class="button small" ${skill.family_has_conflict ? "" : "disabled"} data-open-conflict="${escapeHtml(skill.conflict_family)}">跳到冲突族</button>
      <button class="button small ghost" data-clear-skill-detail="1">关闭详情</button>
    </div>

    <section class="drawer-section">
      <h4>说明</h4>
      <p>${escapeHtml(skill.description || "无描述")}</p>
    </section>

    <section class="drawer-section">
      <h4>来源记录</h4>
      ${
        sourceRows
          ? `
            <div class="table-wrap">
              <table>
                <thead><tr><th>来源</th><th>定位</th><th>版本</th><th>客户端</th><th>范围</th><th>根目录</th></tr></thead>
                <tbody>${sourceRows}</tbody>
              </table>
            </div>
          `
          : `<p class="muted">没有记录到额外来源。</p>`
      }
    </section>

    <section class="drawer-section">
      <h4>客户端覆盖</h4>
      ${overrideRows ? `<div class="mini-list">${overrideRows}</div>` : `<p class="muted">当前没有显式覆盖，全部继承全局策略。</p>`}
    </section>

    <section class="drawer-section">
      <h4>同冲突族其他成员</h4>
      ${conflictRows ? `<div class="skill-chip-list">${conflictRows}</div>` : `<p class="muted">这个技能目前没有同族冲突项。</p>`}
    </section>

    <section class="drawer-section">
      <h4>跳转盘点</h4>
      ${inventoryButtons ? `<div class="skill-chip-list">${inventoryButtons}</div>` : `<p class="muted">当前没有可直接跳转的客户端盘点。</p>`}
    </section>
  `;
}

async function openSkillDetail(skillId, options = {}) {
  state.selectedSkillId = skillId;
  if (options.family) {
    state.skillQuery.family = options.family;
    state.skillQuery.page = 1;
  }
  if (options.switchToSkills) {
    state.skillManagerMode = "instances";
    state.currentView = "skills";
    switchView("skills", { sync: false });
    state.skills = await api(buildSkillsPath());
    renderSkillManager();
    renderSkillsFilters();
    renderSkills();
  }
  state.skillDetail = await api(`/api/skills/${encodeURIComponent(skillId)}`);
  renderSkillDetail();
  syncHash();
}

function clearSkillDetail() {
  state.selectedSkillId = null;
  state.skillDetail = null;
  renderSkillDetail();
  syncHash();
}

async function openConflictFamily(family) {
  state.conflictFamilyFilter = family;
  state.currentView = "conflicts";
  switchView("conflicts", { sync: false });
  state.conflicts = await api(buildConflictsPath());
  renderConflicts();
  syncHash();
}

async function clearConflictFamilyFilter() {
  state.conflictFamilyFilter = "";
  state.conflicts = await api(buildConflictsPath());
  renderConflicts();
  syncHash();
}

function renderConflicts() {
  const conflicts = state.conflicts?.conflicts || [];
  const clients = Object.keys(state.status?.clients || {});
  const renderOverrideSummary = (overrides) => {
    const entries = Object.entries(overrides || {});
    if (!entries.length) {
      return `<span class="muted">继承</span>`;
    }
    return entries
      .map(([client, override]) => `${escapeHtml(client)}: ${escapeHtml(formatOverride(override))}`)
      .join("<br>");
  };
  const filterSummary = state.conflictFamilyFilter
    ? `
      <div class="conflict-filter">
        <span>当前只显示冲突族 <strong>${escapeHtml(state.conflictFamilyFilter)}</strong></span>
        <button class="button small ghost" ${state.serviceOnline === false ? "disabled" : ""} data-clear-conflict-family="1">返回全部冲突</button>
      </div>
    `
    : "";

  $("#conflictList").innerHTML =
    filterSummary +
    (conflicts.length
      ? conflicts
          .map((conflict) => {
            const clientOptions = clients.map((client) => `<option value="${escapeHtml(client)}">${escapeHtml(client)}</option>`).join("");
            const memberOptions = conflict.members
              .map((member) => `<option value="${escapeHtml(member.skill_id)}">${escapeHtml(member.name)} · ${escapeHtml(member.skill_id)}</option>`)
              .join("");
            const rows = conflict.members
              .map(
                (member) => `
                  <tr>
                    <td>
                      <button class="link-button" data-open-skill="${escapeHtml(member.skill_id)}" data-open-skill-family="${escapeHtml(conflict.conflict_family)}">${escapeHtml(member.name)}</button>
                      <div class="mono">${escapeHtml(member.skill_id)}</div>
                    </td>
                    <td>${escapeHtml(zh(member.source_scope, "-"))}</td>
                    <td>${badge(member.status)}</td>
                    <td>${escapeHtml(formatList(member.published_for, "未发布"))}</td>
                    <td>${renderOverrideSummary(member.client_overrides)}</td>
                  </tr>
                `,
              )
              .join("");
            return `
              <article class="conflict-card" data-family="${escapeHtml(conflict.conflict_family)}">
                <div class="panel-head slim">
                  <h3>${escapeHtml(conflict.conflict_family)}</h3>
                  <span class="badge warning">${conflict.member_count} 个变体</span>
                </div>
                <div class="muted">当前胜出项：${escapeHtml(conflict.winner_skill_ids.join(", ") || "-")}</div>
                <div class="muted">各客户端胜出：${escapeHtml(
                  Object.entries(conflict.client_winners || {})
                    .map(([client, skillId]) => `${client}=${skillId}`)
                    .join(", ") || "-",
                )}</div>
                <div class="conflict-actions">
                  <select class="select" data-conflict-client ${state.serviceOnline === false ? "disabled" : ""}>${clientOptions}</select>
                  <select class="select" data-conflict-skill ${state.serviceOnline === false ? "disabled" : ""}>${memberOptions}</select>
                  <button class="button small primary" ${state.serviceOnline === false ? "disabled" : ""} data-conflict-action="prefer">优先使用</button>
                  <button class="button small" ${state.serviceOnline === false ? "disabled" : ""} data-conflict-action="inherit">恢复继承</button>
                  <button class="button small danger" ${state.serviceOnline === false ? "disabled" : ""} data-conflict-action="disable">禁用整个族</button>
                </div>
                <div class="table-wrap">
                  <table>
                    <thead><tr><th>成员</th><th>来源范围</th><th>状态</th><th>已发布到</th><th>客户端覆盖</th></tr></thead>
                    <tbody>${rows}</tbody>
                  </table>
                </div>
              </article>
            `;
          })
          .join("")
      : `<p class="muted">当前没有多版本冲突族。</p>`);
}

async function applyConflictAction(button) {
  const card = button.closest(".conflict-card");
  const family = card.dataset.family;
  const client = card.querySelector("[data-conflict-client]").value;
  const skillId = card.querySelector("[data-conflict-skill]").value;
  const action = button.dataset.conflictAction;
  if (action === "prefer") {
    await runAction(`将 ${skillId} 设为优先`, () => postJson("/api/override/set", { client, conflict_family: family, skill_id: skillId }));
  } else if (action === "inherit") {
    await runAction(`恢复 ${family} 的继承策略`, () => postJson("/api/override/inherit", { client, conflict_family: family }));
  } else if (action === "disable") {
    await runAction(`禁用 ${family}`, () => postJson("/api/override/disable", { client, conflict_family: family }));
  }
  await refreshAll();
}

function renderReports() {
  const report = state.reports?.reports?.[state.reportId];
  if (!report) {
    $("#reportMeta").textContent = "还没有报告内容。";
    $("#reportRendered").innerHTML = "<p class=\"muted\">请先运行一次刷新或重新生成报告。</p>";
    $("#reportRaw").textContent = "";
    return;
  }
  $("#reportMeta").textContent = `${report.path} · ${report.updated_at || "尚未生成"}`;
  $("#reportRaw").textContent = report.content || "";
  $("#reportRendered").innerHTML = renderMarkdown(report.content || "");
  $("#reportRaw").classList.toggle("hidden", !state.reportRaw);
  $("#reportRendered").classList.toggle("hidden", state.reportRaw);
  $$(".report-tabs .pill").forEach((button) => button.classList.toggle("active", button.dataset.report === state.reportId));
}

function renderMarkdown(markdown) {
  const lines = markdown.split(/\r?\n/);
  const html = [];
  const slug = (value) =>
    String(value || "")
      .toLowerCase()
      .replace(/[^a-z0-9\u4e00-\u9fa5]+/g, "-")
      .replace(/^-+|-+$/g, "") || "section";
  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i];
    if (!line.trim()) {
      continue;
    }
    if (line.startsWith("# ")) {
      html.push(`<h1 id="${escapeHtml(`report-${slug(line.slice(2))}`)}">${escapeHtml(line.slice(2))}</h1>`);
      continue;
    }
    if (line.startsWith("## ")) {
      html.push(`<h2 id="${escapeHtml(`report-${slug(line.slice(3))}`)}">${escapeHtml(line.slice(3))}</h2>`);
      continue;
    }
    if (line.startsWith("- ")) {
      html.push(`<p>${escapeHtml(line.slice(2))}</p>`);
      continue;
    }
    if (line.includes("|") && lines[i + 1]?.includes("---")) {
      const headers = line.split("|").slice(1, -1).map((cell) => cell.trim());
      i += 2;
      const rows = [];
      while (i < lines.length && lines[i].includes("|")) {
        rows.push(lines[i].split("|").slice(1, -1).map((cell) => cell.trim()));
        i += 1;
      }
      i -= 1;
      html.push("<div class=\"table-wrap\"><table><thead><tr>");
      headers.forEach((header) => html.push(`<th>${escapeHtml(header)}</th>`));
      html.push("</tr></thead><tbody>");
      rows.forEach((row) => {
        html.push("<tr>");
        row.forEach((cell) => html.push(`<td>${escapeHtml(cell).replace(/`([^`]+)`/g, "<code>$1</code>")}</td>`));
        html.push("</tr>");
      });
      html.push("</tbody></table></div>");
      continue;
    }
    html.push(`<p>${escapeHtml(line).replace(/`([^`]+)`/g, "<code>$1</code>")}</p>`);
  }
  return html.join("");
}

function openReportForClient(client) {
  state.reportId = "inventory";
  switchView("reports");
  renderReports();
  const target = document.getElementById(`report-${String(client || "").toLowerCase()}`);
  if (target) {
    target.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

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

function bindEvents() {
  $("#refreshAll").addEventListener("click", handleAsync(() => runAction("刷新", refreshAll)));
  $("#previewAll").addEventListener(
    "click",
    handleAsync(async () => {
      const result = await runAction("全部预览", async () => {
        state.status = await api("/api/status");
        return Promise.all(Object.keys(state.status.clients).map((client) => api(`/api/clients/${encodeURIComponent(client)}/preview`)));
      });
      $("#clientOutput").textContent = asJson(result);
      await refreshAll();
    }),
  );
  $("#runQuickAction").addEventListener(
    "click",
    handleAsync(async () => {
      if (!state.selectedQuickActionId) {
        toast("请先选择一个快捷动作。");
        return;
      }
      await runQuickAction(state.selectedQuickActionId);
    }),
  );
  $("#copyQuickActionCommand").addEventListener("click", async () => {
    const action = selectedQuickAction();
    if (!action?.command_preview) {
      toast("当前没有可复制的命令。");
      return;
    }
    try {
      await navigator.clipboard.writeText(action.command_preview);
      toast("命令已复制。");
    } catch (_error) {
      toast("复制失败，请手动复制命令预览。");
    }
  });
  $("#showSkillMatrix").addEventListener("click", () => {
    state.skillManagerMode = "matrix";
    syncHash();
    renderSkillManager();
  });
  $("#showSkillInstances").addEventListener("click", () => {
    state.skillManagerMode = "instances";
    syncHash();
    renderSkillManager();
  });
  $("#syncUseSelectedFamilies").addEventListener("click", () => {
    useSelectedFamiliesForSync();
    syncHash();
  });
  $("#syncClearSelection").addEventListener("click", () => {
    state.syncCenter.preview = null;
    state.syncCenter.applyResult = null;
    renderSyncCenter();
  });
  $("#syncSourceClient").addEventListener("change", (event) => {
    state.syncCenter.sourceClient = event.target.value;
    state.syncCenter.targetClients = (state.syncCenter.targetClients || []).filter((client) => client !== state.syncCenter.sourceClient);
    state.syncCenter.preview = null;
    state.syncCenter.applyResult = null;
    renderSyncCenter();
    syncHash();
  });
  $("#syncIncludeSkills").addEventListener("change", (event) => {
    state.syncCenter.includeSkills = Boolean(event.target.checked);
    state.syncCenter.preview = null;
    state.syncCenter.applyResult = null;
    renderSyncCenter();
    syncHash();
  });
  $("#syncIncludeMcp").addEventListener("change", (event) => {
    state.syncCenter.includeMcp = Boolean(event.target.checked);
    state.syncCenter.preview = null;
    state.syncCenter.applyResult = null;
    renderSyncCenter();
    syncHash();
  });
  $("#syncScopeAll").addEventListener("click", () => {
    state.syncCenter.scope = "all_published";
    state.syncCenter.preview = null;
    state.syncCenter.applyResult = null;
    renderSyncCenter();
    syncHash();
  });
  $("#syncScopeSelected").addEventListener("click", () => {
    state.syncCenter.scope = "selected";
    state.syncCenter.preview = null;
    state.syncCenter.applyResult = null;
    renderSyncCenter();
    syncHash();
  });
  $("#previewSync").addEventListener("click", handleAsync(previewSyncCenterAction));
  $("#applySync").addEventListener("click", handleAsync(applySyncCenterAction));
  $("#refreshSkillManager").addEventListener("click", handleAsync(() => refreshSkillManagerView(true)));
  $("#reloadSkillMatrix").addEventListener(
    "click",
    handleAsync(async () => {
      readMatrixFiltersFromDom();
      syncHash();
      await refreshSkillManagerView(true);
    }),
  );
  $("#clearMatrixFilters").addEventListener(
    "click",
    handleAsync(async () => {
      state.matrixQuery = { ...DEFAULT_MATRIX_QUERY };
      state.selectedMatrixClient = null;
      syncHash();
      await refreshSkillManagerView(true);
    }),
  );
  $("#matrixSearch").addEventListener("input", () => {
    window.clearTimeout(matrixSearchTimer);
    matrixSearchTimer = window.setTimeout(
      handleAsync(async () => {
        readMatrixFiltersFromDom();
        syncHash();
        await refreshSkillManagerView(true);
      }),
      220,
    );
  });
  $("#matrixSearch").addEventListener(
    "keydown",
    handleAsync(async (event) => {
      if (event.key === "Enter") {
        window.clearTimeout(matrixSearchTimer);
        readMatrixFiltersFromDom();
        syncHash();
        await refreshSkillManagerView(true);
      }
    }),
  );
  $("#matrixClientFilter").addEventListener("change", handleAsync(async () => {
    readMatrixFiltersFromDom();
    syncHash();
    await refreshSkillManagerView(true);
  }));
  $("#matrixAnomalyFilter").addEventListener("change", handleAsync(async () => {
    readMatrixFiltersFromDom();
    syncHash();
    await refreshSkillManagerView(true);
  }));
  $("#matrixSourceScopeFilter").addEventListener("change", handleAsync(async () => {
    readMatrixFiltersFromDom();
    syncHash();
    await refreshSkillManagerView(true);
  }));
  $("#matrixOnlyAnomalies").addEventListener("click", () => {
    state.matrixQuery.only_anomalies = state.matrixQuery.only_anomalies ? "" : "1";
    syncHash();
    renderSkillManager();
  });
  $("#matrixOnlyDuplicates").addEventListener("click", () => {
    state.matrixQuery.only_duplicates = state.matrixQuery.only_duplicates ? "" : "1";
    syncHash();
    renderSkillManager();
  });
  $("#scanEnabledSources").addEventListener(
    "click",
    handleAsync(async () => {
      await runAction("扫描已启用扫描源", () => postJson("/api/scan-sources/scan", {}));
      await refreshAll();
    }),
  );
  $("#refreshScanSources").addEventListener("click", handleAsync(() => refreshSkillManagerView(true)));
  $("#refreshDiscovery").addEventListener("click", handleAsync(() => refreshSkillManagerView(true)));
  $("#scanSourceForm").addEventListener("submit", handleAsync(submitScanSourceForm));
  $("#scanSourceRole").addEventListener("change", updateScanSourceClientState);
  $("#clearMatrixDetail").addEventListener("click", clearMatrixDetail);
  $("#clientSelect").addEventListener("change", (event) => {
    state.currentClient = event.target.value;
    renderClientDetail();
    renderBackups();
    syncHash();
  });
  $("#inventoryClientSelect").addEventListener(
    "change",
    handleAsync(async (event) => {
      state.currentClient = event.target.value;
      await openInventoryClient(state.currentClient);
    }),
  );
  $("#mcpClientSelect").addEventListener(
    "change",
    handleAsync(async (event) => {
      state.currentClient = event.target.value;
      await openMcpClient(state.currentClient);
    }),
  );
  $("#refreshInventory").addEventListener("click", handleAsync(refreshInventoryView));
  $("#refreshMcp").addEventListener("click", handleAsync(refreshMcpView));
  $("#openInventoryFromClient").addEventListener(
    "click",
    handleAsync(async () => {
      if (!state.currentClient) {
        toast("当前没有选中的客户端。");
        return;
      }
      await openInventoryClient(state.currentClient, { force: true });
    }),
  );
  $("#exportInventoryJson").addEventListener("click", handleAsync(() => exportInventory("json")));
  $("#exportInventoryMarkdown").addEventListener("click", handleAsync(() => exportInventory("markdown")));
  $("#exportInventoryAllJson").addEventListener("click", handleAsync(() => exportInventory("json", null)));
  $("#inventoryDiffTypeFilter").addEventListener("change", (event) => {
    state.inventoryFilters.diffType = event.target.value;
    renderInventory();
  });
  $("#inventoryScopeFilter").addEventListener("change", (event) => {
    state.inventoryFilters.scope = event.target.value;
    renderInventory();
  });
  $("#inventorySourceClientFilter").addEventListener("input", (event) => {
    state.inventoryFilters.sourceClient = event.target.value.trim();
    renderInventory();
  });
  $("#runMcpDedupe").addEventListener(
    "click",
    handleAsync(async () => {
      if (state.currentClient !== "codex") {
        toast("一键去重当前只支持 codex。");
        return;
      }
      const result = await runAction("Codex MCP 去重", () => postJson("/api/mcp/clients/codex/dedupe"));
      $("#mcpDiffOutput").textContent = result.diff?.text || asJson(result);
      await refreshAll();
    }),
  );
  $("#mcpForm").addEventListener("submit", handleAsync(submitMcpForm));
  $("#mcpFormReset").addEventListener("click", resetMcpForm);
  $("#runCleanupScan").addEventListener("click", handleAsync(cleanupScan));
  $("#refreshCleanup").addEventListener("click", handleAsync(refreshCleanupView));
  $("#exportCleanup").addEventListener(
    "click",
    handleAsync(async () => {
      const result = await runAction("导出清理候选项", () => api("/api/cleanup/export"));
      $("#cleanupOutput").textContent = asJson(result);
    }),
  );
  $("#cleanupLabelFilter").addEventListener("change", (event) => {
    state.cleanupLabelFilter = event.target.value;
    renderCleanup();
  });
  $("#forcePublish").addEventListener("change", updatePublishButton);
  $("#runPreview").addEventListener("click", handleAsync(loadPreview));
  $("#runDiff").addEventListener("click", handleAsync(loadDiff));
  $("#runDoctor").addEventListener("click", handleAsync(loadDoctor));
  $("#runPublish").addEventListener("click", handleAsync(publishClient));
  $("#loadBackups").addEventListener("click", handleAsync(loadBackups));
  $("#reloadSkills").addEventListener("click", handleAsync(loadSkillsFromFilters));
  $("#clearSkillFilters").addEventListener("click", handleAsync(resetSkillFilters));
  $("#skillSearch").addEventListener(
    "keydown",
    handleAsync(async (event) => {
      if (event.key === "Enter") {
        await loadSkillsFromFilters();
      }
    }),
  );
  $("#skillSortBy").addEventListener(
    "change",
    handleAsync(async () => {
      readSkillFiltersFromDom();
      state.skillQuery.page = 1;
      syncHash();
      state.skills = await api(buildSkillsPath());
      renderSkills();
    }),
  );
  $("#skillPageSize").addEventListener(
    "change",
    handleAsync(async () => {
      readSkillFiltersFromDom();
      state.skillQuery.page = 1;
      syncHash();
      state.skills = await api(buildSkillsPath());
      renderSkills();
    }),
  );
  $("#toggleSkillSortDir").addEventListener(
    "click",
    handleAsync(async () => {
      state.skillQuery.sort_dir = state.skillQuery.sort_dir === "desc" ? "asc" : "desc";
      renderSkillsFilters();
      syncHash();
      state.skills = await api(buildSkillsPath());
      renderSkills();
    }),
  );
  $("#clearSkillDetail").addEventListener("click", clearSkillDetail);
  $("#githubImportForm").addEventListener("submit", handleAsync(submitGithubImport));
  $("#zipImportForm").addEventListener("submit", handleAsync(submitZipImport));
  $("#regenerateReports").addEventListener(
    "click",
    handleAsync(async () => {
      state.reports = await runAction("重新生成报告", () => postJson("/api/report/regenerate"));
      renderReports();
    }),
  );
  $("#toggleRawReport").addEventListener("click", () => {
    state.reportRaw = !state.reportRaw;
    renderReports();
  });
  $("#clearLog").addEventListener("click", () => {
    $("#eventLog").innerHTML = "";
  });
  $$(".nav-link").forEach((button) =>
    button.addEventListener(
      "click",
      handleAsync(async () => {
        switchView(button.dataset.view);
        renderSkillsFilters();
        renderSkills();
        renderSkillDetail();
        renderConflicts();
        if (button.dataset.view === "inventory" && state.serviceOnline !== false) {
          await loadInventorySummary(false);
          if (state.currentClient) {
            await loadInventoryDetail(state.currentClient, false);
          }
          renderInventory();
        }
        if (button.dataset.view === "mcp" && state.serviceOnline !== false) {
          await loadMcpSummary(false);
          if (state.currentClient) {
            await loadMcpDetail(state.currentClient, false);
          }
          renderMcp();
        }
        if (button.dataset.view === "cleanup" && state.serviceOnline !== false) {
          await loadCleanup(false);
          renderCleanup();
        }
        if (button.dataset.view === "skills" && state.serviceOnline !== false) {
          await refreshSkillManagerView(false);
          if (state.skillManagerMode === "instances") {
            state.skills = await api(buildSkillsPath());
            renderSkills();
            renderSkillDetail();
          }
        }
        if (button.dataset.view === "sync" && state.serviceOnline !== false) {
          await refreshSkillManagerView(false);
          renderSyncCenter();
        }
      }),
    ),
  );
  $$(".report-tabs .pill").forEach((button) =>
    button.addEventListener("click", () => {
      state.reportId = button.dataset.report;
      renderReports();
    }),
  );

  document.addEventListener(
    "click",
    handleAsync(async (event) => {
      const runActionButton = event.target.closest("[data-run-action]");
      if (runActionButton) {
        await runQuickAction(runActionButton.dataset.runAction);
        return;
      }

      const clearMatrixSelection = event.target.closest("[data-clear-matrix-selection]");
      if (clearMatrixSelection) {
        clearMatrixSelections();
        renderSkillManager();
        syncHash();
        return;
      }

      const openSyncCenter = event.target.closest("[data-open-sync-center]");
      if (openSyncCenter) {
        useSelectedFamiliesForSync();
        syncHash();
        return;
      }

      const batchDisable = event.target.closest("[data-batch-disable]");
      if (batchDisable) {
        await runMatrixBatchAction("disable");
        return;
      }

      const batchInherit = event.target.closest("[data-batch-inherit]");
      if (batchInherit) {
        await runMatrixBatchAction("inherit");
        return;
      }

      const openMatrixFamily = event.target.closest("[data-open-matrix-family]");
      if (openMatrixFamily) {
        const family = openMatrixFamily.dataset.openMatrixFamily;
        const client = openMatrixFamily.dataset.openMatrixClient || null;
        if (client) {
          if (state.selectedMatrixFamily === family && state.selectedMatrixClient === client) {
            state.selectedMatrixClient = null;
          } else {
            state.selectedMatrixFamily = family;
            state.selectedMatrixClient = client;
            state.currentClient = client;
          }
        } else if (state.selectedMatrixFamily === family && !state.selectedMatrixClient) {
          state.selectedMatrixFamily = null;
        } else {
          state.selectedMatrixFamily = family;
          state.selectedMatrixClient = null;
        }
        syncHash();
        renderSkillMatrix();
        renderMatrixDrawer();
        if (state.selectedMatrixFamily) {
          await loadMatrixFamilyInstances(state.selectedMatrixFamily);
          renderSkillMatrix();
          renderMatrixDrawer();
        }
        return;
      }

      const selectAction = event.target.closest("[data-select-action]");
      if (selectAction) {
        state.selectedQuickActionId = selectAction.dataset.selectAction;
        renderDashboard();
        return;
      }

      const openClient = event.target.closest("[data-open-client]");
      if (openClient) {
        state.currentClient = openClient.dataset.openClient;
        switchView(openClient.dataset.openClientView || "clients");
        renderClientOptions();
        renderClientDetail();
        if (state.currentView === "inventory" && state.serviceOnline !== false) {
          await openInventoryClient(state.currentClient);
        } else if (state.currentView === "mcp" && state.serviceOnline !== false) {
          await openMcpClient(state.currentClient);
        }
        return;
      }

      const matrixExplain = event.target.closest("[data-matrix-explain]");
      if (matrixExplain) {
        state.selectedMatrixClient = matrixExplain.dataset.matrixExplain || null;
        syncHash();
        renderMatrixDrawer();
        $("#matrixInspectorPanel")?.scrollIntoView({ behavior: "smooth", block: "start" });
        return;
      }

      const matrixPrefer = event.target.closest("[data-matrix-prefer]");
      if (matrixPrefer) {
        const client = matrixPrefer.dataset.matrixPrefer;
        const skillId = matrixPrefer.dataset.matrixSkill;
        await runAction(`将 ${client} 的 ${skillId} 设为优先`, () => postJson("/api/override/set", { client, conflict_family: state.selectedMatrixFamily, skill_id: skillId }));
        await refreshAll();
        return;
      }

      const matrixInherit = event.target.closest("[data-matrix-inherit]");
      if (matrixInherit) {
        const client = matrixInherit.dataset.matrixInherit;
        await runAction(`恢复 ${client} 的继承策略`, () => postJson("/api/override/inherit", { client, conflict_family: state.selectedMatrixFamily }));
        await refreshAll();
        return;
      }

      const matrixDisable = event.target.closest("[data-matrix-disable]");
      if (matrixDisable) {
        const client = matrixDisable.dataset.matrixDisable;
        await runAction(`禁用 ${client} 的当前逻辑 skill`, () => postJson("/api/override/disable", { client, conflict_family: state.selectedMatrixFamily }));
        await refreshAll();
        return;
      }

      const scanSourceRun = event.target.closest("[data-scan-source-run]");
      if (scanSourceRun) {
        await runAction("扫描指定扫描源", () => postJson("/api/scan-sources/scan", { id: scanSourceRun.dataset.scanSourceRun }));
        await refreshAll();
        return;
      }

      const scanSourceToggle = event.target.closest("[data-scan-source-toggle]");
      if (scanSourceToggle) {
        const id = scanSourceToggle.dataset.scanSourceToggle;
        const enabled = scanSourceToggle.dataset.enabled === "true";
        const path = enabled ? "/api/scan-sources/update" : "/api/scan-sources/update";
        await runAction(enabled ? "停用扫描源" : "启用扫描源", () => postJson(path, { id, enabled: !enabled }));
        await refreshSkillManagerView(true);
        return;
      }

      const toggleScanFilter = event.target.closest("[data-toggle-scan-filter]");
      if (toggleScanFilter) {
        const key = toggleScanFilter.dataset.toggleScanFilter;
        state.scanSourceFilters[key] = !state.scanSourceFilters[key];
        renderScanSources();
        return;
      }

      const scanSourceRemove = event.target.closest("[data-scan-source-remove]");
      if (scanSourceRemove) {
        await runAction("移除扫描源", () => postJson("/api/scan-sources/remove", { id: scanSourceRemove.dataset.scanSourceRemove }));
        await refreshSkillManagerView(true);
        return;
      }

      const discoveryGroup = event.target.closest("[data-discovery-group]");
      if (discoveryGroup) {
        state.selectedDiscoveryGroup = discoveryGroup.dataset.discoveryGroup;
        if (state.serviceOnline !== false) {
          await loadDiscoveryGroup(state.selectedDiscoveryGroup, false);
        }
        renderDiscoverySummary();
        return;
      }

      const exportDiscoveryGroup = event.target.closest("[data-export-discovery-group]");
      if (exportDiscoveryGroup) {
        const group = exportDiscoveryGroup.dataset.exportDiscoveryGroup;
        const payload = state.discoveryDetails[group] || (await loadDiscoveryGroup(group, false));
        downloadContent(`discovery-${group}.json`, asJson(payload), "application/json;charset=utf-8");
        return;
      }

      const openInventory = event.target.closest("[data-open-inventory-client]");
      if (openInventory) {
        await openInventoryClient(openInventory.dataset.openInventoryClient);
        return;
      }

      const openMcp = event.target.closest("[data-open-mcp-client]");
      if (openMcp) {
        await openMcpClient(openMcp.dataset.openMcpClient);
        return;
      }

      const copyText = event.target.closest("[data-copy-text]");
      if (copyText) {
        await navigator.clipboard.writeText(copyText.dataset.copyText || "");
        toast("路径已复制。");
        return;
      }

      const openReportClient = event.target.closest("[data-open-report-client]");
      if (openReportClient) {
        openReportForClient(openReportClient.dataset.openReportClient);
        return;
      }

      const clearFamily = event.target.closest("[data-clear-family]");
      if (clearFamily) {
        state.skillQuery.family = "";
        state.skillQuery.page = 1;
        syncHash();
        await loadSkillsFromFilters();
        return;
      }

      const openSkill = event.target.closest("[data-open-skill]");
      if (openSkill) {
        const family = openSkill.dataset.openSkillFamily || "";
        await openSkillDetail(openSkill.dataset.openSkill, { switchToSkills: Boolean(family), family });
        return;
      }

      const filterFamily = event.target.closest("[data-filter-family]");
      if (filterFamily) {
        state.skillQuery.family = filterFamily.dataset.filterFamily;
        state.skillQuery.page = 1;
        syncHash();
        await loadSkillsFromFilters();
        return;
      }

      const jumpConflict = event.target.closest("[data-open-conflict]");
      if (jumpConflict) {
        await openConflictFamily(jumpConflict.dataset.openConflict);
        return;
      }

      const clearConflict = event.target.closest("[data-clear-conflict-family]");
      if (clearConflict) {
        await clearConflictFamilyFilter();
        return;
      }

      const skillPage = event.target.closest("[data-skill-page]");
      if (skillPage) {
        state.skillQuery.page = Math.max(parseIntSafe(skillPage.dataset.skillPage, state.skillQuery.page), 1);
        syncHash();
        state.skills = await api(buildSkillsPath());
        renderSkills();
        return;
      }

      const sortButton = event.target.closest("[data-sort-by]");
      if (sortButton) {
        const nextSort = sortButton.dataset.sortBy;
        if (state.skillQuery.sort_by === nextSort) {
          state.skillQuery.sort_dir = state.skillQuery.sort_dir === "desc" ? "asc" : "desc";
        } else {
          state.skillQuery.sort_by = nextSort;
          state.skillQuery.sort_dir = nextSort === "imported_at" || nextSort === "last_seen_at" ? "desc" : "asc";
        }
        state.skillQuery.page = 1;
        renderSkillsFilters();
        syncHash();
        state.skills = await api(buildSkillsPath());
        renderSkills();
        return;
      }

      const clearDetail = event.target.closest("[data-clear-skill-detail]");
      if (clearDetail) {
        clearSkillDetail();
        return;
      }

      const skillAction = event.target.closest("[data-skill-action]");
      if (skillAction) {
        if (state.serviceOnline === false) {
          toast("服务当前离线，不能修改技能状态。");
          return;
        }
        const skillId = skillAction.dataset.skillId;
        const action = skillAction.dataset.skillAction;
        await runAction(`${action === "disable" ? "禁用" : "启用"} ${skillId}`, () => postJson(`/api/skills/${encodeURIComponent(skillId)}/${action}`));
        await refreshAll();
        return;
      }

      const editMcpServer = event.target.closest("[data-edit-mcp-server]");
      if (editMcpServer) {
        const detail = state.mcpDetails[state.currentClient];
        const server = (detail?.servers || []).find((item) => item.name === editMcpServer.dataset.editMcpServer);
        if (server) {
          $("#mcpOriginalName").value = server.name || "";
          $("#mcpName").value = server.name || "";
          $("#mcpCommand").value = server.command || "";
          $("#mcpArgs").value = (server.args || []).join("\n");
          $("#mcpEnabled").checked = Boolean(server.enabled);
          $("#mcpFormTitle").textContent = `编辑 ${server.name}`;
        }
        return;
      }

      const mcpToggle = event.target.closest("[data-mcp-toggle]");
      if (mcpToggle) {
        const serverName = mcpToggle.dataset.mcpToggle;
        const enabled = mcpToggle.dataset.mcpEnabled === "true";
        const path = `/api/mcp/clients/${encodeURIComponent(state.currentClient)}/${enabled ? "disable" : "enable"}`;
        const result = await runAction(`${enabled ? "禁用" : "启用"} MCP ${serverName}`, () => postJson(path, { server_name: serverName }));
        $("#mcpDiffOutput").textContent = result.diff?.text || asJson(result);
        await refreshAll();
        return;
      }

      const mcpRemove = event.target.closest("[data-mcp-remove]");
      if (mcpRemove) {
        const serverName = mcpRemove.dataset.mcpRemove;
        const result = await runAction(`删除 MCP ${serverName}`, () => postJson(`/api/mcp/clients/${encodeURIComponent(state.currentClient)}/remove`, { server_name: serverName }));
        $("#mcpDiffOutput").textContent = result.diff?.text || asJson(result);
        await refreshAll();
        return;
      }

      const cleanupMark = event.target.closest("[data-cleanup-mark]");
      if (cleanupMark) {
        const skillId = cleanupMark.dataset.cleanupMark;
        const label = cleanupMark.dataset.cleanupLabel;
        await runAction(`标记 ${skillId} 为 ${label}`, () => postJson("/api/cleanup/mark", { skill_id: skillId, label }));
        await refreshCleanupView();
        return;
      }

      const inspect = event.target.closest("[data-inspect-backup]");
      if (inspect) {
        await inspectBackup(inspect.dataset.inspectBackup);
        return;
      }

      const rollback = event.target.closest("[data-rollback-backup]");
      if (rollback) {
        await rollbackBackup(rollback.dataset.rollbackBackup);
        return;
      }

      const conflictButton = event.target.closest("[data-conflict-action]");
      if (conflictButton) {
        await applyConflictAction(conflictButton);
        return;
      }
    }),
  );

  document.addEventListener(
    "change",
    handleAsync(async (event) => {
      const selectFamily = event.target.closest("[data-select-matrix-family]");
      if (selectFamily) {
        toggleMatrixFamilySelection(selectFamily.dataset.selectMatrixFamily);
        renderSkillManager();
        syncHash();
        return;
      }

      const batchClient = event.target.closest("[data-matrix-batch-client]");
      if (batchClient) {
        const client = batchClient.dataset.matrixBatchClient;
        const next = new Set(state.matrixBatchClients || []);
        if (event.target.checked) {
          next.add(client);
        } else {
          next.delete(client);
        }
        state.matrixBatchClients = Array.from(next).sort();
        renderSkillManager();
        return;
      }

      const syncTarget = event.target.closest("[data-sync-target]");
      if (syncTarget) {
        const client = syncTarget.dataset.syncTarget;
        const next = new Set(state.syncCenter.targetClients || []);
        if (event.target.checked) {
          next.add(client);
        } else {
          next.delete(client);
        }
        state.syncCenter.targetClients = Array.from(next).sort();
        state.syncCenter.preview = null;
        state.syncCenter.applyResult = null;
        renderSyncCenter();
        syncHash();
      }
    }),
  );

  window.addEventListener(
    "hashchange",
    handleAsync(async () => {
      if (hashSyncing) {
        return;
      }
      applyHashState();
      if (state.serviceOnline === false) {
        renderAll();
        return;
      }
      await refreshAll();
    }),
  );
}

async function init() {
  applyHashState();
  bindEvents();
  renderAll();
  const online = await checkHealth(true, false);
  if (online) {
    await refreshAll();
  }
}

setInterval(() => {
  checkHealth(true, true);
}, 10000);

window.addEventListener("focus", () => {
  checkHealth(true, true);
});

init().catch((error) => {
  toast(`初始加载失败：${error.message}`);
  logEvent(`初始加载失败：${error.message}`);
});
