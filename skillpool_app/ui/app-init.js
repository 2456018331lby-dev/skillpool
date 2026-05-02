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
