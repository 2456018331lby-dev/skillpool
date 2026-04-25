# SkillPool 同步中心指南

## 1. 同步中心解决什么问题

同步中心解决的是：

- 某个客户端现在用得很好，想把它的 skill 决策同步到别的客户端
- 想把 `codex / claude / hermes` 的 MCP 配置作为模板同步
- 希望先看差异，再应用，而不是盲目覆盖

## 2. Skill 同步语义

Skill 同步不是复制 live 目录。

它会提取源客户端当前：

- `published family -> preferred skill_id`
- 显式 `disabled family`

然后对目标客户端按下面规则处理：

- 能看到同一个 `skill_id`
  - 写入 `prefer:<skill_id>`
- 只能看到同族但不是同一个 `skill_id`
  - 标记为 `未解决 family`
  - 不自动替换
- 完全看不到该 family
  - 标记为 `目标不可见`
- 源端显式禁用的 family
  - 目标端写入 `disabled`

## 3. MCP 同步语义

当前只支持：

- `codex`
- `claude`
- `hermes`

同步方式是 `merge`：

- source 有、target 没有：新增
- source 和 target 同名但命令 / 参数 / enabled 不同：更新
- target 独有：保留

不会做：

- 镜像删除
- 运行态启停

## 4. 推荐操作

### 同步全部已发布 family

```powershell
python skillpool.py sync preview codex --to hermes --skills --mcp
python skillpool.py sync apply codex --to hermes --skills --mcp
```

### 只同步部分 family

```powershell
python skillpool.py sync preview codex --to claude --family my-family --family another-family --skills
python skillpool.py sync apply codex --to claude --family my-family --family another-family --skills
```

### 先只看模板

```powershell
python skillpool.py sync inspect codex
```

## 5. 页面使用

在控制台里：

1. 先在矩阵页勾选 family，或者直接进入同步中心
2. 选源客户端
3. 勾选目标客户端
4. 选 Skill / MCP
5. 点击“预览同步”
6. 看每个目标的：
   - Skill 精确装载
   - 禁用传播
   - 未解决 family
   - 目标不可见
   - MCP 新增 / 更新 / 无变化
7. 没有 `blocked` 再应用

## 6. 常见结果解释

- `未解决 family`
  目标端能看到同族，但不是同一个 `skill_id`

- `目标不可见`
  目标端根本看不到这个 family

- `MCP 不支持同步`
  目标客户端当前不在可写 MCP 支持范围

- `已回滚`
  该目标客户端应用过程失败，已恢复到本次备份前状态
