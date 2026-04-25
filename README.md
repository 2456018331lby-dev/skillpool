# SkillPool

English summary: SkillPool is a Chinese-first local control center for managing one shared skill pool across six AI clients, with safe preview, publish, rollback, inventory, MCP config management, and cross-client template sync.

SkillPool 是一个本地优先、零依赖、中文优先的统一技能池总管。

它解决的是这类长期维护痛点：

- 同一批 skill 分散在 Hermes、openclaw、qclaw、autoclaw、codex、claude 各自目录里，重复、冲突、覆盖关系说不清
- 某个客户端到底读哪个目录、为什么有的 skill 能看到有的看不到，很难解释
- 想把一个客户端当前“已发布决策”同步到别的客户端，没有统一入口
- MCP 配置分散在不同配置文件里，重复项、启用状态、来源差异难以统一管理

SkillPool 的目标不是替代各个客户端，而是成为它们之上的“统一总管”。

## 核心特色

- 一个主池，六个客户端  
  默认主库位于 `%USERPROFILE%\.skill-pool`，各客户端只读 SkillPool 发布或接管后的结果。

- 逻辑矩阵总管  
  默认按“逻辑 skill / family”显示，而不是把重复实例平铺成几百行。

- 可解释的盘点与发现  
  不只给数字，还解释：
  - live 里有什么
  - pool 里有什么
  - published 里有什么
  - 差异为什么出现

- 安全链路完整  
  `preview -> publish -> backup -> rollback -> doctor` 全都保留，不走裸覆盖。

- MCP 配置管理  
  当前支持对 `codex / claude / hermes` 做结构化 MCP 配置管理和同步；  
  `openclaw / qclaw / autoclaw` 继续明确显示为“不支持可靠 MCP 写入”。

- 同步中心  
  可把“某个源客户端当前已发布的 family 决策 + 受支持 MCP 配置”预览后同步到多个目标客户端。

## 和 ccswitch / 客户端原生技能目录的区别

SkillPool 强的地方不在“单纯列出技能”，而在这几件事：

- 统一主池，而不是每个客户端各自维护一套
- 同时看逻辑 family、物理实例、发布结果、live 来源、扫描源、discovery 异常
- 有安全发布和回滚链路
- 有 inventory / discovery / report 体系
- 有跨客户端模板同步
- MCP 管理和 Skill 管理放在同一个本地控制台

## 支持矩阵

| 客户端 | Skill 纳管 | 发布 / 回滚 | Inventory | MCP 盘点 | MCP 写入 | MCP 同步 |
| --- | --- | --- | --- | --- | --- | --- |
| hermes | 支持 | 支持 | 支持 | 支持 | 支持 | 支持 |
| openclaw | 支持 | 支持 | 支持 | 仅说明 unsupported | 不支持 | 不支持 |
| qclaw | 支持 | 支持 | 支持 | 仅说明 unsupported | 不支持 | 不支持 |
| autoclaw | 支持 | 支持 | 支持 | 仅说明 unsupported | 不支持 | 不支持 |
| codex | 支持 | 支持 | 支持 | 支持 | 支持 | 支持 |
| claude | 支持 | 支持 | 支持 | 支持 | 支持 | 支持 |

## 3 分钟快速开始

最推荐的方式：

```powershell
%USERPROFILE%\.skill-pool\open-console.cmd
```

它会：

1. 检查 `127.0.0.1:8765` 是否已经在线  
2. 如果没在线，就启动 `python skillpool.py serve --host 127.0.0.1 --port 8765`  
3. 自动打开浏览器

其他脚本：

```powershell
%USERPROFILE%\.skill-pool\console-status.cmd
%USERPROFILE%\.skill-pool\stop-console.cmd
```

如果想手动命令启动：

```powershell
cd %USERPROFILE%\.skill-pool
python skillpool.py serve --host 127.0.0.1 --port 8765 --open
```

## CLI 常用命令

```powershell
python skillpool.py status
python skillpool.py preview --all
python skillpool.py doctor --deep
python skillpool.py inventory
python skillpool.py mcp list codex
python skillpool.py cleanup list
```

同步与批量动作：

```powershell
python skillpool.py sync inspect codex
python skillpool.py sync preview codex --to hermes --skills --mcp
python skillpool.py sync apply codex --to hermes --to claude --skills --mcp
python skillpool.py sync preview codex --to hermes --family my-family --skills
python skillpool.py batch disable --clients hermes --clients claude --family my-family
python skillpool.py batch inherit --clients hermes --clients claude --family my-family
```

discovery / 扫描源：

```powershell
python skillpool.py scan-sources list
python skillpool.py scan-sources scan
python skillpool.py discovery
python skillpool.py discovery summary
python skillpool.py discovery details transient_only --limit 20
python skillpool.py discovery refresh --summary
```

## 控制台主工作流

### 技能池

- 默认主入口
- 按逻辑 skill / family 显示矩阵
- 左侧看名字、描述、来源、冲突、异常
- 右侧直接看六个客户端状态
- 支持矩阵多选 family
- 支持批量：
  - 禁用
  - 恢复继承
  - 把当前选择送入同步中心

### 同步中心

- 选择源客户端
- 选择目标客户端
- 选择同步 Skill、MCP，或两者
- 选择：
  - 源客户端全部已发布 family
  - 当前矩阵已选 family
- 先预览，再应用
- 明确显示：
  - 会新增什么
  - 会跳过什么
  - 为什么跳过

### 客户端

- 单客户端 `preview / diff / doctor / publish / rollback`
- 高风险动作继续放在这里，不塞回矩阵页

### MCP

- 支持 `codex / claude / hermes`
- 支持查看、启用、禁用、新增、更新、删除
- Codex 支持一键去重

### 盘点

- 展示 live / pool / published / source mismatch / MCP 配置源
- 解释为什么别的工具只显示几十个，而 SkillPool 能看到几百个

## 安全模型

SkillPool 默认按这些原则运行：

- 所有高风险动作先 `preview`
- `publish` 前自动备份
- 失败自动回滚
- `rollback` 支持列出、检查、恢复
- discovery 和扫描源采用缓存优先，不在每次首屏都重扫全盘

## 文档

- `USAGE.zh-CN.md`
  面向日常使用者

- `docs/OPERATIONS_MANUAL.zh-CN.md`
  面向长期维护与值班操作

- `docs/MAINTAINER_GUIDE.zh-CN.md`
  面向开发维护者

- `docs/MAINTENANCE_DOSSIER.zh-CN.md`
  面向后来人接手维护的完整总手册，第一次接手建议先读这一份

- `docs/SYNC_GUIDE.zh-CN.md`
  专门说明同步中心与批量装载/禁用逻辑

- `docs/FEATURES.zh-CN.md`
  功能总表与边界说明

## 技术约束

- 后端：Python 标准库
- 前端：原生 HTML / CSS / JS
- 默认只监听：`127.0.0.1`
- 不做 MCP 运行态进程管理
- 不引入新的 Web 框架

## 开发与验证

```powershell
python -m unittest discover -s tests -v
node --check skillpool_app/ui/app.js
```

## 开源仓库定位

SkillPool 目前按“中文优先实战仓库”整理：

- README 讲清楚问题、能力边界、快速开始
- 功能和操作指南用中文主文档维护
- 英文只保留首页短摘要
- `.github` 模板对齐 `sync / MCP / inventory / performance` 等类别

## 当前状态

当前已经具备的关键能力：

- 技能池矩阵总管
- 扫描源库与 discovery 缓存摘要
- inventory / report
- publish / rollback / doctor
- MCP 配置管理
- 同步中心后端、CLI、HTTP 接口
- 矩阵多选批量禁用 / 恢复继承

仍值得继续工程化收口的方向：

- 首屏性能继续细化
- 前端交互继续压缩成更像一屏维护名录
- 同步中心的细节状态展示继续打磨
- GitHub 开源材料继续补充示例和截图
