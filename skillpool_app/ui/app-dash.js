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

