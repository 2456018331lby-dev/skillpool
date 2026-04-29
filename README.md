## Maintainers

**Simon Su** ([@Simon-Su-1105](https://github.com/Simon-Su-1105)) — Key Maintainer & Contributor  
Email: 1362495971@qq.com

---

English summary: SkillPool is a Chinese-first local control center for managing one shared skill pool across six AI clients, with safe preview, publish, rollback, inventory, MCP config management, and cross-client template sync.

SkillPool 是一个本地优先、零依赖、中文优先的统一技能池总管。

它解决的是这类长期维护痛点：

- 同一批 skill 分散在 Hermes、openclaw、qclaw、autoclaw、codex、claude 各自目录里，重复、冲突、覆盖关系说不清
- 某个客户端到底读哪个目录、为什么有的 skill 能看到有的看不到，很难解释
- 想把一个客户端当前"已发布决策"同步到别的客户端，没有统一入口
- MCP 配置分散在不同配置文件里，重复项、启用状态、来源差异难以统一管理

SkillPool 的目标不是替代各个客户端，而是成为它们之上的"统一总管"。

## 核心特色

- 一个主池，六个客户端  
  默认主库位于 `%USERPROFILE%\\.skill-pool`，各客户端只读 SkillPool 发布或接管后的结果。

- 逻辑矩阵总管  
  默认按"逻辑 skill / family"显示，而不是把重复实例平铺成几百行。

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
  `openclaw / qclaw / autoclaw` 继续明确显示为"不支持可靠 MCP 写入"。

- 同步中心  
  可把"某个源客户端当前已发布的 family 决策 + 受支持 MCP 配置"预览后同步到多个目标客户端。

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

```powershell
%USERPROFILE%\\.skill-pool\\open-console.cmd
```

## CLI 常用命令

```powershell
python skillpool.py status
python skillpool.py preview --all
python skillpool.py doctor --deep
python skillpool.py inventory
```

## 文档

- `USAGE.zh-CN.md` - 面向日常使用者
- `docs/MAINTAINER_GUIDE.zh-CN.md` - 面向开发维护者

## 许可证

MIT
