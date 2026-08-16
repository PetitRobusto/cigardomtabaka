# AGENTS.md — CigarDomTabaka 项目 AI Agent 行为规范

## 核心流程：风险门禁开发

直接实现是默认；设计、测试、审查和验证成本必须与业务风险匹配。主代理自动分级并推进，只有不可逆操作、生产数据修改或缺少关键业务决定时才询问用户。

### 风险分级

| 等级 | 典型范围 | 默认流程 |
|------|----------|----------|
| 低 | 文案、样式、帮助内容、小配置、明确类型修复、局部无状态 UI | 当前干净分支直接修改；自审；最小充分验证 |
| 中 | 普通前后端功能、API 契约、跨文件状态、可恢复数据写入 | 记录简短需求契约；feature branch；实现后补关键测试；一次独立审查 |
| 高 | 会计、金额、汇率、成本、利润、库存、订单状态、权限、幂等、迁移、production 部署 | 必要时正式设计；feature branch；验证不变量和错误路径；合并前独立审查 |

默认流程：

```text
需求契约 → 影响范围扫描 → 直接实现 → 目标验证 → 按风险审查 → CI 全量验证 → 合并或部署
```

- 不强制 TDD 或 RED→GREEN，允许先实现，再补关键行为测试
- 预计 30 分钟内的任务不写正式计划；仅新增领域模型、修改会计规则、跨多个子系统或涉及不可逆数据时写正式 spec/plan
- Superpowers 技能按任务价值调用，不组成每个任务的强制流水线
- 连续两次修复无效时，升级为系统化根因诊断
- Subagent 可用于并行调查、独立模块和集中审查；自动选择数量和模型，不为每个小步骤串行派发

---

## 禁忌与安全边界

- **绝不先 push 后验证** — 修改后必须完成与风险匹配的本地目标验证；完整测试主要由 CI 执行
- 绝不擅自改用户密码调试登录
- 绝不覆盖或擅自 `git stash` 用户未提交的改动；需要切分支时先获得安全、明确的工作区状态
- 不使用运行时 slugify 处理品牌重音字符（Partagás/Bolívar/Ramón Allones），必须用硬编码映射表 BRAND_LOGO_LOCAL
- patch 工具修改 settings/config 前先用 `cat` 验证真实内容（安全过滤会把 AUTH_USER_MODEL 等显示为 `***`）
- 报价时用户说“X款 Y元”默认人民币批发价，不动成本；只有明确说“成本”或“卢布”才改成本
- 默认不 push；只有用户明确要求才 push
- 不可逆操作和生产数据变更必须先获得用户确认

---

## 测试与审查

实现后必须覆盖：

- 会计金额、汇率、成本、利润和库存数量不变量
- 订单、采购、出库、收付款状态流转
- 已实际发生的 Bug 回归
- 数据解析、权限、幂等写入、迁移和不可逆操作

纯排版、颜色、文案、简单组件拼装，以及 TypeScript、Lint 或构建已可靠覆盖的问题，默认不写单元测试。开发期间只跑受影响测试、类型检查、Lint、构建或页面冒烟；完整前后端测试主要由 CI 执行一次。

- 低风险：主代理自审
- 中风险：完成后一次独立审查
- 高风险：可在实现期间审查，合并前再做一次最终独立审查
- 只强制修复 Critical 和当前范围内的 Important；Minor 与无关历史问题记为技术债
- 修复反馈后只复审受影响区域；审查新增工作超过原范围约 30% 时先汇报

---

## Git 与交付

- 低风险可在当前干净分支开发；中高风险使用 feature branch
- worktree 仅用于并行、长期或实验性任务
- Commit message 全部使用中文
- 默认不 push；只有用户明确要求才 push
- production 只部署通过 CI 的准确 commit SHA
- 功能分支完成并合并后切回默认主分支，不遗留无用分支

---

## 前端开发

- ⚠️ **所有前端页面走 React SPA (`frontend/`)**，禁止新建 Django 模板页面
- 涉及新的视觉方向、配色或整体风格时，先做预览并让用户选择
- 前端源码在 `frontend/`（React + Vite + Tailwind + DaisyUI）
- 修改 base.html 导航栏 → 必须同时改桌面端和手机端底部导航（BOTTOM NAV）
- privnote 前端 → React SPA 路由 `/privnote/` 和 `/p/:token/`，不走 Django 模板
- ⚠️ **视觉改动先走 OpenDesign**：新的 UI/Layout/样式方向先在 OpenDesign 原型（`.opendesign/` 目录）验证，再应用到项目；纯功能、类型、文案和明确的小修复可直接修改 React 源码
- 📖 [OpenDesign MCP 使用指南 →](.kilo/opendesign-mcp.md) — MCP 工具、工作流、设计 Token
- 🎨 **OD 项目**: `CigarDomTabaka` (`570372ce-21b8-4752-a21a-bd254f061568`) ↔ 本 Django 项目

---

## 数据相关

- `.db` 不进 git（已在 .gitignore）
- DEV/生产双库：`DJANGO_DEBUG=True` → `cigars_dev.db`，否则 `cigars.db`
- 报价：批发价 → `price_ref`，成本 → `PRICE_OVERRIDE_RUB`
- 雪茄翻译：圈内公认名优先，地限必须带地区名
- 汇率：1 CNY = 12 RUB（浮动）
- 图片匹配用 english_name

---

## 图片下载

- CDP 浏览器需运行在 9222 端口：`google-chrome --remote-debugging-port=9222`
- CCW 有 Cloudflare 保护，必须通过 CDP 浏览器 `fetch()` 下载
- 图片下载前必须先导航到源网站（CORS 限制），不能停在别的页面

---

## Django 陷阱

- Django 5.x async 上下文中不能直接调用 ORM，用 `run_in_executor` 包装
- `media/`、`staticfiles/`、`.db`、`.env` 不进 Git

---

## 项目索引

```
cigardomtabaka/                     # Django 项目根目录
├── manage.py                     # Django 入口
├── requirements.txt              # Python 依赖
├── .env                          # 环境变量（DEBUG/SECRET_KEY/DB等）
│
├── cigardomtabaka_backend/         # Django 项目配置
│   ├── settings.py               # 全局配置、数据库路由、INSTALLED_APPS
│   ├── urls.py                   # 根 URL 路由
│   └── wsgi.py                   # WSGI 入口
│
├── cigars/                       # 【核心】雪茄目录应用
│   ├── models.py                 # Cigar 模型（名称/品牌/品型/尺寸/图片等）
│   ├── views.py                  # 目录页、详情页
│   ├── admin.py                  # Django Admin 配置
│   ├── auth_views.py             # 登录/认证
│   ├── management/commands/      # 管理命令（导入目录等）
│   └── templates/cigars/         # 前端模板
│
├── price_tracker/                # 【价格追踪】应用
│   ├── models.py                 # 价格/汇率/爬虫源模型
│   ├── matcher.py                # 雪茄名称匹配引擎（核心逻辑）
│   ├── scraper.py                # 爬虫调度器
│   ├── views.py                  # API 视图
│   ├── serializers.py            # DRF 序列化器
│   ├── scrapers/                 # 各家爬虫实现
│   │   ├── coh_china.py          # COH 中国站（新版，~535行）
│   │   ├── coh.py                # COH 国际站（旧版，已废弃）
│   │   ├── ihavanas.py           # iHavanas
│   │   ├── egm.py                # EGM Cigars
│   │   └── lcdh_nyon.py          # LCDH Nyon
│   └── management/commands/      # 爬虫/导入/汇率命令
│
├── privnote/                     # 【阅后即焚】应用 — 四类型: inventory/payment/message/quote
│   ├── models.py                 # Privnote + PaymentMethod（含 remark 字段）
│   ├── views.py                  # create / api_privnote / search-cigars / search-customers / payment-methods / quote-products
│   └── migrations/               # DB 迁移（已删除 template/ 目录，前端走 React SPA）
│
├── frontend/                     # React 前端（Vite + Tailwind + DaisyUI）
│   ├── src/                      # React 源码
│   ├── public/                   # 静态资源
│   ├── vite.config.js            # Vite 构建配置
│   └── package.json              # Node 依赖
│
├── templates/                    # Django 全局模板
│   └── base.html                 # ⚠️ 基础模板（导航栏改这里！
│
├── static/                       # Django 静态文件
│   ├── css/                      # 编译后 CSS
│   └── price-tracker/            # Vite 构建产物
│
├── media/                        # 用户上传媒体
│   ├── cigars/                   # 雪茄图片
│   └── brand_logos/              # 品牌 Logo
│
├── tools/                        # 一次性脚本/工具
│   ├── cdp_extract5.py           # CDP 爬虫提取
│   ├── download_images.py        # 图片下载
│   └── ...
│
├── cigars.db                     # 生产数据库（不进 git）
├── cigars_dev.db                 # 开发数据库（不进 git）
├── brand_logos.json              # 品牌 Logo 映射表
├── cigars_catalog.json           # 雪茄目录 JSON
├── image_manifest.json           # 图片清单
│
└── *.xlsx                        # 报价单/价格表（不进 git）
```

### 数据库

| 文件 | 用途 |
|------|------|
| `cigars.db` | 生产库，1334 款 / 27 品牌 |
| `cigars_dev.db` | 开发库，DEBUG=True 时使用 |

### API 端点

| 路径 | 说明 |
|------|------|
| `/admin/` | Django Admin |
| `/cigars/` | 雪茄目录 |
| `/api/prices/` | 价格 API |
| `/privnote/` | 阅后即焚 — 库存/收款/消息/报价 (React SPA) |
| `/p/<token>/` | 客户查看 privnote 链接 |
| `/privnote/api/quote-products/` | 批发价雪茄列表（供创建 quote 时筛选） |

---

## 优先级

1. 本文件（AGENTS.md）— 最高
2. 用户当前任务要求
3. `django-privnote` 技能（privnote 相关工作必加载）
4. 其他技能规范（按风险和任务价值调用）

---

## Privnote 关键规则

- **全部 React SPA**：创建页 `/privnote/`，查看页 `/p/:token/`，后端仅 JSON API
- **四类型**：`inventory` 库存 / `payment` 收款 / `message` 消息 / `quote` 批发报价
- **inventory vs quote**：`inventory`=现货（实际库存，实时计算零售价），`quote`=预售（批发价目表，从 CigarPrice 模型读取）
- **PaymentMethod.remark**：收款备注绑定到收款方式本身（Django Admin 配置），不是创建 privnote 时填
- **搜索**：`search-cigars` 用 RapidFuzz + 拆词 OR + stock_only=0 全目录
- **查看页**：Light 主题，StoreHeader（地址+电话+微信），QR 放大，不显示 PaymentMethod label
- **额外费用**：运费/人肉费 checkbox + 自定义添加
- **quote 实时构建**：查看时从 `CigarPrice` + `PurchaseBatch` 实时构建，价格/库存变动自动反映
- **主入口**：`django-privnote` 技能（`~/.hermes/skills/software-development/django-privnote/SKILL.md`）
3. 系统默认提示
