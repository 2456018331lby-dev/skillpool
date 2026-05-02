# SkillPool 维护者指南

如果你需要一份更完整的接手文档，请先读：

- `docs/MAINTENANCE_DOSSIER.zh-CN.md`

## 1. 当前工程边界

SkillPool 当前是：

- Python 标准库后端
- 原生 HTML / CSS / JS 前端
- 本地单机控制台
- Skill 管理、发布、安全回滚、盘点、MCP 配置管理、跨客户端模板同步

SkillPool 当前不是：

- MCP 运行态进程管理器
- 远程多用户系统
- 带数据库和后台任务守护的 Web 服务

## 2. 关键模块

- `skillpool_app/core.py`
  唯一业务真源

- `skillpool_app/cli.py`
  CLI 命令面

- `skillpool_app/web.py`
  HTTP API 和静态控制台出口

- `skillpool_app/ui/index.html`
  控制台结构

- `skillpool_app/ui/app.js`
  状态、渲染、交互逻辑

- `skillpool_app/ui/styles.css`
  中文控制台视觉层

- `tests/test_skillpool.py`
  回归保护

## 3. 当前重点能力

- 技能池矩阵
- 批量 family 操作
- discovery 缓存摘要 / 分组详情
- 扫描源库
- 同步中心
- MCP 配置管理

## 4. 修改纪律

- 改业务逻辑时，优先补测试
- 改文案或 UI 行为时，同步 README / USAGE / 运维文档
- 高风险动作保持在客户端页，不要随意塞回矩阵单元格
- discovery 和扫描源保持“缓存优先，显式刷新”

## 5. 最低验证标准

### Python 侧

```powershell
python -m unittest discover -s tests -v
```

### 前端语法

```powershell
node --check skillpool_app/ui/app.js
```

### 手工检查建议

```powershell
python skillpool.py serve --host 127.0.0.1 --port 8765
```

重点看：

- 技能池矩阵能否正常渲染
- 批量选择和批量动作是否可用
- 同步中心预览 / 应用是否可解释
- discovery 是否先出摘要再按需取详情

## 6. 推荐下一步工程化方向

- discovery 详情进一步增量化
- 同步中心结果页继续细化
- UI 继续压缩成更接近一屏维护名录
- GitHub 首页补截图、示例和演示流程

## 7. 与开源发布相关的同步项

如果你改了以下任一项，必须同步文档：

- 命令面
- API
- 客户端支持矩阵
- MCP 支持边界
- 同步中心语义
- 批量动作语义
- discovery / scan source 性能策略
