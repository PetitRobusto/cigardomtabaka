# AGENTS.md — CigarDomTabaka Agent 工作约定

本文件约束在本仓库工作的 AI Agent。目标是用与业务风险相称的流程完成任务，同时保护生产数据、财务事实和用户未提交的工作。

## 开始前

- 阅读用户当前需求；用户决定本次任务的目标与范围。
- 阅读本文件。涉及业务语义时阅读 [`CONTEXT.md`](CONTEXT.md)，涉及架构决定时查阅 [`docs/adr/`](docs/adr/)。
- Privnote 任务必须加载 `django-privnote` 技能：`~/.hermes/skills/software-development/django-privnote/SKILL.md`。
- 先检查工作区和影响范围；保留用户已有改动，不擅自覆盖、回滚或 `git stash`。

## 风险门禁

直接实现是默认；只有缺少关键业务决定、操作不可逆或将修改生产数据时才暂停询问。

| 风险 | 典型范围 | 默认流程 |
| --- | --- | --- |
| 低 | 文案、样式、小配置、明确类型修复、局部无状态 UI | 当前干净分支修改；自审；最小充分验证 |
| 中 | 普通前后端功能、API 契约、跨文件状态、可恢复写入 | 简短需求契约；feature branch；关键测试；一次独立审查 |
| 高 | 金额、汇率、成本、利润、库存、订单、权限、幂等、迁移、生产部署 | 必要时先写设计；feature branch；验证不变量和错误路径；最终独立审查 |

默认顺序：`需求契约 → 影响扫描 → 实现 → 目标验证 → 风险审查 → CI → 合并或部署`。

- 30 分钟内且不引入领域模型的任务无需正式计划；新增模型、会计规则、跨子系统或不可逆数据时先写 spec/plan。
- 不强制 TDD，但必须补高价值行为测试和已发生 Bug 的回归测试。
- 连续两次修复无效时转为系统化根因诊断。Subagent 只用于可独立并行的调查、实现或审查。

## 安全边界

- 未经用户明确确认，不修改生产数据、不做不可逆操作、不部署。
- 不修改用户密码调试登录；不提交 `.env`、数据库、媒体、构建产物或秘密。
- 修改 settings/config 前先读取真实文件内容；不要根据过滤后的输出猜值。
- 修改后先完成本地验证，再考虑 push；默认不 push。生产只部署 CI 已通过的准确 commit SHA。

## 必须保护的业务不变量

详细定义以 [`CONTEXT.md`](CONTEXT.md) 为准：

- 基准货币是 CNY；资金账户保留原币余额和人民币账面成本。外部原始价格按原币保存，`price_cny` 仅用于比较展示。
- 用户说“某款 Y 元”默认是人民币批发参考价 `price_ref`；只有明确说“成本”或“卢布”时才改 `PRICE_OVERRIDE_RUB`。
- 正式会计流水入账后不能直接改删；修正通过新的业务动作完成。
- `StockMovement` 是库存数量事实来源，不能直接覆盖批次余额；现货确认不得产生负库存。
- 履约状态与收款状态独立；预收款不是已实现利润。
- 正式写操作保留操作人、业务日期、Agent 来源和幂等信息；Agent 调用业务命令/API，不绕过命令层改余额、库存或正式状态。
- 品牌重音字符通过 `BRAND_LOGO_LOCAL` 硬编码映射处理，不运行时 slugify；图片匹配使用 `english_name`。
- 价格采集、推送、导入共用匹配、去重和下架规则；参考汇率 `1 CNY = 12 RUB` 会浮动，不得当作历史成本。

## 分区规则

### 前端

- 产品页面全部使用 `frontend/` React SPA，不新增 Django 产品模板页面。
- `/privnote/` 和 `/p/:token/` 走 React；后端只提供 JSON API。修改全局导航时同时检查桌面导航和移动底部导航。
- 新 UI、布局、配色或整体视觉方向先在既有 OpenDesign 项目 `CigarDomTabaka`（slug `cigardomtabaka`）预览，默认 agent 为 `claude`，每次设计使用独立 conversation/run；详见 [`.kilo/opendesign-mcp.md`](.kilo/opendesign-mcp.md)。纯功能、类型、文案和明确小修复可直接改 React。

### Privnote

- 类型为 `inventory`、`payment`、`message`、`quote`；展示不创建订单、不预留库存。
- `inventory` 是现货展示，`quote` 是从 `CigarPrice`/`PurchaseBatch` 实时构建的预售批发报价。
- `PaymentMethod.remark` 属于收款方式配置；搜索使用 RapidFuzz、拆词 OR、`stock_only=0`。
- 查看页使用 Light 主题和 `StoreHeader`，支持 QR 放大，不显示 PaymentMethod label。

### 爬虫与 Django

- CDP 使用 `9222`；CCW 图片通过已导航到目标源站的 CDP 页面 `fetch()` 下载。
- Django async 上下文不能直接调用同步 ORM，用 `sync_to_async` 或 executor 包装。
- `DJANGO_DEBUG=True` 使用 `cigars_dev.db`，否则使用 `cigars.db`；本地开发必须明确启用 DEBUG。

## 验证、审查与交付

根据改动选择受影响测试、`manage.py check`、迁移检查、前端 typecheck/lint/Vitest/build 或页面冒烟。金额、库存、订单状态、权限、幂等、解析和迁移必须覆盖成功与错误路径；纯文案、颜色、排版通常只需目标验证。

- 低风险主 Agent 自审；中风险一次独立审查；高风险实现期间和合并前各审查一次。
- 只强制修复本次范围内的 Critical/Important；其余记技术债。反馈修复后只复审受影响区域，范围扩大约 30% 时先汇报。
- 中高风险用 feature branch；worktree 仅用于并行、长期或实验任务。Commit message 使用中文；合并后切回默认分支并清理无用分支。
- 交付说明改动、验证结果、未解决风险和用户后续步骤。

## 仓库导航

| 路径 | 职责 |
| --- | --- |
| `cigars/` | 目录、采购、库存、销售、认证和 Agent 命令 |
| `accounting/` | 资金账户、会计流水、Day 1、费用与分红 |
| `price_tracker/` | 外部价格、匹配、抓取和 ingestion |
| `privnote/` | 临时客户文档和 JSON API |
| `frontend/` | React SPA |
| `cigardomtabaka_backend/` | Django 配置与根路由 |
| `docs/adr/` | 有效架构决策；历史计划以当前代码、ADR 和 `CONTEXT.md` 为准 |
