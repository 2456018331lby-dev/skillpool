# SkillPool 运维操作手册

## 1. 日常值班入口

### 打开控制台

```powershell
open-console.cmd
```

### 查看服务状态

```powershell
console-status.cmd
```

### 关闭控制台

```powershell
stop-console.cmd
```

## 2. 推荐操作顺序

### 单客户端发布

1. `preview`
2. `doctor --deep`
3. `publish`
4. 必要时 `rollback inspect`
5. 必要时 `rollback`

### 跨客户端同步

1. 在矩阵页确认 family
2. 进入同步中心
3. `sync preview`
4. 确认没有 `blocked`
5. 再 `sync apply`

### MCP 配置变更

1. 先看 `mcp diff`
2. 再做启用 / 禁用 / 增删改
3. 对 codex 可先做 `mcp dedupe`

## 3. 常见操作

### 预览所有客户端

```powershell
python skillpool.py preview --all
```

### 深度体检

```powershell
python skillpool.py doctor --deep
python skillpool.py doctor --deep hermes
```

### 盘点所有客户端

```powershell
python skillpool.py inventory
python skillpool.py inventory --all
```

### 重新生成报告

```powershell
python skillpool.py report
```

### 清理候选扫描

```powershell
python skillpool.py cleanup scan
python skillpool.py cleanup list
python skillpool.py cleanup export
```

## 4. 同步中心运维规则

Skill 同步规则：

- 源模板来自源客户端当前 `published_skill_ids`
- 同步时只写客户端 override，不传播全局 `enabled_global`
- 目标端看不到同一个 `skill_id` 时：
  - 若能看到同族其他实例，记为 `未解决 family`
  - 若整个 family 不可见，记为 `目标不可见`

MCP 同步规则：

- 只对 `codex / claude / hermes` 可写
- 同步方式为 `merge`
- 新增和更新 source 的 root servers
- 不删除目标端独有 server

## 5. 风险判断

### 可以直接继续

- preview 状态为 `safe`
- doctor 结果为 `pass`
- sync preview 没有 `blocked_targets`

### 需要停下来看

- preview 为 `warning`
- discovery 有较多 `source_mismatch`
- 目标客户端有 `unresolved_family`

### 不要继续应用

- preview 为 `blocked`
- doctor 为 `fail`
- 同步中心明确提示目标客户端被阻断

## 6. 故障排查

### 页面按钮全部显示 Failed to fetch

先看服务有没有开：

```powershell
console-status.cmd
```

没开就：

```powershell
open-console.cmd
```

### 某个客户端发布被拒绝

先运行：

```powershell
python skillpool.py preview <client>
python skillpool.py doctor --deep <client>
```

### 同步中心无法应用

先看：

- 哪些目标是 `blocked`
- 哪些 family 是 `未解决`
- 哪些 MCP 是 `不支持同步`

## 7. 不要做的事

- 不要把 unsupported MCP 显示成 `0`
- 不要跳过 preview / backup / rollback 链路
- 不要把 SkillPool 变成 MCP 进程管理器
- 不要在没有说明的情况下直接改 live 源目录
