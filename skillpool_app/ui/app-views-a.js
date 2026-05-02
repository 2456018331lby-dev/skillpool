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

