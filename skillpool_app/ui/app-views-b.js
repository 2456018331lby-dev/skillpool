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

