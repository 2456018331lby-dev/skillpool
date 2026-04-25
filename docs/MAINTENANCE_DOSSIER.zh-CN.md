# SkillPool 维护总手册

## 1. 这份文档是给谁看的

这份文档是给后续维护者、接手开发者、以及未来的 AI 代理看的。

目标不是介绍“怎么使用 SkillPool”，而是回答这些更关键的问题：

- SkillPool 现在到底做到什么程度了
- 它的真实边界是什么，哪些能力是刻意不做的
- 仓库和运行态目录分别放什么
- 真正的业务真源在哪
- 以后要改什么文件、先看什么命令、怎么验证、怎么发版
- 当前有哪些已知风险和历史背景，避免后来人重复踩坑

如果你是第一次接手这个项目，建议按下面顺序阅读：

1. 本文档
2. `README.md`
3. `docs/OPERATIONS_MANUAL.zh-CN.md`
4. `docs/MAINTAINER_GUIDE.zh-CN.md`
5. `docs/SYNC_GUIDE.zh-CN.md`

### 1.1 接手第一天怎么做

如果你刚接手这个仓库，建议先按下面顺序确认真实状态：

1. 看仓库状态：

```powershell
git status --short
git remote -v
git branch -vv
```

2. 看 SkillPool 当前状态：

```powershell
python skillpool.py status
python skillpool.py inventory
python skillpool.py discovery summary
```

3. 看 MCP 当前状态：

```powershell
python skillpool.py mcp list codex
python skillpool.py mcp list claude
python skillpool.py mcp list hermes
```

4. 起本地控制台做人工核对：

```powershell
open-console.cmd
```

5. 最后再决定要不要修改代码、状态或发布结果。

## 2. 项目定位

### 2.1 SkillPool 是什么

SkillPool 是一个本地优先、零依赖、中文优先的统一技能池总管。

它统一管理以下 6 个客户端的 skill 和部分 MCP 配置：

- `hermes`
- `openclaw`
- `qclaw`
- `autoclaw`
- `codex`
- `claude`

SkillPool 的核心思路不是“替代客户端”，而是作为这些客户端之上的统一总管，提供：

- 统一主池
- 统一扫描与纳管
- 可解释的 inventory / discovery
- 受保护的 preview / publish / rollback / doctor
- 跨客户端的模板同步
- 对受支持客户端的 MCP 配置管理

### 2.2 SkillPool 不是什么

SkillPool 当前明确不是：

- MCP 运行态进程管理器
- 远程多用户平台
- 带数据库、后台任务队列、守护进程的 Web 服务
- Electron 桌面应用
- Node / React / FastAPI 项目

这几个“不做”是有意选择，不是暂时没做。

## 3. 当前能力边界

### 3.1 Skill 管理

当前已经稳定可用：

- 统一导入与纳管
- 逻辑 skill / family 矩阵
- 原始实例视图
- 客户端 override
- 批量 family 禁用 / 恢复继承
- 同步中心把某个源客户端的已发布模板同步到其他客户端

### 3.2 发布链路

当前已经稳定可用：

- `preview`
- `diff`
- `doctor --deep`
- `publish`
- `backup`
- `rollback list / inspect / latest`

### 3.3 盘点与发现

当前已经稳定可用：

- `inventory`
- `inventory export`
- `discovery summary`
- `discovery details`
- `scan-sources`
- `SKILLS_INDEX / CONFLICTS / INVENTORY / CLEANUP_CANDIDATES`

### 3.4 MCP 管理

当前只对以下客户端开放可写 MCP 配置管理：

- `codex`
- `claude`
- `hermes`

以下客户端当前只能 inventory-only，不做写入：

- `openclaw`
- `qclaw`
- `autoclaw`

### 3.5 明确不支持的能力

- MCP 进程启动 / 停止 / 探活
- 端口监控
- 运行态日志总管
- 自动守护式 discovery 后台刷新
- 多用户并发协作后台

## 4. 仓库结构

### 4.1 源码仓库结构

当前源码仓库中最重要的目录与文件：

- `skillpool.py`
  顶层 CLI 入口

- `skillpool_app/core.py`
  唯一业务真源，几乎所有关键逻辑都在这里

- `skillpool_app/cli.py`
  CLI 命令分发

- `skillpool_app/web.py`
  HTTP API 和控制台静态页面出口

- `skillpool_app/ui/index.html`
  页面结构

- `skillpool_app/ui/app.js`
  前端状态、渲染、交互逻辑

- `skillpool_app/ui/styles.css`
  控制台视觉样式

- `tests/test_skillpool.py`
  当前主要回归测试集合

- `docs/`
  中文文档集合

- `.github/`
  GitHub issue / PR 模板

### 4.2 运行态目录结构

运行态目录在 `%USERPROFILE%\.skill-pool` 下生成，当前约定如下：

- `pool/skills/`
  SkillPool 主池，规范化后的单个 skill 目录

- `cache/imports/`
  GitHub / ZIP 导入缓存

- `publish/`
  每个客户端的发布快照与清单

- `backups/`
  发布与回滚备份

- `reports/`
  生成的人类可读报告

- `state/`
  业务状态文件

这些目录都属于本地运行态数据，不进 Git 仓库。

## 5. 关键状态文件

当前 `state/` 下的重要文件：

- `registry.json`
  Skill 注册表，是 Skill 元数据的核心状态源

- `clients.json`
  客户端配置、最近状态、发布清单状态

- `scan_sources.json`
  自定义扫描源库

- `discovery_cache.json`
  discovery 缓存摘要与详情分组缓存

- `cleanup_candidates.json`
  清理候选项状态

- `mcp_state.json`
  最近一次 MCP 变更的辅助状态

- `lock.json`
  发布 / 同步等操作锁

- `web-console.pid`
- `web-console.out.log`
- `web-console.err.log`
  控制台服务开关和日志

当前 `reports/` 下的重要文件：

- `SKILLS_INDEX.md`
- `CONFLICTS.md`
- `INVENTORY.md`
- `CLEANUP_CANDIDATES.md`
- `CLEANUP_CANDIDATES.json`

## 6. 业务真源和职责分层

### 6.1 后端职责

`skillpool_app/core.py` 是唯一业务真源。

所有这些逻辑都应该优先放在 `core.py`：

- skill 导入 / 纳管
- 客户端发布清单计算
- preview / publish / rollback / doctor
- inventory / discovery
- scan source 管理
- MCP 解析与写回
- sync center 预览和应用
- cleanup 候选扫描
- report 生成

### 6.2 CLI 职责

`skillpool_app/cli.py` 只做命令面解析和转发，不应承载业务逻辑。

### 6.3 Web 层职责

`skillpool_app/web.py` 只做：

- HTTP 路由
- 请求体解析
- 响应包装
- 静态资源提供

不应把业务规则写死在 Web 层。

### 6.4 前端职责

`skillpool_app/ui/app.js` 当前负责：

- 全局前端状态
- 视图切换
- 矩阵渲染
- 扫描源和 discovery 渲染
- 同步中心交互
- MCP 页面交互
- 批量动作和动作按钮事件

如果前端继续变复杂，优先做函数级拆分，不引入新框架。

## 7. 当前主工作流

### 7.1 单客户端安全发布

推荐顺序：

1. `preview`
2. `doctor --deep`
3. `publish`
4. 必要时 `rollback inspect`
5. 必要时 `rollback`

### 7.2 扫描与发现

推荐顺序：

1. 看矩阵和 inventory
2. 看 `discovery summary`
3. 需要时再看 `discovery details`
4. 明确需要时再执行扫描源刷新

当前 discovery 设计是：

- 首页读缓存摘要
- 分组详情按需加载
- 不在每次首屏重扫所有扫描源

### 7.3 同步中心

Skill 同步逻辑：

- 从源客户端当前 `published_skill_ids` 提取 `family -> preferred skill_id`
- 提取显式 `disabled family`
- 目标客户端按以下规则处理：
  - 同一个 `skill_id` 可见：写 `prefer:<skill_id>`
  - 只有同族其他实例：记为 `未解决 family`
  - family 完全不可见：记为 `目标不可见`

MCP 同步逻辑：

- 当前只支持 `codex / claude / hermes`
- 模式固定为 `merge`
- 新增 / 更新 source 的 root servers
- 不删除目标端独有项

### 7.4 MCP 管理

当前 MCP 页面能做：

- 列出 server
- 启用 / 禁用
- 新增 / 更新 / 删除
- Codex 一键去重

当前 MCP 页面不能做：

- 进程管理
- 运行态健康检查

### 7.5 GitHub 同步与发版

当前仓库已经公开发布为：

- GitHub 仓库：`https://github.com/2456018331lby-dev/skillpool`
- 首个公开版本：`v0.1.0`

后续维护建议按下面顺序进行：

1. 先在本地完成修改和验证
2. 检查 `git status --short`
3. 检查本地与远端历史：

```powershell
git fetch origin
git log --oneline --decorate --graph --all
```

4. 确认没有历史分叉风险后，再做：

```powershell
git add .
git commit
git push origin main
```

如果 `git push` 再次遇到网络重置，不要直接强推改历史，先记录失败现象，再决定是否使用 GitHub API 作为兜底发布路径。

## 8. 当前前端结构

控制台当前主要页面：

- `总览`
- `客户端`
- `MCP`
- `盘点`
- `清理`
- `技能池`
- `同步中心`
- `冲突`
- `导入`
- `报告`

其中主入口是：

- `技能池`

主入口当前承载：

- 逻辑矩阵
- 实例展开
- discovery 摘要
- 扫描源管理
- 批量 family 操作
- 跳转同步中心

高风险动作仍然保留在专门页面，不直接塞进矩阵单元格：

- `publish`
- `rollback`
- `doctor`
- `import`

## 9. 当前已知风险和注意事项

### 9.1 discovery 显式刷新仍偏重

虽然首页已经改成缓存优先，但在真实环境里：

- `python skillpool.py discovery summary`

显式刷新仍然可能比较慢。

这不是逻辑错误，而是下一轮最值得继续优化的性能点。

### 9.2 Codex MCP 真实配置里仍可能有重复项

当前真实环境里曾出现：

- `memory / memory-1`
- `sequential-thinking / sequential-thinking-1`

现在已经有去重能力，但未来维护者仍应留意这类重复项是否重新出现。

### 9.3 GitHub 首发历史有特殊背景

`v0.1.0` 首发时，当前环境的 `git push` 反复遇到 HTTPS 网络重置。

因此首发仓库最终是这样完成的：

- 本地独立仓库正常初始化并提交
- GitHub 仓库创建成功
- 远端内容通过 GitHub API 写入
- `main`、`v0.1.0` 和 Release 正常建立

这意味着：

- 本地首个提交哈希
  - `754aad5`
- 远端首个公开提交哈希
  - 与本地不同

原因不是内容差异，而是远端提交对象是通过 API 重新创建的。

后续维护者需要知道这一点，避免误以为历史损坏。

### 9.4 如何处理本地 / 远端历史不一致

后续如果网络稳定，建议先做：

```powershell
git fetch origin
git log --oneline --decorate --graph --all
```

然后再决定是否做历史对齐。

在没有确认清楚之前，不要随意：

- 强推
- 重写 `main`
- 删除远端 tag

## 10. 当前仓库与发布信息

当前公开仓库：

- `https://github.com/2456018331lby-dev/skillpool`

当前公开 Release：

- `v0.1.0`

当前许可证：

- `MIT`

当前默认分支：

- `main`

## 11. 最低验证标准

### 11.1 每次改后必须做

```powershell
python -m unittest discover -s tests -v
```

如果改了前端：

```powershell
node --check skillpool_app/ui/app.js
```

### 11.2 建议加做的命令

```powershell
python skillpool.py status
python skillpool.py inventory
python skillpool.py discovery summary
python skillpool.py sync inspect codex
python skillpool.py mcp list codex
```

### 11.3 浏览器人工检查建议

启动：

```powershell
open-console.cmd
```

重点看：

- 技能池矩阵能否正常打开
- discovery 是否先显示摘要再按需取详情
- 扫描源过滤是否正常
- 同步中心预览 / 应用是否可解释
- MCP 页能否正常进入

### 11.4 常见症状排查顺序

如果出现以下现象，建议优先按这个顺序排查：

- 页面大量显示“无法连接本地 SkillPool 服务”
  - 先执行 `console-status.cmd`
  - 再执行 `open-console.cmd`
  - 再看 `state/web-console.out.log` 和 `state/web-console.err.log`

- 技能数量和预期差很多
  - 先看 `python skillpool.py inventory`
  - 再看 `python skillpool.py discovery summary`
  - 再看 `python skillpool.py scan-sources list`
  - 最后才考虑是否需要刷新扫描源

- 某个客户端为什么没同步上 skill
  - 先看同步中心预览结果
  - 重点看 `未解决 family` 和 `目标不可见`
  - 再确认目标客户端是否真的能看到同一个 `skill_id`

- Codex / Claude / Hermes 的 MCP 看起来不对
  - 先看 `python skillpool.py inventory <client>`
  - 再看 `python skillpool.py mcp list <client>`
  - 如果是 Codex，再额外看是否有重复项需要 `mcp dedupe codex`

- 发布后结果异常
  - 先看 `preview`
  - 再看 `doctor --deep`
  - 必要时 `rollback inspect`
  - 最后才执行 `rollback`

## 12. 改动纪律

### 12.1 代码层

- 业务规则尽量只放 `core.py`
- CLI 和 Web 层不复制业务逻辑
- 前端继续保持原生 JS，不引入构建链
- 尽量不引入新依赖

### 12.2 文档层

如果这些内容发生变化，必须同步文档：

- 命令面
- API
- 页面结构
- MCP 支持边界
- 同步中心语义
- 批量 family 动作语义
- discovery / scan source 性能策略

最少要同步：

- `README.md`
- `USAGE.zh-CN.md`
- `docs/OPERATIONS_MANUAL.zh-CN.md`
- `docs/MAINTAINER_GUIDE.zh-CN.md`

### 12.3 安全层

不要做这些事：

- 不要把 unsupported MCP 显示成 `0`
- 不要跳过 preview / backup / rollback
- 不要把 SkillPool 变成 MCP 运行态进程管理器
- 不要把高风险动作直接塞回矩阵页
- 不要把本地运行态目录纳入 Git 仓库

## 13. 建议的后续优先级

当前建议按这个顺序继续推进：

1. discovery / scan source 显式刷新继续增量化
2. 矩阵页继续压缩成更强的一屏维护总管
3. 同步中心结果页继续细化
4. 用现有 MCP 管理能力处理真实 `codex` 重复项
5. 导入器增强
6. GitHub 首页补更多截图、示例和演示材料

## 14. 给后来人的一句话

SkillPool 当前最重要的资产不是某个页面，而是已经建立起来的这套统一模型：

- 一个主池
- 六个客户端
- 可解释 inventory / discovery
- 安全发布链路
- 可写 MCP 管理
- 跨客户端同步模板

后续所有优化都应该围绕这套模型收口，而不是重新发明第二套状态源。
