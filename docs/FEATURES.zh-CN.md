# SkillPool 功能总表

## Skill 管理

- 统一主池
- 逻辑 skill / family 矩阵
- 原始实例视图
- 启用 / 禁用
- 客户端 override
- 批量 family 禁用 / 恢复继承

## 发布与回滚

- 单客户端 preview
- diff
- doctor --deep
- publish
- backup
- rollback list / inspect / latest

## 盘点与报告

- inventory
- inventory export JSON / Markdown
- SKILLS_INDEX
- CONFLICTS
- INVENTORY
- CLEANUP_CANDIDATES

## discovery 与扫描源

- 扫描源库
- 建议源 / 临时源 / 启用源过滤
- discovery 缓存摘要
- discovery 分组详情按需加载

## 同步中心

- 源客户端 -> 目标客户端模板同步
- Skill 模板同步
- MCP merge 同步
- 先 preview 后 apply

## MCP

- `codex / claude / hermes` 可写
- `openclaw / qclaw / autoclaw` inventory-only
- Codex 一键去重

## 非功能特性

- 零依赖
- 本地单机
- 中文优先
- 安全链路完整
- 适合后续整理成 GitHub 开源仓库
