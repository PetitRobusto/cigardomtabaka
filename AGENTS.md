# AGENTS.md — Moscow Cigar 项目 AI Agent 行为规范

## 核心铁律：Superpowers 流程强制执行

任何代码相关任务（写功能、修bug、重构、设计、部署）必须先走 Superpowers 流程，禁止跳过！

### 必须加载的技能流程

```
brainstorming → writing-plans → [实现阶段技能] → verification-before-completion
```

| 阶段 | 技能 | 触发条件 |
|------|------|----------|
| 动脑子 | `brainstorming` | 任何新功能、修改、创意工作之前 |
| 写计划 | `writing-plans` | 多步骤任务，写入 `.hermes/plans/` |
| 开发 | `test-driven-development` | 写新代码前先写测试 |
| 调试 | `systematic-debugging` | 遇到bug，四阶段根因分析 |
| 审查 | `requesting-code-review` | 提交前安全检查 |
| 验证 | `verification-before-completion` | 声称完成前跑验证命令 |
| 收尾 | `finishing-a-development-branch` | 合并回 master |

---

## 禁忌

- 绝不擅自改用户密码调试登录
- 绝不 git stash 用户未提交的改动（必须先 commit 再切分支）
- 不使用运行时 slugify 处理品牌重音字符（Partagás/Bolívar/Ramón Allones），必须用硬编码映射表 BRAND_LOGO_LOCAL
- patch 工具修改 settings/config 前先用 `cat` 验证真实内容（安全过滤会把 AUTH_USER_MODEL 等显示为 `***`）
- 修完代码必须切回 master，不留在 feature/fix 分支上
- 报价时用户说"X款 Y元"默认人民币批发价，不动成本；只有明确说"成本"或"卢布"才改成本
- 不跳过 Superpowers 流程
- 不直接写前端代码——前端重写用看板 Kanban 派 kimi-coder

---

## Git 工作流

```
master → git checkout -b feature/xxx → 开发 → commit → merge 回 master → git branch -d feature/xxx
```

⚠️ 切分支前先 `git commit` 所有未提交改动，禁止 stash。

---

## 前端开发

- 涉及视觉/配色/风格 → 先加载 `ui-ux-pro-max` 出预览，让用户选方案
- 前端/UI 重写 → 用看板 Kanban 派 kimi-coder，自己不写前端代码
- 后端 Python → 用 coder (deepseek-v4-flash)
- 修改 base.html 导航栏 → 必须同时改桌面端（navbar-end）和手机端底部导航（BOTTOM NAV）
- 前端源码在 `frontend/`（React + Vite + Tailwind + DaisyUI）

---

## 数据相关

- `.db` 不进 git（已在 .gitignore）
- DEV/生产双库：`DJANGO_DEBUG=True` → `cigars_dev.db`，否则 `cigars.db`
- 报价：批发价 → `price_ref`，成本 → `PRICE_OVERRIDE_RUB`
- 雪茄翻译：圈内公认名优先，地限必须带地区名
- 汇率：1 CNY = 12 RUB（浮动）
- 图片匹配用 english_name

---

## 项目索引

```
moscow_cigar/                     # Django 项目根目录
├── manage.py                     # Django 入口
├── requirements.txt              # Python 依赖
├── .env                          # 环境变量（DEBUG/SECRET_KEY/DB等）
│
├── moscow_cigar_backend/         # Django 项目配置
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
├── privnote/                     # 【阅后即焚】应用
│   ├── models.py                 # Privnote 模型（token/密码/过期/销毁）
│   ├── views.py                  # 创建/查看/销毁视图
│   └── templates/privnote/       # 前端模板
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
| `/privnote/` | 阅后即焚 |

---

## 优先级

1. 本文件（AGENTS.md）— 最高
2. Superpowers 技能规范
3. 系统默认提示
