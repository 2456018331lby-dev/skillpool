# SkillPool 中文使用指南

## 1. 打开与关闭

### 一键打开

```powershell
%USERPROFILE%\.skill-pool\open-console.cmd
```

### 查看状态

```powershell
%USERPROFILE%\.skill-pool\console-status.cmd
```

### 一键关闭

```powershell
%USERPROFILE%\.skill-pool\stop-console.cmd
```

### 手动启动

```powershell
cd %USERPROFILE%\.skill-pool
python skillpool.py serve --host 127.0.0.1 --port 8765 --open
```

## 2. 页面总览

### 技能池

这是默认主入口，也是日常维护的主界面。

你会看到：

- 逻辑 skill / family 矩阵
- 六个客户端状态列
- discovery 异常摘要
- 扫描源管理区
- 当前逻辑 skill 详情抽屉

你可以做：

- 搜索和筛选逻辑 skill
- 展开实例层
- 直接对单客户端执行 `优先 / 继承 / 禁用`
- 勾选多个 family
- 批量禁用
- 批量恢复继承
- 将已选 family 送入同步中心

### 同步中心

同步中心用于把“一个源客户端当前的已发布模板”同步到其他客户端。

工作流：

1. 选源客户端
2. 选目标客户端
3. 选同步范围：
   - Skill
   - MCP
   - 两者
4. 选同步集合：
   - 全部已发布 family
   - 当前矩阵已选 family
5. 先运行预览
6. 再应用同步

Skill 同步语义：

- 不是复制 live 目录
- 而是提取源客户端当前 `published family -> preferred skill_id / disabled family`

MCP 同步语义：

- 只对 `codex / claude / hermes` 生效
- 首版是 `merge`
- 不删除目标端独有 server

### 客户端

高风险动作都在这里：

- `preview`
- `diff`
- `doctor --deep`
- `publish`
- `rollback`

建议顺序：

1. 先预览
2. 再深度体检
3. 没问题再发布
4. 回滚前先 inspect backup

### MCP

这里只管理配置，不管理运行态进程。

支持：

- 查看 server 列表
- 启用 / 禁用
- 新增 / 更新 / 删除
- Codex 一键去重

不支持：

- 启停 MCP 进程
- 端口探活
- 运行态日志监控

### 盘点

盘点页专门回答这些问题：

- 这个客户端 live 到底读哪个目录
- 为什么 SkillPool 看到几百个，别的工具只显示几十个
- 哪些 skill 是 live 里有、池里没有
- 哪些 skill 是池里有、客户端没发布
- MCP 配置到底来自哪个文件

### 清理

当前是非破坏性工作流：

- 扫描候选项
- 标记 `candidate / keep / ignore`
- 导出 Markdown / JSON

不会删除文件。

## 3. 最常用 CLI

### 状态与报告

```powershell
python skillpool.py status
python skillpool.py report
python skillpool.py inventory
python skillpool.py inventory codex
python skillpool.py inventory --all
```

### 发布链路

```powershell
python skillpool.py preview hermes
python skillpool.py diff hermes
python skillpool.py doctor --deep hermes
python skillpool.py publish hermes
python skillpool.py rollback list hermes
python skillpool.py rollback inspect hermes <backup_id>
python skillpool.py rollback hermes --latest
```

### MCP

```powershell
python skillpool.py mcp list codex
python skillpool.py mcp diff codex
python skillpool.py mcp enable codex memory
python skillpool.py mcp disable codex memory
python skillpool.py mcp add codex my-server --command uvx --arg mcp-time
python skillpool.py mcp update codex my-server --enabled false
python skillpool.py mcp remove codex my-server
python skillpool.py mcp dedupe codex
```

### 同步中心

```powershell
python skillpool.py sync inspect codex
python skillpool.py sync preview codex --to hermes --skills --mcp
python skillpool.py sync apply codex --to hermes --to claude --skills --mcp
python skillpool.py sync preview codex --to hermes --family my-family --skills
```

### 批量 family 动作

```powershell
python skillpool.py batch disable --clients hermes --clients claude --family my-family
python skillpool.py batch inherit --clients hermes --clients claude --family my-family
```

### 扫描源与 discovery

```powershell
python skillpool.py scan-sources list
python skillpool.py scan-sources add %USERPROFILE%\.agents\skills --role global_source --kind stable
python skillpool.py scan-sources scan
python skillpool.py discovery
python skillpool.py discovery summary
python skillpool.py discovery details transient_only --limit 20
python skillpool.py discovery refresh --summary
```

## 4. 使用建议

### 想统一多个客户端的 skill 策略

推荐做法：

1. 在矩阵页勾选要同步的 family
2. 点“同步已选”
3. 在同步中心确认源客户端和目标客户端
4. 先预览
5. 看清楚 `未解决 family / 目标不可见 / MCP 不支持同步`
6. 再应用

### 想快速禁用一批 family

推荐做法：

1. 在矩阵页勾选多个 family
2. 勾选目标客户端
3. 点“批量禁用”

### 想看为什么某个 skill 没被接管

推荐顺序：

1. 先看矩阵状态
2. 再看实例层
3. 再进盘点页看 `live_only / pool_only / source_mismatch`
4. 必要时看 `INVENTORY.md`

## 5. 重要说明

- `openclaw / qclaw / autoclaw` 的 MCP 当前仍然是 inventory-only
- discovery 和扫描源首页默认读缓存摘要，不会每次都全量重扫
- 真正重扫只会发生在你明确执行：
  - 刷新 discovery
  - 扫描已启用源
  - 仅扫描该源

## 6. 相关文档

- `README.md`
- `docs/OPERATIONS_MANUAL.zh-CN.md`
- `docs/MAINTAINER_GUIDE.zh-CN.md`
- `docs/MAINTENANCE_DOSSIER.zh-CN.md`
- `docs/SYNC_GUIDE.zh-CN.md`
- `docs/FEATURES.zh-CN.md`
