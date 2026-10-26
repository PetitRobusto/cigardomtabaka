# AGENTS.md — CigarDomTabaka Agent 工作约定

本文件约束在本仓库工作的 AI Agent。目标是用与业务风险相称的流程完成任务，同时保护生产数据、财务事实和用户未提交的工作。

## 开始前

- 阅读用户当前需求；用户决定本次任务的目标与范围。
- 阅读本文件。涉及业务语义时阅读 [`CONTEXT.md`](CONTEXT.md)，涉及架构决定时查阅 [`docs/adr/`](docs/adr/)。
- 先检查工作区和影响范围；保留用户已有改动，不擅自覆盖、回滚或 `git stash`。

## 风险门禁

直接实现是默认；只有缺少关键业务决定、操作不可逆或将修改生产数据时才暂停询问。

| 风险 | 典型范围 | 默认流程 |
| --- | --- | --- |
| 低 | 文案、样式、小配置、明确类型修复、局部无状态 UI | 当前工作区修改；自审；最小充分验证 |
| 中 | 普通前后端功能、API 契约、跨文件状态、可恢复写入 | 简短需求契约；feature branch；关键测试；一次独立审查 |
| 高 | 金额、汇率、成本、利润、库存、订单、权限、幂等、迁移、生产部署 | 必要时先写设计；feature branch；验证不变量和错误路径；最终独立审查 |

风险按实际改变的业务行为判断；仅修改展示文案或样式，不因所在模块涉及金额、库存或订单而自动升级。

默认顺序：`需求契约 → 影响扫描 → 实现 → 目标验证 → 风险审查 → 交付`。Push、远程 CI、合并和部署按用户在当前任务中的授权范围执行；已有明确授权不重复询问，生产部署仍须遵守安全边界。

- 低风险任务可在有无关未提交改动的当前工作区完成；保留既有改动，仅在目标文件的修改存在重叠冲突时协调，不为获得干净工作区而清理用户改动。

- 30 分钟内且不引入领域模型的任务无需正式计划；新增模型、会计规则、跨子系统或不可逆数据时先写 spec/plan。
- 不强制 TDD，但必须补高价值行为测试和已发生 Bug 的回归测试。
- 连续两次修复无效时转为系统化根因诊断。

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
- 新 UI、布局、配色或整体视觉方向先在既有 OpenDesign 项目 `CigarDomTabaka`（slug `cigardomtabaka`）预览；先读取项目已有设计和 `brand-spec.md`，每次设计使用独立 conversation/run。纯功能、类型、文案和明确小修复可直接改 React。
- OpenDesign 只能通过当前会话已注册并暴露的 MCP 工具调用，不得直接请求 OpenDesign daemon HTTP API。若 MCP 未注册或未暴露，说明阻塞原因并请用户启用；不得用 `curl`、`fetch` 或其他 HTTP 调用绕过。
- OpenDesign 的设计生成必须使用 Claude Code。先通过已注册工具确认可用运行器，启动时明确选择 Claude Code；不得使用 Codex，也不得在失败时自动切换到 Codex。Claude Code 不可用时说明阻塞原因。

### SEO 计划与迭代

- 后续 SEO 任务先阅读 [`docs/seo-roadmap.md`](docs/seo-roadmap.md)，沿用其中的目标、已验证现状、任务编号与阻塞记录；任务结束时更新状态、证据、日期和下一步。
- 本地实现、线上生效、搜索引擎收录与排名效果分别记录；不要把历史开发库告警当作当前生产缺口，也不要将计划中的发布步骤视为部署授权。
- 型号获奖、媒体品鉴等资料引用原始来源，并在正文提供可点击的来源链接；不把出站链接、点击交互或来源数量描述为排名权重保证。

### 商品图片与批量工作

- 子 Agent 最多同时使用 3 个，统一采用 `gpt-6-luna`、`reasoning_effort=high`；图片盘点、下载、逐张生成、格式导出等重复工作优先委派，主 Agent 负责整合、质量和最终验证。此规则不改变 OpenDesign 必须使用 Claude Code 的要求。
- 商品图沿用网络参考图 → imagegen 统一方向 → 固定店铺水印的流程，保留原图、来源 URL、生成提示和成图清单。已有准确素材优先复用；不把处理后的图片称为门店实拍或当前批次证明。
- 单支竖直、打开的盒子朝右下方，保留正确型号、茄标和盒规。水印使用同一店铺 Logo 和统一归一化坐标，由确定性导出固定位置，不由每次图像生成自由绘制。参数及版本见 [`docs/storefront-images.md`](docs/storefront-images.md)。媒体不提交 Git。
- 产品图已有新版时只展示新版，同款单支和同盒规不重复展示旧版；尚无新版的图片继续使用。旧媒体及关联保留作归档，不因展示替换删除来源。水印统一规则用于新生成版本。

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
