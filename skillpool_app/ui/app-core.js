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
